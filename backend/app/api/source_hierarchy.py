from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.analytics.source_hierarchy import calculate_source_hierarchy


router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
)


@router.get("/source-hierarchy")
def source_hierarchy(
    year: int = Query(...),
    db: Session = Depends(get_db),
):
    return {
        "year": year,
        "sources": calculate_source_hierarchy(
            db,
            year,
        ),
    }
