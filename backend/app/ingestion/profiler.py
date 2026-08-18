import csv
from pathlib import Path

import pandas as pd


def profile_dataframe(df: pd.DataFrame) -> dict:
    """
    Analyze a dataframe without modifying the original data.
    """

    rows = len(df)
    columns = len(df.columns)

    missing_values = int(df.isna().sum().sum())

    duplicate_rows = int(df.duplicated().sum())

    total_cells = rows * columns

    if total_cells > 0:
        missing_percentage = (
            missing_values / total_cells
        ) * 100
    else:
        missing_percentage = 0

    duplicate_percentage = (
        (duplicate_rows / rows) * 100
        if rows > 0
        else 0
    )

    # Basic quality score
    quality_score = max(
        0,
        100
        - missing_percentage
        - duplicate_percentage
    )

    sample_rows = (
        df.head(5)
        .where(pd.notnull(df.head(5)), None)
        .to_dict(orient="records")
    )

    column_information = []

    for column in df.columns:

        column_information.append(
            {
                "name": str(column),
                "dtype": str(df[column].dtype),
                "missing": int(df[column].isna().sum()),
                "unique_values": int(
                    df[column].nunique(dropna=True)
                ),
            }
        )

    return {
        "rows": rows,
        "columns": columns,
        "column_names": [
            str(column)
            for column in df.columns
        ],
        "missing_values": missing_values,
        "duplicate_rows": duplicate_rows,
        "missing_percentage": round(
            missing_percentage,
            2,
        ),
        "duplicate_percentage": round(
            duplicate_percentage,
            2,
        ),
        "quality_score": round(
            quality_score,
            2,
        ),
        "columns_info": column_information,
        "sample_rows": sample_rows,
    }


def profile_file(file_path: str) -> dict:
    """
    Load CSV or Excel file and generate a profile in a streaming manner.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            header_row = next(reader, None)
            if not header_row:
                return {
                    "rows": 0,
                    "columns": 0,
                    "column_names": [],
                    "missing_values": 0,
                    "duplicate_rows": 0,
                    "missing_percentage": 0.0,
                    "duplicate_percentage": 0.0,
                    "quality_score": 0.0,
                    "columns_info": [],
                    "sample_rows": [],
                }

            cols = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(header_row)]
            num_cols = len(cols)
            sample_rows = []
            total_rows = 0
            missing_values = 0

            for row in reader:
                if not row:
                    continue
                total_rows += 1
                if len(sample_rows) < 5:
                    rec = {cols[i]: row[i] if i < len(row) else None for i in range(num_cols)}
                    sample_rows.append(rec)

                row_len = len(row)
                if row_len < num_cols:
                    missing_values += (num_cols - row_len)
                for i in range(min(row_len, num_cols)):
                    val = row[i]
                    if val == "" or val is None or val.strip().lower() in ("nan", "null", "none", "n/a"):
                        missing_values += 1

            total_cells = total_rows * num_cols
            missing_pct = round((missing_values / total_cells) * 100, 2) if total_cells > 0 else 0.0

            return {
                "rows": total_rows,
                "columns": num_cols,
                "column_names": cols,
                "missing_values": missing_values,
                "duplicate_rows": 0,
                "missing_percentage": missing_pct,
                "duplicate_percentage": 0.0,
                "quality_score": 100.0 if total_rows > 0 else 0.0,
                "columns_info": [{"name": c, "dtype": "string", "missing": 0, "unique_values": 0} for c in cols],
                "sample_rows": sample_rows,
            }

    elif suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(file_path)
        return profile_dataframe(df)

    else:
        raise ValueError(
            "Unsupported file format. "
            "Only CSV and Excel files are supported."
        )