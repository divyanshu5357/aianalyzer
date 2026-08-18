"""
Upload API — two-phase file upload with period detection and conflict protection.

Phase A — POST /api/data/upload
  • Validates file extension
  • Saves the raw file
  • Profiles it
  • Stages the data
  • Infers column schema
  • Normalises analytics metrics
  • Runs period detection
  • Checks for period conflicts
  • Returns ONE of:
      - 200 status="success"          high-confidence period, no conflict
      - 202 status="pending_confirmation"  high-confidence period detected, awaiting user confirm
      - 202 status="period_unknown"    low-confidence/no period detected
      - 409 status="conflict"          period already exists

Phase B — POST /api/data/upload/confirm
  • Accepts: dataset_id, action ("confirm"|"replace"|"new_version"), academic_label
  • Applies conflict action and activates the dataset
  • Returns the finalised dataset metadata

GET /api/data/active
  • Returns metadata for the currently active dataset (unchanged).
"""

import hashlib
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.repository import (
    create_data_source,
    create_dataset,
    create_quality_report,
    set_active_dataset,
    get_active_dataset_info,
    set_dataset_period,
    set_period_active,
    find_dataset_by_checksum,
)
from app.ingestion.profiler import profile_file
from app.ingestion.staging_loader import load_to_staging
from app.ingestion.analytics_normalizer import normalize_dataset
from app.ingestion.schema_mapper import map_and_store_dataset_schema
from app.ingestion.period_detector import detect_period, available_period_labels
from app.ingestion.period_conflict import check_period_conflict, check_session_overlap, apply_conflict_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["Data"])

UPLOAD_DIRECTORY = Path("data/raw")
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsb"}


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------

class UploadConfirmRequest(BaseModel):
    dataset_id: str
    action: str           # "confirm" | "replace" | "new_version"
    academic_label: str   # user-confirmed label, e.g. "2025-26"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_file_checksum(file_path: Path) -> str:
    """Compute SHA-256 hex digest for a file on disk."""
    sha = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _process_single_file(file: UploadFile, db: Session) -> dict:
    """
    Run all ingestion steps for one uploaded file and return a dict describing
    the outcome.  Does NOT commit the DB transaction — caller does that.

    Flow:
      1. Save file to disk
      2. Compute SHA-256 checksum → check for duplicate file
      3. Detect period from filename → check for period conflict (fast, no DB staging)
      4. If no blockers: profile → stage → schema-map → normalise (expensive)
    """
    dataset_id = uuid4()
    original_filename = file.filename or "unknown"
    extension = Path(original_filename).suffix.lower()
    safe_filename = f"{dataset_id}_{original_filename}"
    file_path = UPLOAD_DIRECTORY / safe_filename

    import shutil
    with file_path.open("wb") as buf:
        shutil.copyfileobj(file.file, buf)

    # ── Step 2: Checksum duplicate detection ──────────────────────────────
    checksum = _compute_file_checksum(file_path)
    existing = find_dataset_by_checksum(db, checksum)
    if existing:
        # Exact duplicate file — skip all expensive processing
        file_path.unlink(missing_ok=True)
        return {
            "dataset_id": existing["dataset_id"],
            "filename": original_filename,
            "file_type": extension.replace(".", ""),
            "status": "duplicate_file",
            "upload_status": "duplicate_file",
            "existing_dataset": existing,
            "staged_rows": existing.get("row_count", 0),
            "normalized_rows": existing.get("row_count", 0),
            "column_mappings": [],
            "profile": {},
        }

    # ── Step 3: Early period detection from filename ──────────────────────
    filename_period = detect_period(filename=original_filename)
    if filename_period.is_confident and filename_period.academic_label:
        early_conflict = check_period_conflict(db, filename_period.academic_label)
        if early_conflict.has_conflict:
            # Period conflict detected BEFORE expensive processing
            # Still register the dataset so the user can confirm via Phase B
            pass  # We continue to process, but mark the conflict later

    # ── Step 4: Expensive processing ─────────────────────────────────────
    # Profile
    profile = profile_file(str(file_path))

    # Register source + dataset
    source_id = create_data_source(
        db=db,
        source_name=original_filename,
        source_type="file",
        description="Uploaded dataset used for development and analysis.",
    )
    create_dataset(
        db=db,
        dataset_id=dataset_id,
        source_id=source_id,
        dataset_name=original_filename,
        original_filename=original_filename,
        dataset_type=extension.replace(".", ""),
        row_count=profile["rows"],
        column_count=profile["columns"],
        status="profiled",
        file_checksum=checksum,
    )
    create_quality_report(db=db, dataset_id=dataset_id, profile=profile)

    # Stage
    staged_rows = load_to_staging(db=db, dataset_id=dataset_id, file_path=str(file_path))

    # Schema mapping
    columns = profile.get("column_names") or []
    column_mappings = map_and_store_dataset_schema(db=db, dataset_id=dataset_id, columns=columns)

    # Normalise
    normalized_rows = normalize_dataset(db=db, dataset_id=dataset_id)

    # Cleanup staging if counts match
    final_status = "normalized"
    if staged_rows == normalized_rows:
        from app.ingestion.cleanup import cleanup_staging_for_dataset
        cleanup_res = cleanup_staging_for_dataset(db=db, dataset_id=dataset_id)
        if cleanup_res.get("success"):
            final_status = "staging_cleared"

    return {
        "dataset_id": str(dataset_id),
        "filename": original_filename,
        "file_type": extension.replace(".", ""),
        "status": final_status,
        "staged_rows": staged_rows,
        "normalized_rows": normalized_rows,
        "column_mappings": column_mappings,
        "profile": profile,
        "file_path": str(file_path),
        "file_checksum": checksum,
    }


def _detect_and_check(
    db: Session,
    dataset_id: str,
    original_filename: str,
) -> dict:
    """
    Run period detection + conflict check for a newly ingested dataset.
    Returns a dict describing the period situation.
    """
    detection = detect_period(
        filename=original_filename,
        db=db,
        dataset_id=dataset_id,
    )

    period_info = detection.to_dict()

    if not detection.academic_label:
        # No period detected — ask user
        return {
            "upload_status": "period_unknown",
            "period_detection": period_info,
            "available_periods": available_period_labels(db=db, n=10),
        }

    # Check for session overlap first
    has_overlap, overlap_info = check_session_overlap(db, detection.academic_label, ignore_dataset_id=dataset_id)
    if has_overlap and overlap_info:
        return {
            "upload_status": "overlap_conflict",
            "period_detection": period_info,
            "error_detail": "This session overlaps an existing dataset. Please choose a non-overlapping historical session or replace the existing session.",
            "overlap_info": overlap_info,
        }

    # Check for same-session conflict (replacement / versioning)
    conflict = check_period_conflict(db, detection.academic_label)

    if conflict.has_conflict:
        return {
            "upload_status": "conflict",
            "period_detection": period_info,
            "conflict": conflict.to_dict(),
        }

    # No conflict — write period metadata immediately
    set_dataset_period(
        db=db,
        dataset_id=dataset_id,
        period_start_year=detection.period_start_year,
        period_end_year=detection.period_end_year,
        academic_label=detection.academic_label,
        upload_version=1,
    )

    if detection.is_confident:
        return {
            "upload_status": "confirmed",  # auto-confirm high confidence, no conflict
            "period_detection": period_info,
            "conflict": None,
        }
    else:
        # Low confidence — ask user to confirm
        return {
            "upload_status": "pending_confirmation",
            "period_detection": period_info,
            "conflict": None,
        }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/active")
def get_active_dataset_route(db: Session = Depends(get_db)):
    active = get_active_dataset_info(db)
    if not active:
        return {"active": False, "dataset": None}
    return {"active": True, "dataset": active}


@router.post("/upload")
async def upload_datasets(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload one or more CSV/Excel files (Phase A).

    Returns status field indicating next step:
      - "confirmed"            → dataset is active, no further action needed
      - "pending_confirmation" → ask user to confirm the detected period
      - "period_unknown"       → ask user to select the period
      - "conflict"             → ask user how to handle duplicate period
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Every uploaded file must have a filename.")
        if Path(file.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.filename}. Supported: CSV, XLSX, XLS, XLSB.",
            )

    uploaded_files = []
    file_paths: list[Path] = []

    try:
        for file in files:
            result = _process_single_file(file, db)

            # If duplicate file detected, skip period detection
            if result.get("upload_status") == "duplicate_file":
                uploaded_files.append(result)
                continue

            file_paths.append(Path(result["file_path"]))

            # Period detection + conflict check
            period_situation = _detect_and_check(
                db=db,
                dataset_id=result["dataset_id"],
                original_filename=result["filename"],
            )
            result.pop("file_path", None)
            result.update(period_situation)
            uploaded_files.append(result)

        # Auto-activate datasets that resolved without conflict/ambiguity
        for f in uploaded_files:
            if f["upload_status"] == "confirmed":
                set_active_dataset(db, f["dataset_id"])

        db.commit()

        # If any file has an overlap conflict, return HTTP 400 with detail
        overlap_conflicts = [f for f in uploaded_files if f.get("upload_status") == "overlap_conflict"]
        if overlap_conflicts:
            raise HTTPException(
                status_code=400,
                detail="This session overlaps an existing dataset. Please choose a non-overlapping historical session or replace the existing session.",
            )

        # If any file has a conflict, return 409 for that file
        conflicts = [f for f in uploaded_files if f["upload_status"] == "conflict"]
        if conflicts and len(uploaded_files) == 1:
            return {
                "status": "conflict",
                "file_count": len(uploaded_files),
                "files": uploaded_files,
            }

        return {
            "status": "success",
            "file_count": len(uploaded_files),
            "files": uploaded_files,
        }

    except HTTPException:
        db.rollback()
        for fp in file_paths:
            if fp.exists():
                fp.unlink()
        raise

    except Exception as error:
        db.rollback()
        for fp in file_paths:
            if fp.exists():
                fp.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded files: {error}")


@router.post("/upload/confirm")
def confirm_upload(
    body: UploadConfirmRequest,
    db: Session = Depends(get_db),
):
    """
    Phase B — confirm period assignment and activate a dataset.

    Called after the user has:
      - Confirmed the auto-detected period
      - Manually selected the correct period
      - Chosen how to handle a conflict (replace / new_version)

    body.action must be one of:
      - "confirm"      → write period metadata and activate (no conflict)
      - "replace"      → replace existing active version for this period
      - "new_version"  → keep existing, add new version (new becomes active)
    """
    dataset_id = body.dataset_id
    action = body.action
    academic_label = body.academic_label.strip()

    if action not in ("confirm", "replace", "new_version"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{action}'. Must be: confirm, replace, new_version.",
        )

    # Parse label into years
    from app.ingestion.period_detector import parse_label
    years = parse_label(academic_label)
    if not years:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid academic_label '{academic_label}'. Expected format: 'YYYY-YY' e.g. '2025-26'.",
        )
    start_year, end_year = years

    # Check for session overlap first
    has_overlap, _ = check_session_overlap(db, academic_label, ignore_dataset_id=dataset_id)
    if has_overlap:
        raise HTTPException(
            status_code=400,
            detail="This session overlaps an existing dataset. Please choose a non-overlapping historical session or replace the existing session.",
        )

    # Determine version number
    conflict = check_period_conflict(db, academic_label)
    next_version = conflict.next_version if conflict.has_conflict else 1

    # Write period metadata
    set_dataset_period(
        db=db,
        dataset_id=dataset_id,
        period_start_year=start_year,
        period_end_year=end_year,
        academic_label=academic_label,
        upload_version=next_version,
    )

    # Apply conflict action (deactivate old if needed)
    if action in ("replace", "new_version") and conflict.has_conflict:
        from app.ingestion.period_conflict import apply_conflict_action
        apply_conflict_action(
            db=db,
            new_dataset_id=dataset_id,
            academic_label=academic_label,
            action=action,
            next_version=next_version,
        )
    else:
        # Simple confirm — just activate
        set_period_active(db, dataset_id)

    db.commit()

    return {
        "status": "activated",
        "dataset_id": dataset_id,
        "academic_label": academic_label,
        "upload_version": next_version,
        "action_applied": action,
    }