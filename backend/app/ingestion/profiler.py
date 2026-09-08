import csv
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import pandas as pd


def infer_data_type(series: pd.Series) -> str:
    """Infer high-level semantic data type for a pandas Series."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return "string"

    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    # Try string-based numeric / date detection
    sample_str = [str(x).strip() for x in non_null.head(50) if str(x).strip()]
    if sample_str:
        if all(re.match(r"^-?\d+$", s) for s in sample_str):
            return "integer"
        if all(re.match(r"^-?\d+(\.\d+)?$", s) for s in sample_str):
            return "float"
        if all(s.lower() in ("true", "false", "yes", "no", "y", "n", "1", "0") for s in sample_str):
            return "boolean"

    return "string"


def profile_column_series(series: pd.Series, col_name: str) -> Dict[str, Any]:
    """Profile a single column series: type, null %, uniqueness, key likelihood, samples."""
    total_count = len(series)
    null_count = int(series.isna().sum())
    null_percentage = round((null_count / total_count) * 100, 2) if total_count > 0 else 0.0

    non_null = series.dropna()
    unique_count = int(non_null.nunique())
    uniqueness_ratio = round(unique_count / total_count, 4) if total_count > 0 else 0.0

    dtype = infer_data_type(series)

    # Key likelihood heuristics
    is_key_name = bool(re.search(
        r"(?i)(_id\b|\bid$|_code\b|\bcode$|_key\b|\bkey$|prospect|employee|owner|counselor|registration|enquiry|roll_?no)",
        str(col_name)
    ))
    is_likely_key = (
        (uniqueness_ratio >= 0.85 and null_percentage <= 15.0 and total_count >= 2)
        or (is_key_name and unique_count >= 2 and null_percentage <= 30.0)
    )

    # 3-5 distinct sample values
    sample_values = []
    seen = set()
    for val in non_null:
        v_str = str(val).strip()
        if v_str and v_str not in seen:
            seen.add(v_str)
            sample_values.append(v_str)
            if len(sample_values) >= 5:
                break

    return {
        "name": str(col_name),
        "dtype": dtype,
        "missing": null_count,
        "null_count": null_count,
        "null_percentage": null_percentage,
        "unique_values": unique_count,
        "uniqueness_ratio": uniqueness_ratio,
        "is_likely_key": is_likely_key,
        "sample_values": sample_values,
    }


def profile_dataframe(df: pd.DataFrame, sheet_name: str = "default") -> Dict[str, Any]:
    """
    Analyze a dataframe without modifying the original data.
    Provides complete row, column, quality, and column-level profiling metrics.
    """
    rows = len(df)
    columns = len(df.columns)

    missing_values = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    total_cells = rows * columns
    missing_percentage = (missing_values / total_cells) * 100 if total_cells > 0 else 0.0
    duplicate_percentage = (duplicate_rows / rows) * 100 if rows > 0 else 0.0

    quality_score = max(0.0, 100.0 - missing_percentage - duplicate_percentage)

    sample_rows = (
        df.head(5)
        .where(pd.notnull(df.head(5)), None)
        .to_dict(orient="records")
    )

    columns_info = []
    columns_profile = []

    for column in df.columns:
        col_prof = profile_column_series(df[column], str(column))
        columns_profile.append(col_prof)
        columns_info.append({
            "name": col_prof["name"],
            "dtype": col_prof["dtype"],
            "missing": col_prof["missing"],
            "unique_values": col_prof["unique_values"],
            "null_percentage": col_prof["null_percentage"],
            "is_likely_key": col_prof["is_likely_key"],
        })

    return {
        "sheet_name": sheet_name,
        "rows": rows,
        "columns": columns,
        "column_names": [str(column) for column in df.columns],
        "missing_values": missing_values,
        "duplicate_rows": duplicate_rows,
        "missing_percentage": round(missing_percentage, 2),
        "duplicate_percentage": round(duplicate_percentage, 2),
        "quality_score": round(quality_score, 2),
        "columns_info": columns_info,
        "columns_profile": columns_profile,
        "sample_rows": sample_rows,
    }


def profile_multisheet_file(file_path: str) -> Dict[str, Any]:
    """
    Profiles an upload file across all its sheets.
    Supports CSV and multi-sheet Excel (.xlsx, .xls, .xlsb).
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    sheet_profiles = []

    if suffix == ".csv":
        file_size = path.stat().st_size
        try:
            from app.ingestion.staging_loader import (
                is_headerless_crm_row,
                STANDARD_CRM_39_COLUMNS,
                STANDARD_CRM_41_COLUMNS,
            )
            is_headerless = False
            crm_names = None
            try:
                with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f_chk:
                    r1 = next(csv.reader(f_chk), None)
                    if r1 and is_headerless_crm_row(r1):
                        is_headerless = True
                        crm_names = STANDARD_CRM_39_COLUMNS if len(r1) == 39 else STANDARD_CRM_41_COLUMNS
            except Exception:
                pass

            csv_kwargs: Dict[str, Any] = {"encoding": "utf-8-sig", "low_memory": False}
            if is_headerless and crm_names:
                csv_kwargs["names"] = crm_names
                csv_kwargs["header"] = None

            if file_size > 10 * 1024 * 1024:
                # Fast sample profiling for large CSV (>10MB) to prevent OOM
                df_sample = pd.read_csv(file_path, nrows=2000, **csv_kwargs)
                prof = profile_dataframe(df_sample, sheet_name="Sheet1")
                # Count total rows accurately without loading full file into memory
                with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    if is_headerless:
                        row_count = sum(1 for line in f if line.strip())
                    else:
                        row_count = max(0, sum(1 for line in f if line.strip()) - 1)
                prof["rows"] = row_count
                sheet_profiles.append(prof)
            else:
                df = pd.read_csv(file_path, **csv_kwargs)
                prof = profile_dataframe(df, sheet_name="Sheet1")
                sheet_profiles.append(prof)
        except Exception:
            # Fallback to streaming reader for very large or malformed CSVs
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                header_row = next(reader, None)
                if not header_row:
                    empty_prof = {
                        "sheet_name": "Sheet1",
                        "rows": 0,
                        "columns": 0,
                        "column_names": [],
                        "missing_values": 0,
                        "duplicate_rows": 0,
                        "missing_percentage": 0.0,
                        "duplicate_percentage": 0.0,
                        "quality_score": 0.0,
                        "columns_info": [],
                        "columns_profile": [],
                        "sample_rows": [],
                    }
                    sheet_profiles.append(empty_prof)
                else:
                    cols = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(header_row)]
                    num_cols = len(cols)
                    sample_rows = []
                    total_rows = 0
                    missing_values = 0
                    col_samples = {c: [] for c in cols}

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
                            elif len(col_samples[cols[i]]) < 5:
                                col_samples[cols[i]].append(str(val).strip())

                    total_cells = total_rows * num_cols
                    missing_pct = round((missing_values / total_cells) * 100, 2) if total_cells > 0 else 0.0

                    columns_profile = []
                    for c in cols:
                        is_likely_key = bool(re.search(r"(?i)(_id|id|_code|code|_key|key|prospect|employee|owner)", c))
                        columns_profile.append({
                            "name": c,
                            "dtype": "string",
                            "missing": 0,
                            "null_count": 0,
                            "null_percentage": 0.0,
                            "unique_values": total_rows,
                            "uniqueness_ratio": 1.0 if total_rows > 0 else 0.0,
                            "is_likely_key": is_likely_key,
                            "sample_values": col_samples[c],
                        })

                    sheet_profiles.append({
                        "sheet_name": "Sheet1",
                        "rows": total_rows,
                        "columns": num_cols,
                        "column_names": cols,
                        "missing_values": missing_values,
                        "duplicate_rows": 0,
                        "missing_percentage": missing_pct,
                        "duplicate_percentage": 0.0,
                        "quality_score": 100.0 if total_rows > 0 else 0.0,
                        "columns_info": columns_profile,
                        "columns_profile": columns_profile,
                        "sample_rows": sample_rows,
                    })

    elif suffix in [".xlsx", ".xls", ".xlsb"]:
        excel_file = pd.ExcelFile(file_path)
        for sname in excel_file.sheet_names:
            df = excel_file.parse(sname)
            prof = profile_dataframe(df, sheet_name=sname)
            sheet_profiles.append(prof)
    else:
        raise ValueError(
            f"Unsupported file format '{suffix}'. Only CSV and Excel files are supported."
        )

    primary_sheet = sheet_profiles[0] if sheet_profiles else {}
    tot_rows = sum(s.get("rows", 0) for s in sheet_profiles)
    tot_cols = primary_sheet.get("columns", 0)

    return {
        "file_name": path.name,
        "file_type": suffix.replace(".", ""),
        "total_sheets": len(sheet_profiles),
        "sheet_names": [s["sheet_name"] for s in sheet_profiles],
        "sheets": sheet_profiles,
        "total_rows": tot_rows,
        "total_columns": tot_cols,
        # Preserve primary sheet attributes at top level for backward compatibility
        "rows": primary_sheet.get("rows", 0),
        "columns": primary_sheet.get("columns", 0),
        "column_names": primary_sheet.get("column_names", []),
        "missing_values": primary_sheet.get("missing_values", 0),
        "duplicate_rows": primary_sheet.get("duplicate_rows", 0),
        "missing_percentage": primary_sheet.get("missing_percentage", 0.0),
        "duplicate_percentage": primary_sheet.get("duplicate_percentage", 0.0),
        "quality_score": primary_sheet.get("quality_score", 0.0),
        "columns_info": primary_sheet.get("columns_info", []),
        "columns_profile": primary_sheet.get("columns_profile", []),
        "sample_rows": primary_sheet.get("sample_rows", []),
    }


def profile_file(file_path: str) -> Dict[str, Any]:
    """
    Load CSV or Excel file and generate a profile.
    Maintains full backward compatibility with previous profile_file callers.
    """
    return profile_multisheet_file(file_path)