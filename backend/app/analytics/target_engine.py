"""
Target Engine: Target vs Actual Analytical Reconciliation.
Calculates target achievement % across dimensions (Program, State, Source, Campus, Overall) and months.
Enforces strict rule: If actual data for a period is missing or in the future, reports actual as null and achievement as null ('N/A'), NEVER 0%.
"""
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _parse_int_month(val: Any) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip()
    if "-" in s:
        parts = s.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
    if s.isdigit():
        return int(s)
    return None

def get_target_performance(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    dimension_type: Optional[str] = None,
    month: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Returns Target vs Actual performance metrics for specified scope.
    """
    if academic_year is None:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)

    campus_filter = ""
    params: Dict[str, Any] = {"year": academic_year}
    if campus and campus.strip().lower() != "all":
        campus_filter = " AND LOWER(campus_name) = LOWER(:campus)"
        params["campus"] = campus.strip()

    dim_filter = ""
    if dimension_type and dimension_type.strip().lower() != "all":
        dim_filter = " AND LOWER(dimension_type) = LOWER(:dim_type)"
        params["dim_type"] = dimension_type.strip()

    month_filter = ""
    if month is not None:
        month_filter = " AND month = :month"
        params["month"] = month

    # 1. Fetch Target records
    target_sql = text(f"""
        SELECT
            dimension_type,
            dimension_value,
            month,
            SUM(target_leads) AS target_leads,
            SUM(target_admissions) AS target_admissions,
            SUM(target_cucet) AS target_cucet
        FROM analytics.targets
        WHERE academic_year = :year {campus_filter} {dim_filter} {month_filter}
        GROUP BY dimension_type, dimension_value, month
        ORDER BY dimension_type, target_leads DESC
    """)

    try:
        target_rows = db.execute(target_sql, params).mappings().all()
    except Exception as e:
        logger.warning(f"Notice querying analytics.targets: {e}")
        db.rollback()
        target_rows = []

    # 2. Fetch Actual records from dashboard_agg with fallback to uploaded_metrics
    actual_where = "WHERE academic_year = :year"
    if campus and campus.strip().lower() != "all":
        actual_where += ' AND LOWER("campus_name") = LOWER(:campus)'

    dim_select = '"program_name" AS program, "state" AS state, "source" AS source, "campus_name" AS campus'
    dim_group = '"program_name", "state", "source", "campus_name"'

    dtype_clean = (dimension_type or "").strip().lower()
    if dtype_clean == "program":
        dim_select = '"program_name" AS program, NULL AS state, NULL AS source, NULL AS campus'
        dim_group = '"program_name"'
    elif dtype_clean == "state":
        dim_select = 'NULL AS program, "state" AS state, NULL AS source, NULL AS campus'
        dim_group = '"state"'
    elif dtype_clean == "source":
        dim_select = 'NULL AS program, NULL AS state, "source" AS source, NULL AS campus'
        dim_group = '"source"'
    elif dtype_clean == "campus":
        dim_select = 'NULL AS program, NULL AS state, NULL AS source, "campus_name" AS campus'
        dim_group = '"campus_name"'
    elif dtype_clean == "overall":
        dim_select = 'NULL AS program, NULL AS state, NULL AS source, NULL AS campus'
        dim_group = '1'

    actual_sql = text(f"""
        SELECT
            {dim_select},
            created_month,
            SUM(leads_cy) AS leads,
            SUM(cucet_cy) AS cucet,
            SUM(admission_cy) AS admissions
        FROM analytics.dashboard_agg
        {actual_where}
        GROUP BY {dim_group}, created_month
    """)

    try:
        try:
            db.execute(text("SET LOCAL jit = off;"))
        except Exception:
            pass
        actual_rows = db.execute(actual_sql, params).mappings().all()
    except Exception:
        actual_rows = []

    if not actual_rows:
        fallback_actual_sql = text(f"""
            SELECT
                {dim_select},
                created_month,
                SUM(cy_leads) AS leads,
                SUM(cy_cucet) AS cucet,
                SUM(cy_admission) AS admissions
            FROM analytics.uploaded_metrics
            {actual_where}
            GROUP BY {dim_group}, created_month
        """)
        actual_rows = db.execute(fallback_actual_sql, params).mappings().all()

    # Determine max available actual month in CY to distinguish missing future months from 0 actuals
    max_actual_month = None
    if actual_rows:
        months_found = [
            _parse_int_month(r["created_month"])
            for r in actual_rows
            if r["created_month"] is not None and _parse_int_month(r["created_month"]) is not None
        ]
        if months_found:
            max_actual_month = max(months_found)

    # Pre-index actuals into a fast dictionary lookup: key = (dimension_type_lower, dimension_value_lower, month_int_or_None)
    actual_lookup = defaultdict(lambda: {"leads": 0, "admissions": 0})
    for a in actual_rows:
        a_m = _parse_int_month(a["created_month"])
        l = int(a["leads"] or 0)
        adm = int(a["admissions"] or 0)

        # Index overall (both for specific month and for all months)
        actual_lookup[("overall", "overall", a_m)]["leads"] += l
        actual_lookup[("overall", "overall", a_m)]["admissions"] += adm
        actual_lookup[("overall", "overall", None)]["leads"] += l
        actual_lookup[("overall", "overall", None)]["admissions"] += adm

        if a.get("program"):
            p = str(a["program"]).strip().lower()
            actual_lookup[("program", p, a_m)]["leads"] += l
            actual_lookup[("program", p, a_m)]["admissions"] += adm
            actual_lookup[("program", p, None)]["leads"] += l
            actual_lookup[("program", p, None)]["admissions"] += adm

        if a.get("state"):
            st = str(a["state"]).strip().lower()
            actual_lookup[("state", st, a_m)]["leads"] += l
            actual_lookup[("state", st, a_m)]["admissions"] += adm
            actual_lookup[("state", st, None)]["leads"] += l
            actual_lookup[("state", st, None)]["admissions"] += adm

        if a.get("source"):
            src = str(a["source"]).strip().lower()
            actual_lookup[("source", src, a_m)]["leads"] += l
            actual_lookup[("source", src, a_m)]["admissions"] += adm
            actual_lookup[("source", src, None)]["leads"] += l
            actual_lookup[("source", src, None)]["admissions"] += adm

        if a.get("campus"):
            cmp = str(a["campus"]).strip().lower()
            actual_lookup[("campus", cmp, a_m)]["leads"] += l
            actual_lookup[("campus", cmp, a_m)]["admissions"] += adm
            actual_lookup[("campus", cmp, None)]["leads"] += l
            actual_lookup[("campus", cmp, None)]["admissions"] += adm

    items = []
    tot_target_leads = 0
    tot_target_admissions = 0
    tot_actual_leads = 0
    tot_actual_admissions = 0
    has_actual_data = len(actual_rows) > 0

    for t in target_rows:
        dtype = t["dimension_type"]
        dval = t["dimension_value"]
        raw_t_m = t["month"]
        t_m = _parse_int_month(raw_t_m)

        t_leads = float(t["target_leads"] or 0.0)
        t_adm = float(t["target_admissions"] or 0.0)
        tot_target_leads += t_leads
        tot_target_admissions += t_adm

        # Check if actual is available or in the future
        is_future_or_missing = False
        if t_m is not None and max_actual_month is not None and t_m > max_actual_month:
            is_future_or_missing = True
        elif not has_actual_data:
            is_future_or_missing = True

        if is_future_or_missing:
            act_leads = None
            act_adm = None
            leads_pct = None
            adm_pct = None
            status_label = "N/A (Future/Missing Period)"
        else:
            dtype_lower = str(dtype).strip().lower() if dtype else ""
            dval_lower = "overall" if dtype_lower == "overall" else (str(dval).strip().lower() if dval else "")
            match = actual_lookup.get((dtype_lower, dval_lower, t_m), {"leads": 0, "admissions": 0})
            act_leads = match["leads"]
            act_adm = match["admissions"]
            tot_actual_leads += act_leads
            tot_actual_admissions += act_adm

            leads_pct = round((act_leads / t_leads * 100), 2) if t_leads > 0 else 0.0
            adm_pct = round((act_adm / t_adm * 100), 2) if t_adm > 0 else 0.0
            status_label = "Achieved" if adm_pct >= 100 else ("On Track" if adm_pct >= 80 else "Needs Attention")

        items.append({
            "dimension_type": dtype,
            "dimension_value": dval,
            "month": t_m,
            "target_leads": t_leads,
            "actual_leads": act_leads,
            "leads_achievement_pct": leads_pct,
            "target_admissions": t_adm,
            "actual_admissions": act_adm,
            "admissions_achievement_pct": adm_pct,
            "status": status_label,
        })

    # Overall Summary
    overall_leads_pct = round((tot_actual_leads / tot_target_leads * 100), 2) if (tot_target_leads > 0 and has_actual_data) else None
    overall_adm_pct = round((tot_actual_admissions / tot_target_admissions * 100), 2) if (tot_target_admissions > 0 and has_actual_data) else None

    return {
        "academic_year": academic_year,
        "campus": campus or "All",
        "has_actual_data": has_actual_data,
        "max_actual_month": max_actual_month,
        "summary": {
            "target_leads": tot_target_leads,
            "actual_leads": tot_actual_leads if has_actual_data else None,
            "leads_achievement_pct": overall_leads_pct,
            "target_admissions": tot_target_admissions,
            "actual_admissions": tot_actual_admissions if has_actual_data else None,
            "admissions_achievement_pct": overall_adm_pct,
        },
        "items": items,
    }
