from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.analytics.source_performance import calculate_source_performance
from app.analytics.source_insights import build_source_insights


router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
)


@router.get("/source-insights")
def source_insights(
    year: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Return business insights about
    marketing-source performance.
    """

    source_rows = calculate_source_performance(
        db,
        year,
    )

    insights = build_source_insights(
        source_rows
    )

    return {
        "year": year,
        **insights,
    }
