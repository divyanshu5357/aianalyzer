import json
import re
from typing import Any, Optional, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Benchmark / test dataset detection
# ---------------------------------------------------------------------------

_BENCHMARK_PATTERNS = re.compile(
    r"^(Bench_|benchmark_|test_|synthetic_)", re.IGNORECASE
)


def is_benchmark_dataset(name: str | None) -> bool:
    """Return True if *name* looks like a test/benchmark dataset."""
    if not name:
        return False
    return bool(_BENCHMARK_PATTERNS.search(name))


def create_data_source(
    db: Session,
    source_name: str,
    source_type: str,
    description: str | None = None,
):
    query = text(
        """
        INSERT INTO system.data_sources
        (
            source_name,
            source_type,
            description
        )
        VALUES
        (
            :source_name,
            :source_type,
            :description
        )
        RETURNING id
        """
    )

    result = db.execute(
        query,
        {
            "source_name": source_name,
            "source_type": source_type,
            "description": description,
        },
    )

    return result.scalar_one()


def create_dataset(
    db: Session,
    dataset_id,
    source_id,
    dataset_name: str,
    original_filename: str,
    dataset_type: str,
    row_count: int,
    column_count: int,
    status: str = "profiled",
    file_checksum: str | None = None,
):
    query = text(
        """
        INSERT INTO system.datasets
        (
            id,
            source_id,
            dataset_name,
            original_filename,
            dataset_type,
            row_count,
            column_count,
            status,
            file_checksum
        )
        VALUES
        (
            :id,
            :source_id,
            :dataset_name,
            :original_filename,
            :dataset_type,
            :row_count,
            :column_count,
            :status,
            :file_checksum
        )
        RETURNING id
        """
    )

    result = db.execute(
        query,
        {
            "id": dataset_id,
            "source_id": source_id,
            "dataset_name": dataset_name,
            "original_filename": original_filename,
            "dataset_type": dataset_type,
            "row_count": row_count,
            "column_count": column_count,
            "status": status,
            "file_checksum": file_checksum,
        },
    )

    return result.scalar_one()


def create_quality_report(
    db: Session,
    dataset_id,
    profile: dict,
):
    query = text(
        """
        INSERT INTO system.data_quality_reports
        (
            dataset_id,
            total_rows,
            total_columns,
            missing_values,
            duplicate_rows,
            invalid_values,
            quality_score,
            report
        )
        VALUES
        (
            :dataset_id,
            :total_rows,
            :total_columns,
            :missing_values,
            :duplicate_rows,
            :invalid_values,
            :quality_score,
            CAST(:report AS JSONB)
        )
        RETURNING id
        """
    )

    result = db.execute(
        query,
        {
            "dataset_id": dataset_id,
            "total_rows": profile["rows"],
            "total_columns": profile["columns"],
            "missing_values": profile["missing_values"],
            "duplicate_rows": profile["duplicate_rows"],
            "invalid_values": 0,
            "quality_score": profile["quality_score"],
            "report": json.dumps(profile),
        },
    )

    return result.scalar_one()


def set_active_dataset(db: Session, dataset_id, *, allow_benchmark: bool = False) -> None:
    """
    Mark a dataset as active in the database while maintaining scope isolation.
    Only deactivates prior datasets matching the SAME (academic_year, campus_name, workbook_type) scope.
    Preserves active/enabled status of datasets for other academic years or categories.
    """
    target = db.execute(
        text("SELECT id, dataset_name, academic_year, campus_name, workbook_type FROM system.datasets WHERE id = :id"),
        {"id": str(dataset_id)},
    ).mappings().first()

    if not target:
        return

    if not allow_benchmark and is_benchmark_dataset(target["dataset_name"] or ""):
        raise ValueError(
            f"Refusing to activate benchmark dataset '{target['dataset_name']}'. "
            "Pass allow_benchmark=True to override."
        )

    wb_type = str(target.get("workbook_type") or "RAW").upper()
    year = target.get("academic_year")
    campus = target.get("campus_name")

    # Deactivate ONLY datasets matching the same scope
    if wb_type == "RAW" and year:
        db.execute(
            text("""
                UPDATE system.datasets
                SET is_active = FALSE, is_analytics_enabled = FALSE
                WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                  AND academic_year = :yr
                  AND (LOWER(COALESCE(campus_name, '')) = LOWER(COALESCE(:cmp, '')) OR (:cmp IS NULL AND campus_name IS NULL))
                  AND id != :ds_id
            """),
            {"yr": year, "cmp": campus, "ds_id": str(dataset_id)},
        )
    else:
        db.execute(
            text("""
                UPDATE system.datasets
                SET is_active = FALSE, is_analytics_enabled = FALSE
                WHERE UPPER(COALESCE(workbook_type, 'RAW')) = :wb_type
                  AND id != :ds_id
            """),
            {"wb_type": wb_type, "ds_id": str(dataset_id)},
        )

    db.execute(
        text("UPDATE system.datasets SET is_active = TRUE, is_analytics_enabled = TRUE WHERE id = :dataset_id"),
        {"dataset_id": str(dataset_id)},
    )
    db.commit()

    try:
        db.execute(
            text(
                "DELETE FROM system.conversation_context "
                "WHERE dataset_id != :ds_id OR dataset_id IS NULL"
            ),
            {"ds_id": str(dataset_id)},
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to clear stale conversation context: %s", exc
        )



def get_active_dataset(db: Session):
    """
    Retrieve the active dataset ID from system.datasets.
    Restricted strictly to active/enabled RAW workbooks.
    Returns None if no raw dataset is explicitly active or enabled.
    """
    return db.execute(
        text(
            """
            SELECT id
            FROM system.datasets
            WHERE (is_active = TRUE OR is_analytics_enabled = TRUE) AND workbook_type = 'RAW'
            ORDER BY is_active DESC, is_analytics_enabled DESC, created_at DESC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()


def get_active_dataset_info(db: Session):
    """
    Retrieve full metadata for the primary enabled active RAW dataset.
    Falls back to any enabled RAW dataset if none explicitly active.
    """
    row = db.execute(
        text(
            """
            SELECT d.id, d.dataset_name, d.original_filename, d.row_count,
                   d.column_count, d.status, d.created_at,
                   d.academic_label, d.upload_version, d.is_period_active,
                   d.academic_year, d.campus_name, d.is_analytics_enabled,
                   q.quality_score
            FROM system.datasets d
            LEFT JOIN system.data_quality_reports q ON q.dataset_id = d.id
            WHERE (d.is_analytics_enabled = TRUE OR d.is_active = TRUE)
              AND UPPER(COALESCE(d.workbook_type, 'RAW')) = 'RAW'
            ORDER BY d.is_active DESC, d.is_analytics_enabled DESC, d.created_at DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    if not row:
        return None

    return {
        "id": str(row["id"]),
        "dataset_name": row["dataset_name"],
        "original_filename": row["original_filename"],
        "row_count": row["row_count"],
        "column_count": row["column_count"],
        "status": row["status"],
        "created_at": str(row["created_at"]),
        "quality_score": float(row["quality_score"]) if row["quality_score"] is not None else None,
        "academic_label": str(row.get("academic_year")) if row.get("academic_year") else row.get("academic_label"),
        "academic_year": row.get("academic_year"),
        "campus_name": row.get("campus_name"),
        "is_analytics_enabled": bool(row.get("is_analytics_enabled")),
        "upload_version": row.get("upload_version"),
    }


def resolve_raw_dataset(
    db: Session,
    target_year: int | None = None,
    default_dataset: Any = None,
) -> tuple[Any, int, int]:
    """
    Dedicated RAW dataset resolver for actual leads, admissions, and conversion metrics.
    Guarantees that DIMENSION and TARGET datasets are NEVER selected as RAW datasets.
    """
    from datetime import datetime
    from app.agent.agent_service import get_active_dataset_years
    if target_year:
        ds_row = db.execute(
            text("""
                SELECT id, academic_year
                FROM system.datasets
                WHERE is_analytics_enabled = TRUE 
                  AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW' 
                  AND academic_year = :yr
                ORDER BY is_active DESC, created_at DESC
                LIMIT 1
            """),
            {"yr": target_year}
        ).mappings().first()
        if ds_row:
            ds_id = str(ds_row["id"])
            cy_yr = ds_row["academic_year"]
            py_yr = cy_yr - 1
            return ds_id, cy_yr, py_yr

    raw_id = get_active_dataset(db) or (str(default_dataset) if default_dataset else None)
    if raw_id:
        cy_yr, py_yr = get_active_dataset_years(db, raw_id)
        return str(raw_id), cy_yr, py_yr

    return None, datetime.now().year, datetime.now().year - 1


def resolve_target_dataset(db: Session) -> str | None:
    """
    Dedicated TARGET dataset resolver for shared target files across sheets (Source, Program, State).
    Restricted strictly to TARGET workbooks.
    """
    target_id = db.execute(
        text("""
            SELECT d.id
            FROM system.datasets d
            WHERE UPPER(COALESCE(d.workbook_type, '')) = 'TARGET'
              AND (d.is_active = TRUE OR d.is_analytics_enabled = TRUE)
            ORDER BY d.row_count DESC, d.is_active DESC, d.is_analytics_enabled DESC, d.created_at DESC
            LIMIT 1
        """)
    ).scalar_one_or_none()
    return str(target_id) if target_id else None


def resolve_dimension_dataset(db: Session) -> str | None:
    """
    Dedicated DIMENSION dataset resolver for shared master reference tables (Source_ms, Program, State).
    Restricted strictly to DIMENSION workbooks.
    """
    dim_id = db.execute(
        text("""
            SELECT id
            FROM system.datasets
            WHERE UPPER(COALESCE(workbook_type, '')) = 'DIMENSION'
              AND (is_active = TRUE OR is_analytics_enabled = TRUE)
            ORDER BY is_active DESC, is_analytics_enabled DESC, created_at DESC
            LIMIT 1
        """)
    ).scalar_one_or_none()
    return str(dim_id) if dim_id else None


def enable_dataset_analytics(db: Session, dataset_id, force: bool = False) -> dict:
    """
    Enable analytics for a dataset.
    TARGET/DIMENSION: strictly single active master file.
    RAW: scoped by (academic_year, campus_name). Multiple academic years/campuses coexist.
    """
    target = db.execute(
        text("SELECT id, academic_year, campus_name, dataset_name, workbook_type FROM system.datasets WHERE id = :id"),
        {"id": str(dataset_id)},
    ).mappings().first()

    if not target:
        raise ValueError(f"Dataset {dataset_id} not found")

    wb_type = str(target.get("workbook_type") or "RAW").upper()
    year = target.get("academic_year")
    campus = target.get("campus_name")

    if wb_type in ("TARGET", "DIMENSION"):
        conflict = db.execute(
            text("""
                SELECT id, dataset_name FROM system.datasets
                WHERE UPPER(COALESCE(workbook_type, 'RAW')) = :wb_type
                  AND is_analytics_enabled = TRUE AND id != :id
            """),
            {"wb_type": wb_type, "id": str(dataset_id)},
        ).mappings().first()

        if conflict:
            if not force:
                return {
                    "success": False,
                    "warning": True,
                    "conflict_id": str(conflict["id"]),
                    "conflict_name": conflict["dataset_name"],
                    "message": f"An active {wb_type} master ('{conflict['dataset_name']}') already exists. This upload will replace it after successful validation.",
                }
            else:
                db.execute(
                    text("""
                        UPDATE system.datasets
                        SET is_analytics_enabled = FALSE, is_active = FALSE
                        WHERE UPPER(COALESCE(workbook_type, 'RAW')) = :wb_type
                          AND id != :id
                    """),
                    {"wb_type": wb_type, "id": str(dataset_id)},
                )
    elif year and campus and not force:
        conflict = db.execute(
            text("""
                SELECT id, dataset_name FROM system.datasets
                WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                  AND academic_year = :yr AND LOWER(COALESCE(campus_name, '')) = LOWER(COALESCE(:cmp, ''))
                  AND is_analytics_enabled = TRUE AND id != :id
            """),
            {"yr": year, "cmp": campus, "id": str(dataset_id)},
        ).mappings().first()

        if conflict:
            return {
                "success": False,
                "warning": True,
                "conflict_id": str(conflict["id"]),
                "conflict_name": conflict["dataset_name"],
                "message": f"Another enabled dataset ('{conflict['dataset_name']}') already exists for {campus} {year}.",
            }
    elif year and campus and force:
        db.execute(
            text("""
                UPDATE system.datasets
                SET is_analytics_enabled = FALSE, is_active = FALSE
                WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                  AND academic_year = :yr AND LOWER(COALESCE(campus_name, '')) = LOWER(COALESCE(:cmp, ''))
                  AND id != :id
            """),
            {"yr": year, "cmp": campus, "id": str(dataset_id)},
        )

    db.execute(
        text("UPDATE system.datasets SET is_analytics_enabled = TRUE, is_active = TRUE WHERE id = :id"),
        {"id": str(dataset_id)},
    )
    db.commit()
    # Refresh dashboard_agg for this dataset scope only
    try:
        from app.analytics.aggregate_refresh import refresh_dashboard_agg_scoped
        refresh_dashboard_agg_scoped(db, dataset_id=str(dataset_id))
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("dashboard_agg scoped refresh after enable failed: %s", _e)
    return {"success": True, "dataset_id": str(dataset_id), "is_analytics_enabled": True}


def disable_dataset_analytics(db: Session, dataset_id) -> dict:
    """Disable analytics for a dataset without deleting or modifying raw records."""
    db.execute(
        text("UPDATE system.datasets SET is_analytics_enabled = FALSE WHERE id = :id"),
        {"id": str(dataset_id)},
    )
    db.commit()
    # Remove aggregate rows for this dataset only (no reinsertion needed)
    try:
        from app.analytics.aggregate_refresh import delete_dashboard_agg_for_dataset
        delete_dashboard_agg_for_dataset(db, str(dataset_id))
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("dashboard_agg scoped delete after disable failed: %s", _e)
    return {"success": True, "dataset_id": str(dataset_id), "is_analytics_enabled": False}


def update_dataset_metadata(
    db: Session,
    dataset_id,
    academic_year: int,
    campus_name: str,
    dataset_name: str | None = None,
    workbook_type: str | None = None,
) -> dict:
    """
    Update dataset academic_year, campus_name, dataset_name, and workbook_type metadata.
    Updates system.datasets and analytics.uploaded_metrics metadata without touching metric rows.
    """
    params = {
        "id": str(dataset_id),
        "year": int(academic_year),
        "campus": str(campus_name).strip(),
        "label": str(academic_year),
    }

    extra_sql = ""
    if dataset_name:
        extra_sql += ", dataset_name = :dname"
        params["dname"] = str(dataset_name).strip()

    if workbook_type:
        wb_upper = str(workbook_type).strip().upper()
        if wb_upper in ("RAW", "DIMENSION", "TARGET"):
            extra_sql += ", workbook_type = :wb_type"
            params["wb_type"] = wb_upper

    db.execute(
        text(f"""
            UPDATE system.datasets
            SET academic_year = :year,
                campus_name = :campus,
                academic_label = :label
                {extra_sql}
            WHERE id = :id
        """),
        params,
    )

    db.execute(
        text("""
            UPDATE analytics.uploaded_metrics
            SET academic_year = :year,
                campus_name = :campus
            WHERE dataset_id = :id
        """),
        {"year": int(academic_year), "campus": str(campus_name).strip(), "id": str(dataset_id)},
    )

    db.commit()
    return {
        "success": True,
        "dataset_id": str(dataset_id),
        "academic_year": academic_year,
        "campus_name": campus_name,
    }


def get_enabled_datasets(
    db: Session,
    academic_year: int | None = None,
    campus_name: str | None = None,
) -> list[dict]:
    """Retrieve list of enabled datasets filtered by optional year and campus."""
    clauses = ["is_analytics_enabled = TRUE"]
    params = {}

    if academic_year is not None:
        clauses.append("academic_year = :year")
        params["year"] = int(academic_year)

    if campus_name is not None and str(campus_name).lower() not in ("all", "all campuses", ""):
        clauses.append("LOWER(campus_name) = LOWER(:campus)")
        params["campus"] = str(campus_name).strip()

    where_sql = " WHERE " + " AND ".join(clauses)

    rows = db.execute(
        text(f"""
            SELECT id, dataset_name, original_filename, academic_year, campus_name, row_count, status
            FROM system.datasets
            {where_sql}
            ORDER BY academic_year DESC, campus_name ASC
        """),
        params,
    ).mappings().all()

    return [
        {
            "id": str(r["id"]),
            "dataset_name": r["dataset_name"],
            "original_filename": r["original_filename"],
            "academic_year": r["academic_year"],
            "campus_name": r["campus_name"],
            "row_count": r["row_count"],
            "status": r["status"],
        }
        for r in rows
    ]


# ==============================================================================
# Period / Academic-Year Registry
# ==============================================================================

def set_dataset_period(
    db: Session,
    dataset_id,
    period_start_year: int,
    period_end_year: int,
    academic_label: str,
    upload_version: int = 1,
    academic_year: int | None = None,
    campus_name: str | None = None,
) -> None:
    """
    Write period and campus metadata onto an existing dataset row and metrics.
    Called immediately after period detection/confirmation during upload.
    """
    year = academic_year or period_end_year or (int(academic_label) if academic_label and academic_label.isdigit() else None)
    db.execute(
        text(
            """
            UPDATE system.datasets
            SET
                period_start_year = :start_year,
                period_end_year   = :end_year,
                academic_label    = :label,
                academic_year     = :year,
                campus_name       = COALESCE(:campus, campus_name),
                upload_version    = :version
            WHERE id = :dataset_id
            """
        ),
        {
            "start_year": period_start_year,
            "end_year": period_end_year,
            "label": academic_label,
            "year": year,
            "campus": campus_name,
            "version": upload_version,
            "dataset_id": str(dataset_id),
        },
    )
    if year:
        db.execute(
            text(
                """
                UPDATE analytics.uploaded_metrics
                SET academic_year = :year,
                    campus_name = COALESCE(campus_name, :campus)
                WHERE dataset_id = :dataset_id
                """
            ),
            {"year": year, "campus": campus_name, "dataset_id": str(dataset_id)},
        )


def set_period_active(db: Session, dataset_id) -> None:
    """
    Activate this dataset as the is_period_active version for its academic_label.
    Deactivates all other datasets with the same label first.
    Also sets global is_active=TRUE and clears stale conversation context.
    """
    # Fetch the academic_label for this dataset
    row = db.execute(
        text("SELECT academic_label FROM system.datasets WHERE id = :id"),
        {"id": str(dataset_id)},
    ).mappings().first()

    if row and row["academic_label"]:
        label = row["academic_label"]
        # Deactivate all other period versions with same label
        db.execute(
            text(
                """
                UPDATE system.datasets
                SET is_period_active = FALSE
                WHERE academic_label = :label AND id != :id
                """
            ),
            {"label": label, "id": str(dataset_id)},
        )

    # Mark this dataset as period-active
    db.execute(
        text(
            "UPDATE system.datasets SET is_period_active = TRUE WHERE id = :id"
        ),
        {"id": str(dataset_id)},
    )

    # Also update global active flag (backward compatibility)
    set_active_dataset(db, dataset_id)


def get_active_period_for_label(db: Session, academic_label: str) -> dict | None:
    """
    Return metadata for the currently active version of a given academic period.
    """
    row = db.execute(
        text(
            """
            SELECT id, dataset_name, original_filename, period_start_year,
                   period_end_year, academic_label, upload_version, created_at
            FROM system.datasets
            WHERE academic_label = :label AND is_period_active = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"label": academic_label},
    ).mappings().first()

    if not row:
        return None

    return {
        "dataset_id": str(row["id"]),
        "dataset_name": row["dataset_name"],
        "original_filename": row["original_filename"],
        "period_start_year": row["period_start_year"],
        "period_end_year": row["period_end_year"],
        "academic_label": row["academic_label"],
        "upload_version": row["upload_version"],
        "created_at": str(row["created_at"]),
    }


def get_datasets_by_period(db: Session, academic_label: str) -> list[dict]:
    """
    Return all versions (active and historical) for a given academic period.
    Ordered newest first.
    """
    rows = db.execute(
        text(
            """
            SELECT id, dataset_name, original_filename, period_start_year,
                   period_end_year, academic_label, upload_version,
                   is_period_active, is_active, status, created_at
            FROM system.datasets
            WHERE academic_label = :label
            ORDER BY upload_version DESC
            """
        ),
        {"label": academic_label},
    ).mappings().all()

    return [
        {
            "dataset_id": str(r["id"]),
            "dataset_name": r["dataset_name"],
            "original_filename": r["original_filename"],
            "period_start_year": r["period_start_year"],
            "period_end_year": r["period_end_year"],
            "academic_label": r["academic_label"],
            "upload_version": r["upload_version"],
            "is_period_active": r["is_period_active"],
            "is_active": r["is_active"],
            "status": r["status"],
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


def list_all_periods(db: Session) -> list[dict]:
    """
    Return a summary of all distinct academic periods available in the system,
    with the active version's metadata for each.
    Ordered by period_end_year DESC (most recent first).
    """
    rows = db.execute(
        text(
            """
            SELECT
                academic_label,
                period_start_year,
                period_end_year,
                MAX(upload_version) AS latest_version,
                COUNT(*) AS total_versions,
                MAX(CASE WHEN is_period_active THEN id::text END) AS active_dataset_id,
                MAX(CASE WHEN is_period_active THEN original_filename END) AS active_filename,
                MAX(CASE WHEN is_period_active THEN created_at::text END) AS active_created_at
            FROM system.datasets
            WHERE academic_label IS NOT NULL
            GROUP BY academic_label, period_start_year, period_end_year
            ORDER BY period_end_year DESC NULLS LAST
            """
        )
    ).mappings().all()

    return [
        {
            "academic_label": r["academic_label"],
            "period_start_year": r["period_start_year"],
            "period_end_year": r["period_end_year"],
            "latest_version": r["latest_version"],
            "total_versions": r["total_versions"],
            "active_dataset_id": r["active_dataset_id"],
            "active_filename": r["active_filename"],
            "active_created_at": r["active_created_at"],
        }
        for r in rows
    ]


def get_period_pair(
    db: Session,
    cy_label: str,
    py_label: str,
) -> tuple[str | None, str | None]:
    """
    Return the active dataset_ids for two named academic periods.
    Used by the comparison workspace for arbitrary period-to-period analysis.

    Returns: (cy_dataset_id, py_dataset_id) — either may be None if not found.
    """
    cy_info = get_active_period_for_label(db, cy_label)
    py_info = get_active_period_for_label(db, py_label)

    cy_id = cy_info["dataset_id"] if cy_info else None
    py_id = py_info["dataset_id"] if py_info else None

    return cy_id, py_id


# ==============================================================================
# Checksum duplicate detection
# ==============================================================================

def find_dataset_by_checksum(db: Session, checksum: str) -> dict | None:
    """
    Look up any existing dataset with `file_checksum == checksum`.
    Returns metadata dict or None.
    """
    row = db.execute(
        text(
            """
            SELECT id, dataset_name, original_filename, row_count,
                   status, academic_label, created_at
            FROM system.datasets
            WHERE file_checksum = :checksum
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"checksum": checksum},
    ).mappings().first()

    if not row:
        return None

    return {
        "dataset_id": str(row["id"]),
        "dataset_name": row["dataset_name"],
        "original_filename": row["original_filename"],
        "row_count": row["row_count"],
        "status": row["status"],
        "academic_label": row["academic_label"],
        "created_at": str(row["created_at"]),
    }