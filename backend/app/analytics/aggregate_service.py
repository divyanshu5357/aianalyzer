'''Aggregate query service for Executive Dashboard'''
import logging
from typing import Any, List, Dict
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.analytics.scope_resolver import resolve_dataset_scope
from app.analytics.dashboard import _build_scope_where, _percentage, percentage_change, _resolve_dimension_col

from decimal import Decimal

logger = logging.getLogger(__name__)

def _run_agg_query(db: Session, agg_sql: str, agg_params: dict, fallback_sql: str, fallback_params: dict):
    """Execute aggregate query against dashboard_agg, fallback to uploaded_metrics if error or empty."""
    try:
        rows = db.execute(text(agg_sql), agg_params).mappings().all()
        if rows:
            metric_keys = ("leads", "cy_leads", "cucet", "admission", "tot", "cnt", "total")
            first = rows[0]
            if any(k in first for k in metric_keys):
                has_nonzero = any(
                    isinstance(v, (int, float, Decimal)) and v > 0
                    for k, v in first.items()
                    if k in metric_keys
                )
                if not has_nonzero:
                    try:
                        fallback_rows = db.execute(text(fallback_sql), fallback_params).mappings().all()
                        if fallback_rows and any(
                            isinstance(v, (int, float, Decimal)) and v > 0
                            for k, v in fallback_rows[0].items()
                            if k in metric_keys
                        ):
                            return fallback_rows
                    except Exception:
                        pass
            return rows
        return db.execute(text(fallback_sql), fallback_params).mappings().all()
    except Exception as err:
        logger.debug(f"Agg query failed (falling back to uploaded_metrics): {err}")
        db.rollback()
        return db.execute(text(fallback_sql), fallback_params).mappings().all()

import calendar

def get_py_date(dt_str: str, year_diff: int = 1) -> str:
    """Compute equivalent prior-year date with leap-year protection."""
    parts = dt_str.split("-")
    yr = int(parts[0]) - year_diff
    m = int(parts[1])
    d = int(parts[2])
    if m == 2 and d == 29:
        is_leap = (yr % 4 == 0 and yr % 100 != 0) or (yr % 400 == 0)
        if not is_leap:
            d = 28
    return f"{yr:04d}-{m:02d}-{d:02d}"

def generate_chronological_months(from_date: str, to_date: str) -> List[tuple[str, str]]:
    """
    Generate chronological (month_name, month_key) pairs between from_date and to_date.
    e.g. from 2026-01-01 to 2026-06-30 ->
    [('January', '2026-01'), ('February', '2026-02'), ('March', '2026-03'),
     ('April', '2026-04'), ('May', '2026-05'), ('June', '2026-06')]
    """
    start_y, start_m = int(from_date.split("-")[0]), int(from_date.split("-")[1])
    end_y, end_m = int(to_date.split("-")[0]), int(to_date.split("-")[1])

    months = []
    curr_y, curr_m = start_y, start_m
    while (curr_y < end_y) or (curr_y == end_y and curr_m <= end_m):
        m_key = f"{curr_y:04d}-{curr_m:02d}"
        m_name = calendar.month_name[curr_m]
        months.append((m_name, m_key))
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1
    return months

def get_agg_overview(
    db: Session,
    campus: str | None = None,
    years: List[int] | str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> Dict[str, Any]:
    """Return overview KPIs using pre-aggregated dashboard_agg table with fallback.
    Supports dynamic from_date and to_date range filtering with equivalent PY period.
    """
    scope = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope["cy_year"]
    py_year = scope["py_year"]
    where_clause, params = _build_scope_where([], state, source, program)
    if campus and campus.lower() != "all":
        where_clause += ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus
    # Current year filter
    where_clause += " AND academic_year = :cy_year"
    params["cy_year"] = cy_year

    # Check if valid enabled RAW dataset exists for cy_year
    cy_ds_check = db.execute(
        text("""
            SELECT 1 FROM system.datasets
            WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
              AND is_analytics_enabled = TRUE
              AND academic_year = :cy_yr
              AND (LOWER(COALESCE(:cmp, 'all')) = 'all' OR LOWER(COALESCE(campus_name, '')) = LOWER(:cmp))
            LIMIT 1
        """),
        {"cy_yr": cy_year, "cmp": campus},
    ).scalar()

    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    from_m = from_date.strip()[:7] if has_date_filter else None
    to_m = to_date.strip()[:7] if has_date_filter else None

    if not cy_ds_check:
        cy_leads = cy_cucet = cy_admission = None
    else:
        if has_date_filter:
            params["from_m"] = from_m
            params["to_m"] = to_m
            agg_sql = f"""
                SELECT COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN leads_cy ELSE 0 END),0) AS leads,
                       COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cucet_cy ELSE 0 END),0) AS cucet,
                       COALESCE(SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN admission_cy ELSE 0 END),0) AS admission
                FROM analytics.dashboard_agg
                WHERE {where_clause}
            """
            fallback_sql = f"""
                SELECT COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cy_leads ELSE 0 END),0) AS leads,
                       COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cy_cucet ELSE 0 END),0) AS cucet,
                       COALESCE(SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN cy_admission ELSE 0 END),0) AS admission
                FROM analytics.uploaded_metrics
                WHERE {where_clause}
            """
        else:
            agg_sql = f"""
                SELECT COALESCE(SUM(leads_cy),0) AS leads,
                       COALESCE(SUM(cucet_cy),0) AS cucet,
                       COALESCE(SUM(admission_cy),0) AS admission
                FROM analytics.dashboard_agg
                WHERE {where_clause}
            """
            fallback_sql = f"""
                SELECT COALESCE(SUM(cy_leads),0) AS leads,
                       COALESCE(SUM(cy_cucet),0) AS cucet,
                       COALESCE(SUM(cy_admission),0) AS admission
                FROM analytics.uploaded_metrics
                WHERE {where_clause}
            """
        agg_row = _run_agg_query(db, agg_sql, params, fallback_sql, params)[0]
        cy_leads = int(agg_row["leads"] or 0)
        cy_cucet = int(agg_row["cucet"] or 0)
        cy_admission = int(agg_row["admission"] or 0)

        # Self-healing: If valid RAW dataset exists for cy_year but aggregates returned 0,
        # perform a lightweight dataset-scoped backfill (NOT full year scan).
        # Only targets specific analytics-ready datasets missing their aggregate rows.
        if cy_leads == 0 and cy_admission == 0 and cy_ds_check:
            agg_cnt = db.execute(
                text("SELECT COUNT(*) FROM analytics.dashboard_agg WHERE academic_year = :cy_yr"),
                {"cy_yr": cy_year}
            ).scalar() or 0
            if agg_cnt == 0:
                # Find the specific dataset(s) that are analytics-ready but have no agg rows
                missing_ds = db.execute(
                    text("""
                        SELECT sd.id FROM system.datasets sd
                        WHERE sd.is_analytics_enabled = TRUE
                          AND sd.academic_year = :cy_yr
                          AND UPPER(COALESCE(sd.workbook_type, 'RAW')) = 'RAW'
                          AND COALESCE(sd.row_count, 0) > 0
                          AND NOT EXISTS (
                              SELECT 1 FROM analytics.dashboard_agg da
                              WHERE da.dataset_id = sd.id
                          )
                        LIMIT 1
                    """),
                    {"cy_yr": cy_year},
                ).scalars().all()
                if missing_ds:
                    from app.analytics.aggregate_refresh import refresh_dashboard_agg_scoped
                    for ds_id in missing_ds:
                        try:
                            refresh_dashboard_agg_scoped(db, dataset_id=str(ds_id))
                        except Exception as heal_err:
                            logger.warning("Self-heal agg failed for dataset %s: %s", ds_id, heal_err)
                            db.rollback()
                    healed_rows = _run_agg_query(db, agg_sql, params, fallback_sql, params)
                    if healed_rows:
                        cy_leads = int(healed_rows[0]["leads"] or 0)
                        cy_cucet = int(healed_rows[0]["cucet"] or 0)
                        cy_admission = int(healed_rows[0]["admission"] or 0)

    # PY metrics: verify if valid enabled RAW dataset exists for py_year
    py_leads = py_cucet = py_admission = None
    has_py_dataset = False
    py_from_date = None
    py_to_date = None

    if py_year is not None:
        py_ds_check = db.execute(
            text("""
                SELECT 1 FROM system.datasets
                WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                  AND is_analytics_enabled = TRUE
                  AND academic_year = :py_yr
                  AND (LOWER(COALESCE(:cmp, 'all')) = 'all' OR LOWER(COALESCE(campus_name, '')) = LOWER(:cmp))
                LIMIT 1
            """),
            {"py_yr": py_year, "cmp": campus},
        ).scalar()
        has_py_dataset = bool(py_ds_check)

        if has_py_dataset:
            year_diff = (cy_year - py_year) if (cy_year and py_year) else 1
            py_params = dict(params)
            py_params["py_year"] = py_year
            py_where = where_clause.replace('academic_year = :cy_year', 'academic_year = :py_year')

            if has_date_filter:
                py_from_date = get_py_date(from_date.strip(), year_diff)
                py_to_date = get_py_date(to_date.strip(), year_diff)
                py_from_m = py_from_date[:7]
                py_to_m = py_to_date[:7]
                py_params["py_from_m"] = py_from_m
                py_params["py_to_m"] = py_to_m

                agg_sql_py = f"""
                    SELECT COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN GREATEST(leads_cy, leads_py) ELSE 0 END),0) AS leads,
                           COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN GREATEST(cucet_cy, cucet_py) ELSE 0 END),0) AS cucet,
                           COALESCE(SUM(CASE WHEN admission_month >= :py_from_m AND admission_month <= :py_to_m THEN GREATEST(admission_cy, admission_py) ELSE 0 END),0) AS admission
                    FROM analytics.dashboard_agg
                    WHERE {py_where}
                """
                fallback_sql_py = f"""
                    SELECT COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN cy_leads ELSE 0 END),0) AS leads,
                           COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN cy_cucet ELSE 0 END),0) AS cucet,
                           COALESCE(SUM(CASE WHEN admission_month >= :py_from_m AND admission_month <= :py_to_m THEN cy_admission ELSE 0 END),0) AS admission
                    FROM analytics.uploaded_metrics
                    WHERE {py_where}
                """
            else:
                agg_sql_py = f"""
                    SELECT COALESCE(SUM(GREATEST(leads_cy, leads_py)),0) AS leads,
                           COALESCE(SUM(GREATEST(cucet_cy, cucet_py)),0) AS cucet,
                           COALESCE(SUM(GREATEST(admission_cy, admission_py)),0) AS admission
                    FROM analytics.dashboard_agg
                    WHERE {py_where}
                """
                fallback_sql_py = f"""
                    SELECT COALESCE(SUM(cy_leads),0) AS leads,
                           COALESCE(SUM(cy_cucet),0) AS cucet,
                           COALESCE(SUM(cy_admission),0) AS admission
                    FROM analytics.uploaded_metrics
                    WHERE {py_where}
                """
            agg_row_py = _run_agg_query(db, agg_sql_py, py_params, fallback_sql_py, py_params)[0]
            py_leads = int(agg_row_py["leads"] or 0)
            py_cucet = int(agg_row_py["cucet"] or 0)
            py_admission = int(agg_row_py["admission"] or 0)

            # Self-healing for PY (dataset-scoped, non-blocking)
            if py_leads == 0 and py_admission == 0 and py_ds_check:
                agg_cnt_py = db.execute(
                    text("SELECT COUNT(*) FROM analytics.dashboard_agg WHERE academic_year = :py_yr"),
                    {"py_yr": py_year}
                ).scalar() or 0
                if agg_cnt_py == 0:
                    missing_py_ds = db.execute(
                        text("""
                            SELECT sd.id FROM system.datasets sd
                            WHERE sd.is_analytics_enabled = TRUE
                              AND sd.academic_year = :py_yr
                              AND UPPER(COALESCE(sd.workbook_type, 'RAW')) = 'RAW'
                              AND COALESCE(sd.row_count, 0) > 0
                              AND NOT EXISTS (
                                  SELECT 1 FROM analytics.dashboard_agg da
                                  WHERE da.dataset_id = sd.id
                              )
                            LIMIT 1
                        """),
                        {"py_yr": py_year},
                    ).scalars().all()
                    if missing_py_ds:
                        from app.analytics.aggregate_refresh import refresh_dashboard_agg_scoped
                        for ds_id in missing_py_ds:
                            try:
                                refresh_dashboard_agg_scoped(db, dataset_id=str(ds_id))
                            except Exception as heal_err:
                                logger.warning("Self-heal PY agg failed for dataset %s: %s", ds_id, heal_err)
                                db.rollback()
                        healed_py = _run_agg_query(db, agg_sql_py, py_params, fallback_sql_py, py_params)
                        if healed_py:
                            py_leads = int(healed_py[0]["leads"] or 0)
                            py_cucet = int(healed_py[0]["cucet"] or 0)
                            py_admission = int(healed_py[0]["admission"] or 0)

    has_cucet = (cy_cucet is not None and cy_cucet > 0) or (py_cucet is not None and py_cucet > 0)
    cy_conv = _percentage(cy_admission, cy_leads) if (cy_admission is not None and cy_leads is not None) else None
    py_conv = _percentage(py_admission, py_leads) if (py_admission is not None and py_leads is not None) else None

    kpis = {
        "leads": {
            "cy": cy_leads,
            "py": py_leads,
            "change": (cy_leads - py_leads) if (cy_leads is not None and py_leads is not None) else None,
            "growth_pct": percentage_change(cy_leads, py_leads) if (cy_leads is not None and py_leads is not None) else None,
        },
        "admissions": {
            "cy": cy_admission,
            "py": py_admission,
            "change": (cy_admission - py_admission) if (cy_admission is not None and py_admission is not None) else None,
            "growth_pct": percentage_change(cy_admission, py_admission) if (cy_admission is not None and py_admission is not None) else None,
        },
        "conversion_rate": {
            "cy": cy_conv,
            "py": py_conv,
            "change": round(cy_conv - py_conv, 2) if (cy_conv is not None and py_conv is not None) else None,
            "growth_pct": percentage_change(cy_conv, py_conv) if (cy_conv is not None and py_conv is not None) else None,
        }
    }
    if has_cucet:
        kpis["cucet"] = {
            "cy": cy_cucet,
            "py": py_cucet,
            "change": (cy_cucet - py_cucet) if (cy_cucet is not None and py_cucet is not None) else None,
            "growth_pct": percentage_change(cy_cucet, py_cucet) if (cy_cucet is not None and py_cucet is not None) else None,
        }
        cy_cucet_rate = _percentage(cy_admission, cy_cucet) if (cy_admission is not None and cy_cucet is not None) else None
        py_cucet_rate = _percentage(py_admission, py_cucet) if (py_admission is not None and py_cucet is not None) else None
        kpis["cucet_conversion_rate"] = {
            "cy": cy_cucet_rate,
            "py": py_cucet_rate,
            "change": round(cy_cucet_rate - py_cucet_rate, 2) if (cy_cucet_rate is not None and py_cucet_rate is not None) else None,
            "growth_pct": percentage_change(cy_cucet_rate, py_cucet_rate) if (cy_cucet_rate is not None and py_cucet_rate is not None) else None,
        }

    funnel = []
    if cy_leads is not None:
        funnel.append({"stage": "Leads", "count": cy_leads, "pct_of_leads": 100.0, "conversion_rate": 100.0})
        if has_cucet and cy_cucet is not None:
            funnel.append({
                "stage": "CUCET",
                "count": cy_cucet,
                "pct_of_leads": _percentage(cy_cucet, cy_leads),
                "conversion_rate": _percentage(cy_cucet, cy_leads),
            })
            funnel.append({
                "stage": "Admissions",
                "count": cy_admission,
                "pct_of_leads": _percentage(cy_admission, cy_leads),
                "conversion_rate": _percentage(cy_admission, cy_cucet),
            })
        elif cy_admission is not None:
            funnel.append({
                "stage": "Admissions",
                "count": cy_admission,
                "pct_of_leads": _percentage(cy_admission, cy_leads),
                "conversion_rate": _percentage(cy_admission, cy_leads),
            })

    return {
        "scope": scope["scope"],
        "datasets": scope["datasets"],
        "dataset_count": len(scope["datasets"]),
        "current_year": cy_year,
        "previous_year": py_year,
        "from_date": from_date,
        "to_date": to_date,
        "py_from_date": py_from_date,
        "py_to_date": py_to_date,
        "has_cucet": has_cucet,
        "kpis": kpis,
        "funnel": funnel,
    }


def get_agg_monthly_trend(
    db: Session,
    campus: str | None = None,
    years: List[int] | str | None = None,
    metric: str = "admissions",
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> List[Dict[str, Any]]:
    """Compute monthly trend using authentic PostgreSQL date-grouped aggregates.
    Completely eliminates synthetic weighting or fake target multipliers.
    Leads are grouped by creation month (CreatedOn/created_month).
    Admissions are grouped by admission month (mx_AdmissionDate/admission_month).
    CUCET is grouped by creation month (cucet_cy).
    Chronological months are dynamically determined from from_date to to_date.
    """
    scope = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope["cy_year"]
    py_year = scope["py_year"]

    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    if has_date_filter:
        months_meta = generate_chronological_months(from_date.strip(), to_date.strip())
    else:
        # Dynamically generate chronological reporting cycle based on resolved cy_year
        months_meta = [
            ("November", f"{cy_year - 1}-11"),
            ("December", f"{cy_year - 1}-12"),
            ("January", f"{cy_year}-01"),
            ("February", f"{cy_year}-02"),
            ("March", f"{cy_year}-03"),
            ("April", f"{cy_year}-04"),
            ("May", f"{cy_year}-05"),
            ("June", f"{cy_year}-06"),
            ("July", f"{cy_year}-07"),
            ("August", f"{cy_year}-08"),
            ("September", f"{cy_year}-09"),
            ("October", f"{cy_year}-10"),
        ]

    where_clause, params = _build_scope_where([], state, source, program)
    if campus and campus.lower() != "all":
        where_clause += ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus
    where_clause += " AND academic_year = :cy_year"
    params["cy_year"] = cy_year

    # Query authentic monthly admissions from dashboard_agg with fallback to uploaded_metrics
    adm_sql = f"""
        SELECT admission_month AS month_key, SUM(admission_cy) AS cnt
        FROM analytics.dashboard_agg
        WHERE {where_clause} AND admission_month IS NOT NULL AND admission_month != ''
        GROUP BY admission_month;
    """
    fallback_adm_sql = f"""
        SELECT admission_month AS month_key, SUM(cy_admission) AS cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id IN (SELECT id FROM system.datasets WHERE is_analytics_enabled = TRUE)
          AND {where_clause} AND admission_month IS NOT NULL AND admission_month != ''
        GROUP BY admission_month;
    """

    # Query authentic monthly leads from dashboard_agg with fallback to uploaded_metrics
    lead_sql = f"""
        SELECT created_month AS month_key, SUM(leads_cy) AS cnt
        FROM analytics.dashboard_agg
        WHERE {where_clause} AND created_month IS NOT NULL AND created_month != ''
        GROUP BY created_month;
    """
    fallback_lead_sql = f"""
        SELECT created_month AS month_key, SUM(cy_leads) AS cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id IN (SELECT id FROM system.datasets WHERE is_analytics_enabled = TRUE)
          AND {where_clause} AND created_month IS NOT NULL AND created_month != ''
        GROUP BY created_month;
    """

    # Query authentic monthly CUCET from dashboard_agg with fallback to uploaded_metrics
    cucet_sql = f"""
        SELECT created_month AS month_key, SUM(cucet_cy) AS cnt
        FROM analytics.dashboard_agg
        WHERE {where_clause} AND created_month IS NOT NULL AND created_month != ''
        GROUP BY created_month;
    """
    fallback_cucet_sql = f"""
        SELECT created_month AS month_key, SUM(cy_cucet) AS cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id IN (SELECT id FROM system.datasets WHERE is_analytics_enabled = TRUE)
          AND {where_clause} AND created_month IS NOT NULL AND created_month != ''
        GROUP BY created_month;
    """

    cy_adm_map: Dict[str, int] = {}
    cy_lead_map: Dict[str, int] = {}
    cy_cucet_map: Dict[str, int] = {}
    py_adm_map: Dict[str, int] = {}
    py_lead_map: Dict[str, int] = {}
    py_cucet_map: Dict[str, int] = {}

    try:
        db.execute(text("SET LOCAL jit = off;"))
    except Exception:
        pass

    params_py = dict(params)
    params_py["cy_year"] = py_year

    norm_metric = metric.lower().strip()
    need_adm = "adm" in norm_metric or "conversion" in norm_metric or not ("lead" in norm_metric or "cucet" in norm_metric or "reg" in norm_metric)
    need_lead = "lead" in norm_metric or "conversion" in norm_metric
    need_cucet = "cucet" in norm_metric or "reg" in norm_metric

    try:
        # CY Queries (only query what is requested)
        if need_adm:
            adm_rows = _run_agg_query(db, adm_sql, params, fallback_adm_sql, params)
            for r in adm_rows:
                if r.get("month_key"):
                    cy_adm_map[str(r["month_key"])] = int(r["cnt"] or 0)

        if need_lead:
            lead_rows = _run_agg_query(db, lead_sql, params, fallback_lead_sql, params)
            for r in lead_rows:
                if r.get("month_key"):
                    cy_lead_map[str(r["month_key"])] = int(r["cnt"] or 0)

        if need_cucet:
            cucet_rows = _run_agg_query(db, cucet_sql, params, fallback_cucet_sql, params)
            for r in cucet_rows:
                if r.get("month_key"):
                    cy_cucet_map[str(r["month_key"])] = int(r["cnt"] or 0)

        # Self-healing: if CY maps are all empty/zero but RAW dataset exists, backfill and retry
        cy_has_any = any(cy_adm_map.values()) or any(cy_lead_map.values()) or any(cy_cucet_map.values())
        if not cy_has_any:
            has_raw = db.execute(
                text("SELECT 1 FROM system.datasets WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW' AND is_analytics_enabled = TRUE AND academic_year = :cy_yr LIMIT 1"),
                {"cy_yr": cy_year},
            ).scalar()
            if has_raw:
                missing_ds = db.execute(
                    text("""
                        SELECT sd.id FROM system.datasets sd
                        WHERE sd.is_analytics_enabled = TRUE
                          AND sd.academic_year = :cy_yr
                          AND UPPER(COALESCE(sd.workbook_type, 'RAW')) = 'RAW'
                          AND COALESCE(sd.row_count, 0) > 0
                          AND NOT EXISTS (
                              SELECT 1 FROM analytics.dashboard_agg da
                              WHERE da.dataset_id = sd.id
                          )
                        LIMIT 1
                    """),
                    {"cy_yr": cy_year},
                ).scalars().all()
                if missing_ds:
                    from app.analytics.aggregate_refresh import refresh_dashboard_agg_scoped
                    for ds_id in missing_ds:
                        try:
                            refresh_dashboard_agg_scoped(db, dataset_id=str(ds_id))
                        except Exception as heal_err:
                            logger.warning("Self-heal trend agg failed for dataset %s: %s", ds_id, heal_err)
                            db.rollback()
                if need_adm:
                    for r in _run_agg_query(db, adm_sql, params, fallback_adm_sql, params):
                        if r.get("month_key"):
                            cy_adm_map[str(r["month_key"])] = int(r["cnt"] or 0)
                if need_lead:
                    for r in _run_agg_query(db, lead_sql, params, fallback_lead_sql, params):
                        if r.get("month_key"):
                            cy_lead_map[str(r["month_key"])] = int(r["cnt"] or 0)
                if need_cucet:
                    for r in _run_agg_query(db, cucet_sql, params, fallback_cucet_sql, params):
                        if r.get("month_key"):
                            cy_cucet_map[str(r["month_key"])] = int(r["cnt"] or 0)

        # Check if PY dataset genuinely exists
        has_py_dataset = False
        if py_year is not None:
            py_ds_check = db.execute(
                text("""
                    SELECT 1 FROM system.datasets
                    WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                      AND is_analytics_enabled = TRUE
                      AND academic_year = :py_yr
                      AND (LOWER(COALESCE(:cmp, 'all')) = 'all' OR LOWER(COALESCE(campus_name, '')) = LOWER(:cmp))
                    LIMIT 1
                """),
                {"py_yr": py_year, "cmp": campus},
            ).scalar()
            has_py_dataset = bool(py_ds_check)

        if has_py_dataset:
            if need_adm:
                py_adm_rows = _run_agg_query(db, adm_sql, params_py, fallback_adm_sql, params_py)
                for r in py_adm_rows:
                    if r.get("month_key"):
                        py_adm_map[str(r["month_key"])] = int(r["cnt"] or 0)

            if need_lead:
                py_lead_rows = _run_agg_query(db, lead_sql, params_py, fallback_lead_sql, params_py)
                for r in py_lead_rows:
                    if r.get("month_key"):
                        py_lead_map[str(r["month_key"])] = int(r["cnt"] or 0)

            if need_cucet:
                py_cucet_rows = _run_agg_query(db, cucet_sql, params_py, fallback_cucet_sql, params_py)
                for r in py_cucet_rows:
                    if r.get("month_key"):
                        py_cucet_map[str(r["month_key"])] = int(r["cnt"] or 0)
    except Exception as err:
        logger.warning(f"Monthly trend query error: {err}")
        try:
            db.rollback()
        except Exception:
            pass

    # Query targets from analytics.targets or staging Source sheet if target master exists
    from app.database.repository import resolve_target_dataset
    tgt_ds_id = resolve_target_dataset(db)
    has_target_master = bool(tgt_ds_id)
    tgt_adm_map: Dict[str, int] = {}
    tgt_lead_map: Dict[str, int] = {}
    tgt_cucet_map: Dict[str, int] = {}

    if has_target_master:
        from app.analytics.target_service import _is_all_campus
        tgt_campus_clause = ""
        tgt_params: Dict[str, Any] = {"cy_year": cy_year}
        if not _is_all_campus(campus):
            tgt_campus_clause = ' AND LOWER("campus_name") = LOWER(:campus)'
            tgt_params["campus"] = campus
        else:
            tgt_campus_clause = ' AND LOWER("campus_name") = \'all\''

        dim_clause = " AND LOWER(dimension_type) = 'overall'"
        if program and str(program).lower() != "all":
            dim_clause = """ AND LOWER(dimension_type) = 'program' 
                             AND (LOWER(dimension_value) = LOWER(:program) 
                                  OR LOWER(dimension_value) IN (
                                      SELECT LOWER(program_code) FROM organization.course_master 
                                      WHERE LOWER(program_name) = LOWER(:program)
                                  ))"""
            tgt_params["program"] = str(program).strip()
        elif source and str(source).lower() != "all":
            dim_clause = " AND LOWER(dimension_type) = 'source' AND LOWER(dimension_value) = LOWER(:source)"
            tgt_params["source"] = str(source).strip()
        elif state and str(state).lower() != "all":
            dim_clause = " AND LOWER(dimension_type) = 'state' AND LOWER(dimension_value) = LOWER(:state)"
            tgt_params["state"] = str(state).strip()

        tgt_sql = f"""
            SELECT month AS month_key,
                   SUM(target_admissions) AS tgt_adm,
                   SUM(target_leads) AS tgt_lead,
                   SUM(target_cucet) AS tgt_cucet
            FROM analytics.targets
            WHERE academic_year = :cy_year {dim_clause} {tgt_campus_clause} AND month IS NOT NULL
            GROUP BY month;
        """
        try:
            tgt_rows = db.execute(text(tgt_sql), tgt_params).mappings().all()
            for r in tgt_rows:
                m_k = r.get("month_key")
                if m_k is not None:
                    m_str = f"{int(m_k):02d}" if str(m_k).isdigit() else str(m_k).split("-")[-1]
                    tgt_adm_map[m_str] = int(r["tgt_adm"] or 0)
                    tgt_lead_map[m_str] = int(r["tgt_lead"] or 0)
                    tgt_cucet_map[m_str] = int(r["tgt_cucet"] or 0)
        except Exception as err:
            logger.warning(f"Target monthly query error: {err}")
            try:
                db.rollback()
            except Exception:
                pass

        # Direct staging query on Source sheet if targets table returned empty or date filter requested
        if (not tgt_adm_map and not tgt_lead_map and tgt_ds_id) or (has_date_filter and tgt_ds_id):
            try:
                fb_campus_clause = ""
                fb_params: Dict[str, Any] = {"tgt_id": str(tgt_ds_id)}
                if not _is_all_campus(campus):
                    fb_campus_clause = " AND LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) = LOWER(:campus)"
                    fb_params["campus"] = campus

                fb_date_clause = ""
                if has_date_filter:
                    fb_date_clause = " AND SUBSTRING(r.raw_data->>'Date' FROM 1 FOR 10) >= :from_date AND SUBSTRING(r.raw_data->>'Date' FROM 1 FOR 10) <= :to_date"
                    fb_params["from_date"] = from_date.strip()
                    fb_params["to_date"] = to_date.strip()

                fb_sql = f"""
                    SELECT 
                        CASE LOWER(TRIM(COALESCE(r.raw_data->>'Month', '')))
                            WHEN 'jan' THEN '01' WHEN 'feb' THEN '02' WHEN 'mar' THEN '03'
                            WHEN 'apr' THEN '04' WHEN 'may' THEN '05' WHEN 'jun' THEN '06'
                            WHEN 'jul' THEN '07' WHEN 'aug' THEN '08' WHEN 'sep' THEN '09'
                            WHEN 'oct' THEN '10' WHEN 'nov' THEN '11' WHEN 'dec' THEN '12'
                            ELSE SUBSTRING(r.raw_data->>'Date' FROM 6 FOR 2)
                        END as month_key,
                        ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('admission', 'admissions') 
                            THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_adm,
                        ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('lead', 'leads') 
                            THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_lead,
                        ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('cucet') 
                            THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_cucet
                    FROM staging.records r
                    WHERE r.dataset_id = CAST(:tgt_id AS uuid)
                      AND r.raw_data->>'sheet_name' = 'Source'
                      {fb_campus_clause}
                      {fb_date_clause}
                    GROUP BY 1
                    HAVING month_key IS NOT NULL;
                """
                fb_rows = db.execute(text(fb_sql), fb_params).mappings().all()
                if fb_rows:
                    tgt_adm_map.clear()
                    tgt_lead_map.clear()
                    tgt_cucet_map.clear()
                    for r in fb_rows:
                        m_k = r.get("month_key")
                        if m_k:
                            tgt_adm_map[str(m_k)] = int(r["tgt_adm"] or 0)
                            tgt_lead_map[str(m_k)] = int(r["tgt_lead"] or 0)
                            tgt_cucet_map[str(m_k)] = int(r["tgt_cucet"] or 0)
            except Exception as fb_err:
                logger.warning(f"Target fallback monthly query error: {fb_err}")

    norm_cy_adm_map: Dict[str, int] = {}
    for k, v in cy_adm_map.items():
        m_suffix = k.split("-")[-1] if "-" in k else k
        norm_cy_adm_map[m_suffix] = norm_cy_adm_map.get(m_suffix, 0) + v

    norm_cy_lead_map: Dict[str, int] = {}
    for k, v in cy_lead_map.items():
        m_suffix = k.split("-")[-1] if "-" in k else k
        norm_cy_lead_map[m_suffix] = norm_cy_lead_map.get(m_suffix, 0) + v

    norm_cy_cucet_map: Dict[str, int] = {}
    for k, v in cy_cucet_map.items():
        m_suffix = k.split("-")[-1] if "-" in k else k
        norm_cy_cucet_map[m_suffix] = norm_cy_cucet_map.get(m_suffix, 0) + v

    norm_py_adm_map: Dict[str, int] = {}
    for k, v in py_adm_map.items():
        m_suffix = k.split("-")[-1] if "-" in k else k
        norm_py_adm_map[m_suffix] = norm_py_adm_map.get(m_suffix, 0) + v

    norm_py_lead_map: Dict[str, int] = {}
    for k, v in py_lead_map.items():
        m_suffix = k.split("-")[-1] if "-" in k else k
        norm_py_lead_map[m_suffix] = norm_py_lead_map.get(m_suffix, 0) + v

    norm_py_cucet_map: Dict[str, int] = {}
    for k, v in py_cucet_map.items():
        m_suffix = k.split("-")[-1] if "-" in k else k
        norm_py_cucet_map[m_suffix] = norm_py_cucet_map.get(m_suffix, 0) + v

    # Detect available CY month suffixes present in uploaded data
    avail_cy_suffixes = set()
    for k in list(cy_adm_map.keys()) + list(cy_lead_map.keys()) + list(cy_cucet_map.keys()):
        if k:
            suf = k.split("-")[-1] if "-" in k else k
            avail_cy_suffixes.add(suf)

    # If date filter active, all months in the selected range are treated as in scope
    has_partial_months = not has_date_filter and len(avail_cy_suffixes) > 0 and len(avail_cy_suffixes) < 12

    norm_metric = metric.lower().strip()
    trend: List[Dict[str, Any]] = []

    for m_name, month_key in months_meta:
        m_suffix = month_key.split("-")[-1]
        
        # Check if month is uploaded for CY
        is_cy_available = not has_partial_months or (m_suffix in avail_cy_suffixes)

        if is_cy_available:
            c_l = norm_cy_lead_map.get(m_suffix, 0)
            c_a = norm_cy_adm_map.get(m_suffix, 0)
            c_c = norm_cy_cucet_map.get(m_suffix, 0)
            c_r = _percentage(c_a, c_l)
        else:
            c_l = None
            c_a = None
            c_c = None
            c_r = None

        if has_py_dataset:
            p_l = norm_py_lead_map.get(m_suffix, 0)
            p_a = norm_py_adm_map.get(m_suffix, 0)
            p_c = norm_py_cucet_map.get(m_suffix, 0)
            p_r = _percentage(p_a, p_l)
        else:
            p_l = None
            p_a = None
            p_c = None
            p_r = None

        if has_target_master:
            t_a = tgt_adm_map.get(m_suffix, 0)
            t_l = tgt_lead_map.get(m_suffix, 0)
            t_c = tgt_cucet_map.get(m_suffix, 0)
        else:
            t_a = None
            t_l = None
            t_c = None

        if not is_cy_available:
            cy_val = None
        elif norm_metric in ("leads", "lead"):
            cy_val = c_l
        elif norm_metric in ("cucet", "cucet_registrations"):
            cy_val = c_c
        elif norm_metric in ("conversion_rate", "conversion", "rate"):
            cy_val = c_r
        else:
            cy_val = c_a

        if not has_py_dataset:
            py_val = None
        elif norm_metric in ("leads", "lead"):
            py_val = p_l
        elif norm_metric in ("cucet", "cucet_registrations"):
            py_val = p_c
        elif norm_metric in ("conversion_rate", "conversion", "rate"):
            py_val = p_r
        else:
            py_val = p_a

        target_val = None
        if has_target_master:
            target_val = t_l if norm_metric in ("leads", "lead") else (t_c if norm_metric in ("cucet", "cucet_registrations") else t_a)

        trend.append({
            "month": m_name,
            "month_key": month_key,
            "is_available": is_cy_available,
            "cy_leads": c_l,
            "cy_cucet": c_c,
            "cy_admission": c_a,
            "cy_conversion_rate": c_r,
            "py_leads": p_l,
            "py_cucet": p_c,
            "py_admission": p_a,
            "py_conversion_rate": p_r,
            "target_admission": t_a,
            "target_leads": t_l,
            "target_cucet": t_c,
            "metric_value": cy_val,
            "py_value": py_val,
            "cy": cy_val,
            "py": py_val,
            "target": target_val,
        })

    return trend


def get_agg_performance_rankings(
    db: Session,
    dimension: str = "program_name",
    campus: str | None = None,
    years: List[int] | str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> Dict[str, List[Dict[str, Any]]]:
    """Performance rankings using the aggregated table with fallback.
    Supports dynamic from_date and to_date range filtering with equivalent PY period.
    """
    scope = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope["cy_year"]
    py_year = scope["py_year"]
    safe_dim = _resolve_dimension_col(dimension)

    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    from_m = from_date.strip()[:7] if has_date_filter else None
    to_m = to_date.strip()[:7] if has_date_filter else None

    # Build base WHERE clause (aggregated table already limited by year)
    where_clause, params = _build_scope_where([], state, source, program)
    if campus and campus.lower() != "all":
        where_clause += ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus
    where_clause += " AND academic_year = :cy_year"
    params["cy_year"] = cy_year
    params["limit_val"] = limit

    # Current year rows
    if has_date_filter:
        params["from_m"] = from_m
        params["to_m"] = to_m
        sql = f"""
            SELECT "{safe_dim}" as entity,
                   SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN leads_cy ELSE 0 END) as cy_leads,
                   SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN admission_cy ELSE 0 END) as cy_admission
            FROM analytics.dashboard_agg
            WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
            GROUP BY "{safe_dim}"
            HAVING SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN leads_cy ELSE 0 END) > 0 
                OR SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN admission_cy ELSE 0 END) > 0
            ORDER BY cy_admission DESC, cy_leads DESC
            LIMIT :limit_val
        """
        fallback_sql = f"""
            SELECT "{safe_dim}" as entity,
                   SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cy_leads ELSE 0 END) as cy_leads,
                   SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN cy_admission ELSE 0 END) as cy_admission
            FROM analytics.uploaded_metrics
            WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
            GROUP BY "{safe_dim}"
            HAVING SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cy_leads ELSE 0 END) > 0 
                OR SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN cy_admission ELSE 0 END) > 0
            ORDER BY cy_admission DESC, cy_leads DESC
            LIMIT :limit_val
        """
    else:
        sql = f"""
            SELECT "{safe_dim}" as entity,
                   SUM(leads_cy) as cy_leads,
                   SUM(admission_cy) as cy_admission
            FROM analytics.dashboard_agg
            WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
            GROUP BY "{safe_dim}"
            HAVING SUM(leads_cy) > 0 OR SUM(admission_cy) > 0
            ORDER BY cy_admission DESC, cy_leads DESC
            LIMIT :limit_val
        """
        fallback_sql = f"""
            SELECT "{safe_dim}" as entity,
                   SUM(cy_leads) as cy_leads,
                   SUM(cy_admission) as cy_admission
            FROM analytics.uploaded_metrics
            WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
            GROUP BY "{safe_dim}"
            HAVING SUM(cy_leads) > 0 OR SUM(cy_admission) > 0
            ORDER BY cy_admission DESC, cy_leads DESC
            LIMIT :limit_val
        """
    cy_rows = _run_agg_query(db, sql, params, fallback_sql, params)

    # PY data per entity (if PY year exists)
    py_map: Dict[str, Dict[str, int]] = {}
    if py_year is not None:
        py_params = dict(params)
        py_params["py_year"] = py_year
        py_where = where_clause.replace('academic_year = :cy_year', 'academic_year = :py_year')
        if has_date_filter:
            year_diff = (cy_year - py_year) if (cy_year and py_year) else 1
            py_from_date = get_py_date(from_date.strip(), year_diff)
            py_to_date = get_py_date(to_date.strip(), year_diff)
            py_from_m = py_from_date[:7]
            py_to_m = py_to_date[:7]
            py_params["py_from_m"] = py_from_m
            py_params["py_to_m"] = py_to_m
            py_sql = f"""
                SELECT "{safe_dim}" as entity,
                       SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN GREATEST(leads_cy, leads_py) ELSE 0 END) as py_leads,
                       SUM(CASE WHEN admission_month >= :py_from_m AND admission_month <= :py_to_m THEN GREATEST(admission_cy, admission_py) ELSE 0 END) as py_admission
                FROM analytics.dashboard_agg
                WHERE {py_where} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
                GROUP BY "{safe_dim}"
            """
            fallback_py_sql = f"""
                SELECT "{safe_dim}" as entity,
                       SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN cy_leads ELSE 0 END) as py_leads,
                       SUM(CASE WHEN admission_month >= :py_from_m AND admission_month <= :py_to_m THEN cy_admission ELSE 0 END) as py_admission
                FROM analytics.uploaded_metrics
                WHERE {py_where} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
                GROUP BY "{safe_dim}"
            """
        else:
            py_sql = f"""
                SELECT "{safe_dim}" as entity,
                       SUM(leads_cy) as py_leads,
                       SUM(admission_cy) as py_admission
                FROM analytics.dashboard_agg
                WHERE {py_where} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
                GROUP BY "{safe_dim}"
            """
            fallback_py_sql = f"""
                SELECT "{safe_dim}" as entity,
                       SUM(cy_leads) as py_leads,
                       SUM(cy_admission) as py_admission
                FROM analytics.uploaded_metrics
                WHERE {py_where} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
                GROUP BY "{safe_dim}"
            """
        py_rows = _run_agg_query(db, py_sql, py_params, fallback_py_sql, py_params)
        for pr in py_rows:
            key = str(pr["entity"]).strip().lower()
            py_map[key] = {"py_leads": int(pr["py_leads"] or 0), "py_admission": int(pr["py_admission"] or 0)}

    all_items: List[Dict[str, Any]] = []
    for r in cy_rows:
        entity_name = str(r["entity"])
        key = entity_name.strip().lower()
        c_leads = int(r["cy_leads"] or 0)
        c_adm = int(r["cy_admission"] or 0)
        c_rate = _percentage(c_adm, c_leads)
        if py_year is not None and key in py_map:
            p_info = py_map[key]
            p_leads = p_info["py_leads"]
            p_adm = p_info["py_admission"]
            p_rate = _percentage(p_adm, p_leads)
            adm_change = c_adm - p_adm
            growth = percentage_change(c_adm, p_adm)
        else:
            p_leads = p_adm = p_rate = None
            adm_change = growth = None
        all_items.append({
            "entity": entity_name,
            "cy_leads": c_leads,
            "cy_admission": c_adm,
            "cy_rate": c_rate,
            "py_leads": p_leads,
            "py_admission": p_adm,
            "py_rate": p_rate,
            "admission_change": adm_change,
            "growth_pct": growth,
        })

    if py_year is not None:
        with_change = [x for x in all_items if x["admission_change"] is not None]
        improvements = sorted([x for x in with_change if x["admission_change"] > 0],
                             key=lambda x: (x["admission_change"], x["cy_admission"]),
                             reverse=True)
        declines = sorted([x for x in with_change if x["admission_change"] < 0],
                          key=lambda x: x["admission_change"])
    else:
        improvements = sorted(all_items, key=lambda x: x["cy_admission"], reverse=True)
        declines = []

    return {"improvements": improvements[:50], "declines": declines[:50]}


def get_agg_entity_detail(
    db: Session,
    dimension: str,
    value: str,
    campus: str | None = None,
    years: List[int] | str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> Dict[str, Any] | None:
    """Entity detail using the aggregated table with fallback.
    Supports resolution by program_code, raw_program_code, or program_name,
    and supports dynamic date range filtering.
    """
    scope = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope["cy_year"]
    py_year = scope["py_year"]
    safe_dim = _resolve_dimension_col(dimension)

    # Build WHERE for current year
    where_clause, params = _build_scope_where([], None, None, None)
    if campus and campus.lower() != "all":
        where_clause += ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus
    where_clause += " AND academic_year = :cy_year"
    params["cy_year"] = cy_year

    val_trimmed = value.strip()
    if safe_dim == "program_name":
        where_clause += (
            ' AND (LOWER("program_name") = LOWER(:val) '
            'OR LOWER("program_code") = LOWER(:val) '
            'OR LOWER("raw_program_code") = LOWER(:val) '
            'OR "program_name" ILIKE :val_suffix)'
        )
        params["val"] = val_trimmed
        params["val_suffix"] = f"%::{val_trimmed}"
    else:
        where_clause += f' AND LOWER("{safe_dim}") = LOWER(:val)'
        params["val"] = val_trimmed

    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    from_m = from_date.strip()[:7] if has_date_filter else None
    to_m = to_date.strip()[:7] if has_date_filter else None

    if has_date_filter:
        params["from_m"] = from_m
        params["to_m"] = to_m
        agg_sql = f"""
            SELECT COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN leads_cy ELSE 0 END),0) AS leads,
                   COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cucet_cy ELSE 0 END),0) AS cucet,
                   COALESCE(SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN admission_cy ELSE 0 END),0) AS admission
            FROM analytics.dashboard_agg
            WHERE {where_clause}
        """
        fallback_sql = f"""
            SELECT COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cy_leads ELSE 0 END),0) AS leads,
                   COALESCE(SUM(CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cy_cucet ELSE 0 END),0) AS cucet,
                   COALESCE(SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN cy_admission ELSE 0 END),0) AS admission
            FROM analytics.uploaded_metrics
            WHERE {where_clause}
        """
    else:
        agg_sql = f"""
            SELECT COALESCE(SUM(leads_cy),0) AS leads,
                   COALESCE(SUM(cucet_cy),0) AS cucet,
                   COALESCE(SUM(admission_cy),0) AS admission
            FROM analytics.dashboard_agg
            WHERE {where_clause}
        """
        fallback_sql = f"""
            SELECT COALESCE(SUM(cy_leads),0) AS leads,
                   COALESCE(SUM(cy_cucet),0) AS cucet,
                   COALESCE(SUM(cy_admission),0) AS admission
            FROM analytics.uploaded_metrics
            WHERE {where_clause}
        """
    row = _run_agg_query(db, agg_sql, params, fallback_sql, params)[0]
    cy_leads = int(row["leads"] or 0)
    cy_cucet = int(row["cucet"] or 0)
    cy_admission = int(row["admission"] or 0)

    # PY values
    py_leads = py_cucet = py_admission = None
    if py_year is not None:
        py_params = dict(params)
        py_params["py_year"] = py_year
        py_where = where_clause.replace('academic_year = :cy_year', 'academic_year = :py_year')
        if has_date_filter:
            year_diff = (cy_year - py_year) if (cy_year and py_year) else 1
            py_from_date = get_py_date(from_date.strip(), year_diff)
            py_to_date = get_py_date(to_date.strip(), year_diff)
            py_from_m = py_from_date[:7]
            py_to_m = py_to_date[:7]
            py_params["py_from_m"] = py_from_m
            py_params["py_to_m"] = py_to_m
            agg_sql_py = f"""
                SELECT COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN GREATEST(leads_cy, leads_py) ELSE 0 END),0) AS leads,
                       COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN GREATEST(cucet_cy, cucet_py) ELSE 0 END),0) AS cucet,
                       COALESCE(SUM(CASE WHEN admission_month >= :py_from_m AND admission_month <= :py_to_m THEN GREATEST(admission_cy, admission_py) ELSE 0 END),0) AS admission
                FROM analytics.dashboard_agg
                WHERE {py_where}
            """
            fallback_sql_py = f"""
                SELECT COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN cy_leads ELSE 0 END),0) AS leads,
                       COALESCE(SUM(CASE WHEN created_month >= :py_from_m AND created_month <= :py_to_m THEN cy_cucet ELSE 0 END),0) AS cucet,
                       COALESCE(SUM(CASE WHEN admission_month >= :py_from_m AND admission_month <= :py_to_m THEN cy_admission ELSE 0 END),0) AS admission
                FROM analytics.uploaded_metrics
                WHERE {py_where}
            """
        else:
            agg_sql_py = f"""
                SELECT COALESCE(SUM(leads_py),0) AS leads,
                   COALESCE(SUM(cucet_py),0) AS cucet,
                   COALESCE(SUM(admission_py),0) AS admission
                FROM analytics.dashboard_agg
                WHERE {py_where}
            """
            fallback_sql_py = f"""
                SELECT COALESCE(SUM(cy_leads),0) AS leads,
                   COALESCE(SUM(cy_cucet),0) AS cucet,
                   COALESCE(SUM(cy_admission),0) AS admission
                FROM analytics.uploaded_metrics
                WHERE {py_where}
            """
        row_py = _run_agg_query(db, agg_sql_py, py_params, fallback_sql_py, py_params)[0]
        py_leads = int(row_py["leads"] or 0)
        py_cucet = int(row_py["cucet"] or 0)
        py_admission = int(row_py["admission"] or 0)

    if cy_leads == 0 and cy_cucet == 0 and cy_admission == 0 and (py_leads is None or (py_leads == 0 and py_cucet == 0 and py_admission == 0)):
        return None

    cy_rate = _percentage(cy_admission, cy_leads)
    py_rate = _percentage(py_admission, py_leads) if py_leads is not None else None

    # Fetch canonical program attributes from organization.course_master if dimension is program
    program_meta = None
    if dimension in ("program_name", "program", "program_code"):
        cm_row = db.execute(
            text("""
                SELECT program_code, program_name, course_cluster, degree_type, program_category, program_campus, program_group, program_status
                FROM organization.course_master
                WHERE LOWER(program_name) = LOWER(:val) OR LOWER(program_code) = LOWER(:val) OR LOWER(program_key) = LOWER(:val)
                LIMIT 1;
            """),
            {"val": val_trimmed},
        ).fetchone()
        if cm_row:
            program_meta = dict(cm_row._mapping)

    return {
        "dimension": dimension,
        "value": value,
        "current_year": cy_year,
        "previous_year": py_year,
        "from_date": from_date,
        "to_date": to_date,
        "program_attributes": program_meta,
        "breakdowns": {},
        "overview": {
            "leads": {
                "cy": cy_leads,
                "py": py_leads,
                "change": (cy_leads - py_leads) if py_leads is not None else None,
                "growth_pct": percentage_change(cy_leads, py_leads),
            },
            "admissions": {
                "cy": cy_admission,
                "py": py_admission,
                "change": (cy_admission - py_admission) if py_admission is not None else None,
                "growth_pct": percentage_change(cy_admission, py_admission),
            },
            "conversion_rate": {
                "cy": cy_rate,
                "py": py_rate,
                "change": round(cy_rate - py_rate, 2) if py_rate is not None else None,
                "growth_pct": percentage_change(cy_rate, py_rate),
            },
        },
    }


def get_agg_exploration_data(
    db: Session,
    dimension: str,
    metric: str = "admission",
    campus: str | None = None,
    years: List[int] | str | None = None,
    limit: int = 10,
) -> Dict[str, Any] | None:
    """Exploration data using the aggregate layer.

    Returns positive and negative entities based on the chosen metric.
    """
    scope = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope["cy_year"]
    where_clause, params = _build_scope_where([], None, None, None)
    if campus and campus.lower() != "all":
        where_clause += ' AND LOWER("campus_name") = LOWER(:campus)'
        params["campus"] = campus
    where_clause += " AND academic_year = :cy_year"
    params["cy_year"] = cy_year

    safe_dim = _resolve_dimension_col(dimension)
    agg_sql = f"""
        SELECT "{safe_dim}" AS entity,
               COALESCE(SUM(leads_cy),0) AS leads,
               COALESCE(SUM(admission_cy),0) AS admission
        FROM analytics.dashboard_agg
        WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
        GROUP BY "{safe_dim}"
    """
    fallback_sql = f"""
        SELECT "{safe_dim}" AS entity,
               COALESCE(SUM(cy_leads),0) AS leads,
               COALESCE(SUM(cy_admission),0) AS admission
        FROM analytics.uploaded_metrics
        WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
        GROUP BY "{safe_dim}"
    """
    rows = _run_agg_query(db, agg_sql, params, fallback_sql, params)

    processed: List[Dict[str, Any]] = []
    for r in rows:
        e_name = str(r["entity"])
        cy_l = int(r["leads"] or 0)
        cy_a = int(r["admission"] or 0)
        cy_r = _percentage(cy_a, cy_l)
        if metric == "leads":
            change = cy_l
            growth = None
        elif metric == "admission":
            change = cy_a
            growth = None
        else:
            change = round(cy_r - 0, 2)
            growth = percentage_change(cy_r, 0)
        processed.append({
            "entity": e_name,
            "cy_leads": cy_l,
            "cy_admission": cy_a,
            "cy_rate": cy_r,
            "change": change,
            "growth_pct": growth,
        })

    pos = [x for x in processed if (x["change"] or 0) > 0]
    pos.sort(key=lambda x: x["change"], reverse=True)
    neg = [x for x in processed if (x["change"] or 0) < 0]
    neg.sort(key=lambda x: x["change"])
    return {"positive": pos[:limit], "negative": neg[:limit]}


def get_agg_top_performers(
    db: Session,
    campus: str | None = None,
    years: List[int] | str | None = None,
    metric: str = "admission",
    limit: int = 5,
    from_date: str | None = None,
    to_date: str | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Top performers per major dimension using aggregated table with fallback.
    Supports dynamic from_date and to_date range filtering.
    """
    dimensions = ["program_name", "source", "state", "owner", "campus_name"]
    res: Dict[str, List[Dict[str, Any]]] = {}
    scope = resolve_dataset_scope(db, campus=campus, years=years)
    cy_year = scope["cy_year"]

    norm_metric = metric.lower().strip()
    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    from_m = from_date.strip()[:7] if has_date_filter else None
    to_m = to_date.strip()[:7] if has_date_filter else None

    if has_date_filter:
        leads_expr = "CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN leads_cy ELSE 0 END"
        adm_expr = "CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN admission_cy ELSE 0 END"
        fb_leads_expr = "CASE WHEN created_month >= :from_m AND created_month <= :to_m THEN cy_leads ELSE 0 END"
        fb_adm_expr = "CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN cy_admission ELSE 0 END"
    else:
        leads_expr = "leads_cy"
        adm_expr = "admission_cy"
        fb_leads_expr = "cy_leads"
        fb_adm_expr = "cy_admission"

    col_expr = leads_expr if norm_metric == "leads" else adm_expr
    fallback_col = fb_leads_expr if norm_metric == "leads" else fb_adm_expr

    for dim in dimensions:
        safe_dim = _resolve_dimension_col(dim)
        where_clause, params = _build_scope_where([], None, None, None)
        if campus and campus.lower() != "all":
            where_clause += ' AND LOWER("campus_name") = LOWER(:campus)'
            params["campus"] = campus
        where_clause += " AND academic_year = :cy_year"
        params["cy_year"] = cy_year
        if has_date_filter:
            params["from_m"] = from_m
            params["to_m"] = to_m

        agg_sql = f"""
            SELECT "{safe_dim}" AS entity,
                   SUM({col_expr}) AS val,
                   SUM({leads_expr}) AS cy_leads,
                   SUM({adm_expr}) AS cy_admission
            FROM analytics.dashboard_agg
            WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
            GROUP BY "{safe_dim}"
            HAVING SUM({leads_expr}) > 0 OR SUM({adm_expr}) > 0
            ORDER BY val DESC
            LIMIT :limit_val
        """
        fallback_sql = f"""
            SELECT "{safe_dim}" AS entity,
                   SUM({fallback_col}) AS val,
                   SUM({fb_leads_expr}) AS cy_leads,
                   SUM({fb_adm_expr}) AS cy_admission
            FROM analytics.uploaded_metrics
            WHERE {where_clause} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
            GROUP BY "{safe_dim}"
            HAVING SUM({fb_leads_expr}) > 0 OR SUM({fb_adm_expr}) > 0
            ORDER BY val DESC
            LIMIT :limit_val
        """
        exec_params = dict(params)
        exec_params["limit_val"] = limit
        try:
            rows = _run_agg_query(db, agg_sql, exec_params, fallback_sql, exec_params)
            items = []
            for r in rows:
                c_l = int(r["cy_leads"] or 0)
                c_a = int(r["cy_admission"] or 0)
                if norm_metric == "conversion_rate":
                    val = _percentage(c_a, c_l)
                else:
                    val = int(r["val"] or 0)
                items.append({
                    "entity": str(r["entity"]),
                    "value": val,
                    "cy_leads": c_l,
                    "cy_admission": c_a,
                })
            if norm_metric == "conversion_rate":
                items.sort(key=lambda x: x["value"], reverse=True)
                items = items[:limit]
            res[dim] = items
        except Exception as e:
            logger.warning(f"Error fetching top performers for dimension {dim}: {e}")
            res[dim] = []

    return res


def get_agg_insights(
    db: Session,
    campus: str | None = None,
    years: List[int] | str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> List[Dict[str, Any]]:
    """Generate dynamic insight cards based on pre-aggregated data with optional date range."""
    insights: List[Dict[str, Any]] = []

    rankings = get_agg_performance_rankings(
        db, dimension="program_name", campus=campus, years=years, state=state, source=source, program=program,
        from_date=from_date, to_date=to_date, limit=5,
    )
    improvements = rankings.get("improvements", [])
    declines = rankings.get("declines", [])

    if improvements:
        top_prog = improvements[0]
        insights.append({
            "id": "top_program",
            "title": "Top Performing Program",
            "text": f"{top_prog['entity']} led performance with {top_prog['cy_admission']:,} admissions ({top_prog['cy_leads']:,} leads).",
            "dimension": "program_name",
            "value": top_prog["entity"],
            "type": "positive",
        })

    if declines:
        bottom_prog = declines[0]
        insights.append({
            "id": "top_decline_program",
            "title": "Program Needing Attention",
            "text": f"{bottom_prog['entity']} requires review with {bottom_prog['cy_admission']:,} admissions from {bottom_prog['cy_leads']:,} leads.",
            "dimension": "program_name",
            "value": bottom_prog["entity"],
            "type": "warning",
        })

    src_rankings = get_agg_performance_rankings(
        db, dimension="source", campus=campus, years=years, state=state, source=source, program=program,
        from_date=from_date, to_date=to_date, limit=5,
    )
    src_improvements = src_rankings.get("improvements", [])
    if src_improvements:
        top_src = src_improvements[0]
        insights.append({
            "id": "top_source",
            "title": "Primary Acquisition Source",
            "text": f"Source {top_src['entity']} generated {top_src['cy_admission']:,} admissions at a conversion rate of {top_src['cy_rate']}%.",
            "dimension": "source",
            "value": top_src["entity"],
            "type": "positive",
        })

    return insights

