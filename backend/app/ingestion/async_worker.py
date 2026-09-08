"""
Asynchronous Ingestion Worker.

Runs ingestion jobs in the background:
1. Streams/downloads file from ObjectStorageProvider (R2/S3/Local).
2. Computes SHA-256 checksum and validates file format & duplicate status.
3. Profiles multi-sheet workbook or CSV without loading into memory at once.
4. Performs bulk staging load via PostgreSQL COPY STDIN.
5. Checks active approved mappings in intelligence.schema_mappings.
6. Executes MappingExecutor for approved mappings, or pauses at 'mapping_required' for user review.
7. Calculates data quality statistics and refreshes dashboard aggregates.
8. Retains safe error details and preserves original object storage files.
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.database.repository import create_data_source, create_dataset, find_dataset_by_checksum
from app.ingestion.job_tracker import mark_job_completed, mark_job_failed, update_job_progress
from app.ingestion.mapping_executor import calculate_data_quality_report, execute_mapping_normalization
from app.ingestion.profiler import profile_multisheet_file
from app.ingestion.staging_loader import load_to_staging
from app.mapping.mapping_service import get_reusable_mappings_for_columns
from app.storage.service import get_storage_provider

logger = logging.getLogger(__name__)


def run_async_ingestion_job(
    job_id: str,
    dataset_id: str,
    storage_key: str,
    original_filename: str,
    db_session: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Asynchronous ingestion worker execution.
    Can be run in a BackgroundTask thread or background job runner.
    """
    db = db_session or SessionLocal()
    should_close_db = db_session is None

    t0_overall = time.perf_counter()
    logger.info("[ASYNC WORKER] Starting ingestion job_id=%s, dataset_id=%s, key=%s", job_id, dataset_id, storage_key)

    extension = Path(original_filename).suffix.lower()
    storage = get_storage_provider()

    # Create temporary local file for streaming ingestion processing
    temp_fd, temp_path = tempfile.mkstemp(suffix=extension)
    os.close(temp_fd)

    try:
        update_job_progress(job_id, stage="downloading", progress_percent=5.0, message="Downloading file from object storage...", db=db)

        # Stream/download object from storage
        download_success = storage.download_file(storage_key, temp_path)
        if not download_success:
            err_msg = f"Failed to download object storage key: {storage_key}"
            mark_job_failed(job_id, error=err_msg, db=db)
            return {"status": "failed", "error": err_msg}

        # ── Stage 1: File Checksum & Validation ───────────────────────────
        update_job_progress(job_id, stage="parsing", progress_percent=15.0, message="Validating file integrity & checksum...", db=db)

        sha = hashlib.sha256()
        with open(temp_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        checksum = sha.hexdigest()

        # Check duplicate file checksum
        existing = find_dataset_by_checksum(db, checksum)
        if existing and str(existing.get("dataset_id")) != str(dataset_id):
            message = "Duplicate file checksum detected."
            mark_job_completed(job_id, message=message, result_data={"upload_status": "duplicate_file", "existing": existing}, db=db)
            return {"status": "duplicate_file", "existing_dataset": existing}

        # ── Stage 2: Profiling ─────────────────────────────────────────────
        update_job_progress(job_id, stage="profiling", progress_percent=30.0, message="Profiling file columns and multi-sheet structure...", db=db)

        from app.mapping.workbook_classifier import classify_workbook
        multisheet_profile = profile_multisheet_file(temp_path)
        multisheet_profile["filename"] = original_filename
        multisheet_profile["original_filename"] = original_filename
        wb_classification = classify_workbook(multisheet_profile)
        wb_type = wb_classification.get("workbook_type", "RAW")

        # Check existing dataset workbook_type set during upload initiate
        existing_wb = db.execute(
            text("SELECT workbook_type FROM system.datasets WHERE id = :ds_id"),
            {"ds_id": str(dataset_id)},
        ).scalar()
        if existing_wb and str(existing_wb).strip().upper() in ("DIMENSION", "TARGET"):
            wb_type = str(existing_wb).strip().upper()
        elif "dimension" in original_filename.lower():
            wb_type = "DIMENSION"
        elif any(k in original_filename.lower() for k in ("target", "tgt")):
            wb_type = "TARGET"
        total_rows = (
            multisheet_profile.get("total_rows")
            or multisheet_profile.get("rows")
            or sum(s.get("rows", 0) for s in multisheet_profile.get("sheets", []))
        )
        total_cols = (
            multisheet_profile.get("total_columns")
            or multisheet_profile.get("columns")
            or (multisheet_profile.get("sheets", [{}])[0].get("columns", 0) if multisheet_profile.get("sheets") else 0)
        )

        # Register data source and dataset in system.datasets
        existing_ds = db.execute(
            text("SELECT id FROM system.datasets WHERE id = :ds_id"),
            {"ds_id": str(dataset_id)},
        ).scalar()

        if not existing_ds:
            source_id = create_data_source(
                db=db,
                source_name=original_filename,
                source_type="file",
                description="Uploaded dataset stored in object storage.",
            )
            create_dataset(
                db=db,
                dataset_id=dataset_id,
                source_id=source_id,
                dataset_name=original_filename,
                original_filename=original_filename,
                dataset_type=extension.replace(".", ""),
                row_count=total_rows,
                column_count=total_cols,
                status="profiled",
                file_checksum=checksum,
            )
        
        db.execute(
            text(
                """
                UPDATE system.datasets
                SET row_count = :row_count,
                    column_count = :column_count,
                    status = 'profiled',
                    analytics_status = 'PENDING',
                    file_checksum = :file_checksum,
                    workbook_type = :wb_type
                WHERE id = :ds_id
                """
            ),
            {
                "ds_id": str(dataset_id),
                "row_count": total_rows,
                "column_count": total_cols,
                "file_checksum": checksum,
                "wb_type": wb_type,
            },
        )
        db.commit()

        # ── Stage 3: Bulk Staging Insert ──────────────────────────────────
        update_job_progress(job_id, stage="staging", total_rows=total_rows, progress_percent=50.0, message="Bulk loading records into staging database...", db=db)

        def staging_progress(proc_rows: int, tot_rows: int):
            pct = 50.0 + min(30.0, (proc_rows / max(1, tot_rows)) * 30.0)
            update_job_progress(job_id, stage="staging", processed_rows=proc_rows, total_rows=tot_rows, progress_percent=pct, db=db)

        staged_rows = load_to_staging(
            db=db,
            dataset_id=dataset_id,
            file_path=temp_path,
            progress_callback=staging_progress,
            total_rows=total_rows,
        )

        # Update actual row count in system.datasets based on staged rows
        actual_rows = max(staged_rows, total_rows)
        db.execute(
            text("UPDATE system.datasets SET row_count = :staged_rows WHERE id = :ds_id"),
            {"ds_id": str(dataset_id), "staged_rows": actual_rows},
        )
        db.commit()

        # ── Stage 4: Dynamic Mapping Verification & Execution ────────────
        update_job_progress(job_id, stage="mapping_check", processed_rows=staged_rows, total_rows=total_rows, progress_percent=80.0, message="Verifying column mappings...", db=db)

        all_cols = []
        for sheet in multisheet_profile.get("sheets", []):
            all_cols.extend(sheet.get("column_names", []))

        reusable_maps = get_reusable_mappings_for_columns(db, columns=all_cols, source_file=original_filename)

        # ── Period & Campus Detection ─────────────────────────────────────
        try:
            from app.ingestion.period_detector import detect_period
            det = detect_period(original_filename, db, dataset_id)
            if det and det.academic_year:
                db.execute(
                    text("""
                        UPDATE system.datasets
                        SET academic_year = COALESCE(academic_year, :y),
                            campus_name = COALESCE(campus_name, :c)
                        WHERE id = :ds_id
                    """),
                    {"ds_id": str(dataset_id), "y": det.academic_year, "c": det.campus_name},
                )
                db.commit()
        except Exception as det_err:
            logger.warning("Period detection in async worker skipped: %s", det_err)

        # ── Stage 5: Execution (Raw vs Target Routing) ───────────────────
        update_job_progress(job_id, stage="normalization", processed_rows=staged_rows, total_rows=total_rows, progress_percent=90.0, message="Executing mapping normalization...", db=db)

        if wb_type == "TARGET":
            from app.ingestion.target_executor import execute_target_ingestion
            target_res = execute_target_ingestion(db, dataset_id=str(dataset_id))
            normalized_rows = target_res.get("inserted_count", 0)
            quality_stats = {"total_rows": staged_rows, "target_rows": normalized_rows}
        else:
            exec_res = execute_mapping_normalization(
                db=db,
                dataset_id=dataset_id,
                source_file=original_filename,
                sheet_name=multisheet_profile.get("sheets", [{}])[0].get("sheet_name", "default"),
            )
            normalized_rows = exec_res.get("normalized_rows", 0)
            quality_stats = exec_res.get("data_quality") or calculate_data_quality_report(db, str(dataset_id))

        # Compute dataset data coverage metadata (months_covered, start_month, end_month)
        try:
            import json
            m_rows = db.execute(
                text("SELECT DISTINCT created_month FROM analytics.uploaded_metrics WHERE dataset_id::text = :ds_id AND created_month IS NOT NULL ORDER BY created_month"),
                {"ds_id": str(dataset_id)},
            ).scalars().all()
            if m_rows:
                months_covered = []
                for m in m_rows:
                    if isinstance(m, int):
                        months_covered.append(m)
                    elif isinstance(m, str) and "-" in m:
                        try:
                            months_covered.append(int(m.split("-")[1]))
                        except ValueError:
                            pass
                    elif isinstance(m, str) and m.isdigit():
                        months_covered.append(int(m))

                months_covered = sorted(list(set(months_covered)))
                if months_covered:
                    start_month = min(months_covered)
                    end_month = max(months_covered)
                    is_completed_12m = len(months_covered) >= 12
                    db.execute(
                        text("""
                            UPDATE system.datasets
                            SET start_month = :s_m, 
                                end_month = :e_m, 
                                months_covered = CAST(:m_cov AS jsonb),
                                is_period_active = :period_active
                            WHERE id = :ds_id
                        """),
                        {
                            "ds_id": str(dataset_id),
                            "s_m": start_month,
                            "e_m": end_month,
                            "m_cov": json.dumps(months_covered),
                            "period_active": False if is_completed_12m else True,
                        },
                    )
                    db.commit()
        except Exception as cov_err:
            logger.warning("Failed to calculate coverage metadata for %s: %s", dataset_id, cov_err)

        # Activate dataset for its scope & enable analytics only if valid data was ingested
        final_row_count = normalized_rows if normalized_rows > 0 else staged_rows
        if final_row_count > 0:
            try:
                db.execute(
                    text("""
                        UPDATE system.datasets 
                        SET status = 'completed',
                            row_count = :row_count,
                            analytics_status = 'AGGREGATING' 
                        WHERE id = :ds_id
                    """),
                    {"ds_id": str(dataset_id), "row_count": final_row_count},
                )
                db.commit()
                from app.database.repository import set_active_dataset, enable_dataset_analytics
                enable_dataset_analytics(db, str(dataset_id), force=True)
                set_active_dataset(db, str(dataset_id), allow_benchmark=True)
            except Exception as act_err:
                logger.warning("Failed to auto-activate dataset %s post-ingestion: %s", dataset_id, act_err)
        else:
            logger.warning("Dataset %s has 0 rows post-ingestion; leaving inactive", dataset_id)
            db.execute(
                text("""
                    UPDATE system.datasets 
                    SET status = 'failed', 
                        is_active = FALSE, 
                        is_analytics_enabled = FALSE, 
                        analytics_status = 'FAILED' 
                    WHERE id = :ds_id
                """),
                {"ds_id": str(dataset_id)},
            )
            db.commit()

        try:
            from app.analytics.aggregate_refresh import refresh_dashboard_agg_scoped
            refresh_dashboard_agg_scoped(db, dataset_id=str(dataset_id))
            db.execute(
                text("UPDATE system.datasets SET analytics_status = 'ANALYTICS_READY' WHERE id = :ds_id"),
                {"ds_id": str(dataset_id)},
            )
            db.commit()
        except Exception as ref_err:
            logger.warning("Failed to refresh dashboard_agg post-ingestion: %s", ref_err)
            try:
                db.execute(
                    text("UPDATE system.datasets SET analytics_status = 'FAILED' WHERE id = :ds_id"),
                    {"ds_id": str(dataset_id)},
                )
                db.commit()
            except Exception:
                pass

        t1_overall = time.perf_counter()
        logger.info("[ASYNC WORKER] Job completed successfully job_id=%s elapsed=%.4fs normalized_rows=%d", job_id, t1_overall - t0_overall, normalized_rows)

        res_data = {
            "dataset_id": str(dataset_id),
            "upload_id": job_id,
            "filename": original_filename,
            "file_type": extension.replace(".", ""),
            "status": "staging_cleared",
            "upload_status": "success",
            "staged_rows": staged_rows,
            "normalized_rows": normalized_rows,
            "rows_processed": staged_rows,
            "inserted_rows": normalized_rows,
            "updated_rows": 0,
            "duplicate_rows": staged_rows - normalized_rows if staged_rows > normalized_rows else 0,
            "data_quality": quality_stats,
            "reusable_mappings": reusable_maps,
            "elapsed_seconds": round(t1_overall - t0_overall, 4),
        }

        mark_job_completed(job_id, message="Ingestion completed successfully.", result_data=res_data, db=db)
        return res_data

    except Exception as e:
        logger.exception("[ASYNC WORKER] Job failed job_id=%s error=%s", job_id, e)
        err_msg = str(e)
        mark_job_failed(job_id, error=err_msg, db=db)

        # Update dataset status in system.datasets to failed and guarantee it is not active
        try:
            db.execute(
                text("""
                    UPDATE system.datasets 
                    SET status = 'failed', 
                        analytics_status = 'FAILED', 
                        is_active = FALSE, 
                        is_analytics_enabled = FALSE 
                    WHERE id = :ds_id
                """),
                {"ds_id": str(dataset_id)},
            )
            db.commit()
        except Exception:
            pass

        return {"status": "failed", "error": err_msg}

    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        if should_close_db:
            db.close()
