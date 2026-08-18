"""
Admin Data Management API — dataset inventory, benchmark cleanup, full reset.

All destructive endpoints require the ``ALLOW_DATA_RESET`` environment flag to
be ``true``.  The full-reset endpoint additionally requires the caller to send
the exact confirmation phrase ``DELETE ALL UPLOADED DATA``.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.database.repository import (
    get_active_dataset,
    get_active_dataset_info,
    is_benchmark_dataset,
    set_active_dataset,
)
from app.ingestion.cleanup import (
    get_benchmark_datasets_summary,
    cleanup_benchmark_datasets,
    reset_all_uploaded_data,
    delete_dataset_cascade,
)
from app.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_reset_enabled() -> None:
    if not settings.allow_data_reset:
        raise HTTPException(
            status_code=403,
            detail=(
                "Data reset is disabled. Set ALLOW_DATA_RESET=true in "
                "your environment to enable destructive operations."
            ),
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/config")
def get_admin_config() -> dict[str, Any]:
    """Return non-secret admin configuration flags to the frontend."""
    return {
        "allow_data_reset": settings.allow_data_reset,
        "app_env": settings.app_env,
    }


@router.get("/datasets")
def list_all_datasets() -> dict[str, Any]:
    """
    List all datasets with category (production / test / benchmark),
    active status, period info, and row counts.
    """
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT
                    d.id,
                    d.dataset_name,
                    d.original_filename,
                    d.row_count,
                    d.column_count,
                    d.status,
                    d.is_active,
                    d.is_period_active,
                    d.academic_label,
                    d.upload_version,
                    d.file_checksum,
                    d.created_at,
                    q.quality_score
                FROM system.datasets d
                LEFT JOIN system.data_quality_reports q ON q.dataset_id = d.id
                ORDER BY d.created_at DESC
                """
            )
        ).mappings().all()

        datasets = []
        for r in rows:
            name = r["dataset_name"] or ""
            category = "test_benchmark" if is_benchmark_dataset(name) else "production"
            datasets.append(
                {
                    "id": str(r["id"]),
                    "dataset_name": name,
                    "original_filename": r["original_filename"],
                    "row_count": r["row_count"],
                    "column_count": r["column_count"],
                    "status": r["status"],
                    "is_active": bool(r["is_active"]),
                    "is_period_active": bool(r.get("is_period_active")),
                    "academic_label": r.get("academic_label"),
                    "upload_version": r.get("upload_version"),
                    "file_checksum": r.get("file_checksum"),
                    "quality_score": (
                        float(r["quality_score"])
                        if r["quality_score"] is not None
                        else None
                    ),
                    "created_at": str(r["created_at"]),
                    "category": category,
                }
            )

        active_info = get_active_dataset_info(db)
        return {
            "total_datasets": len(datasets),
            "active_dataset": active_info,
            "datasets": datasets,
        }
    finally:
        db.close()


@router.get("/benchmark-summary")
def benchmark_summary() -> dict[str, Any]:
    """Summary of test/benchmark data that can be safely removed."""
    db = SessionLocal()
    try:
        return get_benchmark_datasets_summary(db)
    finally:
        db.close()


class ClearBenchmarkRequest(BaseModel):
    dry_run: bool = True


@router.post("/clear-benchmark")
def clear_benchmark(req: ClearBenchmarkRequest) -> dict[str, Any]:
    """
    Clear test / benchmark / synthetic datasets.  Protected by
    ``ALLOW_DATA_RESET`` env flag.  Never touches the active dataset.
    """
    _require_reset_enabled()

    db = SessionLocal()
    try:
        result = cleanup_benchmark_datasets(db, dry_run=req.dry_run)
        return result
    finally:
        db.close()


class ResetAllRequest(BaseModel):
    confirmation_phrase: str


@router.post("/reset-all")
def reset_all(req: ResetAllRequest) -> dict[str, Any]:
    """
    ⚠️ DESTRUCTIVE: Delete ALL uploaded datasets and all dependent data.

    Requires:
      - ``ALLOW_DATA_RESET=true`` in environment
      - ``confirmation_phrase`` == ``"DELETE ALL UPLOADED DATA"``
    """
    _require_reset_enabled()

    if req.confirmation_phrase != "DELETE ALL UPLOADED DATA":
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid confirmation phrase. "
                'You must send exactly: "DELETE ALL UPLOADED DATA"'
            ),
        )

    db = SessionLocal()
    try:
        result = reset_all_uploaded_data(db)
        return result
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Single-dataset management
# ---------------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/activate")
def activate_dataset(dataset_id: str) -> dict[str, Any]:
    """
    Explicitly set a specific dataset as the active analysis dataset.

    Benchmark/test datasets are rejected unless `allow_benchmark=true`
    is passed as a query parameter (future extension — not exposed to UI).
    """
    db = SessionLocal()
    try:
        # Verify dataset exists
        row = db.execute(
            text(
                "SELECT id, dataset_name, academic_label FROM system.datasets WHERE id = :id"
            ),
            {"id": dataset_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

        ds_name = row["dataset_name"] or ""
        if is_benchmark_dataset(ds_name):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot activate benchmark/test dataset '{ds_name}'. "
                    "Only production datasets can be set as active."
                ),
            )

        set_active_dataset(db, dataset_id)
        db.commit()

        return {
            "status": "activated",
            "dataset_id": dataset_id,
            "dataset_name": ds_name,
            "academic_label": row.get("academic_label"),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        db.close()


class DeleteDatasetRequest(BaseModel):
    confirm: bool = False


@router.delete("/datasets/{dataset_id}")
def delete_single_dataset(dataset_id: str, confirm: bool = False) -> dict[str, Any]:
    """
    Delete a single dataset and all its dependent data (staging, analytics,
    mappings, quality reports, conversation context).

    Requires `confirm=true` query parameter.

    If deleting the currently active dataset, active dataset becomes None.
    Will NOT auto-promote a benchmark dataset.
    """

    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass ?confirm=true to confirm deletion.",
        )

    db = SessionLocal()
    try:
        # Verify dataset exists
        row = db.execute(
            text("SELECT id, dataset_name, is_active FROM system.datasets WHERE id = :id"),
            {"id": dataset_id},
        ).mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found.")

        ds_name = row["dataset_name"] or ""
        was_active = bool(row["is_active"])

        counts = delete_dataset_cascade(db, [dataset_id])

        # If we deleted the active dataset, don't auto-promote anything
        if was_active:
            logger.warning(
                "Deleted active dataset '%s' (%s). Active dataset is now None.",
                ds_name, dataset_id,
            )

        db.commit()

        return {
            "status": "deleted",
            "dataset_id": dataset_id,
            "dataset_name": ds_name,
            "was_active": was_active,
            "deleted_staging_rows": counts["staging"],
            "deleted_analytics_rows": counts["analytics"],
        }
    finally:
        db.close()

