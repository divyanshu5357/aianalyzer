"""
Analytical service for the Program Performance Report with strict Lazy Hierarchical Loading.
Provides aggregated metrics across 4 hierarchy levels:
  Level 1: Program Group (e.g. B.COM, B.E., BCA, MBA)
  Level 2: Program Branch / Variant (e.g. B.COM (H): ACCA : CM201)
  Level 3: Source Category (IN HOUSE, OUT SOURCED, OTHERS)
  Level 4: Sub-Source (e.g. DIRECT, WEBSITE, BROCHURE, nNext)
All aggregations are computed on PostgreSQL (GROUP BY, SUM). Zero raw CRM datasets are loaded.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import time
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.analytics.aggregate_service import get_py_date

logger = logging.getLogger(__name__)

# Server-side cache for top-level report and insights (5 minute TTL)
_PROGRAMS_TOP_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PROGRAMS_INSIGHTS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_PROGRAMS_CACHE_TTL = 300.0

def clear_programs_cache():
    _PROGRAMS_TOP_CACHE.clear()
    _PROGRAMS_INSIGHTS_CACHE.clear()

# Trusted sorting columns to prevent SQL injection
VALID_SORT_FIELDS = {
    "program": "program",
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


def _calculate_row_metrics(
    name: str,
    py_leads: int,
    cy_leads: int,
    py_cucet: int,
    cy_cucet: int,
    py_adm: int,
    cy_adm: int,
    py_refunds: int,
    cy_refunds: int,
    lead_trend: List[int],
    node_id: str,
    level: int,
    has_children: bool,
    extra_props: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Helper to compute all 19 standardized report columns and variance metrics."""
    var_leads = cy_leads - py_leads
    var_leads_pct = (
        round((var_leads / py_leads) * 100, 1)
        if py_leads > 0
        else (0.0 if cy_leads == 0 else 100.0)
    )

    var_cucet = cy_cucet - py_cucet
    var_cucet_pct = (
        round((var_cucet / py_cucet) * 100, 1)
        if py_cucet > 0
        else (0.0 if cy_cucet == 0 else 100.0)
    )

    lead_cucet_pct = round((cy_cucet / cy_leads) * 100, 1) if cy_leads > 0 else 0.0

    var_adm = cy_adm - py_adm
    var_adm_pct = (
        round((var_adm / py_adm) * 100, 1)
        if py_adm > 0
        else (0.0 if cy_adm == 0 else 100.0)
    )

    lead_adm_pct = round((cy_adm / cy_leads) * 100, 1) if cy_leads > 0 else 0.0
    cucet_adm_pct = round((cy_adm / cy_cucet) * 100, 1) if cy_cucet > 0 else 0.0

    net_admissions = cy_adm - cy_refunds
    refund_diff = cy_refunds - py_refunds

    py_refund_rate = round((py_refunds / py_adm) * 100, 1) if py_adm > 0 else 0.0
    cy_refund_rate = round((cy_refunds / cy_adm) * 100, 1) if cy_adm > 0 else 0.0
    refund_rate_diff = round(cy_refund_rate - py_refund_rate, 1)

    row = {
        "id": node_id,
        "program": name,
        "level": level,
        "has_children": has_children,
        "py_leads": py_leads,
        "cy_leads": cy_leads,
        "var_leads": var_leads,
        "var_leads_pct": var_leads_pct,
        "py_cucet": py_cucet,
        "cy_cucet": cy_cucet,
        "var_cucet": var_cucet,
        "var_cucet_pct": var_cucet_pct,
        "lead_cucet_pct": lead_cucet_pct,
        "py_adm": py_adm,
        "cy_adm": cy_adm,
        "var_adm": var_adm,
        "var_adm_pct": var_adm_pct,
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


def get_program_report_top_level(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    sort_by: str = "cy_leads",
    sort_order: str = "desc",
) -> Dict[str, Any]:
    """
    Level 1: Retrieve top-level Program Groups (~30 rows) plus scope-wide total row.
    Calculates 19 metrics strictly server-side with zero raw records sent to client.
    """
    if not academic_year:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)

    py_year = academic_year - 1
    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    
    # Disable JIT for sub-second query performance
    try:
        db.execute(text("SET LOCAL jit = off;"))
    except Exception:
        pass

    try:
        from app.database.organization_seed import seed_organization_master_data
        cm_check = db.execute(text("SELECT 1 FROM organization.course_master LIMIT 1")).scalar()
        if not cm_check:
            seed_organization_master_data(db)
    except Exception as seed_check_err:
        logger.warning("Program service master data seed check notice: %s", seed_check_err)

    where_clauses = ["d.academic_year IN (:py_year, :cy_year)"]
    params: Dict[str, Any] = {"cy_year": academic_year, "py_year": py_year}

    ref_clauses = ["r.academic_year IN (:py_year, :cy_year)"]
    ref_params: Dict[str, Any] = {"cy_year": academic_year, "py_year": py_year}

    if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
        where_clauses.append("LOWER(d.campus_name) = :campus")
        params["campus"] = campus.strip().lower()
        ref_clauses.append("LOWER(r.campus_name) = :campus")
        ref_params["campus"] = campus.strip().lower()

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
        py_lead_expr = "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year AND d.created_month >= :from_m AND d.created_month <= :to_m THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year AND d.admission_month >= :from_m AND d.admission_month <= :to_m THEN d.admission_cy ELSE 0 END"
        py_adm_expr = "CASE WHEN d.academic_year = :py_year AND d.admission_month >= :py_from_m AND d.admission_month <= :py_to_m THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"

        ref_params["from_m"] = from_m
        ref_params["to_m"] = to_m
        ref_params["py_from_m"] = py_from_m
        ref_params["py_to_m"] = py_to_m

        cy_ref_expr = "CASE WHEN r.academic_year = :cy_year AND r.refund_month >= :from_m AND r.refund_month <= :to_m THEN r.refund_count ELSE 0 END"
        py_ref_expr = "CASE WHEN r.academic_year = :py_year AND r.refund_month >= :py_from_m AND r.refund_month <= :py_to_m THEN r.refund_count ELSE 0 END"
    else:
        cy_lead_expr = "CASE WHEN d.academic_year = :cy_year THEN d.leads_cy ELSE 0 END"
        py_lead_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year THEN d.admission_cy ELSE 0 END"
        py_adm_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"

        cy_ref_expr = "CASE WHEN r.academic_year = :cy_year THEN r.refund_count ELSE 0 END"
        py_ref_expr = "CASE WHEN r.academic_year = :py_year THEN r.refund_count ELSE 0 END"

    where_sql = " AND ".join(where_clauses)
    ref_where_sql = " AND ".join(ref_clauses)

    # Check server-side cache
    cache_key = f"{academic_year}:{campus}:{from_date}:{to_date}:{sort_by}:{sort_order}"
    now_ts = time.time()
    if cache_key in _PROGRAMS_TOP_CACHE:
        c_time, c_data = _PROGRAMS_TOP_CACHE[cache_key]
        if now_ts - c_time < _PROGRAMS_CACHE_TTL:
            return c_data

    # Load course dimension mappings (423 records, instant < 5ms)
    courses = db.execute(
        text("SELECT program_code, program_name, program_group FROM organization.course_master WHERE program_group IS NOT NULL AND TRIM(program_group) != ''")
    ).fetchall()
    code_map: Dict[str, str] = {}
    name_map: Dict[str, str] = {}
    for c_code, c_name, c_grp in courses:
        if c_code and c_code.strip():
            code_map[c_code.strip().lower()] = c_grp.strip()
        if c_name and c_name.strip():
            name_map[c_name.strip().lower()] = c_grp.strip()

    # Pre-aggregate dashboard_agg by (year, pcode, raw_pcode, pname, created_month)
    # Zero cross joins on 1.25M rows!
    agg_sql = f"""
        SELECT 
            d.academic_year,
            LOWER(TRIM(d.program_code)) as pcode,
            LOWER(TRIM(COALESCE(d.raw_program_code, ''))) as raw_pcode,
            LOWER(TRIM(COALESCE(d.program_name, ''))) as pname,
            d.created_month,
            SUM({cy_lead_expr}) as cy_leads,
            SUM({py_lead_expr}) as py_leads,
            SUM({cy_cucet_expr}) as cy_cucet,
            SUM({py_cucet_expr}) as py_cucet,
            SUM({cy_adm_expr}) as cy_adm,
            SUM({py_adm_expr}) as py_adm
        FROM analytics.dashboard_agg d
        WHERE {where_sql}
        GROUP BY d.academic_year, LOWER(TRIM(d.program_code)), LOWER(TRIM(COALESCE(d.raw_program_code, ''))), LOWER(TRIM(COALESCE(d.program_name, ''))), d.created_month
    """
    agg_rows = db.execute(text(agg_sql), params).fetchall()

    ref_sql = f"""
        SELECT 
            LOWER(TRIM(r.program_code)) as pcode,
            SUM({cy_ref_expr}) as cy_refunds,
            SUM({py_ref_expr}) as py_refunds
        FROM analytics.program_refunds_summary r
        WHERE {ref_where_sql}
        GROUP BY LOWER(TRIM(r.program_code))
    """
    ref_rows = db.execute(text(ref_sql), ref_params).fetchall()

    groups: Dict[str, Dict[str, int]] = {}
    group_trends: Dict[str, Dict[str, int]] = {}
    distinct_months = set()

    for r in agg_rows:
        yr = r[0]
        pcode = r[1] or ""
        raw_pcode = r[2] or ""
        pname = r[3] or ""
        m = r[4]

        grp = code_map.get(pcode) or code_map.get(raw_pcode) or name_map.get(pname) or "OTHER"

        if grp not in groups:
            groups[grp] = {
                "py_leads": 0, "cy_leads": 0,
                "py_cucet": 0, "cy_cucet": 0,
                "py_adm": 0, "cy_adm": 0,
                "py_refunds": 0, "cy_refunds": 0,
            }
            group_trends[grp] = {}

        cy_l = int(r[5] or 0)
        groups[grp]["cy_leads"] += cy_l
        groups[grp]["py_leads"] += int(r[6] or 0)
        groups[grp]["cy_cucet"] += int(r[7] or 0)
        groups[grp]["py_cucet"] += int(r[8] or 0)
        groups[grp]["cy_adm"] += int(r[9] or 0)
        groups[grp]["py_adm"] += int(r[10] or 0)

        if m and yr == academic_year:
            distinct_months.add(m)
            group_trends[grp][m] = group_trends[grp].get(m, 0) + cy_l

    for r in ref_rows:
        pcode = r[0] or ""
        grp = code_map.get(pcode) or name_map.get(pcode) or "OTHER"
        if grp not in groups:
            groups[grp] = {
                "py_leads": 0, "cy_leads": 0,
                "py_cucet": 0, "cy_cucet": 0,
                "py_adm": 0, "cy_adm": 0,
                "py_refunds": 0, "cy_refunds": 0,
            }
            group_trends[grp] = {}
        groups[grp]["cy_refunds"] += int(r[1] or 0)
        groups[grp]["py_refunds"] += int(r[2] or 0)

    sorted_months = sorted(list(distinct_months))

    tot_py_leads = tot_cy_leads = tot_py_cucet = tot_cy_cucet = 0
    tot_py_adm = tot_cy_adm = tot_py_refunds = tot_cy_refunds = 0
    tot_monthly: Dict[str, int] = {m: 0 for m in sorted_months}

    processed_rows = []
    for grp, m in groups.items():
        py_l = m["py_leads"]
        cy_l = m["cy_leads"]
        py_c = m["py_cucet"]
        cy_c = m["cy_cucet"]
        py_a = m["py_adm"]
        cy_a = m["cy_adm"]
        py_r = m["py_refunds"]
        cy_r = m["cy_refunds"]

        if cy_l == 0 and py_l == 0:
            continue

        tot_py_leads += py_l
        tot_cy_leads += cy_l
        tot_py_cucet += py_c
        tot_cy_cucet += cy_c
        tot_py_adm += py_a
        tot_cy_adm += cy_a
        tot_py_refunds += py_r
        tot_cy_refunds += cy_r

        grp_trend_dict = group_trends.get(grp, {})
        row_trend = []
        for m_key in sorted_months:
            cnt = grp_trend_dict.get(m_key, 0)
            row_trend.append(cnt)
            tot_monthly[m_key] += cnt

        node_id = f"group:{grp}"
        item = _calculate_row_metrics(
            name=grp,
            py_leads=py_l,
            cy_leads=cy_l,
            py_cucet=py_c,
            cy_cucet=cy_c,
            py_adm=py_a,
            cy_adm=cy_a,
            py_refunds=py_r,
            cy_refunds=cy_r,
            lead_trend=row_trend,
            node_id=node_id,
            level=1,
            has_children=True,
            extra_props={"program_group": grp},
        )
        processed_rows.append(item)

    # Calculate Total Row from aggregate sums (never averaged)
    total_trend = [tot_monthly[m] for m in sorted_months]
    total_row = _calculate_row_metrics(
        name="Total",
        py_leads=tot_py_leads,
        cy_leads=tot_cy_leads,
        py_cucet=tot_py_cucet,
        cy_cucet=tot_cy_cucet,
        py_adm=tot_py_adm,
        cy_adm=tot_cy_adm,
        py_refunds=tot_py_refunds,
        cy_refunds=tot_cy_refunds,
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

    resp = {
        "rows": processed_rows,
        "total": total_row,
        "count": len(processed_rows),
        "scope": {
            "academic_year": academic_year,
            "py_year": py_year,
            "campus": campus or "All Campuses",
            "from_date": from_date,
            "to_date": to_date,
            "sort_by": sort_key,
            "sort_order": "asc" if not reverse else "desc",
        },
    }

    _PROGRAMS_TOP_CACHE[cache_key] = (now_ts, resp)
    return resp



def get_program_hierarchy_children(
    db: Session,
    level: str,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    program_group: Optional[str] = None,
    program_code: Optional[str] = None,
    lead_type: Optional[str] = None,
    main_source: Optional[str] = None,
    report_source: Optional[str] = None,
    source_category: Optional[str] = None,
    sub_source: Optional[str] = None,
    sort_by: str = "cy_leads",
    sort_order: str = "desc",
) -> Dict[str, Any]:
    """
    Lazy hierarchical child loader (5-level drill-down):
      Level 2 ('program' or 'branch'): children of Level 1 program_group
      Level 3 ('lead_type' or 'source_category'): children of Level 2 program_code
      Level 4 ('main_source' or 'sub_source'): children of Level 3 program_code + lead_type
      Level 5 ('report_source'): children of Level 4 program_code + lead_type + main_source
    All 13 metrics are computed server-side in PostgreSQL from raw dashboard_agg data.
    """
    norm_level = level.lower().strip()
    if norm_level == "branch":
        norm_level = "program"
    elif norm_level == "source_category":
        norm_level = "lead_type"
    elif norm_level == "sub_source":
        norm_level = "main_source"

    eff_pcode = (program_code or "").strip() or None
    eff_lead_type = (lead_type or source_category or "").strip() or None
    eff_main_src = (main_source or sub_source or "").strip() or None
    eff_report_src = (report_source or "").strip() or None

    if not academic_year:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)
    py_year = academic_year - 1
    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())

    try:
        db.execute(text("SET LOCAL jit = off;"))
    except Exception:
        pass

    where_clauses = ["d.academic_year IN (:py_year, :cy_year)"]
    params: Dict[str, Any] = {"cy_year": academic_year, "py_year": py_year}

    ref_clauses = ["r.academic_year IN (:py_year, :cy_year)"]
    ref_params: Dict[str, Any] = {"cy_year": academic_year, "py_year": py_year}

    if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
        where_clauses.append("LOWER(d.campus_name) = :campus")
        params["campus"] = campus.strip().lower()
        ref_clauses.append("LOWER(r.campus_name) = :campus")
        ref_params["campus"] = campus.strip().lower()

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
        py_lead_expr = "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year AND d.created_month >= :from_m AND d.created_month <= :to_m THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year AND d.admission_month >= :from_m AND d.admission_month <= :to_m THEN d.admission_cy ELSE 0 END"
        py_adm_expr = "CASE WHEN d.academic_year = :py_year AND d.admission_month >= :py_from_m AND d.admission_month <= :py_to_m THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"

        ref_params["from_m"] = from_m
        ref_params["to_m"] = to_m
        ref_params["py_from_m"] = py_from_m
        ref_params["py_to_m"] = py_to_m

        cy_ref_expr = "CASE WHEN r.academic_year = :cy_year AND r.refund_month >= :from_m AND r.refund_month <= :to_m THEN r.refund_count ELSE 0 END"
        py_ref_expr = "CASE WHEN r.academic_year = :py_year AND r.refund_month >= :py_from_m AND r.refund_month <= :py_to_m THEN r.refund_count ELSE 0 END"
    else:
        cy_lead_expr = "CASE WHEN d.academic_year = :cy_year THEN d.leads_cy ELSE 0 END"
        py_lead_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"

        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"

        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year THEN d.admission_cy ELSE 0 END"
        py_adm_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"

        cy_ref_expr = "CASE WHEN r.academic_year = :cy_year THEN r.refund_count ELSE 0 END"
        py_ref_expr = "CASE WHEN r.academic_year = :py_year THEN r.refund_count ELSE 0 END"

    where_sql = " AND ".join(where_clauses)
    ref_where_sql = " AND ".join(ref_clauses)

    rows = []

    # -------------------------------------------------------------
    # LEVEL 2: Program / Branch (children of Level 1 program_group)
    # -------------------------------------------------------------
    if norm_level == "program":
        level_int = 2
        has_children = True
        prog_grp = (program_group or "").strip()
        params["p_group"] = prog_grp
        ref_params["p_group"] = prog_grp

        if prog_grp.upper() == "OTHER":
            group_filter = "(c.program_group IS NULL OR c.program_group = 'OTHER')"
            union_sql = "UNION SELECT DISTINCT LOWER(d.program_code) as pcode, d.program_code as raw_code, d.program_name, NULL as program_name_short FROM analytics.dashboard_agg d WHERE LOWER(d.program_code) NOT IN (SELECT pcode FROM known_codes)"
        else:
            group_filter = "c.program_group = :p_group"
            union_sql = ""

        query_sql = f"""
            WITH known_codes AS (
                SELECT DISTINCT LOWER(program_code) as pcode FROM organization.course_master WHERE program_code IS NOT NULL
            ),
            target_branches AS (
                SELECT DISTINCT LOWER(c.program_code) as pcode, c.program_code as raw_code, c.program_name, c.program_name_short
                FROM organization.course_master c
                WHERE {group_filter}
                {union_sql}
            ),
            agg_data AS (
                SELECT 
                    LOWER(d.program_code) as pcode,
                    d.created_month,
                    SUM({cy_lead_expr}) as cy_leads,
                    SUM({py_lead_expr}) as py_leads,
                    SUM({cy_cucet_expr}) as cy_cucet,
                    SUM({py_cucet_expr}) as py_cucet,
                    SUM({cy_adm_expr}) as cy_adm,
                    SUM({py_adm_expr}) as py_adm
                FROM analytics.dashboard_agg d
                JOIN target_branches b ON LOWER(d.program_code) = b.pcode
                WHERE {where_sql}
                GROUP BY LOWER(d.program_code), d.created_month
            ),
            ref_data AS (
                SELECT 
                    LOWER(r.program_code) as pcode,
                    SUM({cy_ref_expr}) as cy_refunds,
                    SUM({py_ref_expr}) as py_refunds
                FROM analytics.program_refunds_summary r
                JOIN target_branches b ON LOWER(r.program_code) = b.pcode
                WHERE {ref_where_sql}
                GROUP BY LOWER(r.program_code)
            )
            SELECT 
                b.raw_code as program_code,
                COALESCE(b.program_name_short, b.program_name, b.raw_code) as program_name,
                a.created_month,
                COALESCE(a.py_leads, 0) as py_leads,
                COALESCE(a.cy_leads, 0) as cy_leads,
                COALESCE(a.py_cucet, 0) as py_cucet,
                COALESCE(a.cy_cucet, 0) as cy_cucet,
                COALESCE(a.py_adm, 0) as py_adm,
                COALESCE(a.cy_adm, 0) as cy_adm,
                COALESCE(r.py_refunds, 0) as py_refunds,
                COALESCE(r.cy_refunds, 0) as cy_refunds
            FROM target_branches b
            JOIN agg_data a ON b.pcode = a.pcode
            LEFT JOIN ref_data r ON b.pcode = r.pcode
            WHERE COALESCE(a.cy_leads, 0) > 0 OR COALESCE(a.py_leads, 0) > 0
        """
        all_params = {**params, **ref_params}
        res = db.execute(text(query_sql), all_params).fetchall()

        branch_metrics: Dict[str, Dict[str, Any]] = {}
        branch_trends: Dict[str, Dict[str, int]] = {}
        distinct_months = set()

        for r in res:
            raw_code = str(r[0])
            p_name = str(r[1])
            m_key = r[2]
            py_l = int(r[3] or 0)
            cy_l = int(r[4] or 0)
            py_c = int(r[5] or 0)
            cy_c = int(r[6] or 0)
            py_a = int(r[7] or 0)
            cy_a = int(r[8] or 0)
            py_r = int(r[9] or 0)
            cy_r = int(r[10] or 0)

            if raw_code not in branch_metrics:
                branch_metrics[raw_code] = {
                    "name": p_name,
                    "py_leads": 0, "cy_leads": 0,
                    "py_cucet": 0, "cy_cucet": 0,
                    "py_adm": 0, "cy_adm": 0,
                    "py_refunds": py_r, "cy_refunds": cy_r,
                }
                branch_trends[raw_code] = {}

            bm = branch_metrics[raw_code]
            bm["py_leads"] += py_l
            bm["cy_leads"] += cy_l
            bm["py_cucet"] += py_c
            bm["cy_cucet"] += cy_c
            bm["py_adm"] += py_a
            bm["cy_adm"] += cy_a

            if m_key:
                distinct_months.add(m_key)
                branch_trends[raw_code][m_key] = branch_trends[raw_code].get(m_key, 0) + cy_l

        sorted_m = sorted(list(distinct_months))

        for raw_code, bm in branch_metrics.items():
            node_id = f"prog:{prog_grp}:{raw_code}"
            b_dict = branch_trends.get(raw_code, {})
            row_trend = [b_dict.get(m, 0) for m in sorted_m]

            rows.append(
                _calculate_row_metrics(
                    name=bm["name"],
                    py_leads=bm["py_leads"],
                    cy_leads=bm["cy_leads"],
                    py_cucet=bm["py_cucet"],
                    cy_cucet=bm["cy_cucet"],
                    py_adm=bm["py_adm"],
                    cy_adm=bm["cy_adm"],
                    py_refunds=bm["py_refunds"],
                    cy_refunds=bm["cy_refunds"],
                    lead_trend=row_trend,
                    node_id=node_id,
                    level=level_int,
                    has_children=has_children,
                    extra_props={
                        "program_group": prog_grp,
                        "program_code": raw_code,
                    },
                )
            )


    # -------------------------------------------------------------
    # LEVEL 3: Lead Type (children of Level 2 program_code)
    # IN HOUSE, OUT SOURCED, OTHERS dynamically from source_master / raw
    # -------------------------------------------------------------
    elif norm_level == "lead_type":
        level_int = 3
        has_children = True
        params["p_code"] = eff_pcode.lower()
        ref_params["p_code"] = eff_pcode.lower()

        lead_type_expr = "COALESCE(NULLIF(UPPER(TRIM(sm.lead_type)), ''), NULLIF(UPPER(TRIM(d.lead_type)), ''), 'OTHERS')"
        ref_lead_type_expr = "COALESCE(NULLIF(UPPER(TRIM(sm.lead_type)), ''), NULLIF(UPPER(TRIM(r.lead_type)), ''), 'OTHERS')"

        query_sql = f"""
            WITH agg_data AS (
                SELECT 
                    {lead_type_expr} as lead_type,
                    SUM({cy_lead_expr}) as cy_leads,
                    SUM({py_lead_expr}) as py_leads,
                    SUM({cy_cucet_expr}) as cy_cucet,
                    SUM({py_cucet_expr}) as py_cucet,
                    SUM({cy_adm_expr}) as cy_adm,
                    SUM({py_adm_expr}) as py_adm
                FROM analytics.dashboard_agg d
                LEFT JOIN organization.source_master sm ON LOWER(TRIM(d.source)) = LOWER(TRIM(sm.source))
                WHERE {where_sql} AND LOWER(d.program_code) = :p_code
                GROUP BY {lead_type_expr}
            ),
            ref_data AS (
                SELECT 
                    {ref_lead_type_expr} as lead_type,
                    SUM({cy_ref_expr}) as cy_refunds,
                    SUM({py_ref_expr}) as py_refunds
                FROM analytics.program_refunds_summary r
                LEFT JOIN organization.source_master sm ON LOWER(TRIM(r.source)) = LOWER(TRIM(sm.source))
                WHERE {ref_where_sql} AND LOWER(r.program_code) = :p_code
                GROUP BY {ref_lead_type_expr}
            )
            SELECT 
                COALESCE(a.lead_type, r.lead_type) as lead_type,
                COALESCE(a.py_leads, 0) as py_leads,
                COALESCE(a.cy_leads, 0) as cy_leads,
                COALESCE(a.py_cucet, 0) as py_cucet,
                COALESCE(a.cy_cucet, 0) as cy_cucet,
                COALESCE(a.py_adm, 0) as py_adm,
                COALESCE(a.cy_adm, 0) as cy_adm,
                COALESCE(r.py_refunds, 0) as py_refunds,
                COALESCE(r.cy_refunds, 0) as cy_refunds
            FROM agg_data a
            FULL OUTER JOIN ref_data r ON a.lead_type = r.lead_type
            WHERE COALESCE(a.cy_leads, 0) > 0 OR COALESCE(a.py_leads, 0) > 0
        """
        all_params = {**params, **ref_params}
        res = db.execute(text(query_sql), all_params).fetchall()

        # Monthly trend for lead types
        trend_where = [
            "d.academic_year = :cy_year",
            "d.created_month IS NOT NULL",
            "LOWER(d.program_code) = :p_code",
        ]
        trend_params = {"cy_year": academic_year, "p_code": eff_pcode.lower()}
        if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
            trend_where.append("LOWER(d.campus_name) = :campus")
            trend_params["campus"] = campus.strip().lower()
        if has_date_filter:
            trend_where.append("d.created_month >= :from_m AND d.created_month <= :to_m")
            trend_params["from_m"] = from_date.strip()[:7]
            trend_params["to_m"] = to_date.strip()[:7]

        cat_trend_sql = f"""
            SELECT 
                {lead_type_expr} as lt,
                d.created_month,
                SUM(d.leads_cy) as leads
            FROM analytics.dashboard_agg d
            LEFT JOIN organization.source_master sm ON LOWER(TRIM(d.source)) = LOWER(TRIM(sm.source))
            WHERE {" AND ".join(trend_where)}
            GROUP BY {lead_type_expr}, d.created_month
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
            py_l = int(r[1] or 0)
            cy_l = int(r[2] or 0)
            py_c = int(r[3] or 0)
            cy_c = int(r[4] or 0)
            py_a = int(r[5] or 0)
            cy_a = int(r[6] or 0)
            py_r = int(r[7] or 0)
            cy_r = int(r[8] or 0)

            node_id = f"lt:{eff_pcode}:{cat_name}"
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
                    py_refunds=py_r,
                    cy_refunds=cy_r,
                    lead_trend=row_trend,
                    node_id=node_id,
                    level=level_int,
                    has_children=has_children,
                    extra_props={
                        "program_group": program_group,
                        "program_code": eff_pcode,
                        "lead_type": cat_name,
                        "source_category": cat_name,
                    },
                )
            )

    # -------------------------------------------------------------
    # LEVEL 4: Main Source (children of Level 3 program_code + lead_type)
    # Direct, Website, Career_360, CP, etc. dynamically from source_master
    # -------------------------------------------------------------
    elif norm_level == "main_source":
        level_int = 4
        has_children = True
        params["p_code"] = eff_pcode.lower()
        params["eff_lt"] = eff_lead_type.upper()
        ref_params["p_code"] = eff_pcode.lower()
        ref_params["eff_lt"] = eff_lead_type.upper()

        lead_type_expr = "COALESCE(NULLIF(UPPER(TRIM(sm.lead_type)), ''), NULLIF(UPPER(TRIM(d.lead_type)), ''), 'OTHERS')"
        ref_lead_type_expr = "COALESCE(NULLIF(UPPER(TRIM(sm.lead_type)), ''), NULLIF(UPPER(TRIM(r.lead_type)), ''), 'OTHERS')"
        main_src_expr = "COALESCE(NULLIF(TRIM(sm.main_source), ''), NULLIF(TRIM(d.source), ''), 'Direct')"
        ref_main_src_expr = "COALESCE(NULLIF(TRIM(sm.main_source), ''), NULLIF(TRIM(r.source), ''), 'Direct')"

        query_sql = f"""
            WITH agg_data AS (
                SELECT 
                    {main_src_expr} as main_source,
                    SUM({cy_lead_expr}) as cy_leads,
                    SUM({py_lead_expr}) as py_leads,
                    SUM({cy_cucet_expr}) as cy_cucet,
                    SUM({py_cucet_expr}) as py_cucet,
                    SUM({cy_adm_expr}) as cy_adm,
                    SUM({py_adm_expr}) as py_adm
                FROM analytics.dashboard_agg d
                LEFT JOIN organization.source_master sm ON LOWER(TRIM(d.source)) = LOWER(TRIM(sm.source))
                WHERE {where_sql} 
                  AND LOWER(d.program_code) = :p_code
                  AND {lead_type_expr} = :eff_lt
                GROUP BY {main_src_expr}
            ),
            ref_data AS (
                SELECT 
                    {ref_main_src_expr} as main_source,
                    SUM({cy_ref_expr}) as cy_refunds,
                    SUM({py_ref_expr}) as py_refunds
                FROM analytics.program_refunds_summary r
                LEFT JOIN organization.source_master sm ON LOWER(TRIM(r.source)) = LOWER(TRIM(sm.source))
                WHERE {ref_where_sql} 
                  AND LOWER(r.program_code) = :p_code
                  AND {ref_lead_type_expr} = :eff_lt
                GROUP BY {ref_main_src_expr}
            )
            SELECT 
                COALESCE(a.main_source, r.main_source) as main_source,
                COALESCE(a.py_leads, 0) as py_leads,
                COALESCE(a.cy_leads, 0) as cy_leads,
                COALESCE(a.py_cucet, 0) as py_cucet,
                COALESCE(a.cy_cucet, 0) as cy_cucet,
                COALESCE(a.py_adm, 0) as py_adm,
                COALESCE(a.cy_adm, 0) as cy_adm,
                COALESCE(r.py_refunds, 0) as py_refunds,
                COALESCE(r.cy_refunds, 0) as cy_refunds
            FROM agg_data a
            FULL OUTER JOIN ref_data r ON a.main_source = r.main_source
            WHERE COALESCE(a.cy_leads, 0) > 0 OR COALESCE(a.py_leads, 0) > 0
        """
        all_params = {**params, **ref_params}
        res = db.execute(text(query_sql), all_params).fetchall()

        # Monthly trend for main sources
        trend_where = [
            "d.academic_year = :cy_year",
            "d.created_month IS NOT NULL",
            "LOWER(d.program_code) = :p_code",
            f"{lead_type_expr} = :eff_lt",
        ]
        trend_params = {
            "cy_year": academic_year,
            "p_code": eff_pcode.lower(),
            "eff_lt": eff_lead_type.upper(),
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
                {main_src_expr} as ms,
                d.created_month,
                SUM(d.leads_cy) as leads
            FROM analytics.dashboard_agg d
            LEFT JOIN organization.source_master sm ON LOWER(TRIM(d.source)) = LOWER(TRIM(sm.source))
            WHERE {" AND ".join(trend_where)}
            GROUP BY {main_src_expr}, d.created_month
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
            py_l = int(r[1] or 0)
            cy_l = int(r[2] or 0)
            py_c = int(r[3] or 0)
            cy_c = int(r[4] or 0)
            py_a = int(r[5] or 0)
            cy_a = int(r[6] or 0)
            py_r = int(r[7] or 0)
            cy_r = int(r[8] or 0)

            node_id = f"ms:{eff_pcode}:{eff_lead_type}:{src_name}"
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
                    py_refunds=py_r,
                    cy_refunds=cy_r,
                    lead_trend=row_trend,
                    node_id=node_id,
                    level=level_int,
                    has_children=has_children,
                    extra_props={
                        "program_group": program_group,
                        "program_code": eff_pcode,
                        "lead_type": eff_lead_type,
                        "source_category": eff_lead_type,
                        "main_source": src_name,
                        "sub_source": src_name,
                    },
                )
            )

    # -------------------------------------------------------------
    # LEVEL 5: Report Source (children of Level 4 main_source)
    # Granular campaign/vendor source dynamically from source_master
    # -------------------------------------------------------------
    elif norm_level == "report_source":
        level_int = 5
        has_children = False
        params["p_code"] = eff_pcode.lower()
        params["eff_lt"] = eff_lead_type.upper()
        params["eff_ms"] = eff_main_src
        ref_params["p_code"] = eff_pcode.lower()
        ref_params["eff_lt"] = eff_lead_type.upper()
        ref_params["eff_ms"] = eff_main_src

        lead_type_expr = "COALESCE(NULLIF(UPPER(TRIM(sm.lead_type)), ''), NULLIF(UPPER(TRIM(d.lead_type)), ''), 'OTHERS')"
        ref_lead_type_expr = "COALESCE(NULLIF(UPPER(TRIM(sm.lead_type)), ''), NULLIF(UPPER(TRIM(r.lead_type)), ''), 'OTHERS')"
        main_src_expr = "COALESCE(NULLIF(TRIM(sm.main_source), ''), NULLIF(TRIM(d.source), ''), 'Direct')"
        ref_main_src_expr = "COALESCE(NULLIF(TRIM(sm.main_source), ''), NULLIF(TRIM(r.source), ''), 'Direct')"
        rep_src_expr = "COALESCE(NULLIF(TRIM(sm.report_source), ''), NULLIF(TRIM(d.source), ''), 'Direct')"
        ref_rep_src_expr = "COALESCE(NULLIF(TRIM(sm.report_source), ''), NULLIF(TRIM(r.source), ''), 'Direct')"

        query_sql = f"""
            WITH agg_data AS (
                SELECT 
                    {rep_src_expr} as report_source,
                    SUM({cy_lead_expr}) as cy_leads,
                    SUM({py_lead_expr}) as py_leads,
                    SUM({cy_cucet_expr}) as cy_cucet,
                    SUM({py_cucet_expr}) as py_cucet,
                    SUM({cy_adm_expr}) as cy_adm,
                    SUM({py_adm_expr}) as py_adm
                FROM analytics.dashboard_agg d
                LEFT JOIN organization.source_master sm ON LOWER(TRIM(d.source)) = LOWER(TRIM(sm.source))
                WHERE {where_sql} 
                  AND LOWER(d.program_code) = :p_code
                  AND {lead_type_expr} = :eff_lt
                  AND {main_src_expr} = :eff_ms
                GROUP BY {rep_src_expr}
            ),
            ref_data AS (
                SELECT 
                    {ref_rep_src_expr} as report_source,
                    SUM({cy_ref_expr}) as cy_refunds,
                    SUM({py_ref_expr}) as py_refunds
                FROM analytics.program_refunds_summary r
                LEFT JOIN organization.source_master sm ON LOWER(TRIM(r.source)) = LOWER(TRIM(sm.source))
                WHERE {ref_where_sql} 
                  AND LOWER(r.program_code) = :p_code
                  AND {ref_lead_type_expr} = :eff_lt
                  AND {ref_main_src_expr} = :eff_ms
                GROUP BY {ref_rep_src_expr}
            )
            SELECT 
                COALESCE(a.report_source, r.report_source) as report_source,
                COALESCE(a.py_leads, 0) as py_leads,
                COALESCE(a.cy_leads, 0) as cy_leads,
                COALESCE(a.py_cucet, 0) as py_cucet,
                COALESCE(a.cy_cucet, 0) as cy_cucet,
                COALESCE(a.py_adm, 0) as py_adm,
                COALESCE(a.cy_adm, 0) as cy_adm,
                COALESCE(r.py_refunds, 0) as py_refunds,
                COALESCE(r.cy_refunds, 0) as cy_refunds
            FROM agg_data a
            FULL OUTER JOIN ref_data r ON a.report_source = r.report_source
            WHERE COALESCE(a.cy_leads, 0) > 0 OR COALESCE(a.py_leads, 0) > 0
        """
        all_params = {**params, **ref_params}
        res = db.execute(text(query_sql), all_params).fetchall()

        # Monthly trend for report sources
        trend_where = [
            "d.academic_year = :cy_year",
            "d.created_month IS NOT NULL",
            "LOWER(d.program_code) = :p_code",
            f"{lead_type_expr} = :eff_lt",
            f"{main_src_expr} = :eff_ms",
        ]
        trend_params = {
            "cy_year": academic_year,
            "p_code": eff_pcode.lower(),
            "eff_lt": eff_lead_type.upper(),
            "eff_ms": eff_main_src,
        }
        if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
            trend_where.append("LOWER(d.campus_name) = :campus")
            trend_params["campus"] = campus.strip().lower()
        if has_date_filter:
            trend_where.append("d.created_month >= :from_m AND d.created_month <= :to_m")
            trend_params["from_m"] = from_date.strip()[:7]
            trend_params["to_m"] = to_date.strip()[:7]

        rep_trend_sql = f"""
            SELECT 
                {rep_src_expr} as rs,
                d.created_month,
                SUM(d.leads_cy) as leads
            FROM analytics.dashboard_agg d
            LEFT JOIN organization.source_master sm ON LOWER(TRIM(d.source)) = LOWER(TRIM(sm.source))
            WHERE {" AND ".join(trend_where)}
            GROUP BY {rep_src_expr}, d.created_month
            ORDER BY 1, 2
        """
        tr_rows = db.execute(text(rep_trend_sql), trend_params).fetchall()
        rep_trends: Dict[str, Dict[str, int]] = {}
        distinct_months = set()
        for tr in tr_rows:
            rs_name = tr[0]
            m_key = tr[1]
            rep_trends.setdefault(rs_name, {})[m_key] = int(tr[2] or 0)
            distinct_months.add(m_key)
        sorted_m = sorted(list(distinct_months))

        for r in res:
            rs_name = str(r[0])
            py_l = int(r[1] or 0)
            cy_l = int(r[2] or 0)
            py_c = int(r[3] or 0)
            cy_c = int(r[4] or 0)
            py_a = int(r[5] or 0)
            cy_a = int(r[6] or 0)
            py_r = int(r[7] or 0)
            cy_r = int(r[8] or 0)

            node_id = f"rs:{eff_pcode}:{eff_lead_type}:{eff_main_src}:{rs_name}"
            r_dict = rep_trends.get(rs_name, {})
            row_trend = [r_dict.get(m, 0) for m in sorted_m]

            rows.append(
                _calculate_row_metrics(
                    name=rs_name,
                    py_leads=py_l,
                    cy_leads=cy_l,
                    py_cucet=py_c,
                    cy_cucet=cy_c,
                    py_adm=py_a,
                    cy_adm=cy_a,
                    py_refunds=py_r,
                    cy_refunds=cy_r,
                    lead_trend=row_trend,
                    node_id=node_id,
                    level=level_int,
                    has_children=has_children,
                    extra_props={
                        "program_group": program_group,
                        "program_code": eff_pcode,
                        "lead_type": eff_lead_type,
                        "source_category": eff_lead_type,
                        "main_source": eff_main_src,
                        "sub_source": eff_main_src,
                        "report_source": rs_name,
                    },
                )
            )

    # Sort children
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
        "level": norm_level,
        "parent": {
            "program_group": program_group,
            "program_code": eff_pcode,
            "program": eff_pcode,
            "lead_type": eff_lead_type,
            "main_source": eff_main_src,
            "source_category": eff_lead_type,
            "sub_source": eff_main_src,
        },
    }


def get_program_insights(
    db: Session,
    program_group: str,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dedicated Program Diagnostic & AI Insights Engine.
    Analyzes YoY Admissions Trajectory (Growth vs Drop) and isolates Root Cause Drivers:
      - Which Lead Types are Working Good (Growth Drivers) vs Bad (Declining / Drag)
      - Which Main Sources are Driving Admissions vs Dropping
      - Actionable Diagnostic Takeaways & Recommendations
    """
    if not academic_year:
        from app.analytics.period_helper import get_active_or_max_academic_year
        academic_year = get_active_or_max_academic_year(db)

    # Server-side cache check
    cache_key = f"{program_group}:{academic_year}:{campus}:{from_date}:{to_date}"
    now_ts = time.time()
    if cache_key in _PROGRAMS_INSIGHTS_CACHE:
        c_time, c_data = _PROGRAMS_INSIGHTS_CACHE[cache_key]
        if (now_ts - c_time) < _PROGRAMS_CACHE_TTL:
            return c_data

    py_year = academic_year - 1
    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())

    try:
        db.execute(text("SET LOCAL jit = off;"))
    except Exception:
        pass

    # Find matching course codes for program_group
    courses = db.execute(
        text("SELECT LOWER(TRIM(program_code)), program_group FROM organization.course_master WHERE program_group IS NOT NULL")
    ).fetchall()
    matching_pcodes = {r[0] for r in courses if r[1] and r[1].strip().upper() == program_group.strip().upper()}
    if not matching_pcodes:
        matching_pcodes = {program_group.strip().lower()}

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
        py_lead_expr = "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"
        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year AND d.created_month >= :from_m AND d.created_month <= :to_m THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = "CASE WHEN d.academic_year = :py_year AND d.created_month >= :py_from_m AND d.created_month <= :py_to_m THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"
        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year AND d.admission_month >= :from_m AND d.admission_month <= :to_m THEN d.admission_cy ELSE 0 END"
        py_adm_expr = "CASE WHEN d.academic_year = :py_year AND d.admission_month >= :py_from_m AND d.admission_month <= :py_to_m THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"
    else:
        cy_lead_expr = "CASE WHEN d.academic_year = :cy_year THEN d.leads_cy ELSE 0 END"
        py_lead_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.leads_cy, d.leads_py) ELSE 0 END"
        cy_cucet_expr = "CASE WHEN d.academic_year = :cy_year THEN d.cucet_cy ELSE 0 END"
        py_cucet_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.cucet_cy, d.cucet_py) ELSE 0 END"
        cy_adm_expr = "CASE WHEN d.academic_year = :cy_year THEN d.admission_cy ELSE 0 END"
        py_adm_expr = "CASE WHEN d.academic_year = :py_year THEN GREATEST(d.admission_cy, d.admission_py) ELSE 0 END"

    where_sql = " AND ".join(where_clauses)

    lead_type_expr = "COALESCE(NULLIF(UPPER(TRIM(sm.lead_type)), ''), NULLIF(UPPER(TRIM(d.lead_type)), ''), 'OTHERS')"
    main_src_expr = "COALESCE(NULLIF(TRIM(sm.main_source), ''), NULLIF(TRIM(d.source), ''), 'Direct')"

    sql = f"""
        SELECT 
            LOWER(TRIM(d.program_code)) as pcode,
            {lead_type_expr} as lead_type,
            {main_src_expr} as main_source,
            SUM({cy_lead_expr}) as cy_leads,
            SUM({py_lead_expr}) as py_leads,
            SUM({cy_cucet_expr}) as cy_cucet,
            SUM({py_cucet_expr}) as py_cucet,
            SUM({cy_adm_expr}) as cy_adm,
            SUM({py_adm_expr}) as py_adm
        FROM analytics.dashboard_agg d
        LEFT JOIN organization.source_master sm ON LOWER(TRIM(d.source)) = LOWER(TRIM(sm.source))
        WHERE {where_sql}
        GROUP BY 1, 2, 3
    """
    rows = db.execute(text(sql), params).fetchall()

    # Filter to this program group
    prog_rows = [r for r in rows if (r[0] in matching_pcodes or program_group.strip().upper() == "ALL")]

    tot_cy_leads = sum(int(r[3] or 0) for r in prog_rows)
    tot_py_leads = sum(int(r[4] or 0) for r in prog_rows)
    tot_cy_cucet = sum(int(r[5] or 0) for r in prog_rows)
    tot_py_cucet = sum(int(r[6] or 0) for r in prog_rows)
    tot_cy_adm = sum(int(r[7] or 0) for r in prog_rows)
    tot_py_adm = sum(int(r[8] or 0) for r in prog_rows)

    var_adm = tot_cy_adm - tot_py_adm
    var_adm_pct = round((var_adm / tot_py_adm * 100), 1) if tot_py_adm > 0 else (0.0 if tot_cy_adm == 0 else 100.0)
    var_leads = tot_cy_leads - tot_py_leads
    var_leads_pct = round((var_leads / tot_py_leads * 100), 1) if tot_py_leads > 0 else (0.0 if tot_cy_leads == 0 else 100.0)
    var_cucet = tot_cy_cucet - tot_py_cucet
    var_cucet_pct = round((var_cucet / tot_py_cucet * 100), 1) if tot_py_cucet > 0 else (0.0 if tot_cy_cucet == 0 else 100.0)

    conv_cy = round((tot_cy_adm / tot_cy_leads * 100), 2) if tot_cy_leads > 0 else 0.0
    conv_py = round((tot_py_adm / tot_py_leads * 100), 2) if tot_py_leads > 0 else 0.0

    if var_adm > 0:
        trajectory = "GROWING"
        trajectory_status = "up"
        trajectory_badge = f"+{var_adm:,} Admissions (+{var_adm_pct}%)"
    elif var_adm < 0:
        trajectory = "DROPPING"
        trajectory_status = "down"
        trajectory_badge = f"{var_adm:,} Admissions ({var_adm_pct}%)"
    else:
        trajectory = "STABLE"
        trajectory_status = "stable"
        trajectory_badge = "Admissions Flat (0.0%)"

    # -------------------------------------------------------------
    # 1. Lead Types Performance Breakdown (Good vs Bad)
    # -------------------------------------------------------------
    lt_map: Dict[str, Dict[str, Any]] = {}
    for r in prog_rows:
        lt = str(r[1] or "OTHERS")
        if lt not in lt_map:
            lt_map[lt] = {"cy_leads": 0, "py_leads": 0, "cy_cucet": 0, "py_cucet": 0, "cy_adm": 0, "py_adm": 0}
        lt_map[lt]["cy_leads"] += int(r[3] or 0)
        lt_map[lt]["py_leads"] += int(r[4] or 0)
        lt_map[lt]["cy_cucet"] += int(r[5] or 0)
        lt_map[lt]["py_cucet"] += int(r[6] or 0)
        lt_map[lt]["cy_adm"] += int(r[7] or 0)
        lt_map[lt]["py_adm"] += int(r[8] or 0)

    lead_type_insights = []
    for lt, m in lt_map.items():
        lt_cy_l = m["cy_leads"]
        lt_py_l = m["py_leads"]
        lt_cy_a = m["cy_adm"]
        lt_py_a = m["py_adm"]
        lt_var_a = lt_cy_a - lt_py_a
        lt_var_a_pct = round((lt_var_a / lt_py_a * 100), 1) if lt_py_a > 0 else (0.0 if lt_cy_a == 0 else 100.0)
        lt_var_l = lt_cy_l - lt_py_l
        lt_var_l_pct = round((lt_var_l / lt_py_l * 100), 1) if lt_py_l > 0 else (0.0 if lt_cy_l == 0 else 100.0)
        lt_conv = round((lt_cy_a / lt_cy_l * 100), 2) if lt_cy_l > 0 else 0.0

        # Working good vs bad logic
        is_good = (lt_var_a > 0) or (lt_var_l > 0 and lt_var_a >= 0) or (lt_conv >= conv_cy and lt_cy_a > 0)
        if is_good:
            status = "good"
            status_label = "Working Good (Growth Driver)"
            reason = f"High contribution: {lt_cy_a:,} admissions generated ({lt_var_a:+d} YoY, {lt_var_a_pct:+.1f}%) with {lt_conv:.2f}% conversion rate."
        else:
            status = "bad"
            status_label = "Underperforming / Drag"
            reason = f"Admissions changed by {lt_var_a:+d} ({lt_var_a_pct:+.1f}%) with {lt_var_l:+d} leads change ({lt_var_l_pct:+.1f}%)."

        lead_type_insights.append({
            "lead_type": lt,
            "status": status,
            "status_label": status_label,
            "cy_leads": lt_cy_l,
            "py_leads": lt_py_l,
            "var_leads": lt_var_l,
            "var_leads_pct": lt_var_l_pct,
            "cy_adm": lt_cy_a,
            "py_adm": lt_py_a,
            "var_adm": lt_var_a,
            "var_adm_pct": lt_var_a_pct,
            "conversion_rate": lt_conv,
            "reason": reason,
        })

    lead_type_insights.sort(key=lambda x: (x["status"] != "good", -x["cy_adm"], -x["var_adm"]))

    # -------------------------------------------------------------
    # 2. Main Sources Performance Breakdown (Good vs Bad Contributors)
    # -------------------------------------------------------------
    src_map: Dict[str, Dict[str, Any]] = {}
    for r in prog_rows:
        src = str(r[2] or "Direct")
        lt = str(r[1] or "OTHERS")
        key = f"{src}___{lt}"
        if key not in src_map:
            src_map[key] = {"source_name": src, "lead_type": lt, "cy_leads": 0, "py_leads": 0, "cy_adm": 0, "py_adm": 0}
        src_map[key]["cy_leads"] += int(r[3] or 0)
        src_map[key]["py_leads"] += int(r[4] or 0)
        src_map[key]["cy_adm"] += int(r[7] or 0)
        src_map[key]["py_adm"] += int(r[8] or 0)

    source_insights = []
    for key, m in src_map.items():
        s_cy_l = m["cy_leads"]
        s_py_l = m["py_leads"]
        s_cy_a = m["cy_adm"]
        s_py_a = m["py_adm"]
        s_var_a = s_cy_a - s_py_a
        s_var_a_pct = round((s_var_a / s_py_a * 100), 1) if s_py_a > 0 else (0.0 if s_cy_a == 0 else 100.0)
        s_var_l = s_cy_l - s_py_l
        s_var_l_pct = round((s_var_l / s_py_l * 100), 1) if s_py_l > 0 else (0.0 if s_cy_l == 0 else 100.0)
        s_conv = round((s_cy_a / s_cy_l * 100), 2) if s_cy_l > 0 else 0.0

        is_good = (s_var_a > 0) or (s_cy_a >= 10 and s_var_a >= 0)
        status = "good" if is_good else ("bad" if s_var_a < 0 or s_var_l < 0 else "neutral")

        source_insights.append({
            "source_name": m["source_name"],
            "lead_type": m["lead_type"],
            "status": status,
            "cy_leads": s_cy_l,
            "py_leads": s_py_l,
            "var_leads": s_var_l,
            "var_leads_pct": s_var_l_pct,
            "cy_adm": s_cy_a,
            "py_adm": s_py_a,
            "var_adm": s_var_a,
            "var_adm_pct": s_var_a_pct,
            "conversion_rate": s_conv,
        })

    # Top good sources (growth drivers)
    good_sources = [s for s in source_insights if s["status"] == "good"]
    good_sources.sort(key=lambda x: (-x["var_adm"], -x["cy_adm"]))

    # Top bad sources (drops / drag)
    bad_sources = [s for s in source_insights if s["status"] == "bad" or s["var_adm"] < 0 or s["var_leads"] < 0]
    bad_sources.sort(key=lambda x: (x["var_adm"], x["var_leads"]))

    # -------------------------------------------------------------
    # 3. AI Takeaways & Diagnostics Synthesis
    # -------------------------------------------------------------
    takeaways = []
    
    # Overall summary point
    if trajectory == "GROWING":
        takeaways.append({
            "type": "positive",
            "title": "Positive Growth Trajectory",
            "description": f"{program_group} admissions surged by +{var_adm:,} (+{var_adm_pct:.1f}% YoY) to {tot_cy_adm:,} total enrolled students.",
        })
    elif trajectory == "DROPPING":
        takeaways.append({
            "type": "negative",
            "title": "Admission Contraction Alert",
            "description": f"{program_group} admissions contracted by {var_adm:,} ({var_adm_pct:.1f}% YoY) from {tot_py_adm:,} down to {tot_cy_adm:,}.",
        })
    else:
        takeaways.append({
            "type": "neutral",
            "title": "Stable Intake Performance",
            "description": f"{program_group} maintained steady volume with {tot_cy_adm:,} admissions ({var_adm:+d} YoY).",
        })

    # Lead Type Driver point
    top_good_lt = next((lt for lt in lead_type_insights if lt["status"] == "good" and lt["cy_adm"] > 0), None)
    top_bad_lt = next((lt for lt in lead_type_insights if lt["status"] == "bad" and (lt["var_adm"] < 0 or lt["var_leads"] < 0)), None)

    if top_good_lt:
        takeaways.append({
            "type": "positive",
            "title": f"Key Growth Engine: {top_good_lt['lead_type']}",
            "description": f"Propelled by {top_good_lt['lead_type']} leads generating {top_good_lt['cy_adm']:,} admissions ({top_good_lt['var_adm']:+d} YoY) at {top_good_lt['conversion_rate']:.2f}% conversion efficiency.",
        })

    if top_bad_lt:
        takeaways.append({
            "type": "negative",
            "title": f"Underperforming Channel: {top_bad_lt['lead_type']}",
            "description": f"{top_bad_lt['lead_type']} channel experienced a decline of {top_bad_lt['var_adm']:+d} admissions ({top_bad_lt['var_leads']:+d} leads). Recommend reviewing campaign targeting and counselor outreach.",
        })

    # Source Driver point
    if good_sources:
        top_s = good_sources[0]
        takeaways.append({
            "type": "positive",
            "title": f"Top Source Performer: {top_s['source_name']}",
            "description": f"{top_s['source_name']} delivered {top_s['cy_adm']:,} admissions ({top_s['var_adm']:+d} YoY, conversion {top_s['conversion_rate']:.1f}%).",
        })

    if bad_sources and bad_sources[0]["var_adm"] < 0:
        bad_s = bad_sources[0]
        takeaways.append({
            "type": "warning",
            "title": f"Source Drop Alert: {bad_s['source_name']}",
            "description": f"{bad_s['source_name']} dropped by {bad_s['var_adm']} admissions ({bad_s['var_leads']:+d} leads). Investigate funnel leakage or vendor lead quality.",
        })

    # Actionable Recommendation
    takeaways.append({
        "type": "action",
        "title": "Actionable Optimization Strategy",
        "description": f"Allocate additional counsellor capacity to high-converting {top_good_lt['lead_type'] if top_good_lt else 'Direct'} leads and conduct rapid follow-up on CUCET registered prospects ({tot_cy_cucet:,} candidates).",
    })

    return {
        "program_group": program_group,
        "academic_year": academic_year,
        "campus": campus or "All Campuses",
        "trajectory": trajectory,
        "trajectory_status": trajectory_status,
        "trajectory_badge": trajectory_badge,
        "metrics": {
            "cy_admissions": tot_cy_adm,
            "py_admissions": tot_py_adm,
            "var_admissions": var_adm,
            "var_admissions_pct": var_adm_pct,
            "cy_leads": tot_cy_leads,
            "py_leads": tot_py_leads,
            "var_leads": var_leads,
            "var_leads_pct": var_leads_pct,
            "cy_cucet": tot_cy_cucet,
            "py_cucet": tot_py_cucet,
            "var_cucet": var_cucet,
            "var_cucet_pct": var_cucet_pct,
            "conversion_rate_cy": conv_cy,
            "conversion_rate_py": conv_py,
        },
        "lead_types": lead_type_insights,
        "top_growth_sources": good_sources[:6],
        "top_drag_sources": bad_sources[:6],
        "takeaways": takeaways,
    }
    _PROGRAMS_INSIGHTS_CACHE[cache_key] = (now_ts, resp)
    return resp

