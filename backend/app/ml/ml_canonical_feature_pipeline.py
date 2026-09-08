"""
Phase 11.5: Canonical PostgreSQL ML Feature Pipeline
Extracts 100% distinct, reproducible ML features from staging.records (RAW datasets).
Enforces ProspectID deduplication, strict target leakage prevention, and canonical database mappings.
"""

import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.repository import resolve_raw_dataset
from app.normalization.dimension_resolver import (
    StateResolver,
    SourceResolver,
    EmployeeResolver,
)

logger = logging.getLogger(__name__)

# Forbidden post-t0 target leakage fields (must NEVER appear in ML feature matrix)
FORBIDDEN_LEAKAGE_FIELDS = {
    "mx_admissiondate",
    "mx_admission_done",
    "mx_refund_status",
    "mx_refund_initiated_on",
    "mx_fasttrackid",
    "mx_account_no",
    "mx_cucet_first_payment_date",
    "prospectstage",
    "lead_type_post_admission",
}

CANONICAL_FEATURE_COLUMNS = [
    "campus_name",
    "academic_year",
    "program_code",
    "source_canonical",
    "lead_type",
    "state_canonical",
    "state_code",
    "zone",
    "owner_canonical",
    "team",
    "created_month",
    "created_dayofweek",
    "created_hour",
    "cy_cucet",
]

TARGET_COLUMN = "cy_admission"


def validate_no_leakage(column_names: List[str]) -> None:
    """Validate that no forbidden target leakage columns are present in the feature schema."""
    cols_lower = {str(c).lower().strip() for c in column_names}
    intersection = cols_lower.intersection(FORBIDDEN_LEAKAGE_FIELDS)
    if intersection:
        raise ValueError(
            f"TARGET LEAKAGE DETECTED! Forbidden fields present in feature set: {intersection}"
        )


class CanonicalMLFeaturePipeline:
    """Extracts features directly from PostgreSQL staging.records for RAW datasets."""

    def __init__(self, db: Session):
        self.db = db
        self.state_resolver = StateResolver(db)
        self.source_resolver = SourceResolver(db)
        self.employee_resolver = EmployeeResolver(db)

    def extract_features(
        self, year: Optional[int] = None, dataset_id: Optional[str] = None, limit: Optional[int] = None
    ) -> pd.DataFrame:
        """Extract canonical ML features from PostgreSQL staging.records (RAW datasets only)."""
        target_ds_id = dataset_id
        if not target_ds_id and year:
            target_ds_id = resolve_raw_dataset(self.db, year)
        
        where_clauses = ["d.workbook_type = 'RAW'"]
        params: Dict[str, Any] = {}

        if target_ds_id:
            where_clauses.append("r.dataset_id = :ds_id")
            params["ds_id"] = str(target_ds_id)

        limit_sql = f"LIMIT {limit}" if limit else ""

        # Query distinct ProspectIDs from staging.records
        query = text(f"""
            WITH raw_leads AS (
                SELECT DISTINCT ON (r.raw_data->>'ProspectID')
                    r.id,
                    r.dataset_id,
                    d.academic_year,
                    COALESCE(r.raw_data->>'CampusHandled', r.raw_data->>'Campus', 'Mohali') as campus_name,
                    COALESCE(r.raw_data->>'Program Code', r.raw_data->>'Program Name', 'UNMAPPED_PROGRAM') as program_code,
                    COALESCE(r.raw_data->>'MSSourcebi', r.raw_data->>'Source', 'Unknown') as source_raw,
                    COALESCE(r.raw_data->>'State', 'Unknown') as state_raw,
                    COALESCE(r.raw_data->>'OwnerIdName', 'Unassigned') as owner_raw,
                    r.raw_data->>'CreatedOn' as created_on_str,
                    r.created_at,
                    CASE 
                        WHEN NULLIF(TRIM(r.raw_data->>'mx_CUCET_Registration_Date'), '') IS NOT NULL 
                             AND LOWER(TRIM(r.raw_data->>'mx_CUCET_Registration_Date')) != 'null' THEN 1 
                        ELSE 0 
                    END as cy_cucet,
                    CASE 
                        WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL 
                             AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN 1 
                        ELSE 0 
                    END as cy_admission
                FROM staging.records r
                JOIN system.datasets d ON r.dataset_id = d.id
                WHERE {" AND ".join(where_clauses)}
                ORDER BY r.raw_data->>'ProspectID', r.created_at ASC
            )
            SELECT * FROM raw_leads
            ORDER BY created_at ASC
            {limit_sql};
        """)

        rows = self.db.execute(query, params).mappings().all()

        records = []
        for row in rows:
            target_val = int(row["cy_admission"] or 0)

            # Dimension Resolution & Missingness Policies
            state_res = self.state_resolver.resolve(row["state_raw"])
            source_res = self.source_resolver.resolve(row["source_raw"])
            emp_res = self.employee_resolver.resolve(row["owner_raw"])

            state_canonical = state_res.canonical_value or "UNMAPPED_STATE"
            state_code = state_res.extra.get("state_code") or "UNMAPPED_CODE"
            zone = state_res.extra.get("zone") or emp_res.extra.get("zone") or "UNMAPPED_ZONE"

            source_canonical = source_res.canonical_value or "UNMAPPED_SOURCE"
            lead_type = source_res.extra.get("lead_type") or "Unmapped"
            owner_canonical = emp_res.canonical_value or "UNMAPPED_OWNER"
            team = emp_res.extra.get("team") or "UNMAPPED_TEAM"

            # Parse CreatedOn Timestamp
            created_dt = None
            if row["created_on_str"]:
                try:
                    created_dt = pd.to_datetime(row["created_on_str"])
                except Exception:
                    created_dt = row["created_at"]
            else:
                created_dt = row["created_at"]

            if created_dt and not pd.isna(created_dt):
                created_month = created_dt.month
                created_dayofweek = created_dt.weekday()
                created_hour = created_dt.hour
            else:
                created_month = 1
                created_dayofweek = 0
                created_hour = 12

            academic_yr = int(row["academic_year"] or (created_dt.year if created_dt else 2026))

            record = {
                "id": str(row["id"]),
                "dataset_id": str(row["dataset_id"]),
                "campus_name": str(row["campus_name"] or "Mohali"),
                "academic_year": academic_yr,
                "program_code": str(row["program_code"] or "UNMAPPED_PROGRAM"),
                "source_canonical": source_canonical,
                "lead_type": lead_type,
                "state_canonical": state_canonical,
                "state_code": state_code,
                "zone": zone,
                "owner_canonical": owner_canonical,
                "team": team,
                "created_month": created_month,
                "created_dayofweek": created_dayofweek,
                "created_hour": created_hour,
                "cy_cucet": int(row["cy_cucet"] or 0),
                TARGET_COLUMN: target_val,
            }
            records.append(record)

        df = pd.DataFrame(records)
        if not df.empty:
            validate_no_leakage(list(df.columns))
        return df


def get_canonical_feature_summary() -> Dict[str, Any]:
    """Return summary of canonical feature schema contract."""
    return {
        "target": TARGET_COLUMN,
        "target_type": "binary",
        "canonical_features": CANONICAL_FEATURE_COLUMNS,
        "forbidden_leakage_fields": list(FORBIDDEN_LEAKAGE_FIELDS),
        "total_canonical_features": len(CANONICAL_FEATURE_COLUMNS),
    }
