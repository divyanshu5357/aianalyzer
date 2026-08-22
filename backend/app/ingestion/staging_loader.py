import csv
import io
import json
from pathlib import Path
from typing import Any, Iterator, Dict, Callable, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
import openpyxl


def clean_value_for_json(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-compatible python types."""
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def stream_file_records(file_path: str, chunk_size: int = 20000) -> Iterator[list[Dict[str, Any]]]:
    """
    Stream file contents in chunks to maintain low memory usage.
    Supports CSV, XLSX, XLS, and XLSB.
    """
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".csv":
        for chunk in pd.read_csv(file_path, chunksize=chunk_size):
            chunk_records = []
            for _, row in chunk.iterrows():
                rec = {str(col): clean_value_for_json(row[col]) for col in chunk.columns}
                chunk_records.append(rec)
            yield chunk_records

    elif extension == ".xlsx":
        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = None
        current_chunk = []
        for r in rows:
            if not header:
                header = [str(cell) if cell is not None else f"col_{i}" for i, cell in enumerate(r)]
                continue
            rec = {header[i]: clean_value_for_json(r[i]) if i < len(r) else None for i in range(len(header))}
            current_chunk.append(rec)
            if len(current_chunk) >= chunk_size:
                yield current_chunk
                current_chunk = []
        if current_chunk:
            yield current_chunk
        wb.close()

    elif extension in [".xls", ".xlsb"]:
        engine = "pyxlsb" if extension == ".xlsb" else "xlrd"
        df = pd.read_excel(file_path, engine=engine)
        current_chunk = []
        for _, row in df.iterrows():
            rec = {str(col): clean_value_for_json(row[col]) for col in df.columns}
            current_chunk.append(rec)
            if len(current_chunk) >= chunk_size:
                yield current_chunk
                current_chunk = []
        if current_chunk:
            yield current_chunk

    else:
        raise ValueError(f"Unsupported file format: {extension}")


class CsvToStagingStream(io.TextIOBase):
    """
    Memory-efficient streaming buffer for PostgreSQL COPY STDIN.
    Reads CSV file line-by-line formatted as tab-separated TSV:
    dataset_id \t row_number \t raw_data_json \t cleaning_status \n
    """
    def __init__(
        self,
        file_path: str,
        dataset_id: str,
        chunk_size: int = 50000,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        total_rows: int = 0,
    ):
        self.file_obj = open(file_path, "r", encoding="utf-8-sig", errors="replace")
        self.reader = csv.reader(self.file_obj)
        self.dataset_id = str(dataset_id)
        self.chunk_size = chunk_size
        self.progress_callback = progress_callback
        self.total_rows = total_rows
        self.row_counter = 1
        header_row = next(self.reader, None)
        if header_row:
            self.header = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(header_row)]
        else:
            self.header = []
        self.buffer = io.StringIO()

    def read(self, size=-1):
        buf_val = self.buffer.getvalue()
        pos = self.buffer.tell()
        if pos < len(buf_val):
            chunk = buf_val[pos:]
            self.buffer.seek(0, io.SEEK_END)
            return chunk

        self.buffer = io.StringIO()
        count = 0
        for row in self.reader:
            if not row:
                continue
            rec = {
                self.header[i]: row[i] if i < len(row) else None
                for i in range(len(self.header))
            }
            rec_json = json.dumps(rec).replace("\\", "\\\\").replace("\t", " ").replace("\r", "").replace("\n", " ")
            self.buffer.write(f"{self.dataset_id}\t{self.row_counter}\t{rec_json}\tpending\n")
            self.row_counter += 1
            count += 1
            if count >= self.chunk_size:
                break

        if count > 0 and self.progress_callback:
            try:
                self.progress_callback(self.row_counter - 1, self.total_rows)
            except Exception:
                pass

        if count == 0:
            return ""

        self.buffer.seek(0)
        return self.buffer.read()

    def close(self):
        if hasattr(self, "file_obj") and self.file_obj:
            self.file_obj.close()


def load_to_staging(
    db: Session,
    dataset_id,
    file_path: str,
    batch_size: int = 20000,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    total_rows: int = 0,
) -> int:
    """
    Load data from file into staging.records using PostgreSQL COPY bulk streaming.
    """
    from app.database.connection import engine

    path = Path(file_path)
    extension = path.suffix.lower()
    dataset_id_str = str(dataset_id)

    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()

        if extension == ".csv":
            stream_buf = CsvToStagingStream(
                file_path,
                dataset_id_str,
                chunk_size=50000,
                progress_callback=progress_callback,
                total_rows=total_rows,
            )
            copy_sql = "COPY staging.records (dataset_id, row_number, raw_data, cleaning_status) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', QUOTE E'\\b')"
            cursor.copy_expert(copy_sql, stream_buf)
            staged = stream_buf.row_counter - 1
            stream_buf.close()
            raw_conn.commit()


            if progress_callback:
                try:
                    progress_callback(staged, total_rows or staged)
                except Exception:
                    pass
            return staged

        else:
            row_counter = 1
            copy_sql = "COPY staging.records (dataset_id, row_number, raw_data, cleaning_status) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', QUOTE E'\\b')"
            for chunk in stream_file_records(file_path, chunk_size=batch_size):
                buf = io.StringIO()
                for record in chunk:
                    rec_json = json.dumps(record).replace("\\", "\\\\").replace("\t", " ").replace("\r", "").replace("\n", " ")
                    buf.write(f"{dataset_id_str}\t{row_counter}\t{rec_json}\tpending\n")
                    row_counter += 1
                buf.seek(0)
                cursor.copy_expert(copy_sql, buf)
                buf.close()
                if progress_callback:
                    try:
                        progress_callback(row_counter - 1, total_rows)
                    except Exception:
                        pass
            raw_conn.commit()
            staged = row_counter - 1
            if progress_callback:
                try:
                    progress_callback(staged, total_rows or staged)
                except Exception:
                    pass
            return staged
    finally:
        raw_conn.close()