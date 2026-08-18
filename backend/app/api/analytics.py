from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.analytics.data_source import (
    get_analytics_funnel,
    get_analytics_source_performance,
    get_analytics_source_hierarchy,
    get_analytics_source_detail,
)

router = APIRouter(
    prefix="/api/analytics",
    tags=["Analytics"],
)


@router.get("/funnel")
def get_funnel(
    year: int = Query(...),
    dataset_id: str | None = Query(None),
    source_type: str = Query("auto"),
    db: Session = Depends(get_db),
):
    return get_analytics_funnel(
        db=db,
        year=year,
        dataset_id=dataset_id,
        source_type=source_type,
    )


@router.get("/source-hierarchy")
def get_source_hierarchy(
    year: int = Query(...),
    dataset_id: str | None = Query(None),
    source_type: str = Query("auto"),
    db: Session = Depends(get_db),
):
    return {
        "year": year,
        "sources": get_analytics_source_hierarchy(
            db=db,
            year=year,
            dataset_id=dataset_id,
            source_type=source_type,
        ),
    }


@router.get("/source-detail")
def source_detail(
    year: int = Query(...),
    main_source: str = Query(...),
    source: str = Query(...),
    dataset_id: str | None = Query(None),
    source_type: str = Query("auto"),
    db: Session = Depends(get_db),
):
    return get_analytics_source_detail(
        db=db,
        year=year,
        main_source=main_source,
        source=source,
        dataset_id=dataset_id,
        source_type=source_type,
    )


@router.get("/source-performance")
def get_source_performance(
    year: int = Query(...),
    dataset_id: str | None = Query(None),
    source_type: str = Query("auto"),
    db: Session = Depends(get_db),
):
    return {
        "year": year,
        "sources": get_analytics_source_performance(
            db=db,
            year=year,
            dataset_id=dataset_id,
            source_type=source_type,
        ),
    }