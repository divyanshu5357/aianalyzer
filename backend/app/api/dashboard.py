from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.database.repository import get_active_dataset
from app.agent.agent_service import get_active_dataset_years
from app.analytics.dashboard import (
    get_dashboard_overview,
    get_insights,
    get_top_performers,
    get_entity_detail,
    get_exploration_data,
    get_manual_comparison,
    get_monthly_trend,
    get_performance_rankings,
    get_dashboard_filter_options,
)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


@router.get("/options")
def get_filter_options(
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        return {
            "academic_sessions": [],
            "campuses": [],
            "states": [],
            "sources": [],
            "programs": [],
        }
    return get_dashboard_filter_options(db, dataset_id, academic_session)


@router.get("/overview")
def get_overview(
    academic_session: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    return get_dashboard_overview(
        db=db,
        dataset_id=dataset_id,
        academic_session=academic_session,
        campus=campus,
        state=state,
        source=source,
        program=program,
    )


@router.get("/insights")
def get_dashboard_insights(
    academic_session: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    cy_year, py_year = get_active_dataset_years(db, dataset_id)
    return get_insights(
        db=db,
        dataset_id=dataset_id,
        cy_year=cy_year,
        py_year=py_year,
        academic_session=academic_session,
        campus=campus,
        state=state,
        source=source,
        program=program,
    )


@router.get("/top-performers")
def get_dashboard_top_performers(
    metric: str = Query("admission", pattern="^(leads|admission|conversion_rate)$"),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    return get_top_performers(db, dataset_id, metric, limit)


@router.get("/entity/{dimension}/{value}")
def get_dashboard_entity_detail(
    dimension: str,
    value: str,
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    cy_year, py_year = get_active_dataset_years(db, dataset_id)
    detail = get_entity_detail(db, dataset_id, dimension, value, cy_year, py_year)
    if not detail:
        raise HTTPException(status_code=404, detail="Entity or dimension not found.")
    return detail


@router.get("/explore")
def explore_performance(
    dimension: str = Query("program_name"),
    metric: str = Query("admission", pattern="^(leads|admission|conversion_rate)$"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    data = get_exploration_data(db, dataset_id, dimension, metric, limit)
    if data is None:
        raise HTTPException(status_code=404, detail="Dimension not found or has no data.")
    return data


@router.get("/compare")
def compare_entities(
    dimension: str = Query("source"),
    value_a: str = Query(...),
    value_b: str = Query(...),
    metric: str = Query("admission", pattern="^(leads|admission|conversion_rate)$"),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    data = get_manual_comparison(db, dataset_id, dimension, value_a, value_b, metric)
    if data is None:
        raise HTTPException(status_code=404, detail="Dimension not found or has no data.")
    return data


@router.get("/dimension-values")
def get_dim_values(dimension: str, db: Session = Depends(get_db)):
    import re
    from sqlalchemy import text
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    safe_dim = re.sub(r"[^\w_]", "", dimension)
    sql = f"""
        SELECT DISTINCT "{safe_dim}" as val 
        FROM analytics.uploaded_metrics 
        WHERE dataset_id = :ds_id AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
        ORDER BY val ASC
        LIMIT 100
    """
    rows = db.execute(text(sql), {"ds_id": str(dataset_id)}).fetchall()
    return [r[0] for r in rows if r[0]]


@router.get("/monthly-trend")
def get_dashboard_monthly_trend(
    academic_session: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    return get_monthly_trend(
        db=db,
        dataset_id=dataset_id,
        academic_session=academic_session,
        campus=campus,
        state=state,
        source=source,
        program=program,
    )


@router.get("/performance-rankings")
def get_dashboard_performance_rankings(
    dimension: str = Query("program_name"),
    academic_session: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    dataset_id = get_active_dataset(db)
    if not dataset_id:
        raise HTTPException(status_code=400, detail="No active dataset selected.")
    return get_performance_rankings(
        db=db,
        dataset_id=dataset_id,
        dimension=dimension,
        academic_session=academic_session,
        campus=campus,
        state=state,
        source=source,
        program=program,
    )
