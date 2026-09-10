"""
API endpoints for Program Performance Report with strict lazy hierarchical loading.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.analytics.program_service import (
    get_program_report_top_level,
    get_program_hierarchy_children,
    get_program_insights,
)

router = APIRouter(prefix="/api/programs", tags=["Program Performance Report"])


@router.get("/report")
def get_program_report(
    academic_year: Optional[int] = Query(None, description="Academic year (CY)"),
    campus: Optional[str] = Query(None, description="Campus filter (e.g. Mohali, All)"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    sort_by: str = Query("cy_leads", description="Sort column"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
    db: Session = Depends(get_db),
):
    """
    Returns the Level 1 top-level program group report (~30 rows) plus scope-wide total row.
    Calculated 100% server-side in PostgreSQL. Zero raw CRM dataset records are sent to client.
    """
    try:
        data = get_program_report_top_level(
            db=db,
            academic_year=academic_year,
            campus=campus,
            from_date=from_date,
            to_date=to_date,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return {"success": True, "data": data}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load program report: {str(exc)}",
        )


@router.get("/report/children")
def get_program_children(
    level: str = Query(..., description="Child level: 'program', 'lead_type', 'main_source', 'report_source' (or legacy aliases 'branch', 'source_category', 'sub_source')"),
    academic_year: Optional[int] = Query(None, description="Academic year (CY)"),
    campus: Optional[str] = Query(None, description="Campus filter"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    program_group: Optional[str] = Query(None, description="Parent program group for level='program'/'branch'"),
    program_code: Optional[str] = Query(None, description="Parent program code"),
    program: Optional[str] = Query(None, description="Alias for program_code or program name"),
    lead_type: Optional[str] = Query(None, description="Parent lead type (IN HOUSE, OUT SOURCED, OTHERS)"),
    source_category: Optional[str] = Query(None, description="Legacy alias for lead_type"),
    main_source: Optional[str] = Query(None, description="Parent main source (Career_360, Direct, Website, etc.)"),
    report_source: Optional[str] = Query(None, description="Parent report source"),
    sort_by: str = Query("cy_leads", description="Sort column"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
    db: Session = Depends(get_db),
):
    """
    Lazy hierarchical child loader (5-level drill-down):
    - Level 2 (program / branch): returns programs belonging to program_group
    - Level 3 (lead_type / source_category): returns lead types (IN HOUSE, OUT SOURCED, OTHERS) for program
    - Level 4 (main_source / sub_source): returns main sources (Direct, Website, Career_360, etc.) for program + lead_type
    - Level 5 (report_source): returns report sources for program + lead_type + main_source
    """
    # Normalize level aliases
    norm_level = level.lower().strip()
    if norm_level == "branch":
        norm_level = "program"
    elif norm_level == "source_category":
        norm_level = "lead_type"
    elif norm_level == "sub_source":
        norm_level = "main_source"

    valid_levels = ("program", "lead_type", "main_source", "report_source")
    if norm_level not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hierarchy level '{level}'. Must be one of {valid_levels}",
        )

    # Normalize parameters
    effective_pcode = (program_code or program or "").strip() or None
    effective_lead_type = (lead_type or source_category or "").strip() or None
    effective_main_src = (main_source or "").strip() or None

    if norm_level == "program" and not program_group:
        raise HTTPException(
            status_code=400,
            detail="Parameter 'program_group' is required when level='program'",
        )

    if norm_level in ("lead_type", "main_source", "report_source") and not effective_pcode:
        raise HTTPException(
            status_code=400,
            detail=f"Parameter 'program_code' or 'program' is required when level='{level}'",
        )

    if norm_level in ("main_source", "report_source") and not effective_lead_type:
        raise HTTPException(
            status_code=400,
            detail=f"Parameter 'lead_type' is required when level='{level}'",
        )

    if norm_level == "report_source" and not effective_main_src:
        raise HTTPException(
            status_code=400,
            detail="Parameter 'main_source' is required when level='report_source'",
        )

    try:
        data = get_program_hierarchy_children(
            db=db,
            level=norm_level,
            academic_year=academic_year,
            campus=campus,
            from_date=from_date,
            to_date=to_date,
            program_group=program_group,
            program_code=effective_pcode,
            lead_type=effective_lead_type,
            main_source=effective_main_src,
            report_source=report_source,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return {"success": True, "data": data}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load program children for level '{level}': {str(exc)}",
        )


@router.get("/insights")
def get_program_insights_endpoint(
    program_group: str = Query(..., description="Program group name (e.g. CSE, MBA, B.Sc.)"),
    academic_year: Optional[int] = Query(None, description="Academic year (CY)"),
    campus: Optional[str] = Query(None, description="Campus filter"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    Returns deep diagnostic AI insights for a specific program group:
    - Overall Admissions & Leads YoY Trajectory (Growth vs Drop)
    - Lead Types Breakdown (Working Good vs Underperforming / Drag)
    - Top Sources Performance (Contributing Drivers vs Declining)
    - Actionable AI Takeaways & Recommendations
    """
    try:
        data = get_program_insights(
            db=db,
            program_group=program_group,
            academic_year=academic_year,
            campus=campus,
            from_date=from_date,
            to_date=to_date,
        )
        return {"success": True, "data": data}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate program insights for '{program_group}': {str(exc)}",
        )


