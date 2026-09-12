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
                COALESCE(cm.program_name, um.program_name, um.raw_program_code) AS program_name,
                COALESCE(cm.course_cluster, um.course_cluster) AS course_cluster,
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
                {"" if dataset_filter else "AND sd.is_analytics_enabled = TRUE"}
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
    """Deletes aggregated rows belonging to a specific dataset.

    Used when a dataset is deleted or replaced to purge its contribution
    from the pre-aggregated dashboard table without a full rebuild.

    Returns the number of deleted aggregate rows.
    """
    ds_id_str = str(dataset_id)
    result = db.execute(
        text("DELETE FROM analytics.dashboard_agg WHERE dataset_id = CAST(:ds_id AS uuid)"),
        {"ds_id": ds_id_str},
    )
    deleted = result.rowcount
    db.execute(
        text("DELETE FROM analytics.gender_monthly_agg WHERE dataset_id = CAST(:ds_id AS uuid)"),
        {"ds_id": ds_id_str},
    )
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


def refresh_program_refunds(db: Session, dataset_id: Optional[str] = None) -> int:
    """Populate or refresh analytics.program_refunds_summary from staging.records
    based on business rule: ProspectStage = 'Enrolled' AND mx_Refund_Status = 'Pending'.
    """
    logger.info("Refreshing program refunds summary...")
    ds_filter = "AND r.dataset_id = CAST(:ds_id AS uuid)" if dataset_id else ""
    params = {"ds_id": dataset_id} if dataset_id else {}

    try:
        if dataset_id:
            db.execute(text("""
                DELETE FROM analytics.program_refunds_summary
                WHERE academic_year IN (
                    SELECT academic_year FROM system.datasets WHERE id = CAST(:ds_id AS uuid)
                )
            """), params)
        else:
            db.execute(text("TRUNCATE TABLE analytics.program_refunds_summary"))

        insert_sql = f"""
            INSERT INTO analytics.program_refunds_summary (
                academic_year,
                campus_name,
                program_code,
                source,
                lead_type,
                refund_month,
                refund_count
            )
            SELECT 
                COALESCE(d.academic_year, 2026),
                COALESCE(NULLIF(TRIM(r.raw_data->>'mx_Campus'), ''), d.campus_name, 'Mohali'),
                COALESCE(NULLIF(TRIM(r.raw_data->>'Program Code'), ''), NULLIF(TRIM(r.raw_data->>'ProgramCode'), ''), 'OTHER'),
                COALESCE(NULLIF(TRIM(r.raw_data->>'Source'), ''), NULLIF(TRIM(r.raw_data->>'Origin'), ''), 'Direct'),
                r.raw_data->>'ProspectStage',
                system.parse_month(COALESCE(NULLIF(TRIM(r.raw_data->>'mx_Refund_Initiated_On'), ''), NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), ''), NULLIF(TRIM(r.raw_data->>'CreatedOn'), ''))),
                COUNT(*)
            FROM staging.records r
            JOIN system.datasets d ON d.id = r.dataset_id
            WHERE LOWER(TRIM(r.raw_data->>'ProspectStage')) = 'enrolled'
              AND LOWER(TRIM(COALESCE(r.raw_data->>'mx_Refund_Status', ''))) = 'pending'
              {ds_filter}
            GROUP BY 1, 2, 3, 4, 5, 6
        """
        res = db.execute(text(insert_sql), params)
        db.commit()
        cnt = res.rowcount if hasattr(res, "rowcount") else 0
        logger.info("Refreshed program refunds summary: %s rows inserted", cnt)
        return cnt
    except Exception as e:
        logger.warning("Error refreshing program refunds summary: %s", e)
        db.rollback()
        return 0


def refresh_gender_agg_scoped(
    db: Session,
    dataset_id: Optional[str] = None,
) -> dict:
    """Refresh gender_monthly_agg for a specific dataset scope only.

    Populates analytics.gender_monthly_agg from staging.records once during ingestion
    using the exact business definition:
    - Admission: mx_AdmissionDate valid and not null
    - Identity: ProspectID
    - Discovered gender: INITCAP(mx_Gender_New) or 'Unspecified'
    - Discovered month: system.parse_month(mx_AdmissionDate)

    Zero runtime table scans of staging.records are required thereafter.
    """
    t0 = time.perf_counter()
    if dataset_id is None:
        return backfill_gender_agg(db)

    ds_id_str = str(dataset_id)

    # Step 1: Delete existing aggregates for this dataset
    del_res = db.execute(
        text("DELETE FROM analytics.gender_monthly_agg WHERE dataset_id = CAST(:ds_id AS uuid)"),
        {"ds_id": ds_id_str},
    )
    deleted_rows = del_res.rowcount

    # Step 2: Verify dataset is analytics-enabled
    ds_row = db.execute(
        text("SELECT is_analytics_enabled, academic_year, campus_name FROM system.datasets WHERE id = CAST(:ds_id AS uuid)"),
        {"ds_id": ds_id_str},
    ).mappings().first()

    inserted_rows = 0
    if ds_row:
        insert_sql = text("""
            INSERT INTO analytics.gender_monthly_agg (
                dataset_id,
                academic_year,
                campus_name,
                admission_month,
                gender,
                admissions,
                created_at,
                updated_at
            )
            SELECT 
                r.dataset_id,
                COALESCE(d.academic_year, d.period_end_year, EXTRACT(YEAR FROM CURRENT_DATE)::int) AS academic_year,
                COALESCE(NULLIF(TRIM(r.raw_data->>'mx_Campus'), ''), d.campus_name, 'All') AS campus_name,
                system.parse_month(NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '')) AS admission_month,
                COALESCE(NULLIF(INITCAP(TRIM(r.raw_data->>'mx_Gender_New')), ''), 'Unspecified') AS gender,
                COUNT(DISTINCT r.raw_data->>'ProspectID') AS admissions,
                NOW(),
                NOW()
            FROM staging.records r
            INNER JOIN system.datasets d ON d.id = r.dataset_id
            WHERE r.dataset_id = CAST(:ds_id AS uuid)
              AND NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL
              AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null'
              AND TRIM(r.raw_data->>'mx_AdmissionDate') != ''
              AND system.parse_month(NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '')) IS NOT NULL
            GROUP BY 1, 2, 3, 4, 5
            ON CONFLICT (dataset_id, academic_year, campus_name, admission_month, gender)
            DO UPDATE SET 
                admissions = EXCLUDED.admissions,
                updated_at = NOW();
        """)
        ins_res = db.execute(insert_sql, {"ds_id": ds_id_str})
        inserted_rows = ins_res.rowcount or 0

    db.commit()
    t_total = time.perf_counter()
    duration_ms = round((t_total - t0) * 1000, 2)
    logger.info("[SCOPED GENDER AGG] dataset=%s deleted=%d inserted=%d total_ms=%.2f", ds_id_str, deleted_rows, inserted_rows, duration_ms)

    return {
        "dataset_id": ds_id_str,
        "deleted_rows": deleted_rows,
        "inserted_rows": inserted_rows,
        "total_ms": duration_ms,
    }


def delete_gender_agg_for_dataset(db: Session, dataset_id: str) -> int:
    """Deletes gender aggregated rows belonging to a specific dataset."""
    ds_id_str = str(dataset_id)
    result = db.execute(
        text("DELETE FROM analytics.gender_monthly_agg WHERE dataset_id = CAST(:ds_id AS uuid)"),
        {"ds_id": ds_id_str},
    )
    deleted = result.rowcount
    db.commit()
    logger.info("[GENDER AGG DELETE] Removed %d rows for dataset %s", deleted, ds_id_str)
    return deleted


def backfill_gender_agg(db: Session, dataset_id: Optional[str] = None) -> dict:
    """Safely backfills analytics.gender_monthly_agg for existing datasets.

    Can be run out-of-band without re-uploading the RAW dataset.
    """
    t0 = time.perf_counter()
    if dataset_id:
        target_ids = [str(dataset_id)]
    else:
        rows = db.execute(
            text("""
                SELECT id 
                FROM system.datasets 
                WHERE is_analytics_enabled = TRUE 
                  AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                  AND status NOT IN ('failed', 'initiated')
                ORDER BY created_at ASC
            """)
        ).scalars().all()
        target_ids = [str(r) for r in rows]

    total_inserted = 0
    results = []
    for ds_id in target_ids:
        try:
            existing = db.execute(
                text("SELECT COUNT(*) FROM analytics.gender_monthly_agg WHERE dataset_id = CAST(:ds_id AS uuid)"),
                {"ds_id": ds_id}
            ).scalar() or 0
            if existing == 0:
                res = refresh_gender_agg_scoped(db, dataset_id=ds_id)
                total_inserted += res.get("inserted_rows", 0)
                results.append(res)
        except Exception as e:
            logger.warning("Backfill failed for dataset %s: %s", ds_id, e)
            db.rollback()

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    logger.info("[BACKFILL GENDER AGG] Processed %d datasets, %d rows in %.2f ms", len(target_ids), total_inserted, duration_ms)
    return {
        "datasets_processed": len(target_ids),
        "total_inserted": total_inserted,
        "duration_ms": duration_ms,
        "details": results,
    }


def backfill_dashboard_agg(db: Session, dataset_id: Optional[str] = None, target_year: Optional[int] = None) -> dict:
    """Safely backfills analytics.dashboard_agg for existing datasets if missing or incomplete."""
    t0 = time.perf_counter()
    if dataset_id:
        target_ids = [str(dataset_id)]
    else:
        query = """
            SELECT id FROM system.datasets 
            WHERE is_analytics_enabled = TRUE 
              AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
              AND status NOT IN ('failed', 'initiated')
              AND COALESCE(row_count, 0) > 0
        """
        params: dict = {}
        if target_year:
            query += " AND academic_year = :yr"
            params["yr"] = target_year
        query += " ORDER BY academic_year DESC, created_at DESC"
        rows = db.execute(text(query), params).scalars().all()
        target_ids = [str(r) for r in rows]

    total_inserted = 0
    results = []
    for ds_id in target_ids:
        try:
            # Check if this dataset already has aggregate rows
            existing = db.execute(
                text("SELECT COUNT(*) FROM analytics.dashboard_agg WHERE dataset_id = :ds_id"),
                {"ds_id": ds_id}
            ).scalar() or 0
            if existing == 0:
                res = refresh_dashboard_agg_scoped(db, dataset_id=ds_id)
                total_inserted += res.get("inserted_rows", 0)
                results.append(res)
        except Exception as e:
            logger.warning("Dashboard aggregate backfill failed for dataset %s: %s", ds_id, e)
            db.rollback()

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    logger.info("[BACKFILL DASHBOARD AGG] Processed %d datasets, %d rows in %.2f ms", len(target_ids), total_inserted, duration_ms)
    return {
        "datasets_checked": len(target_ids),
        "total_inserted": total_inserted,
        "duration_ms": duration_ms,
        "details": results,
    }


def ensure_aggregates_populated(db: Session) -> dict:
    """Startup and runtime self-healing routine for all analytics aggregates.
    1. Syncs missing academic_year and campus_name in analytics.uploaded_metrics from system.datasets.
    2. Ensures dashboard_agg is populated for all enabled RAW datasets.
    3. Ensures gender_monthly_agg is populated for all enabled RAW datasets.
    """
    t0 = time.perf_counter()
    try:
        # Step 1: Sync missing metadata in uploaded_metrics
        db.execute(text("""
            UPDATE analytics.uploaded_metrics um
            SET academic_year = sd.academic_year
            FROM system.datasets sd
            WHERE um.dataset_id = sd.id
              AND um.academic_year IS NULL
              AND sd.academic_year IS NOT NULL;
        """))
        db.execute(text("""
            UPDATE analytics.uploaded_metrics um
            SET campus_name = sd.campus_name
            FROM system.datasets sd
            WHERE um.dataset_id = sd.id
              AND (um.campus_name IS NULL OR um.campus_name = '')
              AND sd.campus_name IS NOT NULL;
        """))
        db.commit()
    except Exception as e:
        logger.warning("Syncing uploaded_metrics metadata notice: %s", e)
        db.rollback()

    # Step 2: Backfill dashboard_agg where missing
    dash_res = backfill_dashboard_agg(db)

    # Step 3: Backfill gender_monthly_agg where missing
    gender_res = backfill_gender_agg(db)

    # Step 4: Ensure program_refunds_summary is populated
    try:
        ref_cnt = db.execute(text("SELECT COUNT(*) FROM analytics.program_refunds_summary")).scalar() or 0
        if ref_cnt == 0:
            refresh_program_refunds(db)
    except Exception as e:
        logger.warning("Refunds summary check notice: %s", e)
        db.rollback()

    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "dashboard_agg": dash_res,
        "gender_agg": gender_res,
        "total_duration_ms": duration_ms,
    }


