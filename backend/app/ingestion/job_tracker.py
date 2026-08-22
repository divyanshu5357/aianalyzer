import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Thread-safe in-memory cache for fast reads & single-instance fallback
_JOBS_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _format_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(
    job_id: str,
    filename: str = "",
    dataset_id: Optional[str] = None,
    total_rows: int = 0,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    job_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "filename": filename,
        "stage": "parsing",
        "status": "processing",
        "progress_percent": 5.0,
        "total_rows": total_rows,
        "processed_rows": 0,
        "message": "Starting file parsing...",
        "error": None,
        "updated_at": _format_now(),
    }

    with _CACHE_LOCK:
        _JOBS_CACHE[job_id] = job_data.copy()

    if db:
        try:
            db.execute(
                text(
                    """
                    INSERT INTO system.ingestion_jobs 
                    (job_id, dataset_id, filename, stage, status, progress_percent, total_rows, processed_rows, message, error, updated_at)
                    VALUES (:job_id, :dataset_id, :filename, :stage, :status, :progress_percent, :total_rows, :processed_rows, :message, :error, NOW())
                    ON CONFLICT (job_id) DO UPDATE SET
                        dataset_id = EXCLUDED.dataset_id,
                        stage = EXCLUDED.stage,
                        status = EXCLUDED.status,
                        progress_percent = EXCLUDED.progress_percent,
                        total_rows = EXCLUDED.total_rows,
                        processed_rows = EXCLUDED.processed_rows,
                        message = EXCLUDED.message,
                        error = EXCLUDED.error,
                        updated_at = NOW();
                    """
                ),
                {
                    "job_id": job_id,
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "stage": "parsing",
                    "status": "processing",
                    "progress_percent": 5.0,
                    "total_rows": total_rows,
                    "processed_rows": 0,
                    "message": "Starting file parsing...",
                    "error": None,
                },
            )
            db.commit()
        except Exception as e:
            logger.warning("Failed to persist ingestion_jobs row: %s", e)
            db.rollback()

    return job_data


def update_job_progress(
    job_id: str,
    stage: str,
    processed_rows: int = 0,
    total_rows: int = 0,
    progress_percent: Optional[float] = None,
    message: Optional[str] = None,
    dataset_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    with _CACHE_LOCK:
        current = _JOBS_CACHE.get(job_id, {})

    tot_rows = total_rows if total_rows > 0 else current.get("total_rows", 0)
    proc_rows = processed_rows if processed_rows > 0 else current.get("processed_rows", 0)
    ds_id = dataset_id or current.get("dataset_id")

    if progress_percent is None:
        # Default stage progress ranges:
        # parsing: 0-10%
        # staging: 10-45%
        # validation: 45-50%
        # normalization: 50-95%
        # finalization: 95-99%
        if tot_rows > 0:
            ratio = min(1.0, max(0.0, proc_rows / tot_rows))
            if stage == "parsing":
                progress_percent = round(5.0 + ratio * 5.0, 1)
            elif stage == "staging":
                progress_percent = round(10.0 + ratio * 35.0, 1)
            elif stage == "validation":
                progress_percent = 48.0
            elif stage == "normalization":
                progress_percent = round(50.0 + ratio * 45.0, 1)
            elif stage == "finalization":
                progress_percent = round(95.0 + ratio * 4.0, 1)
            else:
                progress_percent = current.get("progress_percent", 5.0)
        else:
            stage_defaults = {
                "parsing": 5.0,
                "staging": 20.0,
                "validation": 48.0,
                "normalization": 75.0,
                "finalization": 98.0,
            }
            progress_percent = stage_defaults.get(stage, current.get("progress_percent", 5.0))

    progress_percent = round(max(0.0, min(100.0, float(progress_percent))), 1)

    default_messages = {
        "parsing": "Parsing dataset file & profiling metrics...",
        "staging": f"Staging records into database ({proc_rows:,} / {tot_rows:,} rows)..." if tot_rows > 0 else "Staging records into database...",
        "validation": "Validating schema & mapping canonical fields...",
        "normalization": f"Normalizing metrics data ({proc_rows:,} / {tot_rows:,} rows)..." if tot_rows > 0 else "Normalizing metrics data...",
        "finalization": "Clearing staging records & activating dataset...",
    }

    msg = message or default_messages.get(stage, "Processing ingestion pipeline...")

    updated_data = {
        "job_id": job_id,
        "dataset_id": ds_id,
        "filename": current.get("filename", ""),
        "stage": stage,
        "status": "processing",
        "progress_percent": progress_percent,
        "total_rows": tot_rows,
        "processed_rows": proc_rows,
        "message": msg,
        "error": None,
        "updated_at": _format_now(),
    }

    with _CACHE_LOCK:
        _JOBS_CACHE[job_id] = updated_data.copy()

    if db:
        try:
            db.execute(
                text(
                    """
                    UPDATE system.ingestion_jobs
                    SET dataset_id = COALESCE(:dataset_id, dataset_id),
                        stage = :stage,
                        status = 'processing',
                        progress_percent = :progress_percent,
                        total_rows = :total_rows,
                        processed_rows = :processed_rows,
                        message = :message,
                        updated_at = NOW()
                    WHERE job_id = :job_id;
                    """
                ),
                {
                    "job_id": job_id,
                    "dataset_id": ds_id,
                    "stage": stage,
                    "progress_percent": progress_percent,
                    "total_rows": tot_rows,
                    "processed_rows": proc_rows,
                    "message": msg,
                },
            )
            db.commit()
        except Exception as e:
            logger.warning("Failed to update ingestion_jobs progress for job %s: %s", job_id, e)
            db.rollback()

    return updated_data


def mark_job_completed(
    job_id: str,
    message: str = "Ingestion complete",
    result_data: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    with _CACHE_LOCK:
        current = _JOBS_CACHE.get(job_id, {})

    tot = current.get("total_rows", 0)
    proc = current.get("processed_rows", tot) or tot
    res_data = result_data if result_data is not None else current.get("result_data")

    updated_data = {
        "job_id": job_id,
        "dataset_id": current.get("dataset_id"),
        "filename": current.get("filename", ""),
        "stage": "completed",
        "status": "completed",
        "progress_percent": 100.0,
        "total_rows": tot,
        "processed_rows": proc,
        "message": message,
        "error": None,
        "result_data": res_data,
        "updated_at": _format_now(),
    }

    with _CACHE_LOCK:
        _JOBS_CACHE[job_id] = updated_data.copy()

    if db:
        try:
            import json
            db.execute(
                text(
                    """
                    UPDATE system.ingestion_jobs
                    SET stage = 'completed',
                        status = 'completed',
                        progress_percent = 100.0,
                        processed_rows = total_rows,
                        message = :message,
                        result_data = :result_data,
                        updated_at = NOW()
                    WHERE job_id = :job_id;
                    """
                ),
                {
                    "job_id": job_id,
                    "message": message,
                    "result_data": json.dumps(res_data) if res_data is not None else None,
                },
            )
            db.commit()
        except Exception as e:
            logger.warning("Failed to mark ingestion_job completed: %s", e)
            db.rollback()

    return updated_data


def mark_job_failed(
    job_id: str,
    error: str,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    with _CACHE_LOCK:
        current = _JOBS_CACHE.get(job_id, {})

    updated_data = {
        "job_id": job_id,
        "dataset_id": current.get("dataset_id"),
        "filename": current.get("filename", ""),
        "stage": current.get("stage", "failed"),
        "status": "failed",
        "progress_percent": current.get("progress_percent", 0.0),
        "total_rows": current.get("total_rows", 0),
        "processed_rows": current.get("processed_rows", 0),
        "message": f"Ingestion failed: {error}",
        "error": error,
        "result_data": None,
        "updated_at": _format_now(),
    }

    with _CACHE_LOCK:
        _JOBS_CACHE[job_id] = updated_data.copy()

    if db:
        try:
            db.execute(
                text(
                    """
                    UPDATE system.ingestion_jobs
                    SET status = 'failed',
                        error = :error,
                        message = :message,
                        updated_at = NOW()
                    WHERE job_id = :job_id;
                    """
                ),
                {"job_id": job_id, "error": error, "message": f"Ingestion failed: {error}"},
            )
            db.commit()
        except Exception as e:
            logger.warning("Failed to mark ingestion_job failed: %s", e)
            db.rollback()

    return updated_data


def get_job_status(job_id: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    # Check in-memory cache first
    with _CACHE_LOCK:
        cached = _JOBS_CACHE.get(job_id)

    if cached:
        return cached

    # Fallback to DB
    if db:
        try:
            row = db.execute(
                text(
                    """
                    SELECT job_id, dataset_id, filename, stage, status, progress_percent, total_rows, processed_rows, message, error, result_data, updated_at
                    FROM system.ingestion_jobs
                    WHERE job_id = :job_id;
                    """
                ),
                {"job_id": job_id},
            ).mappings().first()

            if row:
                res_data = row.get("result_data")
                if isinstance(res_data, str):
                    import json
                    try:
                        res_data = json.loads(res_data)
                    except Exception:
                        pass

                res = {
                    "job_id": row["job_id"],
                    "dataset_id": row["dataset_id"],
                    "filename": row["filename"],
                    "stage": row["stage"],
                    "status": row["status"],
                    "progress_percent": float(row["progress_percent"]),
                    "total_rows": int(row["total_rows"]),
                    "processed_rows": int(row["processed_rows"]),
                    "message": row["message"],
                    "error": row["error"],
                    "result_data": res_data,
                    "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
                }
                with _CACHE_LOCK:
                    _JOBS_CACHE[job_id] = res.copy()
                return res
        except Exception as e:
            logger.warning("Failed to query ingestion_jobs from DB: %s", e)

    return None

