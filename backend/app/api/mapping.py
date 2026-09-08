"""
FastAPI Router for Dynamic File/Sheet/Column Mapping Foundation.

Endpoints:
- POST /api/mapping/inspect: Inspect and profile uploaded files/sheets and columns
- POST /api/mapping/suggest-relationships: Suggest relationships using keys, synonyms & value overlap
- POST /api/mapping/approve: Approve, edit, or reject mapping candidates
- GET  /api/mapping/saved: Retrieve stored mapping configurations
"""
from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.ingestion.profiler import profile_multisheet_file
from app.mapping.mapping_service import (
    approve_or_edit_mappings,
    get_reusable_mappings_for_columns,
    list_saved_mappings,
    save_multiple_mapping_configurations,
)
from app.mapping.relationship_detector import (
    detect_relationships_against_canonical_entities,
    detect_sheet_relationships,
)

router = APIRouter(prefix="/api/mapping", tags=["Dynamic Mapping"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Schemas
# ─────────────────────────────────────────────────────────────────────────────

class InspectRequest(BaseModel):
    file_path: Optional[str] = None
    dataset_id: Optional[str] = None


class SuggestRelationshipsRequest(BaseModel):
    source_sheet: Dict[str, Any]
    target_sheet: Optional[Dict[str, Any]] = None
    source_file: str = "upload"
    target_file: str = "target"
    include_canonical: bool = True
    auto_persist_suggestions: bool = True


class MappingDecision(BaseModel):
    id: Optional[str] = None
    action: str = Field("approve", description="'approve', 'reject', or 'edit'")
    source_file: Optional[str] = "upload"
    source_sheet: Optional[str] = "default"
    source_column: Optional[str] = None
    target_entity: Optional[str] = None
    target_column: Optional[str] = None
    confidence: Optional[float] = 1.0


class ApproveMappingsRequest(BaseModel):
    decisions: List[MappingDecision]


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter, Depends, File, HTTPException, Query, status, UploadFile, Request

@router.post(
    "/inspect",
    summary="Inspect Uploaded File and Return Profiled Sheets & Columns",
    status_code=status.HTTP_200_OK,
)
async def inspect_file_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Inspects a file (via upload or existing file path) and returns full sheet
    and column profiling (data types, null %, uniqueness, key likelihood, samples).
    Also checks previously approved mappings that can be reused.
    """
    target_path: Optional[str] = None
    temp_dir: Optional[str] = None
    dataset_id: Optional[str] = None
    file_path_req: Optional[str] = None

    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            dataset_id = body.get("dataset_id")
            file_path_req = body.get("file_path")
        except Exception:
            pass

    try:
        if file is not None:
            temp_dir = tempfile.mkdtemp(prefix="upload_inspect_")
            target_path = os.path.join(temp_dir, file.filename or "uploaded_file")
            with open(target_path, "wb") as f_out:
                shutil.copyfileobj(file.file, f_out)
            file_name = file.filename or "uploaded_file"
        elif file_path_req:
            target_path = file_path_req
            file_name = os.path.basename(target_path)
        elif dataset_id:
            # Look up dataset filepath if dataset_id provided
            ds_row = db.execute(
                text("SELECT original_filename FROM system.datasets WHERE id::text = :ds_id"),
                {"ds_id": str(dataset_id)},
            ).mappings().first()
            if not ds_row:
                raise HTTPException(status_code=404, detail="Dataset not found")
            file_name = ds_row["original_filename"]
            # Look in masterdata or storage uploads
            potential = os.path.join(os.getcwd(), "masterdata", file_name)
            if not os.path.exists(potential):
                potential = os.path.join(os.getcwd(), "data", "storage", "uploads", file_name)
            if os.path.exists(potential):
                target_path = potential
            else:
                target_path = None
        else:
            raise HTTPException(
                status_code=400,
                detail="Either a file upload or file_path/dataset_id must be provided.",
            )

        if target_path and os.path.exists(target_path):
            profile = profile_multisheet_file(target_path)
        else:
            profile = {"filename": file_name, "sheets": [], "total_rows": 0, "total_columns": 0}

        # Collect all column names across sheets to find reusable mappings
        all_cols = []
        for s in profile.get("sheets", []):
            all_cols.extend(s.get("column_names", []))

        reusable = get_reusable_mappings_for_columns(db, columns=list(set(all_cols)), source_file=file_name)
        profile["reusable_mappings"] = reusable

        return profile

    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


@router.post(
    "/suggest-relationships",
    summary="Detect and Suggest Relationships Using Common Columns/Keys",
    status_code=status.HTTP_200_OK,
)
def suggest_relationships_endpoint(
    req: SuggestRelationshipsRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Detects relationship candidates using:
    - Reusable previously approved mappings (confidence = 1.0)
    - Exact key matching & name normalization
    - Equivalent column-name variations (ProgramCode / Program Code, OwnerID / EmployeeID)
    - Sample value overlap (Jaccard similarity)
    - Ambiguity detection & confirmation requirements
    """
    source_cols = req.source_sheet.get("column_names") or [
        c.get("name") for c in req.source_sheet.get("columns_profile", [])
    ]
    reusable = get_reusable_mappings_for_columns(db, columns=source_cols, source_file=req.source_file)

    suggestions: List[Dict[str, Any]] = []
    mapped_columns = set()

    # 1. Attach approved reusable mappings first
    for col_name, r_map in reusable.items():
        suggestions.append({
            "source_file": req.source_file,
            "source_sheet": req.source_sheet.get("sheet_name", "default"),
            "source_column": col_name,
            "target_entity": r_map["target_entity"],
            "target_sheet": r_map.get("target_sheet", "default"),
            "target_column": r_map["target_column"],
            "confidence": 1.0,
            "status": "approved",
            "match_type": r_map.get("match_type", "reused"),
            "is_key_relationship": True,
            "requires_confirmation": False,
            "is_ambiguous": False,
            "is_reused": True,
            "mapping_version": r_map.get("mapping_version", 1),
        })
        mapped_columns.add(col_name)

    # Filter out columns already mapped via reuse
    unmapped_sheet = dict(req.source_sheet)
    if "columns_profile" in unmapped_sheet:
        unmapped_sheet["columns_profile"] = [
            c for c in unmapped_sheet["columns_profile"] if c.get("name") not in mapped_columns
        ]

    # 2. Detect relationships against target sheet or canonical entities
    detected = []
    if req.target_sheet:
        detected = detect_sheet_relationships(
            source_sheet=unmapped_sheet,
            target_sheet=req.target_sheet,
            source_file=req.source_file,
            target_file=req.target_file,
        )
    elif req.include_canonical:
        detected = detect_relationships_against_canonical_entities(
            source_sheet=unmapped_sheet,
            source_file=req.source_file,
        )

    for item in detected:
        item["is_reused"] = False
        suggestions.append(item)

    # 3. Optionally persist newly detected suggestions
    if req.auto_persist_suggestions and suggestions:
        to_persist = [s for s in suggestions if not s.get("is_reused")]
        if to_persist:
            save_multiple_mapping_configurations(db, to_persist)

    high_conf = sum(1 for s in suggestions if s.get("confidence", 0) >= 0.85 and not s.get("is_ambiguous"))
    req_conf = sum(1 for s in suggestions if s.get("requires_confirmation"))

    return {
        "source_file": req.source_file,
        "source_sheet": req.source_sheet.get("sheet_name", "default"),
        "total_suggestions": len(suggestions),
        "high_confidence_count": high_conf,
        "requires_confirmation_count": req_conf,
        "suggestions": suggestions,
    }


@router.post(
    "/approve",
    summary="Approve, Edit, or Reject Mappings",
    status_code=status.HTTP_200_OK,
)
def approve_mappings_endpoint(
    req: ApproveMappingsRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Approve, edit, or reject mapping candidates.
    Approved mappings are persisted and become active for automatic reuse in future uploads.
    """
    decisions_data = [
        d.model_dump() if hasattr(d, "model_dump") else d.dict()
        for d in req.decisions
    ]
    result = approve_or_edit_mappings(db, decisions_data)
    return result


@router.get(
    "/saved",
    summary="Retrieve Saved & Approved Mappings",
    status_code=status.HTTP_200_OK,
)
def get_saved_mappings_endpoint(
    target_entity: Optional[str] = Query(None, description="Filter by target entity"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. 'approved')"),
    source_file: Optional[str] = Query(None, description="Filter by source file pattern"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Returns saved mappings from the intelligence.schema_mappings repository."""
    mappings = list_saved_mappings(
        db=db,
        target_entity=target_entity,
        status=status,
        source_file=source_file,
        limit=limit,
    )
    return {
        "count": len(mappings),
        "mappings": mappings,
    }


class ExecuteMappingRequest(BaseModel):
    dataset_id: str
    source_file: Optional[str] = "upload"
    sheet_name: Optional[str] = "default"
    decisions: Optional[List[MappingDecision]] = None


@router.post(
    "/execute",
    summary="Execute Approved Mappings and Normalize Ingestion Dataset",
    status_code=status.HTTP_200_OK,
)
def execute_mapping_endpoint(
    req: ExecuteMappingRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Saves/approves mapping decisions (if provided), executes MappingExecutor to normalize
    staging.records raw data into analytics.uploaded_metrics, generates quality report,
    and refreshes dashboard aggregates.
    """
    if req.decisions:
        decisions_data = [
            d.model_dump() if hasattr(d, "model_dump") else d.dict()
            for d in req.decisions
        ]
        approve_or_edit_mappings(db, decisions_data)

    from app.ingestion.mapping_executor import execute_mapping_normalization
    result = execute_mapping_normalization(
        db=db,
        dataset_id=req.dataset_id,
        source_file=req.source_file,
        sheet_name=req.sheet_name or "default",
    )
    return result


@router.post(
    "/preview-quality",
    summary="Generate Pre-Ingestion Data Quality Metrics",
    status_code=status.HTTP_200_OK,
)
def preview_quality_endpoint(
    dataset_id: str = Query(..., description="Dataset ID to calculate preview quality for"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Generates preview data quality report (rows, blank program count, duplicate prospect count, coverage %)."""
    from app.ingestion.mapping_executor import calculate_data_quality_report
    return calculate_data_quality_report(db=db, dataset_id=dataset_id)


@router.post(
    "/classify-workbook",
    summary="Classify Multi-Sheet Workbook and Sheets",
    status_code=status.HTTP_200_OK,
)
def classify_workbook_endpoint(
    workbook_profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Classifies multi-sheet workbook into RAW, DIMENSION, or TARGET and categorizes each sheet."""
    from app.mapping.workbook_classifier import classify_workbook
    return classify_workbook(workbook_profile)


@router.post(
    "/detect-multisheet",
    summary="Detect Cross-Sheet Relationships with Sample Value Overlap",
    status_code=status.HTTP_200_OK,
)
def detect_multisheet_endpoint(
    workbook_profiles: List[Dict[str, Any]],
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Detects relationship candidates across multi-sheet workbooks using column names, synonyms, data types, and Jaccard sample value overlap %."""
    from app.mapping.relationship_detector import detect_multisheet_workbook_relationships
    from app.mapping.mapping_service import list_saved_mappings
    saved = list_saved_mappings(db, status="approved")
    relationships = detect_multisheet_workbook_relationships(workbook_profiles, saved_mappings=saved)
    return {"detected_relationships": relationships, "count": len(relationships)}


class BatchApproveRequest(BaseModel):
    mappings: List[Dict[str, Any]]
    workbook_type: Optional[str] = "raw_data"


@router.post(
    "/approve-batch",
    summary="Approve Batch of Multi-Sheet Mappings",
    status_code=status.HTTP_200_OK,
)
def approve_batch_endpoint(
    req: BatchApproveRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Approves a batch of multi-sheet relationship mappings with version increment."""
    from app.mapping.mapping_service import batch_save_multisheet_mappings
    saved = batch_save_multisheet_mappings(db, req.mappings, workbook_type=req.workbook_type or "raw_data")
    return {"saved_count": len(saved), "saved": saved}


