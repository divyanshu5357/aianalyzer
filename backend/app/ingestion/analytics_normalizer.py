from typing import Any
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session

COLUMN_MAP = {
    "Owner": "owner",
    "Cluster": "cluster",
    "Lead Type": "lead_type",
    "Source Cluster": "main_source",
    "MSSourcebi": "source",
    "Campus Name": "campus_name",
    "State Group": "state",
    "Program Name (Short)": "program_name",
    "CY Leads": "cy_leads",
    "CY CUCET": "cy_cucet",
    "CY Admission": "cy_admission",
    "PY Leads": "py_leads",
    "PY CUCET": "py_cucet",
    "PY Admission": "py_admission",
}


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        val_str = value.replace(",", "").strip()
        if not val_str:
            return 0.0
        try:
            return float(val_str)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _text(value: Any) -> str | None:
    if value is None:
        return None
    val_str = str(value).strip()
    return val_str or None


from typing import Any, Optional, Callable

def normalize_dataset(
    db: Session,
    dataset_id: Any,
    batch_size: int = 50000,
    mode: str = "insert",  # "insert" (fast direct load) or "upsert" (conflict resolution)
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> int:
    """
    Convert staging JSON records into the normalized analytics.uploaded_metrics table.
    Uses set-based, database-side chunked SQL operations for minimum memory & maximum speed.
    """
    # 1. Fetch dynamic column mapping for dataset
    try:
        from app.ingestion.schema_mapper import get_dataset_column_mapping
        mapping = get_dataset_column_mapping(db, dataset_id).get("by_canonical", {})
    except Exception:
        mapping = {}

    def get_orig(field: str, default_orig: str) -> str:
        orig = mapping.get(field) or default_orig
        return orig.replace("'", "''")

    col_owner = get_orig("owner", "Owner")
    col_cluster = get_orig("cluster", "Cluster")
    col_lead_type = get_orig("lead_type", "Lead Type")
    col_main_source = get_orig("main_source", "Source Cluster")
    col_source = get_orig("source", "MSSourcebi")
    col_campus = get_orig("campus_name", "Campus Name")
    col_state = get_orig("state", "State Group")
    col_prog = get_orig("program_name", "Program Name (Short)")

    col_cy_l = get_orig("cy_leads", "CY Leads")
    col_cy_c = get_orig("cy_cucet", "CY CUCET")
    col_cy_a = get_orig("cy_admission", "CY Admission")
    col_py_l = get_orig("py_leads", "PY Leads")
    col_py_c = get_orig("py_cucet", "PY CUCET")
    col_py_a = get_orig("py_admission", "PY Admission")

    # Set local working memory for this normalization transaction
    db.execute(text("SET LOCAL work_mem = '64MB';"))

    # For direct insert mode, ensure no prior leftover metrics exist for this dataset_id
    if mode == "insert":
        db.execute(
            text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id = :dataset_id"),
            {"dataset_id": dataset_id},
        )

    # Get min and max row_number from staging for chunked execution
    bounds = db.execute(
        text("SELECT MIN(row_number), MAX(row_number) FROM staging.records WHERE dataset_id = :dataset_id"),
        {"dataset_id": dataset_id},
    ).first()

    if not bounds or bounds[0] is None or bounds[1] is None:
        return 0

    min_row, max_row = int(bounds[0]), int(bounds[1])
    total_rows = max_row - min_row + 1

    # Construct chunk insert SQL
    conflict_clause = ""
    if mode == "upsert":
        conflict_clause = """
        ON CONFLICT (dataset_id, row_number)
        DO UPDATE SET
            owner = EXCLUDED.owner,
            cluster = EXCLUDED.cluster,
            lead_type = EXCLUDED.lead_type,
            main_source = EXCLUDED.main_source,
            source = EXCLUDED.source,
            campus_name = EXCLUDED.campus_name,
            state = EXCLUDED.state,
            program_name = EXCLUDED.program_name,
            cy_leads = EXCLUDED.cy_leads,
            cy_cucet = EXCLUDED.cy_cucet,
            cy_admission = EXCLUDED.cy_admission,
            py_leads = EXCLUDED.py_leads,
            py_cucet = EXCLUDED.py_cucet,
            py_admission = EXCLUDED.py_admission
        """

    chunk_sql = text(f"""
        INSERT INTO analytics.uploaded_metrics (
            id,
            dataset_id,
            row_number,
            owner,
            cluster,
            lead_type,
            main_source,
            source,
            campus_name,
            state,
            program_name,
            cy_leads,
            cy_cucet,
            cy_admission,
            py_leads,
            py_cucet,
            py_admission
        )
        SELECT
            gen_random_uuid(),
            :dataset_id,
            row_number,
            NULLIF(TRIM(raw_data->>'{col_owner}'), ''),
            NULLIF(TRIM(raw_data->>'{col_cluster}'), ''),
            NULLIF(TRIM(raw_data->>'{col_lead_type}'), ''),
            NULLIF(TRIM(raw_data->>'{col_main_source}'), ''),
            NULLIF(TRIM(raw_data->>'{col_source}'), ''),
            NULLIF(TRIM(raw_data->>'{col_campus}'), ''),
            NULLIF(TRIM(raw_data->>'{col_state}'), ''),
            NULLIF(TRIM(raw_data->>'{col_prog}'), ''),
            COALESCE(NULLIF(REPLACE(raw_data->>'{col_cy_l}', ',', ''), '')::numeric, 0),
            COALESCE(NULLIF(REPLACE(raw_data->>'{col_cy_c}', ',', ''), '')::numeric, 0),
            COALESCE(NULLIF(REPLACE(raw_data->>'{col_cy_a}', ',', ''), '')::numeric, 0),
            COALESCE(NULLIF(REPLACE(raw_data->>'{col_py_l}', ',', ''), '')::numeric, 0),
            COALESCE(NULLIF(REPLACE(raw_data->>'{col_py_c}', ',', ''), '')::numeric, 0),
            COALESCE(NULLIF(REPLACE(raw_data->>'{col_py_a}', ',', ''), '')::numeric, 0)
        FROM staging.records
        WHERE dataset_id = :dataset_id
          AND row_number >= :start_row AND row_number <= :end_row
        {conflict_clause}
    """)

    curr_start = min_row
    while curr_start <= max_row:
        curr_end = curr_start + batch_size - 1
        db.execute(
            chunk_sql,
            {
                "dataset_id": dataset_id,
                "start_row": curr_start,
                "end_row": curr_end,
            },
        )
        processed = min(max_row, curr_end) - min_row + 1
        if progress_callback:
            try:
                progress_callback(processed, total_rows)
            except Exception:
                pass
        curr_start = curr_end + 1

    cnt = db.execute(
        text("SELECT count(*) FROM analytics.uploaded_metrics WHERE dataset_id = :dataset_id"),
        {"dataset_id": dataset_id},
    ).scalar()
    final_count = int(cnt or 0)
    if progress_callback:
        try:
            progress_callback(final_count, total_rows)
        except Exception:
            pass
    return final_count