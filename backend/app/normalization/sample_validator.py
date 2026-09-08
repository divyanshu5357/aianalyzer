"""
Phase 10 — Manual Sample Validation

Selects a deterministic random sample of 100 records from each dataset.
For each record validates raw→canonical mappings for all dimensions and statuses.
Produces a per-record report: resolved correctly / unresolved / requires review.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.normalization.status_registry import resolve_prospect_stage
from app.normalization.dimension_resolver import DimensionResolverSuite

logger = logging.getLogger(__name__)


def validate_sample(db: Session, dataset_id: str, sample_size: int = 100, seed: int = 42) -> Dict[str, Any]:
    """
    Select a deterministic random sample from the analytics layer and validate
    each record's dimension resolutions.
    """
    ds = db.execute(text(
        "SELECT dataset_name, campus_name, academic_year "
        "FROM system.datasets WHERE id = :id"
    ), {"id": dataset_id}).mappings().first()

    if not ds:
        raise ValueError(f"Dataset {dataset_id} not found")

    resolvers = DimensionResolverSuite(db)

    # Deterministic sample using TABLESAMPLE or ORDER BY md5 for reproducibility
    sample_rows = db.execute(text(f"""
        SELECT id, row_number, owner, source, state, lead_type, campus_name,
               program_name, course_cluster, state_code, zone, team, source_cluster,
               academic_year, cy_leads, cy_cucet, cy_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :ds_id
        ORDER BY md5(id::text || '{seed}')
        LIMIT :limit
    """), {"ds_id": dataset_id, "limit": sample_size}).mappings().all()

    # Also fetch raw staging data if available
    has_staging = db.execute(text(
        "SELECT COUNT(*) FROM staging.records WHERE dataset_id = :id LIMIT 1"
    ), {"id": dataset_id}).scalar() or 0

    records = []
    resolved_count = 0
    unresolved_count = 0
    review_count = 0

    for row in sample_rows:
        record = {
            "row_number": row["row_number"],
            "validations": {},
        }

        # Status validation
        status_res = resolve_prospect_stage(row["lead_type"])
        record["validations"]["status"] = {
            "raw": row["lead_type"],
            "canonical": status_res.canonical_value,
            "admission_flag": status_res.admission_flag,
            "refunded_flag": status_res.refunded_flag,
            "resolution_status": status_res.resolution_status,
            "cy_admission_matches": (
                (status_res.admission_flag == 1 and int(row["cy_admission"] or 0) == 1) or
                (status_res.admission_flag == 0 and int(row["cy_admission"] or 0) == 0)
            ),
        }

        # State validation
        state_res = resolvers.state.resolve(row["state"])
        record["validations"]["state"] = {
            "raw": row["state"],
            "canonical": state_res.canonical_value,
            "resolution_method": state_res.resolution_method,
            "resolution_status": state_res.resolution_status,
            "state_code": state_res.extra.get("state_code"),
            "zone": state_res.extra.get("zone"),
        }

        # Source validation
        source_res = resolvers.source.resolve(row["source"])
        record["validations"]["source"] = {
            "raw": row["source"],
            "canonical": source_res.canonical_value,
            "resolution_method": source_res.resolution_method,
            "resolution_status": source_res.resolution_status,
        }

        # Employee validation
        emp_res = resolvers.employee.resolve(row["owner"])
        record["validations"]["employee"] = {
            "raw": row["owner"],
            "canonical": emp_res.canonical_value,
            "resolution_method": emp_res.resolution_method,
            "resolution_status": emp_res.resolution_status,
            "team": emp_res.extra.get("team"),
        }

        # Program validation
        prog_res = resolvers.program.resolve(row["program_name"])
        record["validations"]["program"] = {
            "raw": row["program_name"],
            "canonical": prog_res.canonical_value,
            "resolution_method": prog_res.resolution_method,
            "resolution_status": prog_res.resolution_status,
        }

        # Campus and year
        record["validations"]["campus"] = row["campus_name"]
        record["validations"]["academic_year"] = row["academic_year"]

        # Determine overall status
        all_statuses = [
            record["validations"]["status"]["resolution_status"],
            state_res.resolution_status,
            source_res.resolution_status,
            emp_res.resolution_status,
        ]

        if all(s == "RESOLVED" for s in all_statuses):
            record["overall"] = "RESOLVED"
            resolved_count += 1
        elif any(s == "REVIEW_REQUIRED" for s in all_statuses):
            record["overall"] = "REVIEW_REQUIRED"
            review_count += 1
        else:
            record["overall"] = "PARTIAL"
            unresolved_count += 1

        records.append(record)

    return {
        "dataset_id": dataset_id,
        "dataset_name": ds["dataset_name"],
        "campus": ds["campus_name"],
        "year": ds["academic_year"],
        "sample_size": len(records),
        "has_staging": has_staging > 0,
        "summary": {
            "resolved": resolved_count,
            "unresolved": unresolved_count,
            "review_required": review_count,
        },
        "records": records,
    }


def validate_all_samples(db: Session, sample_size: int = 100) -> List[Dict[str, Any]]:
    """Validate samples from all analytics-enabled datasets."""
    datasets = db.execute(text(
        "SELECT id FROM system.datasets WHERE is_analytics_enabled = TRUE ORDER BY campus_name, academic_year"
    )).fetchall()

    results = []
    for (ds_id,) in datasets:
        try:
            result = validate_sample(db, str(ds_id), sample_size=sample_size)
            results.append(result)
        except Exception as e:
            logger.error(f"Sample validation failed for {ds_id}: {e}")
    return results
