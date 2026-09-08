"""
API endpoints for State-Wise Analysis with strict lazy hierarchical loading.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.analytics.state_service import (
    get_state_report_top_level,
    get_state_hierarchy_children,
)

router = APIRouter(prefix="/api/states", tags=["State Wise Analysis"])


@router.get("/report")
def get_state_report(
    academic_year: Optional[int] = Query(None, description="Academic year (CY)"),
    campus: Optional[str] = Query(None, description="Campus filter (e.g. Mohali, All)"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    sort_by: str = Query("cy_leads", description="Sort column"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
    db: Session = Depends(get_db),
):
    """
    Returns the Level 1 top-level State report (~36 rows) plus scope-wide total row.
    Calculated 100% server-side in PostgreSQL. Zero raw CRM dataset records are sent to client.
    """
    try:
        data = get_state_report_top_level(
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
            detail=f"Failed to load state report: {str(exc)}",
        )


@router.get("/report/children")
def get_state_children(
    level: str = Query(..., description="Child level: 'source_category' or 'sub_source'"),
    state: str = Query(..., description="Parent state (e.g. Punjab)"),
    source_category: Optional[str] = Query(None, description="Parent source category for level='sub_source'"),
    academic_year: Optional[int] = Query(None, description="Academic year (CY)"),
    campus: Optional[str] = Query(None, description="Campus filter"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    sort_by: str = Query("cy_leads", description="Sort column"),
    sort_order: str = Query("desc", description="Sort direction (asc, desc)"),
    db: Session = Depends(get_db),
):
    """
    Lazy hierarchical child loader:
    - source_category: returns source categories (IN HOUSE, OUT SOURCED, OTHERS) for state
    - sub_source: returns specific sources (Google, Direct, Website, etc.) for state + source_category
    """
    valid_levels = ("source_category", "sub_source")
    if level not in valid_levels:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hierarchy level '{level}'. Must be one of {valid_levels}",
        )

    if not state or not state.strip():
        raise HTTPException(
            status_code=400,
            detail="Parameter 'state' is required.",
        )

    if level == "sub_source" and not source_category:
        raise HTTPException(
            status_code=400,
            detail="Parameter 'source_category' is required when level='sub_source'",
        )

    try:
        data = get_state_hierarchy_children(
            db=db,
            level=level,
            academic_year=academic_year,
            campus=campus,
            from_date=from_date,
            to_date=to_date,
            state=state,
            source_category=source_category,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return {"success": True, "data": data}
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load state children for level '{level}': {str(exc)}",
        )
