"""
Phase 6: ML Feature Engineering & Target Leakage Audit Pipeline

Reproducible feature engineering pipeline built upon Phase 5 canonical normalization architecture.
Strictly enforces prediction target cy_admission (1=admitted, 0=not admitted) and target leakage prevention.
"""

import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.normalization.dimension_resolver import (
    StateResolver,
    SourceResolver,
    EmployeeResolver,
)

logger = logging.getLogger(__name__)

# List of forbidden leakage fields (must NEVER appear in feature dataset)
FORBIDDEN_LEAKAGE_FIELDS = {
    "mx_admissiondate",
    "mx_admission_done",
    "mx_refund_status",
    "mx_refund_initiated_on",
    "mx_fasttrackid",
    "mx_account_no",
    "mx_cucet_first_payment_date",
    "prospectstage",
    "lead_type",
}

ACCEPTED_FEATURE_COLUMNS = [
    "campus_name",
    "academic_year",
    "source_canonical",
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


class MLFeaturePipeline:
    def __init__(self, db: Session):
        self.db = db
        self.state_resolver = StateResolver(db)
        self.source_resolver = SourceResolver(db)
        self.employee_resolver = EmployeeResolver(db)

    def extract_features(
        self, dataset_id: Optional[str] = None, limit: Optional[int] = None
    ) -> pd.DataFrame:
        """Extract reproducible ML features from analytics.uploaded_metrics.
        
        Applies canonical master data resolution and dimension-specific missingness policies.
        """
        where_clause = "WHERE d.is_analytics_enabled = TRUE"
        params: Dict[str, Any] = {}
        if dataset_id:
            where_clause += " AND u.dataset_id = :dataset_id"
            params["dataset_id"] = str(dataset_id)

        limit_clause = f" LIMIT {limit}" if limit else ""

        query = text(f"""
            SELECT 
                u.id,
                u.dataset_id,
                u.campus_name,
                u.academic_year,
                u.owner,
                u.main_source,
                u.source,
                u.state,
                u.created_at,
                u.cy_cucet,
                u.cy_admission
            FROM analytics.uploaded_metrics u
            JOIN system.datasets d ON u.dataset_id = d.id
            {where_clause}
            ORDER BY u.created_at ASC
            {limit_clause}
        """)

        rows = self.db.execute(query, params).mappings().all()

        records = []
        for row in rows:
            # 1. Target Variable (Strictly {0, 1})
            target_val = int(row["cy_admission"]) if row["cy_admission"] is not None else 0
            if target_val not in (0, 1):
                target_val = 1 if target_val > 0 else 0

            # 2. Dimension Resolution & Missingness Policies
            state_res = self.state_resolver.resolve(row["state"])
            source_res = self.source_resolver.resolve(row["source"] or row["main_source"])
            emp_res = self.employee_resolver.resolve(row["owner"])

            state_canonical = state_res.canonical_value or "UNMAPPED_STATE"
            state_code = state_res.extra.get("state_code") or "UNMAPPED_CODE"
            zone = state_res.extra.get("zone") or emp_res.extra.get("zone") or "UNMAPPED_ZONE"

            source_canonical = source_res.canonical_value or "UNMAPPED_SOURCE"
            owner_canonical = emp_res.canonical_value or "UNMAPPED_OWNER"
            team = emp_res.extra.get("team") or "UNMAPPED_TEAM"

            # 3. Temporal Features ($t_0$)
            created_dt = row["created_at"]
            if created_dt:
                created_month = created_dt.month
                created_dayofweek = created_dt.weekday()
                created_hour = created_dt.hour
            else:
                created_month = 1
                created_dayofweek = 0
                created_hour = 12

            # 4. Early Engagement Flag
            cy_cucet = int(row["cy_cucet"]) if row["cy_cucet"] is not None else 0

            record = {
                "id": str(row["id"]),
                "dataset_id": str(row["dataset_id"]),
                "campus_name": row["campus_name"] or "UNMAPPED_CAMPUS",
                "academic_year": int(row["academic_year"]),
                "source_canonical": source_canonical,
                "state_canonical": state_canonical,
                "state_code": state_code,
                "zone": zone,
                "owner_canonical": owner_canonical,
                "team": team,
                "created_month": created_month,
                "created_dayofweek": created_dayofweek,
                "created_hour": created_hour,
                "cy_cucet": cy_cucet,
                TARGET_COLUMN: target_val,
            }
            records.append(record)

        df = pd.DataFrame(records)
        validate_no_leakage(list(df.columns))
        return df


def get_feature_schema_summary() -> Dict[str, Any]:
    """Return static summary of ML feature contract for verification & API metadata."""
    return {
        "target": TARGET_COLUMN,
        "target_type": "binary",
        "accepted_features": ACCEPTED_FEATURE_COLUMNS,
        "forbidden_leakage_fields": list(FORBIDDEN_LEAKAGE_FIELDS),
        "total_accepted_features": len(ACCEPTED_FEATURE_COLUMNS),
    }
