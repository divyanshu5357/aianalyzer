"""
Aggregate refresh service for Executive Dashboard

Populates analytics.dashboard_agg materialized aggregate from analytics.uploaded_metrics with
state canonicalization and lead_type business classification using CTE pre-aggregation.

Supports both scoped (per-dataset) and full refresh modes.
"""

import logging
import time
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.normalization.state_resolver import STATE_LOOKUP, FOREIGN_LOCATIONS
from app.normalization.lead_type_resolver import IN_HOUSE_KEYWORDS, OUT_SOURCED_KEYWORDS

logger = logging.getLogger(__name__)


def _build_sql_state_case() -> str:
    """Build PostgreSQL CASE statement for state canonicalization."""
    branches = []

    group_by_canonical = {}
    for raw_k, canonical_v in STATE_LOOKUP.items():
        group_by_canonical.setdefault(canonical_v, []).append(raw_k.replace("'", "''"))

    for canonical, keys in group_by_canonical.items():
        keys_str = ", ".join(f"'{k}'" for k in keys)
        branches.append(f"WHEN LOWER(TRIM(COALESCE(state, ''))) IN ({keys_str}) THEN '{canonical}'")

    foreign_keys_str = ", ".join(f"'{k}'" for k in FOREIGN_LOCATIONS)
    branches.append(f"WHEN LOWER(TRIM(COALESCE(state, ''))) IN ({foreign_keys_str}) THEN 'INTERNATIONAL'")

    return f"CASE {' '.join(branches)} ELSE 'UNMAPPED_STATE' END"


def _build_sql_lead_type_case() -> str:
    """Build PostgreSQL CASE statement for lead type resolution on source."""
    outsourced_conds = " OR ".join(f"LOWER(COALESCE(source, '')) LIKE '%{kw}%'" for kw in OUT_SOURCED_KEYWORDS)
    inhouse_conds = " OR ".join(f"LOWER(COALESCE(source, '')) LIKE '%{kw}%'" for kw in IN_HOUSE_KEYWORDS)

    return f"""
        CASE
            WHEN {outsourced_conds} THEN 'OUT SOURCED'
            WHEN {inhouse_conds} THEN 'IN HOUSE'
            ELSE 'OTHERS'
        END
    """


def _build_insert_sql(dataset_filter: str = "") -> str:
    """Build the CTE-based INSERT statement for dashboard_agg refresh.

    Args:
        dataset_filter: Additional WHERE clause fragment for scoping, e.g.
                        "AND um.dataset_id = :ds_id"
    """
    state_case_expr = _build_sql_state_case()
    lead_type_case_expr = _build_sql_lead_type_case()

    return f"""
        WITH raw_agg AS (
            SELECT
                um.dataset_id,
                um.campus_name,
                COALESCE(um.academic_year, sd.academic_year) AS academic_year,
                um.state AS state,
                um.source AS source,
                COALESCE(um.program_code, um.raw_program_code) AS program_code,
                um.raw_program_code AS raw_program_code,
                COALESCE(um.program_name, cm.program_name) AS program_name,
                COALESCE(um.course_cluster, cm.course_cluster) AS course_cluster,
                um.created_month,
                um.admission_month,
                um.owner,
                SUM(um.cy_leads) AS leads_cy,
                SUM(um.cy_cucet) AS cucet_cy,
                SUM(um.cy_admission) AS admission_cy,
                SUM(um.py_leads) AS leads_py,
                SUM(um.py_cucet) AS cucet_py,
                SUM(um.py_admission) AS admission_py
            FROM analytics.uploaded_metrics um
            INNER JOIN system.datasets sd
                ON sd.id = um.dataset_id
                AND sd.is_analytics_enabled = TRUE
            LEFT JOIN organization.course_master cm
                ON um.program_code = cm.program_code
            WHERE 1=1 {dataset_filter}
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12
        )
        INSERT INTO analytics.dashboard_agg (
            dataset_id,
            campus_name,
            academic_year,
            state,
            lead_type,
            source,
            raw_program_code,
            program_code,
            course_cluster,
            program_name,
            created_month,
            admission_month,
            owner,
            leads_cy,
            cucet_cy,
            admission_cy,
            leads_py,
            cucet_py,
            admission_py,
            created_at,
            updated_at
        )
        SELECT
            dataset_id,
            campus_name,
            academic_year,
            {state_case_expr} AS state,
            {lead_type_case_expr} AS lead_type,
            source,
            raw_program_code,
            program_code,
            course_cluster,
            program_name,
            created_month,
            admission_month,
            owner,
            leads_cy,
            cucet_cy,
            admission_cy,
            leads_py,
            cucet_py,
            admission_py,
            NOW() AS created_at,
            NOW() AS updated_at
        FROM raw_agg;
    """


def refresh_dashboard_agg_scoped(
    db: Session,
    dataset_id: Optional[str] = None,
) -> dict:
    """Refresh dashboard_agg for a specific dataset scope only.

    Instead of TRUNCATE + full rebuild, this:
    1. Deletes only the rows owned by the given dataset_id
    2. Re-inserts aggregated data for that dataset only

    This makes the operation O(dataset_rows) instead of O(all_rows).
    Other datasets' aggregated data remains untouched.

    Returns timing information for performance monitoring.
    """
    t0 = time.perf_counter()

    if dataset_id is None:
        # Fallback to full refresh
        return refresh_dashboard_agg(db)

    ds_id_str = str(dataset_id)

    # Step 1: Delete existing aggregates for this dataset
    t1_del = time.perf_counter()
    del_result = db.execute(
        text("DELETE FROM analytics.dashboard_agg WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id_str},
    )
    deleted_rows = del_result.rowcount
    t2_del = time.perf_counter()

    # Step 2: Check if dataset is still analytics-enabled (skip insert if disabled/deleted)
    ds_check = db.execute(
        text("SELECT is_analytics_enabled FROM system.datasets WHERE id = :ds_id"),
        {"ds_id": ds_id_str},
    ).scalar()

    inserted_rows = 0
    t3_ins = t2_del

    if ds_check is True:
        # Step 3: Re-insert aggregated data for this dataset only
        insert_sql = _build_insert_sql(dataset_filter="AND um.dataset_id = :ds_id")
        db.execute(text(insert_sql), {"ds_id": ds_id_str})

        cnt = db.execute(
            text("SELECT COUNT(*) FROM analytics.dashboard_agg WHERE dataset_id = :ds_id"),
            {"ds_id": ds_id_str},
        ).scalar()
        inserted_rows = int(cnt or 0)
        t3_ins = time.perf_counter()

    db.commit()
    t_total = time.perf_counter()

    timings = {
        "delete_ms": round((t2_del - t1_del) * 1000, 2),
        "insert_ms": round((t3_ins - t2_del) * 1000, 2),
        "total_ms": round((t_total - t0) * 1000, 2),
        "deleted_rows": deleted_rows,
        "inserted_rows": inserted_rows,
        "dataset_id": ds_id_str,
    }

    logger.info(
        "[SCOPED AGG REFRESH] dataset=%s deleted=%d inserted=%d total_ms=%.2f",
        ds_id_str, deleted_rows, inserted_rows, timings["total_ms"],
    )

    return timings


def delete_dashboard_agg_for_dataset(db: Session, dataset_id: str) -> int:
    """Remove all dashboard_agg rows owned by a dataset.

    Used during dataset deletion — no re-insertion needed.
    Returns the number of deleted aggregate rows.
    """
    ds_id_str = str(dataset_id)
    result = db.execute(
        text("DELETE FROM analytics.dashboard_agg WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id_str},
    )
    deleted = result.rowcount
    db.commit()
    logger.info("[AGG DELETE] Removed %d dashboard_agg rows for dataset %s", deleted, ds_id_str)
    return deleted


def refresh_dashboard_agg(db: Session) -> dict:
    """Full refresh of the analytics.dashboard_agg table.

    WARNING: This truncates and rebuilds ALL data. Use refresh_dashboard_agg_scoped()
    for per-dataset operations. This function should only be called during:
    - Initial schema migration / first-time setup
    - State canonicalization re-runs (affects all scopes)
    - Explicit admin-triggered full rebuild
    """
    t0 = time.perf_counter()

    db.execute(text("DELETE FROM analytics.dashboard_agg;"))

    insert_sql = _build_insert_sql()
    db.execute(text(insert_sql))
    db.commit()

    t_total = time.perf_counter()
    duration_ms = round((t_total - t0) * 1000, 2)
    logger.info("[FULL AGG REFRESH] Completed in %.2f ms", duration_ms)
    return {"total_ms": duration_ms}
