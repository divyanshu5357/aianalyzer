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
    level: str = Query(..., description="Child level: 'branch', 'source_category', or 'sub_source'"),
    academic_year: Optional[int] = Query(None, description="Academic year (CY)"),
    campus: Optional[str] = Query(None, description="Campus filter"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    program_group: Optional[str] = Query(None, description="Parent program group for level='branch'"),
    program_code: Optional[str] = Query(None, description="Parent program code for level='source_category' or 'sub_source'"),
    source_category: Optional[str] = Query(None, description="Parent source category for level='sub_source'"),
    sort_by: str = Query("cy_leads", description="Sort column"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
    db: Session = Depends(get_db),
):
    """
    Lazy hierarchical child loader:
    - branch: returns branches belonging to program_group
    - source_category: returns source categories (IN HOUSE, OUT SOURCED, OTHERS) for program_code
    - sub_source: returns specific sources (Google, Direct, Website, etc.) for program_code + source_category
    """
    valid_levels = ("branch", "source_category", "sub_source")
    if level not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hierarchy level '{level}'. Must be one of {valid_levels}",
        )

    if level == "branch" and not program_group:
        raise HTTPException(
            status_code=400,
            detail="Parameter 'program_group' is required when level='branch'",
        )

    if level in ("source_category", "sub_source") and not program_code:
        raise HTTPException(
            status_code=400,
            detail=f"Parameter 'program_code' is required when level='{level}'",
        )

    if level == "sub_source" and not source_category:
        raise HTTPException(
            status_code=400,
            detail="Parameter 'source_category' is required when level='sub_source'",
        )

    try:
        data = get_program_hierarchy_children(
            db=db,
            level=level,
            academic_year=academic_year,
            campus=campus,
            from_date=from_date,
            to_date=to_date,
            program_group=program_group,
            program_code=program_code,
            source_category=source_category,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return {"success": True, "data": data}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load program children for level '{level}': {str(exc)}",
        )
