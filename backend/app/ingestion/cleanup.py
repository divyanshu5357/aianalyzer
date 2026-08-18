import logging
from typing import Any, Dict, List
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern used to identify test / benchmark / synthetic datasets
# ---------------------------------------------------------------------------

_TEST_DATASET_SQL_FILTER = """
    (
        dataset_name LIKE 'Bench_%'
        OR dataset_name LIKE 'benchmark_%'
        OR dataset_name ILIKE 'test_%'
        OR dataset_name ILIKE 'synthetic_%'
        OR original_filename LIKE 'benchmark_%.csv'
        OR original_filename ILIKE 'test_%.csv'
        OR original_filename ILIKE 'synthetic_%.csv'
    )
"""


def get_benchmark_datasets_summary(db: Session) -> Dict[str, Any]:
    """
    Identify test / benchmark / synthetic datasets.

    Excludes any dataset currently marked as active (is_active = TRUE).
    Returns list of candidate datasets and total row/storage summary.
    """
    active_dataset_id = db.execute(
        text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")
    ).scalar()

    query = text(f"""
        SELECT id, dataset_name, original_filename, row_count,
               is_active, status, created_at
        FROM system.datasets
        WHERE {_TEST_DATASET_SQL_FILTER}
        ORDER BY created_at DESC
    """)

    rows = db.execute(query).mappings().all()

    candidates = []
    total_rows = 0

    for r in rows:
        ds_id = str(r["id"])
        is_active = bool(r["is_active"]) or (ds_id == str(active_dataset_id))

        if not is_active:
            candidates.append({
                "id": ds_id,
                "dataset_name": r["dataset_name"],
                "original_filename": r["original_filename"],
                "row_count": r["row_count"],
                "status": r["status"],
                "created_at": str(r["created_at"])
            })
            total_rows += (r["row_count"] or 0)

    return {
        "candidate_count": len(candidates),
        "total_rows": total_rows,
        "active_dataset_id": str(active_dataset_id) if active_dataset_id else None,
        "candidates": candidates
    }


def delete_dataset_cascade(db: Session, dataset_ids: list[str]) -> Dict[str, int]:
    """
    Delete all dependent data for a list of dataset IDs.
    Returns counts of deleted rows per table.
    """
    if not dataset_ids:
        return {"staging": 0, "analytics": 0, "datasets": 0}

    staging_deleted = 0
    analytics_deleted = 0

    for ds_id in dataset_ids:
        staging_deleted += db.execute(
            text("DELETE FROM staging.records WHERE dataset_id = :ds_id"),
            {"ds_id": ds_id},
        ).rowcount

        analytics_deleted += db.execute(
            text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
            {"ds_id": ds_id},
        ).rowcount

        db.execute(
            text("DELETE FROM intelligence.column_mappings WHERE dataset_id = :ds_id"),
            {"ds_id": ds_id},
        )

        db.execute(
            text("DELETE FROM system.data_quality_reports WHERE dataset_id = :ds_id"),
            {"ds_id": ds_id},
        )

    # Invalidate conversation contexts tied to deleted datasets
    for ds_id in dataset_ids:
        try:
            db.execute(
                text("DELETE FROM system.conversation_context WHERE dataset_id = :ds_id"),
                {"ds_id": ds_id},
            )
        except Exception:
            pass

    datasets_deleted = 0
    for ds_id in dataset_ids:
        datasets_deleted += db.execute(
            text("DELETE FROM system.datasets WHERE id = :ds_id"),
            {"ds_id": ds_id},
        ).rowcount

    return {
        "staging": staging_deleted,
        "analytics": analytics_deleted,
        "datasets": datasets_deleted,
    }


# Keep backward-compatible private alias
_delete_dataset_cascade = delete_dataset_cascade


def cleanup_benchmark_datasets(db: Session, dry_run: bool = False) -> Dict[str, Any]:
    """
    Safe development cleanup for old benchmark/test/synthetic datasets.
    Deletes staging, analytics, mappings, quality reports, and dataset records.
    NEVER deletes the active dataset or real user uploads.
    """
    summary = get_benchmark_datasets_summary(db)
    candidates = summary["candidates"]

    if not candidates or dry_run:
        return {
            "status": "dry_run" if dry_run else "no_op",
            "deleted_datasets": 0,
            "deleted_staging_rows": 0,
            "deleted_analytics_rows": 0,
            "candidates_summary": summary
        }

    dataset_ids = [c["id"] for c in candidates]
    counts = _delete_dataset_cascade(db, dataset_ids)

    # Also clean up unreferenced data sources created during benchmarks
    db.execute(
        text("""
            DELETE FROM system.data_sources
            WHERE id NOT IN (
                SELECT DISTINCT source_id
                FROM system.datasets
                WHERE source_id IS NOT NULL
            )
              AND (
                  source_name LIKE 'Bench_%'
                  OR source_name LIKE 'benchmark_%'
                  OR source_name ILIKE 'test_%'
                  OR source_name ILIKE 'synthetic_%'
              )
        """)
    )

    # Invalidate conversation contexts tied to deleted datasets
    for ds_id in dataset_ids:
        db.execute(
            text("DELETE FROM system.conversation_context WHERE dataset_id = :ds_id"),
            {"ds_id": ds_id},
        )

    db.commit()

    logger.info(
        "Cleaned up %d benchmark datasets (%d staging rows, %d analytics rows).",
        counts["datasets"], counts["staging"], counts["analytics"],
    )

    return {
        "status": "success",
        "deleted_datasets": counts["datasets"],
        "deleted_staging_rows": counts["staging"],
        "deleted_analytics_rows": counts["analytics"],
    }


def reset_all_uploaded_data(db: Session) -> Dict[str, Any]:
    """
    ⚠️ DESTRUCTIVE: Delete ALL uploaded datasets, staging, analytics, and
    conversation data.  Preserves the database schema/tables themselves.

    Must only be called when ALLOW_DATA_RESET=true AND the caller has validated
    the user confirmation phrase.
    """
    # Gather ALL dataset IDs
    rows = db.execute(
        text("SELECT id FROM system.datasets")
    ).mappings().all()
    dataset_ids = [str(r["id"]) for r in rows]

    if not dataset_ids:
        return {"status": "no_op", "deleted_datasets": 0}

    counts = _delete_dataset_cascade(db, dataset_ids)

    # Clean data sources
    db.execute(text("DELETE FROM system.data_sources"))

    # Clean conversations
    try:
        db.execute(text("DELETE FROM system.conversation_context"))
        db.execute(text("DELETE FROM system.conversation_messages"))
        db.execute(text("DELETE FROM system.conversations"))
    except Exception as exc:
        logger.warning("Error clearing conversations during reset: %s", exc)

    db.commit()

    logger.warning(
        "FULL DATA RESET: deleted %d datasets, %d staging rows, %d analytics rows.",
        counts["datasets"], counts["staging"], counts["analytics"],
    )

    return {
        "status": "success",
        "deleted_datasets": counts["datasets"],
        "deleted_staging_rows": counts["staging"],
        "deleted_analytics_rows": counts["analytics"],
    }


def cleanup_staging_for_dataset(db: Session, dataset_id: Any) -> Dict[str, Any]:
    """
    Safely remove staging.records for a dataset ONLY after normalization and validation succeed.
    Verifies:
    1. Dataset exists in system.datasets
    2. Analytics row count matches expected dataset row count
    3. Dataset is not currently processing
    4. Dataset status moves to 'staging_cleared'
    Never removes analytics.uploaded_metrics or active dataset analytics data.
    """
    ds_id_str = str(dataset_id)
    dataset = db.execute(
        text("SELECT id, row_count, status, is_active FROM system.datasets WHERE id = :ds_id"),
        {"ds_id": ds_id_str}
    ).mappings().first()

    if not dataset:
        return {"success": False, "reason": f"Dataset {ds_id_str} not found."}

    expected_rows = dataset["row_count"] or 0

    # Verify analytics metrics row count
    analytics_cnt = db.execute(
        text("SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id_str}
    ).scalar() or 0

    if expected_rows > 0 and analytics_cnt < expected_rows:
        return {
            "success": False,
            "reason": f"Normalization incomplete. Expected {expected_rows} rows in analytics, found {analytics_cnt}."
        }

    # Delete staging records for this dataset
    deleted_staging = db.execute(
        text("DELETE FROM staging.records WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id_str}
    ).rowcount

    # Update dataset status
    db.execute(
        text("UPDATE system.datasets SET status = 'staging_cleared' WHERE id = :ds_id"),
        {"ds_id": ds_id_str}
    )

    db.commit()

    return {
        "success": True,
        "dataset_id": ds_id_str,
        "deleted_staging_rows": deleted_staging,
        "analytics_rows_preserved": analytics_cnt,
        "status": "staging_cleared"
    }
