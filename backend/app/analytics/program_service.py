"""
Analytical service for the Program Performance Report with strict Lazy Hierarchical Loading.
Provides aggregated metrics across 4 hierarchy levels:
  Level 1: Program Group (e.g. B.COM, B.E., BCA, MBA)
  Level 2: Program Branch / Variant (e.g. B.COM (H): ACCA : CM201)
  Level 3: Source Category (IN HOUSE, OUT SOURCED, OTHERS)
  Level 4: Sub-Source (e.g. DIRECT, WEBSITE, BROCHURE, nNext)
All aggregations are computed on PostgreSQL (GROUP BY, SUM). Zero raw CRM datasets are loaded.
"""

from typing import Dict, Any, List, Optional
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.analytics.aggregate_service import get_py_date

logger = logging.getLogger(__name__)

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

    query_sql = f"""
        WITH prog_metrics AS (
            SELECT 
                LOWER(TRIM(d.program_code)) as pcode,
                LOWER(TRIM(COALESCE(d.raw_program_code, ''))) as raw_pcode,
                LOWER(TRIM(COALESCE(d.program_name, ''))) as pname,
                SUM({cy_lead_expr}) as cy_leads,
                SUM({py_lead_expr}) as py_leads,
                SUM({cy_cucet_expr}) as cy_cucet,
                SUM({py_cucet_expr}) as py_cucet,
                SUM({cy_adm_expr}) as cy_adm,
                SUM({py_adm_expr}) as py_adm
            FROM analytics.dashboard_agg d
            WHERE {where_sql}
            GROUP BY LOWER(TRIM(d.program_code)), LOWER(TRIM(COALESCE(d.raw_program_code, ''))), LOWER(TRIM(COALESCE(d.program_name, '')))
        ),
        prog_refunds AS (
            SELECT 
                LOWER(TRIM(r.program_code)) as pcode,
                SUM({cy_ref_expr}) as cy_refunds,
                SUM({py_ref_expr}) as py_refunds
            FROM analytics.program_refunds_summary r
            WHERE {ref_where_sql}
            GROUP BY LOWER(TRIM(r.program_code))
        ),
        courses_dim AS (
            SELECT DISTINCT 
                LOWER(TRIM(program_code)) as pcode,
                LOWER(TRIM(program_name)) as pname,
                TRIM(program_group) as program_group
            FROM organization.course_master
            WHERE program_group IS NOT NULL AND TRIM(program_group) != ''
        )
        SELECT 
            COALESCE(NULLIF(TRIM(c.program_group), ''), 'OTHER') as program_group,
            COALESCE(SUM(m.py_leads), 0) as py_leads,
            COALESCE(SUM(m.cy_leads), 0) as cy_leads,
            COALESCE(SUM(m.py_cucet), 0) as py_cucet,
            COALESCE(SUM(m.cy_cucet), 0) as cy_cucet,
            COALESCE(SUM(m.py_adm), 0) as py_adm,
            COALESCE(SUM(m.cy_adm), 0) as cy_adm,
            COALESCE(SUM(r.py_refunds), 0) as py_refunds,
            COALESCE(SUM(r.cy_refunds), 0) as cy_refunds
        FROM prog_metrics m
        LEFT JOIN courses_dim c ON (
            m.pcode = c.pcode 
            OR m.raw_pcode = c.pcode 
            OR m.pname = c.pcode
            OR m.pname = c.pname
        )
        LEFT JOIN prog_refunds r ON m.pcode = r.pcode
        GROUP BY COALESCE(NULLIF(TRIM(c.program_group), ''), 'OTHER')
        HAVING COALESCE(SUM(m.cy_leads), 0) > 0 OR COALESCE(SUM(m.py_leads), 0) > 0
    """

    all_params = {**params, **ref_params}
    result_rows = db.execute(text(query_sql), all_params).fetchall()

    # Query monthly trend points for CY by program group
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
            COALESCE(NULLIF(TRIM(c.program_group), ''), 'OTHER') as program_group,
            d.created_month,
            SUM(d.leads_cy) as leads
        FROM analytics.dashboard_agg d
        LEFT JOIN (
            SELECT DISTINCT 
                LOWER(TRIM(program_code)) as pcode, 
                LOWER(TRIM(program_name)) as pname,
                TRIM(program_group) as program_group 
            FROM organization.course_master
            WHERE program_group IS NOT NULL AND TRIM(program_group) != ''
        ) c ON (
            LOWER(TRIM(d.program_code)) = c.pcode 
            OR LOWER(TRIM(COALESCE(d.raw_program_code, ''))) = c.pcode
            OR LOWER(TRIM(d.program_name)) = c.pcode
            OR LOWER(TRIM(d.program_name)) = c.pname
        )
        WHERE {" AND ".join(trend_where)}
        GROUP BY COALESCE(NULLIF(TRIM(c.program_group), ''), 'OTHER'), d.created_month
        ORDER BY 1, 2
    """
    trend_rows = db.execute(text(trend_sql), trend_params).fetchall()

    # Build group -> [lead_count] trend points
    group_trends: Dict[str, Dict[str, int]] = {}
    distinct_months = set()
    for tr in trend_rows:
        grp = tr[0]
        m_key = tr[1]
        cnt = int(tr[2] or 0)
        group_trends.setdefault(grp, {})[m_key] = cnt
        distinct_months.add(m_key)

    sorted_months = sorted(list(distinct_months))

    # Total accumulators
    tot_py_leads = tot_cy_leads = tot_py_cucet = tot_cy_cucet = 0
    tot_py_adm = tot_cy_adm = tot_py_refunds = tot_cy_refunds = 0
    tot_monthly: Dict[str, int] = {m: 0 for m in sorted_months}

    processed_rows = []
    for r in result_rows:
        grp = str(r[0])
        py_l = int(r[1] or 0)
        cy_l = int(r[2] or 0)
        py_c = int(r[3] or 0)
        cy_c = int(r[4] or 0)
        py_a = int(r[5] or 0)
        cy_a = int(r[6] or 0)
        py_r = int(r[7] or 0)
        cy_r = int(r[8] or 0)

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
        for m in sorted_months:
            cnt = grp_trend_dict.get(m, 0)
            row_trend.append(cnt)
            tot_monthly[m] += cnt

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

    return {
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
        else:
            group_filter = "c.program_group = :p_group"

        query_sql = f"""
            WITH known_codes AS (
                SELECT DISTINCT LOWER(program_code) as pcode FROM organization.course_master WHERE program_code IS NOT NULL
            ),
            target_branches AS (
                SELECT DISTINCT LOWER(c.program_code) as pcode, c.program_code as raw_code, c.program_name, c.program_name_short
                FROM organization.course_master c
                WHERE {group_filter}
                {"UNION SELECT DISTINCT LOWER(d.program_code) as pcode, d.program_code as raw_code, d.program_name, NULL as program_name_short FROM analytics.dashboard_agg d WHERE LOWER(d.program_code) NOT IN (SELECT pcode FROM known_codes)" if prog_grp.upper() == "OTHER" else ""}
            ),
            agg_data AS (
                SELECT 
                    LOWER(d.program_code) as pcode,
                    SUM({cy_lead_expr}) as cy_leads,
                    SUM({py_lead_expr}) as py_leads,
                    SUM({cy_cucet_expr}) as cy_cucet,
                    SUM({py_cucet_expr}) as py_cucet,
                    SUM({cy_adm_expr}) as cy_adm,
                    SUM({py_adm_expr}) as py_adm
                FROM analytics.dashboard_agg d
                JOIN target_branches b ON LOWER(d.program_code) = b.pcode
                WHERE {where_sql}
                GROUP BY LOWER(d.program_code)
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
                COALESCE(a.py_leads, 0) as py_leads,
                COALESCE(a.cy_leads, 0) as cy_leads,
                COALESCE(a.py_cucet, 0) as py_cucet,
                COALESCE(a.cy_cucet, 0) as cy_cucet,
                COALESCE(a.py_adm, 0) as py_adm,
                COALESCE(a.cy_adm, 0) as cy_adm,
                COALESCE(r.py_refunds, 0) as py_refunds,
                COALESCE(r.cy_refunds, 0) as cy_refunds
            FROM target_branches b
            LEFT JOIN agg_data a ON b.pcode = a.pcode
            LEFT JOIN ref_data r ON b.pcode = r.pcode
            WHERE COALESCE(a.cy_leads, 0) > 0 OR COALESCE(a.py_leads, 0) > 0
        """
        all_params = {**params, **ref_params}
        res = db.execute(text(query_sql), all_params).fetchall()

        # Monthly trend for programs
        trend_where = [
            "d.academic_year = :cy_year",
            "d.created_month IS NOT NULL",
            "d.program_code IS NOT NULL",
        ]
        trend_params = {"cy_year": academic_year, "p_group": prog_grp}
        if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
            trend_where.append("LOWER(d.campus_name) = :campus")
            trend_params["campus"] = campus.strip().lower()
        if has_date_filter:
            trend_where.append("d.created_month >= :from_m AND d.created_month <= :to_m")
            trend_params["from_m"] = from_date.strip()[:7]
            trend_params["to_m"] = to_date.strip()[:7]

        branch_trend_sql = f"""
            SELECT 
                LOWER(d.program_code) as pcode,
                d.created_month,
                SUM(d.leads_cy) as leads
            FROM analytics.dashboard_agg d
            JOIN organization.course_master c ON LOWER(d.program_code) = LOWER(c.program_code)
            WHERE {group_filter} AND {" AND ".join(trend_where)}
            GROUP BY LOWER(d.program_code), d.created_month
            ORDER BY 1, 2
        """
        tr_rows = db.execute(text(branch_trend_sql), trend_params).fetchall()
        branch_trends: Dict[str, Dict[str, int]] = {}
        distinct_months = set()
        for tr in tr_rows:
            pcode = tr[0]
            m_key = tr[1]
            branch_trends.setdefault(pcode, {})[m_key] = int(tr[2] or 0)
            distinct_months.add(m_key)
        sorted_m = sorted(list(distinct_months))

        for r in res:
            raw_code = str(r[0])
            p_name = str(r[1])
            py_l = int(r[2] or 0)
            cy_l = int(r[3] or 0)
            py_c = int(r[4] or 0)
            cy_c = int(r[5] or 0)
            py_a = int(r[6] or 0)
            cy_a = int(r[7] or 0)
            py_r = int(r[8] or 0)
            cy_r = int(r[9] or 0)

            node_id = f"prog:{prog_grp}:{raw_code}"
            b_dict = branch_trends.get(raw_code.lower(), {})
            row_trend = [b_dict.get(m, 0) for m in sorted_m]

            rows.append(
                _calculate_row_metrics(
                    name=p_name,
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
                        "program_group": prog_grp,
                        "program_code": raw_code,
                        "program": raw_code,
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
                        "program": eff_pcode,
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
                        "program": eff_pcode,
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
                        "program": eff_pcode,
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

