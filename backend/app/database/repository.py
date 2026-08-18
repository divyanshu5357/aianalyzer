import json
import re

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
    Mark a dataset as active in the database while setting all other datasets inactive.
    Resets stale conversation context to guarantee dataset isolation.

    Raises ValueError if the dataset is a benchmark/test dataset and
    allow_benchmark is not explicitly True.
    """
    if not allow_benchmark:
        row = db.execute(
            text("SELECT dataset_name FROM system.datasets WHERE id = :id"),
            {"id": str(dataset_id)},
        ).mappings().first()
        if row and is_benchmark_dataset(row["dataset_name"]):
            raise ValueError(
                f"Refusing to activate benchmark dataset '{row['dataset_name']}'. "
                "Pass allow_benchmark=True to override."
            )

    db.execute(text("UPDATE system.datasets SET is_active = FALSE WHERE is_active = TRUE"))
    db.execute(
        text("UPDATE system.datasets SET is_active = TRUE WHERE id = :dataset_id"),
        {"dataset_id": dataset_id},
    )
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

    Returns None if no dataset is explicitly marked active.
    Does NOT silently promote the latest dataset — callers must handle None.
    """
    return db.execute(
        text(
            """
            SELECT id
            FROM system.datasets
            WHERE is_active = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()


def get_active_dataset_info(db: Session):
    """
    Retrieve full metadata for the active dataset.

    Returns None if no dataset is explicitly marked active.
    Does NOT fall back to the latest dataset.
    """
    row = db.execute(
        text(
            """
            SELECT d.id, d.dataset_name, d.original_filename, d.row_count,
                   d.column_count, d.status, d.created_at,
                   d.academic_label, d.upload_version, d.is_period_active,
                   q.quality_score
            FROM system.datasets d
            LEFT JOIN system.data_quality_reports q ON q.dataset_id = d.id
            WHERE d.is_active = TRUE
            ORDER BY d.created_at DESC
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
        "academic_label": row.get("academic_label"),
        "upload_version": row.get("upload_version"),
    }


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
) -> None:
    """
    Write period metadata onto an existing dataset row.
    Called immediately after period detection/confirmation during upload.
    """
    db.execute(
        text(
            """
            UPDATE system.datasets
            SET
                period_start_year = :start_year,
                period_end_year   = :end_year,
                academic_label    = :label,
                upload_version    = :version
            WHERE id = :dataset_id
            """
        ),
        {
            "start_year": period_start_year,
            "end_year": period_end_year,
            "label": academic_label,
            "version": upload_version,
            "dataset_id": str(dataset_id),
        },
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