from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.analytics.counsellor_service import (
    get_counsellor_summary,
    get_counsellors_list,
    get_counsellor_detail_report,
    get_lead_activity,
    generate_counsellor_report,
)

router = APIRouter(tags=["Counsellor Operations"])


@router.get("/api/counsellors")
@router.get("/api/counsellor")
@router.get("/api/counsellor/summary")
@router.get("/api/counsellors/summary")
def get_counsellors_summary_endpoint(
    academic_year: Optional[int] = Query(None),
    campus: Optional[str] = Query(None),
    counsellor: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns counsellor performance summary list and high-level KPIs.
    
    Uses ultra-fast set-based aggregation for Level 1 list, supporting search,
    academic year, and campus filters.
    """
    search_term = search or counsellor
    if program and program.lower() != "all":
        return get_counsellor_summary(
            db=db,
            academic_year=academic_year,
            campus=campus,
            counsellor=search_term,
            program=program,
        )
    return get_counsellors_list(
        db=db,
        academic_year=academic_year,
        campus=campus,
        search=search_term,
    )


@router.get("/api/counsellors/report")
@router.get("/api/counsellor/report")
@router.get("/api/counsellors/{owner_id:path}/report")
@router.get("/api/counsellor/{owner_id:path}/report")
def get_counsellor_report_endpoint(
    owner_id: Optional[str] = None,
    counsellor: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    campus: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns selected counsellor Level 2 detail performance report.
    
    Includes 4 KPI cards and dynamic Source Category performance table
    ranked by conversion rate descending.
    """
    identifier = owner_id or counsellor
    if not identifier or not str(identifier).strip():
        raise HTTPException(status_code=400, detail="Counsellor owner_id or counsellor parameter is required")
    
    try:
        return get_counsellor_detail_report(
            db=db,
            counsellor_id_or_name=str(identifier).strip(),
            academic_year=academic_year,
            campus=campus,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/counsellor/leads")
@router.get("/api/counsellors/leads")
def get_lead_activity_report(
    academic_year: Optional[int] = Query(None),
    campus: Optional[str] = Query(None),
    counsellor: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    cluster: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    disposition: Optional[str] = Query(None),
    attempt_bucket: Optional[str] = Query(None),
    followup_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort_by: str = Query("created_on"),
    order: str = Query("desc"),
    db: Session = Depends(get_db),
):
    """Returns paginated lead activity records with multi-column filtering."""
    return get_lead_activity(
        db=db,
        academic_year=academic_year,
        campus=campus,
        counsellor=counsellor,
        program=program,
        cluster=cluster,
        state=state,
        source=source,
        disposition=disposition,
        attempt_bucket=attempt_bucket,
        followup_status=followup_status,
        search=search,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )


@router.get("/api/counsellor/export")
@router.get("/api/counsellors/export")
def export_counsellor_report(
    report_type: str = Query("counsellor_performance"),
    export_format: str = Query("csv"),
    academic_year: Optional[int] = Query(None),
    campus: Optional[str] = Query(None),
    counsellor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Exports counsellor analytics as CSV or XLSX file download stream."""
    content, media_type = generate_counsellor_report(
        db=db,
        report_type=report_type,
        export_format=export_format,
        academic_year=academic_year,
        campus=campus,
        counsellor=counsellor,
    )
    filename = f"{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
