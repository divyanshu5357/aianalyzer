"""
Analytical service for State-Wise Analysis with strict Lazy Hierarchical Loading.
Provides aggregated metrics across 3 hierarchy levels:
  Level 1: State (e.g. PUNJAB, HARYANA, UTTAR PRADESH, HIMACHAL PRADESH)
  Level 2: Source Category (e.g. IN HOUSE, OUT SOURCED, OTHERS)
  Level 3: Sub-Source (e.g. Google, CollegeDekho, Shiksha, Website, Direct)
All aggregations are computed 100% on PostgreSQL (GROUP BY, SUM). Zero raw CRM records are loaded.
"""

from typing import Dict, Any, List, Optional
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.analytics.aggregate_service import get_py_date

logger = logging.getLogger(__name__)

# Trusted sorting columns to prevent SQL injection
VALID_SORT_FIELDS = {
    "state": "state",
    "name": "name",
    "py_leads": "py_leads",
    "cy_leads": "cy_leads",
    "var_leads": "var_leads",
    "py_cucet": "py_cucet",
    "cy_cucet": "cy_cucet",
    "var_cucet": "var_cucet",
    "lead_cucet_pct": "lead_cucet_pct",
    "py_adm": "py_adm",
    "cy_adm": "cy_adm",
    "var_adm": "var_adm",
    "lead_adm_pct": "lead_adm_pct",
    "cucet_adm_pct": "cucet_adm_pct",
    "net_admissions": "net_admissions",
}

_STATE_MASTER_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def _get_state_master_lookup(db: Session) -> Dict[str, Dict[str, Any]]:
    global _STATE_MASTER_CACHE
    if _STATE_MASTER_CACHE is None:
        try:
            rows = db.execute(
                text("SELECT DISTINCT ON (LOWER(TRIM(state_name))) state_name, state_code FROM organization.state_master ORDER BY LOWER(TRIM(state_name)), state_code")
            ).fetchall()
            lookup = {}
            for r in rows:
                k = (r[0] or "").strip().lower()
                if k:
                    lookup[k] = {"state_name": r[0], "state_code": r[1]}
            _STATE_MASTER_CACHE = lookup
        except Exception:
            _STATE_MASTER_CACHE = {}
    return _STATE_MASTER_CACHE


def _calculate_row_metrics(
    name: str,
    py_leads: Optional[int],
    cy_leads: int,
    py_cucet: Optional[int],
    cy_cucet: int,
    py_adm: Optional[int],
    cy_adm: int,
    py_refunds: int,
    cy_refunds: int,
    lead_trend: List[int],
    node_id: str,
    level: int,
    has_children: bool,
    extra_props: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Helper to compute standardized report columns, variance metrics, and status indicator."""
    if py_leads is not None:
        var_leads = cy_leads - py_leads
        var_leads_pct = (
            round((var_leads / py_leads) * 100, 1)
            if py_leads > 0
            else (0.0 if cy_leads == 0 else 100.0)
        )
    else:
        var_leads = None
        var_leads_pct = None

    if py_cucet is not None:
        var_cucet = cy_cucet - py_cucet
        var_cucet_pct = (
            round((var_cucet / py_cucet) * 100, 1)
            if py_cucet > 0
            else (0.0 if cy_cucet == 0 else 100.0)
        )
    else:
        var_cucet = None
        var_cucet_pct = None

    lead_cucet_pct = round((cy_cucet / cy_leads) * 100, 1) if cy_leads > 0 else 0.0

    if py_adm is not None:
        var_adm = cy_adm - py_adm
        var_adm_pct = (
            round((var_adm / py_adm) * 100, 1)
            if py_adm > 0
            else (0.0 if cy_adm == 0 else 100.0)
        )
    else:
        var_adm = None
        var_adm_pct = None

    lead_adm_pct = round((cy_adm / cy_leads) * 100, 1) if cy_leads > 0 else 0.0
    cucet_adm_pct = round((cy_adm / cy_cucet) * 100, 1) if cy_cucet > 0 else 0.0

    net_admissions = cy_adm - cy_refunds
    refund_diff = cy_refunds - py_refunds

    py_refund_rate = (
        round((py_refunds / py_adm) * 100, 1)
        if (py_adm is not None and py_adm > 0)
        else 0.0
    )
    cy_refund_rate = round((cy_refunds / cy_adm) * 100, 1) if cy_adm > 0 else 0.0
    refund_rate_diff = round(cy_refund_rate - py_refund_rate, 1)

    # Dynamic status indicator:
    # Green (positive) if CY leads > PY leads
    # Red (negative) if CY leads < PY leads
    # Neutral if equal or if PY is missing
    if py_leads is None:
        status_indicator = "neutral"
    elif cy_leads > py_leads:
        status_indicator = "positive"
    elif cy_leads < py_leads:
        status_indicator = "negative"
    else:
        status_indicator = "neutral"

    row = {
        "id": node_id,
        "name": name,
        "state": name,
        "level": level,
        "has_children": has_children,
        "status_indicator": status_indicator,
        "py_leads": py_leads if py_leads is not None else 0,
        "cy_leads": cy_leads,
        "var_leads": var_leads if var_leads is not None else 0,
        "var_leads_pct": var_leads_pct if var_leads_pct is not None else 0.0,
        "py_cucet": py_cucet if py_cucet is not None else 0,
        "cy_cucet": cy_cucet,
        "var_cucet": var_cucet if var_cucet is not None else 0,
        "var_cucet_pct": var_cucet_pct if var_cucet_pct is not None else 0.0,
        "lead_cucet_pct": lead_cucet_pct,
        "py_adm": py_adm if py_adm is not None else 0,
        "cy_adm": cy_adm,
        "var_adm": var_adm if var_adm is not None else 0,
        "var_adm_pct": var_adm_pct if var_adm_pct is not None else 0.0,
        "lead_adm_pct": lead_adm_pct,
        "cucet_adm_pct": cucet_adm_pct,
        "lead_trend": lead_trend,
        "net_admissions": net_admissions,
        "refund_py_vs_cy": {
            "py": py_refunds,
            "cy": cy_refunds,
            "diff": refund_diff,
        },
        "refund_pct_py_vs_cy": {
            "py_pct": py_refund_rate,
            "cy_pct": cy_refund_rate,
            "diff_pct": refund_rate_diff,
        },
        "fee_paid": "N/A",
        "net_fee_paid_pct": "N/A",
    }
    if extra_props:
        row.update(extra_props)
    return row


def get_state_report_top_level(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    sort_by: str = "cy_leads",
    sort_order: str = "desc",
) -> Dict[str, Any]:
    """
    Level 1: Retrieve top-level States (~36 rows) plus scope-wide total row.
    Calculates 14+ standardized metrics strictly server-side with zero raw records sent to client.
    """
    if not academic_year:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)

    py_year = academic_year - 1
    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())

    # Optimize JIT for fast analytical queries
    try:
        db.execute(text("SET jit = off;"))
    except Exception:
        pass

    # Check if PY data exists in dashboard_agg for this scope
    py_exists_check = db.execute(
        text("SELECT 1 FROM analytics.dashboard_agg WHERE academic_year = :py_year LIMIT 1"),
        {"py_year": py_year},
    ).scalar()
    py_available = bool(py_exists_check)

    where_clauses = ["d.academic_year IN (:py_year, :cy_year)"]
    params: Dict[str, Any] = {"cy_year": academic_year, "py_year": py_year}

    if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
        where_clauses.append("LOWER(d.campus_name) = :campus")
        params["campus"] = campus.strip().lower()

    if has_date_filter:
        from_m = from_date.strip()[:7]
        to_m = to_date.strip()[:7]
        py_from_m = get_py_date(from_date.strip())[:7]
        py_to_m = get_py_date(to_date.strip())[:7]

        params["from_m"] = from_m
        params["to_m"] = to_m
        params["py_from_m"] = py_from_m
        params["py_to_m"] = py_to_m

        cy_lead_expr = "CASE WHEN d.academic_year = :cy_year AND d.created_month >= :from_m AND d.created_month <= :to_m THEN d.leads_cy ELSE 0 END"
        py_lead_expr = (
            "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year AND d.created_month >= :from_m AND d.created_month <= :to_m THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = (
            "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year AND d.admission_month >= :from_m AND d.admission_month <= :to_m THEN d.admission_cy ELSE 0 END"
        py_adm_expr = (
            "CASE WHEN d.academic_year = :py_year AND d.admission_month >= :py_from_m AND d.admission_month <= :py_to_m THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"
            if py_available
            else "0"
        )
    else:
        cy_lead_expr = "CASE WHEN d.academic_year = :cy_year THEN d.leads_cy ELSE 0 END"
        py_lead_expr = (
            "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = (
            "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year THEN d.admission_cy ELSE 0 END"
        py_adm_expr = (
            "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"
            if py_available
            else "0"
        )

    where_sql = " AND ".join(where_clauses)

    query_sql = f"""
        SELECT 
            COALESCE(NULLIF(TRIM(d.state), ''), 'UNMAPPED_STATE') as raw_state,
            SUM({py_lead_expr}) as py_leads,
            SUM({cy_lead_expr}) as cy_leads,
            SUM({py_cucet_expr}) as py_cucet,
            SUM({cy_cucet_expr}) as cy_cucet,
            SUM({py_adm_expr}) as py_adm,
            SUM({cy_adm_expr}) as cy_adm
        FROM analytics.dashboard_agg d
        WHERE {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(d.state), ''), 'UNMAPPED_STATE')
        HAVING (SUM({cy_lead_expr}) > 0 OR SUM({py_lead_expr}) > 0)
    """

    result_rows = db.execute(text(query_sql), params).fetchall()

    # Query monthly trend points for CY by state
    trend_where = ["d.academic_year = :cy_year", "d.created_month IS NOT NULL"]
    trend_params: Dict[str, Any] = {"cy_year": academic_year}
    if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
        trend_where.append("LOWER(d.campus_name) = :campus")
        trend_params["campus"] = campus.strip().lower()
    if has_date_filter:
        trend_where.append("d.created_month >= :from_m AND d.created_month <= :to_m")
        trend_params["from_m"] = from_date.strip()[:7]
        trend_params["to_m"] = to_date.strip()[:7]

    trend_sql = f"""
        SELECT 
            COALESCE(NULLIF(TRIM(d.state), ''), 'UNMAPPED_STATE') as raw_state,
            d.created_month,
            SUM(d.leads_cy) as leads
        FROM analytics.dashboard_agg d
        WHERE {" AND ".join(trend_where)}
        GROUP BY COALESCE(NULLIF(TRIM(d.state), ''), 'UNMAPPED_STATE'), d.created_month
        ORDER BY 1, 2
    """
    trend_rows = db.execute(text(trend_sql), trend_params).fetchall()

    # Build state -> [monthly_lead_counts] trend
    state_trends: Dict[str, Dict[str, int]] = {}
    distinct_months = set()
    for tr in trend_rows:
        s_key = tr[0]
        m_key = tr[1]
        cnt = int(tr[2] or 0)
        state_trends.setdefault(s_key, {})[m_key] = cnt
        distinct_months.add(m_key)

    sorted_months = sorted(list(distinct_months))

    # Total accumulators
    tot_py_leads = tot_cy_leads = tot_py_cucet = tot_cy_cucet = 0
    tot_py_adm = tot_cy_adm = 0
    tot_monthly: Dict[str, int] = {m: 0 for m in sorted_months}

    sm_lookup = _get_state_master_lookup(db)
    processed_rows = []
    for r in result_rows:
        raw_state = str(r[0])
        sm_info = sm_lookup.get(raw_state.strip().lower())
        canonical_name = str(sm_info["state_name"] if sm_info else raw_state)
        state_code = str(sm_info["state_code"]) if (sm_info and sm_info.get("state_code")) else None
        py_l = int(r[1] or 0) if py_available else None
        cy_l = int(r[2] or 0)
        py_c = int(r[3] or 0) if py_available else None
        cy_c = int(r[4] or 0)
        py_a = int(r[5] or 0) if py_available else None
        cy_a = int(r[6] or 0)

        if py_available and py_l is not None:
            tot_py_leads += py_l
            tot_py_cucet += (py_c or 0)
            tot_py_adm += (py_a or 0)

        tot_cy_leads += cy_l
        tot_cy_cucet += cy_c
        tot_cy_adm += cy_a

        st_trend_dict = state_trends.get(raw_state, {})
        row_trend = []
        for m in sorted_months:
            cnt = st_trend_dict.get(m, 0)
            row_trend.append(cnt)
            tot_monthly[m] += cnt

        node_id = f"state:{raw_state}"
        item = _calculate_row_metrics(
            name=raw_state.upper(),
            py_leads=py_l,
            cy_leads=cy_l,
            py_cucet=py_c,
            cy_cucet=cy_c,
            py_adm=py_a,
            cy_adm=cy_a,
            py_refunds=0,
            cy_refunds=0,
            lead_trend=row_trend,
            node_id=node_id,
            level=1,
            has_children=True,
            extra_props={
                "state_key": raw_state,
                "canonical_name": canonical_name,
                "state_code": state_code,
            },
        )
        processed_rows.append(item)

    # Calculate Total Row from aggregate sums (never averaged)
    total_trend = [tot_monthly[m] for m in sorted_months]
    total_row = _calculate_row_metrics(
        name="Total",
        py_leads=tot_py_leads if py_available else None,
        cy_leads=tot_cy_leads,
        py_cucet=tot_py_cucet if py_available else None,
        cy_cucet=tot_cy_cucet,
        py_adm=tot_py_adm if py_available else None,
        cy_adm=tot_cy_adm,
        py_refunds=0,
        cy_refunds=0,
        lead_trend=total_trend,
        node_id="TOTAL",
        level=0,
        has_children=False,
    )

    # Sort rows safely
    sort_key = VALID_SORT_FIELDS.get(sort_by.lower(), "cy_leads")
    reverse = sort_order.lower() != "asc"
    processed_rows.sort(
        key=lambda x: (
            x[sort_key]
            if isinstance(x.get(sort_key), (int, float))
            else str(x.get(sort_key, "")).lower()
        ),
        reverse=reverse,
    )

    return {
        "rows": processed_rows,
        "total": total_row,
        "count": len(processed_rows),
        "scope": {
            "academic_year": academic_year,
            "py_year": py_year,
            "py_available": py_available,
            "campus": campus or "All Campuses",
            "from_date": from_date,
            "to_date": to_date,
            "sort_by": sort_key,
            "sort_order": "asc" if not reverse else "desc",
        },
    }


def get_state_hierarchy_children(
    db: Session,
    level: str,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    state: Optional[str] = None,
    source_category: Optional[str] = None,
    sort_by: str = "cy_leads",
    sort_order: str = "desc",
) -> Dict[str, Any]:
    """
    Lazy hierarchical child loader:
      level='source_category': children of Level 1 state
      level='sub_source': children of Level 2 state + source_category
    """
    if not academic_year:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)

    py_year = academic_year - 1
    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())

    try:
        db.execute(text("SET jit = off;"))
    except Exception:
        pass

    py_exists_check = db.execute(
        text("SELECT 1 FROM analytics.dashboard_agg WHERE academic_year = :py_year LIMIT 1"),
        {"py_year": py_year},
    ).scalar()
    py_available = bool(py_exists_check)

    where_clauses = ["d.academic_year IN (:py_year, :cy_year)"]
    params: Dict[str, Any] = {"cy_year": academic_year, "py_year": py_year}

    if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
        where_clauses.append("LOWER(d.campus_name) = :campus")
        params["campus"] = campus.strip().lower()

    if state and state.strip():
        where_clauses.append("lower(d.state) = :state_filter")
        params["state_filter"] = state.strip().lower()

    if has_date_filter:
        from_m = from_date.strip()[:7]
        to_m = to_date.strip()[:7]
        py_from_m = get_py_date(from_date.strip())[:7]
        py_to_m = get_py_date(to_date.strip())[:7]

        params["from_m"] = from_m
        params["to_m"] = to_m
        params["py_from_m"] = py_from_m
        params["py_to_m"] = py_to_m

        cy_lead_expr = "CASE WHEN d.academic_year = :cy_year AND d.created_month >= :from_m AND d.created_month <= :to_m THEN d.leads_cy ELSE 0 END"
        py_lead_expr = (
            "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year AND d.created_month >= :from_m AND d.created_month <= :to_m THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = (
            "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year AND d.admission_month >= :from_m AND d.admission_month <= :to_m THEN d.admission_cy ELSE 0 END"
        py_adm_expr = (
            "CASE WHEN d.academic_year = :py_year AND d.admission_month >= :py_from_m AND d.admission_month <= :py_to_m THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"
            if py_available
            else "0"
        )
    else:
        cy_lead_expr = "CASE WHEN d.academic_year = :cy_year THEN d.leads_cy ELSE 0 END"
        py_lead_expr = (
            "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = (
            "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"
            if py_available
            else "0"
        )

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year THEN d.admission_cy ELSE 0 END"
        py_adm_expr = (
            "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"
            if py_available
            else "0"
        )

    where_sql = " AND ".join(where_clauses)
    rows = []

    # -------------------------------------------------------------
    # LEVEL 2: Source Category for a given State
    # -------------------------------------------------------------
    if level == "source_category":
        level_int = 2
        has_children = True
        st_name = (state or "").strip()

        query_sql = f"""
            SELECT 
                COALESCE(NULLIF(TRIM(d.lead_type), ''), 'OTHERS') as source_category,
                SUM({py_lead_expr}) as py_leads,
                SUM({cy_lead_expr}) as cy_leads,
                SUM({py_cucet_expr}) as py_cucet,
                SUM({cy_cucet_expr}) as cy_cucet,
                SUM({py_adm_expr}) as py_adm,
                SUM({cy_adm_expr}) as cy_adm
            FROM analytics.dashboard_agg d
            WHERE {where_sql}
            GROUP BY COALESCE(NULLIF(TRIM(d.lead_type), ''), 'OTHERS')
            HAVING SUM({cy_lead_expr}) > 0 OR SUM({py_lead_expr}) > 0
        """
        res = db.execute(text(query_sql), params).fetchall()

        # Monthly trend for source categories
        trend_where = [
            "d.academic_year = :cy_year",
            "d.created_month IS NOT NULL",
            "lower(d.state) = :state_filter",
        ]
        trend_params = {"cy_year": academic_year, "state_filter": st_name.lower()}
        if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
            trend_where.append("LOWER(d.campus_name) = :campus")
            trend_params["campus"] = campus.strip().lower()
        if has_date_filter:
            trend_where.append("d.created_month >= :from_m AND d.created_month <= :to_m")
            trend_params["from_m"] = from_date.strip()[:7]
            trend_params["to_m"] = to_date.strip()[:7]

        cat_trend_sql = f"""
            SELECT 
                COALESCE(NULLIF(TRIM(d.lead_type), ''), 'OTHERS') as cat,
                d.created_month,
                SUM(d.leads_cy) as leads
            FROM analytics.dashboard_agg d
            WHERE {" AND ".join(trend_where)}
            GROUP BY COALESCE(NULLIF(TRIM(d.lead_type), ''), 'OTHERS'), d.created_month
            ORDER BY 1, 2
        """
        tr_rows = db.execute(text(cat_trend_sql), trend_params).fetchall()
        cat_trends: Dict[str, Dict[str, int]] = {}
        distinct_months = set()
        for tr in tr_rows:
            cat_name = tr[0]
            m_key = tr[1]
            cat_trends.setdefault(cat_name, {})[m_key] = int(tr[2] or 0)
            distinct_months.add(m_key)
        sorted_m = sorted(list(distinct_months))

        for r in res:
            cat_name = str(r[0])
            py_l = int(r[1] or 0) if py_available else None
            cy_l = int(r[2] or 0)
            py_c = int(r[3] or 0) if py_available else None
            cy_c = int(r[4] or 0)
            py_a = int(r[5] or 0) if py_available else None
            cy_a = int(r[6] or 0)

            node_id = f"category:{st_name}:{cat_name}"
            c_dict = cat_trends.get(cat_name, {})
            row_trend = [c_dict.get(m, 0) for m in sorted_m]

            rows.append(
                _calculate_row_metrics(
                    name=cat_name,
                    py_leads=py_l,
                    cy_leads=cy_l,
                    py_cucet=py_c,
                    cy_cucet=cy_c,
                    py_adm=py_a,
                    cy_adm=cy_a,
                    py_refunds=0,
                    cy_refunds=0,
                    lead_trend=row_trend,
                    node_id=node_id,
                    level=level_int,
                    has_children=has_children,
                    extra_props={
                        "state": st_name,
                        "source_category": cat_name,
                    },
                )
            )

    # -------------------------------------------------------------
    # LEVEL 3: Sub-Source for a given State + Source Category
    # -------------------------------------------------------------
    elif level == "sub_source":
        level_int = 3
        has_children = False
        st_name = (state or "").strip()
        src_cat = (source_category or "").strip()
        params["src_cat"] = src_cat

        query_sql = f"""
            SELECT 
                COALESCE(NULLIF(TRIM(d.source), ''), 'UNKNOWN') as sub_source,
                SUM({py_lead_expr}) as py_leads,
                SUM({cy_lead_expr}) as cy_leads,
                SUM({py_cucet_expr}) as py_cucet,
                SUM({cy_cucet_expr}) as cy_cucet,
                SUM({py_adm_expr}) as py_adm,
                SUM({cy_adm_expr}) as cy_adm
            FROM analytics.dashboard_agg d
            WHERE {where_sql} 
              AND COALESCE(NULLIF(TRIM(d.lead_type), ''), 'OTHERS') = :src_cat
            GROUP BY COALESCE(NULLIF(TRIM(d.source), ''), 'UNKNOWN')
            HAVING SUM({cy_lead_expr}) > 0 OR SUM({py_lead_expr}) > 0
        """
        res = db.execute(text(query_sql), params).fetchall()

        # Monthly trend for sub-sources
        trend_where = [
            "d.academic_year = :cy_year",
            "d.created_month IS NOT NULL",
            "lower(d.state) = :state_filter",
            "COALESCE(NULLIF(TRIM(d.lead_type), ''), 'OTHERS') = :src_cat",
        ]
        trend_params = {
            "cy_year": academic_year,
            "state_filter": st_name.lower(),
            "src_cat": src_cat,
        }
        if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
            trend_where.append("LOWER(d.campus_name) = :campus")
            trend_params["campus"] = campus.strip().lower()
        if has_date_filter:
            trend_where.append("d.created_month >= :from_m AND d.created_month <= :to_m")
            trend_params["from_m"] = from_date.strip()[:7]
            trend_params["to_m"] = to_date.strip()[:7]

        src_trend_sql = f"""
            SELECT 
                COALESCE(NULLIF(TRIM(d.source), ''), 'UNKNOWN') as src,
                d.created_month,
                SUM(d.leads_cy) as leads
            FROM analytics.dashboard_agg d
            WHERE {" AND ".join(trend_where)}
            GROUP BY COALESCE(NULLIF(TRIM(d.source), ''), 'UNKNOWN'), d.created_month
            ORDER BY 1, 2
        """
        tr_rows = db.execute(text(src_trend_sql), trend_params).fetchall()
        src_trends: Dict[str, Dict[str, int]] = {}
        distinct_months = set()
        for tr in tr_rows:
            src_name = tr[0]
            m_key = tr[1]
            src_trends.setdefault(src_name, {})[m_key] = int(tr[2] or 0)
            distinct_months.add(m_key)
        sorted_m = sorted(list(distinct_months))

        for r in res:
            src_name = str(r[0])
            py_l = int(r[1] or 0) if py_available else None
            cy_l = int(r[2] or 0)
            py_c = int(r[3] or 0) if py_available else None
            cy_c = int(r[4] or 0)
            py_a = int(r[5] or 0) if py_available else None
            cy_a = int(r[6] or 0)

            node_id = f"subsource:{st_name}:{src_cat}:{src_name}"
            s_dict = src_trends.get(src_name, {})
            row_trend = [s_dict.get(m, 0) for m in sorted_m]

            rows.append(
                _calculate_row_metrics(
                    name=src_name,
                    py_leads=py_l,
                    cy_leads=cy_l,
                    py_cucet=py_c,
                    cy_cucet=cy_c,
                    py_adm=py_a,
                    cy_adm=cy_a,
                    py_refunds=0,
                    cy_refunds=0,
                    lead_trend=row_trend,
                    node_id=node_id,
                    level=level_int,
                    has_children=has_children,
                    extra_props={
                        "state": st_name,
                        "source_category": src_cat,
                        "sub_source": src_name,
                    },
                )
            )

    # Sort children safely
    sort_key = VALID_SORT_FIELDS.get(sort_by.lower(), "cy_leads")
    reverse = sort_order.lower() != "asc"
    rows.sort(
        key=lambda x: (
            x[sort_key]
            if isinstance(x.get(sort_key), (int, float))
            else str(x.get(sort_key, "")).lower()
        ),
        reverse=reverse,
    )

    return {
        "rows": rows,
        "count": len(rows),
        "level": level,
        "scope": {
            "academic_year": academic_year,
            "py_year": py_year,
            "py_available": py_available,
            "campus": campus or "All Campuses",
            "from_date": from_date,
            "to_date": to_date,
            "state": state,
            "source_category": source_category,
            "sort_by": sort_key,
            "sort_order": "asc" if not reverse else "desc",
        },
    }
