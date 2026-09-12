from datetime import datetime
import logging
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.analytics.scope_resolver import resolve_dataset_scope
from app.analytics.dashboard import (
    get_dashboard_overview,
    get_insights,
    get_top_performers,
    get_entity_detail,
    get_exploration_data,
    get_manual_comparison,
    get_hierarchy_clusters,
    get_hierarchy_drilldown,
    get_monthly_trend,
    get_performance_rankings,
    get_dashboard_filter_options,
)
from app.analytics.geography_gender_service import (
    get_admissions_by_gender,
    get_admissions_by_india_state,
    get_international_admissions,
)
from app.analytics.period_helper import get_active_or_max_academic_year
import time

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
)

_DASH_API_CACHE: dict[str, tuple[float, Any]] = {}
_DASH_API_CACHE_TTL = 86400.0  # 24 hours (invalidated on dataset upload/reset)


def clear_dash_api_cache():
    _DASH_API_CACHE.clear()


def _get_dash_cache(key: str) -> Optional[Any]:
    if key in _DASH_API_CACHE:
        ts, val = _DASH_API_CACHE[key]
        if time.time() - ts < _DASH_API_CACHE_TTL:
            return val
    return None


def _set_dash_cache(key: str, val: Any) -> None:
    _DASH_API_CACHE[key] = (time.time(), val)


def _validate_date_range(from_date: Optional[str], to_date: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Validate from_date and to_date parameters (ISO YYYY-MM-DD, from_date <= to_date)."""
    if not from_date and not to_date:
        return None, None
    if (from_date and not to_date) or (to_date and not from_date):
        raise HTTPException(status_code=400, detail="Both from_date and to_date must be provided together.")
    try:
        f_dt = datetime.strptime(from_date.strip(), "%Y-%m-%d")
        t_dt = datetime.strptime(to_date.strip(), "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")
    if f_dt > t_dt:
        raise HTTPException(status_code=400, detail="from_date cannot be after to_date.")
    return from_date.strip(), to_date.strip()


def _parse_years_param(
    years: Optional[str] = None,
    academic_year: Optional[int] = None,
    academic_session: Optional[str] = None,
) -> Optional[List[int]]:
    year_list = []
    if years:
        year_list.extend([int(y.strip()) for y in years.split(",") if y.strip().isdigit()])
    if academic_year and academic_year not in year_list:
        year_list.append(int(academic_year))
    if academic_session and str(academic_session).strip().isdigit():
        ay = int(str(academic_session).strip())
        if ay not in year_list:
            year_list.append(ay)
    return year_list if year_list else None


@router.get("/scope")
def get_resolved_scope(
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns resolved dataset scope metadata and included enabled datasets."""
    year_list = _parse_years_param(years, academic_year, academic_session)
    return resolve_dataset_scope(db, campus=campus, years=year_list)


@router.get("/options")
def get_filter_options(
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    year_list = _parse_years_param(years, academic_year, academic_session)
    return get_dashboard_filter_options(db, campus=campus, years=year_list)


@router.get("/overview")
def get_overview(
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)

    cache_key = f"overview:{campus}:{year_list}:{state}:{source}:{program}:{valid_from}:{valid_to}"
    cached = _get_dash_cache(cache_key)
    if cached is not None:
        return cached

    res = get_dashboard_overview(
        db=db,
        campus=campus,
        years=year_list,
        state=state,
        source=source,
        program=program,
        from_date=valid_from,
        to_date=valid_to,
    )
    _set_dash_cache(cache_key, res)
    return res


@router.get("/insights")
def get_dashboard_insights(
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)

    cache_key = f"insights:{campus}:{year_list}:{state}:{source}:{program}:{valid_from}:{valid_to}"
    cached = _get_dash_cache(cache_key)
    if cached is not None:
        return cached

    res = get_insights(
        db=db,
        campus=campus,
        years=year_list,
        state=state,
        source=source,
        program=program,
        from_date=valid_from,
        to_date=valid_to,
    )
    _set_dash_cache(cache_key, res)
    return res


def _normalize_metric(metric: str) -> str:
    metric_clean = metric.lower().strip()
    if metric_clean in ("admissions", "admission"):
        return "admission"
    elif metric_clean in ("leads", "lead"):
        return "leads"
    return metric_clean


@router.get("/top-performers")
def get_dashboard_top_performers(
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    metric: str = Query("admission", pattern="^(leads?|admissions?|conversion_rate|cucet)$"),
    limit: int = Query(5, ge=1, le=20),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)

    metric_clean = _normalize_metric(metric)

    return get_top_performers(
        db=db,
        campus=campus,
        years=year_list,
        metric=metric_clean,
        limit=limit,
        from_date=valid_from,
        to_date=valid_to,
    )
    year_list = []
    if years:
        year_list.extend([int(y.strip()) for y in years.split(",") if y.strip().isdigit()])
    if academic_year and academic_year not in year_list:
        year_list.append(int(academic_year))
    if academic_session and str(academic_session).strip().isdigit():
        ay = int(str(academic_session).strip())
        if ay not in year_list:
            year_list.append(ay)
    return year_list if year_list else None


@router.get("/entity")
def get_dashboard_entity_detail_query(
    dimension: str = Query(...),
    value: str = Query(...),
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)
    detail = get_entity_detail(
        db=db,
        dimension=dimension,
        value=value,
        campus=campus,
        years=year_list,
        from_date=valid_from,
        to_date=valid_to,
    )
    if not detail:
        raise HTTPException(status_code=404, detail=f"Entity '{value}' for dimension '{dimension}' not found.")
    return detail


@router.get("/entity/{dimension}/{value:path}")
def get_dashboard_entity_detail(
    dimension: str,
    value: str,
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)
    detail = get_entity_detail(
        db=db,
        dimension=dimension,
        value=value,
        campus=campus,
        years=year_list,
        from_date=valid_from,
        to_date=valid_to,
    )
    if not detail:
        raise HTTPException(status_code=404, detail=f"Entity '{value}' for dimension '{dimension}' not found.")
    return detail


@router.get("/explore")
def explore_performance(
    dimension: str = Query("program_name"),
    metric: str = Query("admission", pattern="^(leads|admission|conversion_rate)$"),
    limit: int = Query(10, ge=1, le=100),
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    year_list = _parse_years_param(years, academic_year, academic_session)

    data = get_exploration_data(
        db=db,
        dimension=dimension,
        metric=metric,
        campus=campus,
        years=year_list,
        limit=limit,
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Dimension not found or has no data.")
    return data


@router.get("/hierarchy/clusters")
def get_hierarchy_clusters_endpoint(
    dimension: str = Query("source"),
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    year_list = _parse_years_param(years, academic_year, academic_session)

    return get_hierarchy_clusters(
        db=db,
        dimension=dimension,
        campus=campus,
        years=year_list,
    )


@router.get("/hierarchy/drilldown")
def get_hierarchy_drilldown_endpoint(
    dimension: str = Query("source"),
    cluster_name: str = Query(...),
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    year_list = _parse_years_param(years, academic_year, academic_session)

    return get_hierarchy_drilldown(
        db=db,
        dimension=dimension,
        cluster_name=cluster_name,
        campus=campus,
        years=year_list,
    )


@router.get("/compare")
def compare_entities(
    dimension: str = Query("source"),
    value_a: Optional[str] = Query(None),
    value_b: Optional[str] = Query(None),
    value_c: Optional[str] = Query(None),
    entities: Optional[str] = Query(None),
    metric: str = Query("admission", pattern="^(leads|admission|conversion_rate)$"),
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    year_list = _parse_years_param(years, academic_year, academic_session)

    entities_list = None
    if entities:
        entities_list = [e.strip() for e in entities.split(",") if e.strip()]

    data = get_manual_comparison(
        db=db,
        dimension=dimension,
        value_a=value_a,
        value_b=value_b,
        value_c=value_c,
        entities_list=entities_list,
        metric=metric,
        campus=campus,
        years=year_list,
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Dimension not found or has no data.")
    return data


@router.get("/dimension-values")
def get_dim_values(
    dimension: str,
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    from sqlalchemy import text
    from app.analytics.dashboard import _resolve_dimension_col
    year_list = _parse_years_param(years, academic_year, academic_session)

    scope_data = resolve_dataset_scope(db, campus=campus, years=year_list)
    dataset_ids = scope_data["dataset_ids"]
    if not dataset_ids:
        return []

    safe_dim = _resolve_dimension_col(dimension)
    
    # Try querying dashboard_agg first by total volume for dashboard_agg columns
    if safe_dim in ("source", "main_source", "state", "program_name", "campus_name", "lead_type"):
        try:
            where_parts = [f'"{safe_dim}" IS NOT NULL', f'"{safe_dim}" != \'\'']
            params: dict[str, Any] = {}
            if campus and campus.lower() != "all":
                where_parts.append('LOWER("campus_name") = LOWER(:campus)')
                params["campus"] = campus
            if scope_data["scope"]["years"]:
                where_parts.append('academic_year IN :years')
                params["years"] = tuple(scope_data["scope"]["years"])
            if safe_dim in ("source", "main_source"):
                where_parts.append(f'"{safe_dim}" !~ \'^[0-9]{{10,12}}$\'')
            where_sql = " AND ".join(where_parts)

            sql_agg = text(
                f'SELECT "{safe_dim}", SUM(leads_cy) as tot '
                f'FROM analytics.dashboard_agg '
                f'WHERE {where_sql} '
                f'GROUP BY "{safe_dim}" '
                f'ORDER BY tot DESC, "{safe_dim}" ASC LIMIT 100'
            )
            rows = db.execute(sql_agg, params).fetchall()
            if rows:
                return [r[0] for r in rows if r[0]]
        except Exception as e:
            import logging
            logging.exception("get_dim_values dashboard_agg query failed: %s", e)
            db.rollback()

    ds_quoted = ",".join(f"'{str(d)}'" for d in dataset_ids)
    phone_filter = f' AND "{safe_dim}" !~ \'^[0-9]{{10,12}}$\'' if safe_dim in ("source", "main_source") else ""
    sql = text(
        f'SELECT "{safe_dim}", COUNT(*) as cnt '
        f'FROM analytics.uploaded_metrics '
        f'WHERE dataset_id::text IN ({ds_quoted}) AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != \'\'{phone_filter} '
        f'GROUP BY "{safe_dim}" '
        f'ORDER BY cnt DESC, "{safe_dim}" ASC LIMIT 100'
    )
    rows = db.execute(sql).fetchall()
    if rows:
        return [r[0] for r in rows if r[0]]

    # Final fallback across all available uploaded metrics if scope lacks dimension entries
    fallback_sql = text(
        f'SELECT DISTINCT "{safe_dim}" FROM analytics.uploaded_metrics '
        f'WHERE "{safe_dim}" IS NOT NULL AND "{safe_dim}" != \'\'{phone_filter} '
        f'ORDER BY "{safe_dim}" ASC LIMIT 100'
    )
    fb_rows = db.execute(fallback_sql).fetchall()
    return [r[0] for r in fb_rows if r[0]]



@router.get("/monthly-trend")
def get_dashboard_monthly_trend(
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    metric: Optional[str] = Query("admissions"),
    academic_session: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)

    cache_key = f"monthly:{campus}:{year_list}:{metric}:{state}:{source}:{program}:{valid_from}:{valid_to}"
    cached = _get_dash_cache(cache_key)
    if cached is not None:
        return cached

    res = get_monthly_trend(
        db=db,
        campus=campus,
        years=year_list,
        metric=metric or "admissions",
        state=state,
        source=source,
        program=program,
        from_date=valid_from,
        to_date=valid_to,
    )
    _set_dash_cache(cache_key, res)
    return res


@router.get("/performance-rankings")
def get_dashboard_performance_rankings(
    dimension: str = Query("program_name"),
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)

    cache_key = f"rankings:{dimension}:{campus}:{year_list}:{state}:{source}:{program}:{valid_from}:{valid_to}"
    cached = _get_dash_cache(cache_key)
    if cached is not None:
        return cached

    res = get_performance_rankings(
        db=db,
        dimension=dimension,
        campus=campus,
        years=year_list,
        state=state,
        source=source,
        program=program,
        from_date=valid_from,
        to_date=valid_to,
    )
    _set_dash_cache(cache_key, res)
    return res


@router.get("/data-control")
@router.get("/data-control/history")
def get_data_control_history(db: Session = Depends(get_db)):
    """Returns Data Control / Upload History directly from system.datasets with real PostgreSQL counts."""
    rows = db.execute(
        text("""
            SELECT 
                d.id,
                d.original_filename,
                d.workbook_type,
                d.academic_label,
                d.academic_year,
                d.month,
                d.campus_name,
                COALESCE(d.row_count, 0) as row_count,
                COALESCE(d.distinct_prospect_count, 0) as distinct_prospect_count,
                COALESCE(d.rows_inserted, d.row_count, 0) as rows_inserted,
                COALESCE(d.rows_updated, 0) as rows_updated,
                d.status,
                d.is_active,
                d.is_analytics_enabled,
                d.created_at
            FROM system.datasets d
            ORDER BY d.created_at DESC;
        """)
    ).mappings().all()

    return {
        "status": "success",
        "total_datasets": len(rows),
        "history": [dict(r) for r in rows],
    }


@router.get("/metrics")
def get_unified_metrics_contract(
    campus: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Unified analytics contract returning CY, PY, Target, Variance, and Growth metrics."""
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)

    overview = get_dashboard_overview(
        db=db,
        campus=campus,
        years=year_list,
        state=state,
        source=source,
        program=program,
        from_date=valid_from,
        to_date=valid_to,
    )
    trend = get_monthly_trend(
        db=db,
        campus=campus,
        years=year_list,
        metric="admissions",
        state=state,
        source=source,
        program=program,
        from_date=valid_from,
        to_date=valid_to,
    )

    kpis = overview.get("kpis", {})
    cy_adm = kpis.get("admissions", {}).get("cy", 0)
    py_adm = kpis.get("admissions", {}).get("py")
    cy_lead = kpis.get("leads", {}).get("cy", 0)
    py_lead = kpis.get("leads", {}).get("py")

    cy_trend_adm = sum(r.get("cy") or 0 for r in trend if r.get("cy") is not None)
    py_trend_adm = sum(r.get("py") or 0 for r in trend if r.get("py") is not None)

    cy_diff = cy_adm - cy_trend_adm
    py_diff = (py_adm or 0) - py_trend_adm

    if cy_diff != 0 or py_diff != 0:
        logger.error(
            f"RECONCILIATION MISMATCH -> KPI_CY: {cy_adm}, MONTHLY_CY: {cy_trend_adm}, DIFF_CY: {cy_diff} | "
            f"KPI_PY: {py_adm}, MONTHLY_PY: {py_trend_adm}, DIFF_PY: {py_diff} | Campus: {campus}"
        )

    return {
        "selected_year": overview.get("current_year"),
        "previous_year": overview.get("previous_year"),
        "cy": {
            "leads": cy_lead,
            "admissions": cy_adm,
            "conversion_rate": kpis.get("conversion_rate", {}).get("cy"),
        },
        "py": {
            "leads": py_lead,
            "admissions": py_adm,
            "conversion_rate": kpis.get("conversion_rate", {}).get("py"),
        },
        "growth": {
            "admissions_pct": kpis.get("admissions", {}).get("growth_pct"),
            "leads_pct": kpis.get("leads", {}).get("growth_pct"),
        },
        "monthly_trend": trend,
        "reconciliation": {
            "passed": (cy_diff == 0 and py_diff == 0),
            "cy_kpi": cy_adm,
            "cy_monthly_sum": cy_trend_adm,
            "py_kpi": py_adm,
            "py_monthly_sum": py_trend_adm,
        },
    }


@router.get("/admissions-by-gender")
@router.get("/admissions-gender")
def get_gender_admissions(
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    lead_type: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)
    selected_year = year_list[0] if year_list else (academic_year or get_active_or_max_academic_year(db))

    cache_key = f"gender:{selected_year}:{campus}:{month}:{lead_type}:{program}:{source}:{state}:{valid_from}:{valid_to}"
    cached = _get_dash_cache(cache_key)
    if cached is not None:
        return cached

    res = get_admissions_by_gender(
        db=db,
        academic_year=selected_year,
        campus=campus,
        month=month,
        lead_type=lead_type,
        program=program,
        source=source,
        state=state,
        from_date=valid_from,
        to_date=valid_to,
    )
    _set_dash_cache(cache_key, res)
    return res


@router.get("/admissions-by-state")
@router.get("/admissions-state")
def get_india_state_admissions(
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    lead_type: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)
    selected_year = year_list[0] if year_list else (academic_year or get_active_or_max_academic_year(db))

    cache_key = f"state:{selected_year}:{campus}:{month}:{lead_type}:{program}:{source}:{valid_from}:{valid_to}"
    cached = _get_dash_cache(cache_key)
    if cached is not None:
        return cached

    res = get_admissions_by_india_state(
        db=db,
        academic_year=selected_year,
        campus=campus,
        month=month,
        lead_type=lead_type,
        program=program,
        source=source,
        from_date=valid_from,
        to_date=valid_to,
    )
    _set_dash_cache(cache_key, res)
    return res


@router.get("/international-admissions")
def get_outside_india_admissions(
    academic_year: Optional[int] = Query(None),
    academic_session: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    lead_type: Optional[str] = Query(None),
    program: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    years: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    valid_from, valid_to = _validate_date_range(from_date, to_date)
    year_list = _parse_years_param(years, academic_year, academic_session)
    selected_year = year_list[0] if year_list else (academic_year or get_active_or_max_academic_year(db))

    cache_key = f"international:{selected_year}:{campus}:{month}:{lead_type}:{program}:{source}:{valid_from}:{valid_to}"
    cached = _get_dash_cache(cache_key)
    if cached is not None:
        return cached

    res = get_international_admissions(
        db=db,
        academic_year=selected_year,
        campus=campus,
        month=month,
        lead_type=lead_type,
        program=program,
        source=source,
        from_date=valid_from,
        to_date=valid_to,
    )
    _set_dash_cache(cache_key, res)
    return res

