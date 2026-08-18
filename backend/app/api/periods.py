"""
Periods API — list, query, activate, and compare academic periods.

Endpoints:
  GET  /api/periods                          → all available periods
  GET  /api/periods/{label}                  → all versions for a period
  POST /api/periods/{label}/activate/{id}    → activate a specific version
  GET  /api/periods/compare                  → compare two periods
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.repository import (
    list_all_periods,
    get_datasets_by_period,
    set_period_active,
    get_active_period_for_label,
    get_period_pair,
)
from app.analytics.period_resolver import compare_periods, get_historical_trend, VALID_DIMENSIONS
from app.analytics.workspace import (
    get_workspace_filter_options,
    query_workspace_comparison,
)

router = APIRouter(prefix="/api/periods", tags=["Periods"])


from app.analytics.period_resolver import (
    compare_periods,
    get_historical_trend,
    list_all_analytical_years,
    VALID_DIMENSIONS,
)

@router.get("")
def get_all_periods(db: Session = Depends(get_db)):
    """
    Return a summary of all distinct academic periods available in the system
    along with available analytical years (e.g. [2023, 2024, 2025, 2026]).
    """
    periods = list_all_periods(db)
    years = list_all_analytical_years(db)
    return {
        "total": len(periods),
        "periods": periods,
        "years": years,
    }


@router.get("/years")
def get_analytical_years(db: Session = Depends(get_db)):
    """
    Return all available analytical years (e.g. [2023, 2024, 2025, 2026]).
    """
    years = list_all_analytical_years(db)
    return {
        "years": years,
        "default_year_a": years[-1] if years else None,
        "default_year_b": years[-2] if len(years) >= 2 else (years[0] if years else None),
    }


@router.get("/compare")
def compare_two_periods(
    period_a: str = Query(..., description="Year A or period label, e.g. '2025' or '2025-26'"),
    period_b: str = Query(..., description="Year B or period label, e.g. '2026' or '2024-25'"),
    metric: str = Query("admissions", description="Metric: leads | admissions | cucet | conversion_rate"),
    dimension: str = Query("program_name", description="Grouping dimension"),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Compare a metric across two analytical years or periods by dimension.
    """
    if str(period_a).strip() == str(period_b).strip():
        raise HTTPException(
            status_code=400,
            detail="Please select two different years for comparison.",
        )

    if dimension not in VALID_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dimension '{dimension}'. Valid: {sorted(VALID_DIMENSIONS)}",
        )

    valid_metrics = {"leads", "admissions", "admission", "cucet", "conversion_rate"}
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric '{metric}'. Valid: {sorted(valid_metrics)}",
        )

    try:
        result = compare_periods(
            db=db,
            metric=metric,
            period_a_label=period_a,
            period_b_label=period_b,
            dimension=dimension,
            limit=limit,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/trend")
def get_trend(
    metric: str = Query("admissions", description="Metric: leads | admissions | cucet | conversion_rate"),
    dimension: str = Query("program_name", description="Grouping dimension"),
    db: Session = Depends(get_db),
):
    """
    Get historical trend for a metric across all active periods by dimension.
    """
    if dimension not in VALID_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dimension '{dimension}'. Valid: {sorted(VALID_DIMENSIONS)}",
        )

    valid_metrics = {"leads", "admissions", "admission", "cucet", "conversion_rate"}
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric '{metric}'. Valid: {sorted(valid_metrics)}",
        )

    try:
        return get_historical_trend(db, metric, dimension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/workspace")
def get_analytics_workspace(
    workspace: str = Query(..., description="source | program"),
    period_a: str = Query(..., description="Baseline academic period label"),
    period_b: str = Query(..., description="Comparison academic period label"),
    metric: str = Query("leads", description="leads | admissions | conversion_rate"),
    performance: str = Query("all", description="all | increased | decreased"),
    sort_field: str = Query("absolute_change"),
    sort_direction: str = Query("desc", description="asc | desc"),
    display: str = Query("both", description="exact | percentage | both"),
    state: str | None = Query(None),
    source: str | None = Query(None),
    campus: str | None = Query(None),
    owner: str | None = Query(None),
    program: str | None = Query(None),
    specialization: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """BI-table source/program comparison with all work done in PostgreSQL."""
    try:
        return query_workspace_comparison(
            db,
            workspace=workspace,
            period_a_label=period_a,
            period_b_label=period_b,
            metric=metric,
            performance=performance,
            sort_field=sort_field,
            sort_direction=sort_direction,
            display=display,
            limit=limit,
            offset=offset,
            filters={
                "state": state,
                "source": source,
                "campus": campus,
                "owner": owner,
                "program": program,
                "specialization": specialization,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/workspace/options")
def get_analytics_workspace_options(
    workspace: str = Query(..., description="source | program"),
    period_a: str = Query(...),
    period_b: str = Query(...),
    db: Session = Depends(get_db),
):
    """Bounded filter values across the two active period datasets."""
    try:
        return get_workspace_filter_options(
            db,
            workspace=workspace,
            period_a_label=period_a,
            period_b_label=period_b,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{label}")
def get_period_versions(
    label: str,
    db: Session = Depends(get_db),
):
    """
    Return all uploaded versions for a given academic period label (e.g. "2025-26").
    Includes both active and historical versions.
    """
    versions = get_datasets_by_period(db, label)
    if not versions:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for period '{label}'.",
        )
    return {
        "academic_label": label,
        "total_versions": len(versions),
        "versions": versions,
    }


@router.post("/{label}/activate/{dataset_id}")
def activate_period_version(
    label: str,
    dataset_id: str,
    db: Session = Depends(get_db),
):
    """
    Activate a specific version of a period as the primary dataset for analytics.

    This is used to:
    - Switch back to an older version for audit/recovery
    - Promote a new_version upload to active after confirmation

    Only one version per period can be active at a time.
    """
    # Verify the dataset exists and belongs to the claimed period
    versions = get_datasets_by_period(db, label)
    ids = [v["dataset_id"] for v in versions]

    if dataset_id not in ids:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{dataset_id}' not found under period '{label}'.",
        )

    set_period_active(db, dataset_id)
    db.commit()

    return {
        "status": "activated",
        "academic_label": label,
        "active_dataset_id": dataset_id,
    }
