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


def normalize_dataset(
    db: Session,
    dataset_id: Any,
    batch_size: int = 50000,
) -> int:
    """
    Convert staging JSON records into the normalized
    analytics.uploaded_metrics table using set-based SQL operations.
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

    query = text(f"""
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
    """)

    # Set local working memory for this normalization transaction
    db.execute(text("SET LOCAL work_mem = '64MB';"))
    db.execute(query, {"dataset_id": dataset_id})
    cnt = db.execute(
        text("SELECT count(*) FROM analytics.uploaded_metrics WHERE dataset_id = :dataset_id"),
        {"dataset_id": dataset_id}
    ).scalar()
    return int(cnt or 0)