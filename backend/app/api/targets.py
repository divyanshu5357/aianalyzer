"""
FastAPI Target Engine & Reconciliation Endpoints.
Exposes Target vs Actual performance comparison and target workbook ingestion.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.analytics.target_engine import get_target_performance
from app.ingestion.target_executor import execute_target_ingestion

router = APIRouter(
    prefix="/api/targets",
    tags=["Targets"],
)


@router.get("/performance")
def get_target_vs_actual_performance(
    academic_year: Optional[int] = Query(None, description="Academic year to evaluate"),
    campus: Optional[str] = Query(None, description="Campus filter"),
    dimension_type: Optional[str] = Query(None, description="Dimension breakdown type (program, state, source, campus, overall)"),
    month: Optional[int] = Query(None, description="Filter specific month (1..12)"),
    db: Session = Depends(get_db),
):
    """
    Returns Target vs Actual performance comparison metrics.
    If actual data for a month/dimension is absent or in the future, returns actual as null ('N/A').
    """
    if academic_year is None:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)

    return get_target_performance(
        db=db,
        academic_year=academic_year,
        campus=campus,
        dimension_type=dimension_type,
        month=month,
    )


@router.post("/execute/{dataset_id}")
def execute_target_dataset(
    dataset_id: str,
    academic_year: Optional[int] = Query(None),
    campus_name: str = Query("All"),
    db: Session = Depends(get_db),
):
    """
    Ingests staged target records for dataset_id into analytics.targets.
    """
    if academic_year is None:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)
    res = execute_target_ingestion(
        db=db,
        dataset_id=dataset_id,
        academic_year=academic_year,
        campus_name=campus_name,
    )
    return res
