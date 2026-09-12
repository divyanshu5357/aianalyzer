import logging
import re
import time
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.analytics.scope_resolver import resolve_dataset_scope

logger = logging.getLogger(__name__)

_FILTER_OPTIONS_CACHE: dict[str, tuple[float, dict]] = {}
_FILTER_CACHE_TTL = 86400.0  # 24 hours (invalidated on dataset upload/reset)


def clear_filter_options_cache():
    _FILTER_OPTIONS_CACHE.clear()


def _resolve_dimension_col(dimension: str) -> str:
    """Map common business dimension aliases to physical DB column names."""
    norm = str(dimension).lower().strip()
    mapping = {
        "program": "program_name",
        "program_name": "program_name",
        "campus": "campus_name",
        "campus_name": "campus_name",
        "state": "state",
        "state_name": "state",
        "source": "source",
        "main_source": "source",
        "lead_type": "lead_type",
        "lead type": "lead_type",
        "leadtype": "lead_type",
        "cluster": "course_cluster",
        "course_cluster": "course_cluster",
        "city": "city",
        "zone": "zone",
        "counsellor": "owner",
        "counselor": "owner",
        "owner": "owner",
        "emp": "owner",
        "employee": "owner",
        "academic_session": "academic_year",
        "academic_year": "academic_year",
        "period": "academic_year",
    }
    col = mapping.get(norm, norm)
    return re.sub(r"[^\w_]", "", col)


def _build_scope_where(
    dataset_ids: list[Any],
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
) -> tuple[str, dict[str, Any]]:
    clauses = ["1=1"]
    params: dict[str, Any] = {}
    if state and state.lower() != "all":
        clauses.append("LOWER(state) = LOWER(:state)")
        params["state"] = state
    if source and source.lower() != "all":
        clauses.append("LOWER(source) = LOWER(:source)")
        params["source"] = source
    if program and program.lower() != "all":
        clauses.append("LOWER(program_name) = LOWER(:program)")
        params["program"] = program
    return " AND ".join(clauses), params


def get_dashboard_filter_options(
    db: Session,
    campus: str | None = None,
    years: list[int] | str | None = None,
) -> dict[str, list[str]]:
    """Query dynamic, distinct non-null filter options available in resolved scope."""
    canonical_campus = (campus or 'all').strip().lower()
    canonical_years = str(sorted(years) if isinstance(years, list) else (years or 'all'))
    cache_key = f"{canonical_campus}:{canonical_years}"
    now = time.time()
    if cache_key in _FILTER_OPTIONS_CACHE:
        ts, cached_val = _FILTER_OPTIONS_CACHE[cache_key]
        if now - ts < _FILTER_CACHE_TTL:
            return cached_val

    # Also check if 'all:all' cache can serve if present
    if "all:all" in _FILTER_OPTIONS_CACHE and canonical_campus == "all" and canonical_years in ("all", "None", "[2026]"):
        ts, cached_val = _FILTER_OPTIONS_CACHE["all:all"]
        if now - ts < _FILTER_CACHE_TTL:
            return cached_val

    scope_data = resolve_dataset_scope(db, campus=campus, years=years)
    dataset_ids = scope_data["dataset_ids"]

    # 1. Quick Campus lookup from system.datasets (instant < 1ms)
    campus_rows = db.execute(text(
        "SELECT DISTINCT campus_name FROM system.datasets "
        "WHERE is_analytics_enabled = TRUE AND campus_name IS NOT NULL AND campus_name != '' "
        "ORDER BY campus_name ASC"
    )).fetchall()
    avail_campuses = [str(r[0]) for r in campus_rows if r[0]]
    if not avail_campuses:
        avail_campuses = ["Mohali"]

    # 2. Distinct Years from system.datasets (instant < 1ms)
    years_rows = db.execute(text(
        "SELECT DISTINCT academic_year FROM system.datasets "
        "WHERE is_analytics_enabled = TRUE AND academic_year IS NOT NULL "
        "ORDER BY academic_year DESC"
    )).fetchall()
    avail_years = [str(r[0]) for r in years_rows if r[0]]

    # 3. Canonical Lead Types (constant, instantaneous < 0.1ms)
    avail_lead_types = ["IN HOUSE", "OUT SOURCED", "OTHERS"]

    # 4. Scope filters for states, sources, programs
    where_parts = []
    params: dict[str, Any] = {}
    if campus and campus.lower() != "all":
        where_parts.append('LOWER("campus_name") = LOWER(:campus)')
        params["campus"] = campus
    if scope_data["scope"]["years"]:
        where_parts.append('academic_year IN :years')
        params["years"] = tuple(scope_data["scope"]["years"])
    base_where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # Helper for distinct values using index-friendly SELECT DISTINCT
    def get_distinct_fast(col_name: str, max_limit: int = 250) -> list[str]:
        col_where = f'{base_where} {"AND" if base_where else "WHERE"} "{col_name}" IS NOT NULL AND "{col_name}" != \'\''
        try:
            sql = text(f'SELECT DISTINCT "{col_name}" FROM analytics.dashboard_agg {col_where} ORDER BY "{col_name}" ASC LIMIT {max_limit}')
            rows = db.execute(sql, params).fetchall()
            vals = [str(r[0]).strip() for r in rows if r[0] and str(r[0]).strip()]
            if col_name in ("source", "main_source"):
                # Filter out pure phone numbers in Python (0.01ms vs 2000ms un-indexed regex on DB)
                vals = [v for v in vals if not re.match(r"^[0-9]{10,12}$", v)]
            return vals
        except Exception as e:
            logger.debug("Distinct query notice on %s: %s", col_name, e)
            db.rollback()
            return []

    distinct_states = get_distinct_fast("state")
    distinct_sources = get_distinct_fast("source")
    distinct_programs = get_distinct_fast("program_name", max_limit=300)

    # Dynamic date range from dashboard_agg or datasets
    from app.analytics.period_helper import get_active_or_max_academic_year
    cy_year = scope_data.get("cy_year") or get_active_or_max_academic_year(db)
    dt_row = db.execute(text("""
        SELECT MIN(COALESCE(created_month, admission_month)) as min_m,
               MAX(COALESCE(admission_month, created_month)) as max_m
        FROM analytics.dashboard_agg
        WHERE academic_year = :cy_year
    """), {"cy_year": cy_year}).fetchone()
    min_m = dt_row[0] if (dt_row and dt_row[0]) else f"{cy_year - 1}-11"
    max_m = dt_row[1] if (dt_row and dt_row[1]) else f"{cy_year}-10"
    min_date = f"{min_m}-01"
    import calendar
    try:
        max_y, max_month = int(max_m.split("-")[0]), int(max_m.split("-")[1])
        last_day = calendar.monthrange(max_y, max_month)[1]
        max_date = f"{max_m}-{last_day:02d}"
    except Exception:
        max_date = f"{max_m}-28"

    date_range = {
        "min_date": min_date,
        "max_date": max_date,
        "default_from": f"{cy_year - 1}-11-01" if min_date <= f"{cy_year - 1}-11-01" else min_date,
        "default_to": max_date,
    }

    result = {
        "academic_sessions": avail_years if avail_years else [str(y) for y in scope_data["scope"]["years"]],
        "campuses": avail_campuses,
        "states": distinct_states,
        "sources": distinct_sources,
        "programs": distinct_programs,
        "lead_types": avail_lead_types,
        "date_range": date_range,
    }
    _FILTER_OPTIONS_CACHE[cache_key] = (now, result)
    # Also save as fallback for all:all if default scope
    if canonical_campus == "all":
        _FILTER_OPTIONS_CACHE["all:all"] = (now, result)
    return result


def check_dimension_exists(db: Session, dataset_ids: list[str], col: str) -> bool:
    """Check if a column has non-null, non-empty data in the dataset scope."""
    if not dataset_ids:
        return False
    try:
        col_name = _resolve_dimension_col(col)
        ds_quoted = ",".join(f"'{str(d)}'" for d in dataset_ids)
        query = text(
            f'SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id::text IN ({ds_quoted}) AND "{col_name}" IS NOT NULL AND "{col_name}" != \'\''
        )
        cnt = db.execute(query).scalar() or 0
        return cnt > 0
    except Exception as e:
        logger.warning(f"Error checking dimension '{col}' existence: {e}")
        return False


def _percentage(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def percentage_change(current: float, previous: float | None) -> float | None:
    if previous is None or not previous:
        return None
    return round(((float(current) - float(previous)) / float(previous)) * 100.0, 2)


def get_dashboard_overview(
    db: Session,
    campus: str | None = None,
    years: list[int] | str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    """Delegate to aggregate service for overview KPIs."""
    from app.analytics.aggregate_service import get_agg_overview
    return get_agg_overview(db, campus=campus, years=years, state=state, source=source, program=program, from_date=from_date, to_date=to_date)


def get_insights(
    db: Session,
    campus: str | None = None,
    years: list[int] | str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    """Delegate to aggregate service for insights."""
    from app.analytics.aggregate_service import get_agg_insights
    return get_agg_insights(db, campus=campus, years=years, state=state, source=source, program=program, from_date=from_date, to_date=to_date)


def get_top_performers(
    db: Session,
    campus: str | None = None,
    years: list[int] | str | None = None,
    metric: str = "admission",
    limit: int = 5,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Delegate to aggregate service for top performers."""
    from app.analytics.aggregate_service import get_agg_top_performers
    return get_agg_top_performers(db, campus=campus, years=years, metric=metric, limit=limit, from_date=from_date, to_date=to_date)


def get_monthly_trend(
    db: Session,
    campus: str | None = None,
    years: list[int] | str | None = None,
    metric: str = "admissions",
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict[str, Any]]:
    """Delegate to aggregate service for monthly trend."""
    from app.analytics.aggregate_service import get_agg_monthly_trend
    return get_agg_monthly_trend(db, campus=campus, years=years, metric=metric, state=state, source=source, program=program, from_date=from_date, to_date=to_date)


def get_performance_rankings(
    db: Session,
    dimension: str = "program_name",
    campus: str | None = None,
    years: list[int] | str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Delegate to aggregate service for performance rankings."""
    from app.analytics.aggregate_service import get_agg_performance_rankings
    return get_agg_performance_rankings(db, dimension=dimension, campus=campus, years=years, state=state, source=source, program=program, from_date=from_date, to_date=to_date)


def get_entity_detail(
    db: Session,
    dimension: str,
    value: str,
    campus: str | None = None,
    years: list[int] | str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any] | None:
    """Delegate to aggregate service for entity detail."""
    from app.analytics.aggregate_service import get_agg_entity_detail
    return get_agg_entity_detail(db, dimension=dimension, value=value, campus=campus, years=years, from_date=from_date, to_date=to_date)


def get_exploration_data(
    db: Session,
    dimension: str,
    metric: str = "admission",
    campus: str | None = None,
    years: list[int] | str | None = None,
    limit: int = 10,
) -> dict[str, Any] | None:
    from app.analytics.aggregate_service import get_agg_exploration_data
    return get_agg_exploration_data(
        db,
        dimension=dimension,
        metric=metric,
        campus=campus,
        years=years,
        limit=limit,
    )


def get_hierarchy_clusters(
    db: Session,
    dimension: str = "source",
    campus: str | None = None,
    years: list[int] | str | None = None,
) -> dict[str, Any]:
    """Get Level 1 clusters for Lead Source (lead_type) or Program (course_cluster)."""
    scope_data = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope_data["cy_year"]

    dim_lower = dimension.lower().strip()
    target_col = "lead_type" if dim_lower in ("source", "lead_type", "lead type") else "course_cluster"
    sub_item_col = "source" if target_col == "lead_type" else "program_name"

    params: dict[str, Any] = {"cy_year": cy_year}
    campus_filter = ""
    if campus and campus.lower() != "all":
        campus_filter = ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus

    sql = text(
        f'SELECT COALESCE("{target_col}", \'OTHERS\') AS cluster_name, '
        f'COALESCE(SUM(leads_cy), 0) AS cy_leads, '
        f'COALESCE(SUM(admission_cy), 0) AS cy_admission, '
        f'COALESCE(SUM(leads_py), 0) AS py_leads, '
        f'COALESCE(SUM(admission_py), 0) AS py_admission, '
        f'COUNT(DISTINCT "{sub_item_col}") AS item_count '
        f'FROM analytics.dashboard_agg '
        f'WHERE academic_year = :cy_year{campus_filter} '
        f'GROUP BY "{target_col}" '
        f'ORDER BY cy_leads DESC'
    )
    rows = db.execute(sql, params).mappings().all()

    clusters = []
    total_leads = sum(r["cy_leads"] for r in rows) or 1
    for r in rows:
        cy_leads = int(r["cy_leads"])
        cy_admission = int(r["cy_admission"])
        py_leads = int(r["py_leads"])
        py_admission = int(r["py_admission"])
        cy_rate = round((cy_admission / cy_leads * 100), 2) if cy_leads > 0 else 0.0
        py_rate = round((py_admission / py_leads * 100), 2) if py_leads > 0 else 0.0

        clusters.append({
            "cluster_name": r["cluster_name"],
            "cy_leads": cy_leads,
            "cy_admission": cy_admission,
            "cy_rate": cy_rate,
            "py_leads": py_leads,
            "py_admission": py_admission,
            "py_rate": py_rate,
            "item_count": int(r["item_count"]),
            "share_pct": round((cy_leads / total_leads * 100), 1),
        })

    return {
        "dimension": dimension,
        "level": 1,
        "clusters": clusters,
        "total_clusters": len(clusters),
    }


def get_hierarchy_drilldown(
    db: Session,
    dimension: str = "source",
    cluster_name: str = "IN HOUSE",
    campus: str | None = None,
    years: list[int] | str | None = None,
) -> dict[str, Any]:
    """Get Level 2 individual items belonging to a specified cluster."""
    scope_data = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope_data["cy_year"]

    dim_lower = dimension.lower().strip()
    cluster_col = "lead_type" if dim_lower in ("source", "lead_type", "lead type") else "course_cluster"
    item_col = "source" if cluster_col == "lead_type" else "program_name"

    params: dict[str, Any] = {"cy_year": cy_year, "cluster_name": cluster_name.strip()}
    campus_filter = ""
    if campus and campus.lower() != "all":
        campus_filter = ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus

    cluster_match_clause = (
        f'(LOWER("{cluster_col}") = LOWER(:cluster_name) OR ("{cluster_col}" IS NULL AND LOWER(:cluster_name) IN (\'others\', \'unmapped\')))'
    )
    fallback_item_name = "'Unmapped Program'" if item_col == "program_name" else "'Others'"
    sql = text(
        f'SELECT COALESCE("{item_col}", {fallback_item_name}) AS item_name, '
        f'COALESCE(SUM(leads_cy), 0) AS cy_leads, '
        f'COALESCE(SUM(admission_cy), 0) AS cy_admission, '
        f'COALESCE(SUM(leads_py), 0) AS py_leads, '
        f'COALESCE(SUM(admission_py), 0) AS py_admission '
        f'FROM analytics.dashboard_agg '
        f'WHERE academic_year = :cy_year{campus_filter} AND {cluster_match_clause} '
        f'GROUP BY "{item_col}" '
        f'ORDER BY cy_leads DESC'
    )
    rows = db.execute(sql, params).mappings().all()

    items = []
    total_cluster_leads = sum(r["cy_leads"] for r in rows) or 1
    for r in rows:
        cy_leads = int(r["cy_leads"])
        cy_admission = int(r["cy_admission"])
        py_leads = int(r["py_leads"])
        py_admission = int(r["py_admission"])
        cy_rate = round((cy_admission / cy_leads * 100), 2) if cy_leads > 0 else 0.0
        py_rate = round((py_admission / py_leads * 100), 2) if py_leads > 0 else 0.0

        items.append({
            "item_name": r["item_name"],
            "cy_leads": cy_leads,
            "cy_admission": cy_admission,
            "cy_rate": cy_rate,
            "py_leads": py_leads,
            "py_admission": py_admission,
            "py_rate": py_rate,
            "share_of_cluster_pct": round((cy_leads / total_cluster_leads * 100), 1),
        })

    return {
        "dimension": dimension,
        "level": 2,
        "cluster_name": cluster_name,
        "items": items,
        "total_items": len(items),
    }


def get_manual_comparison(
    db: Session,
    dimension: str,
    value_a: str | None = None,
    value_b: str | None = None,
    value_c: str | None = None,
    entities_list: list[str] | None = None,
    metric: str = "admission",
    campus: str | None = None,
    years: list[int] | str | None = None,
) -> dict[str, Any] | None:
    scope_data = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope_data["cy_year"]
    safe_dim = _resolve_dimension_col(dimension)

    vals = []
    if entities_list:
        vals = [e.strip() for e in entities_list if e and e.strip()]
    if not vals:
        if value_a:
            vals.append(value_a.strip())
        if value_b:
            vals.append(value_b.strip())
        if value_c and value_c.strip():
            vals.append(value_c.strip())

    if not vals:
        return None

    params: dict[str, Any] = {"cy_year": cy_year}
    val_clauses = []
    for idx, v in enumerate(vals):
        param_key = f"val_{idx}"
        val_clauses.append(f"LOWER(\"{safe_dim}\") = LOWER(:{param_key})")
        params[param_key] = v

    where_val_sql = " OR ".join(val_clauses)
    campus_filter = ""
    if campus and campus.lower() != "all":
        campus_filter = ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus

    rows = []
    if safe_dim in ("source", "main_source", "state", "program_name", "campus_name", "lead_type", "course_cluster"):
        try:
            agg_sql = text(
                f'SELECT "{safe_dim}" AS entity, '
                f'COALESCE(SUM(leads_cy), 0) AS cy_leads, '
                f'COALESCE(SUM(admission_cy), 0) AS cy_admission, '
                f'COALESCE(SUM(leads_py), 0) AS py_leads, '
                f'COALESCE(SUM(admission_py), 0) AS py_admission '
                f'FROM analytics.dashboard_agg '
                f'WHERE academic_year = :cy_year{campus_filter} AND ({where_val_sql}) '
                f'GROUP BY "{safe_dim}"'
            )
            rows = db.execute(agg_sql, params).mappings().all()
        except Exception as err:
            logger.debug(f"Agg query failed in comparison (falling back): {err}")
            db.rollback()

    if not rows:
        cy_ds_ids = scope_data["cy_dataset_ids"]
        if cy_ds_ids:
            ds_quoted = ",".join(f"'{str(d)}'" for d in cy_ds_ids)
            fb_sql = text(
                f'SELECT "{safe_dim}" AS entity, '
                f'COALESCE(SUM(cy_leads), 0) AS cy_leads, '
                f'COALESCE(SUM(cy_admission), 0) AS cy_admission, '
                f'COALESCE(SUM(py_leads), 0) AS py_leads, '
                f'COALESCE(SUM(py_admission), 0) AS py_admission '
                f'FROM analytics.uploaded_metrics '
                f'WHERE dataset_id::text IN ({ds_quoted}) AND ({where_val_sql}) '
                f'GROUP BY "{safe_dim}"'
            )
            rows = db.execute(fb_sql, params).mappings().all()

    row_dict = {str(r["entity"]).lower().strip(): r for r in rows}
    entity_results = []
    max_rate = -1.0
    top_performer = None

    for v in vals:
        match = row_dict.get(v.lower().strip())
        cy_leads = int(match["cy_leads"]) if match else 0
        cy_admission = int(match["cy_admission"]) if match else 0
        py_leads = int(match["py_leads"]) if match else 0
        py_admission = int(match["py_admission"]) if match else 0

        cy_rate = round((cy_admission / cy_leads * 100), 2) if cy_leads > 0 else 0.0
        py_rate = round((py_admission / py_leads * 100), 2) if py_leads > 0 else 0.0

        item = {
            "entity": match["entity"] if match else v,
            "cy_leads": cy_leads,
            "cy_admission": cy_admission,
            "cy_rate": cy_rate,
            "py_leads": py_leads,
            "py_admission": py_admission,
            "py_rate": py_rate,
            "is_top_performer": False,
        }
        entity_results.append(item)

        if cy_rate > max_rate:
            max_rate = cy_rate
            top_performer = item["entity"]

    for item in entity_results:
        if item["entity"] == top_performer:
            item["is_top_performer"] = True

    # Backward compatible value_a and value_b fields
    val_a_res = entity_results[0] if len(entity_results) > 0 else {"entity": value_a or "Value A", "cy_leads": 0, "cy_admission": 0, "cy_rate": 0.0}
    val_b_res = entity_results[1] if len(entity_results) > 1 else {"entity": value_b or "Value B", "cy_leads": 0, "cy_admission": 0, "cy_rate": 0.0}

    diff_leads = val_a_res["cy_leads"] - val_b_res["cy_leads"]
    diff_adm = val_a_res["cy_admission"] - val_b_res["cy_admission"]
    diff_rate = round(val_a_res["cy_rate"] - val_b_res["cy_rate"], 2)

    return {
        "dimension": dimension,
        "metric": metric,
        "entities": entity_results,
        "top_performer": {
            "entity": top_performer or (val_a_res["entity"] if val_a_res else ""),
            "cy_rate": max_rate if max_rate >= 0 else 0.0,
        },
        "value_a": val_a_res,
        "value_b": val_b_res,
        "differences": {
            "cy_leads": diff_leads,
            "py_leads": (val_a_res.get("py_leads", 0) - val_b_res.get("py_leads", 0)),
            "cy_admission": diff_adm,
            "py_admission": (val_a_res.get("py_admission", 0) - val_b_res.get("py_admission", 0)),
            "cy_rate": diff_rate,
            "py_rate": round(val_a_res.get("py_rate", 0.0) - val_b_res.get("py_rate", 0.0), 2),
        },
    }
