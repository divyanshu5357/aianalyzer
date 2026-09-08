"""
Counsellor & Lead Activity Analytics Service

Calculates trusted counsellor summaries, time-to-first-call, call attempt bucketing,
follow-up exception tracking, and multi-format report exports (CSV/XLSX).
"""
import io
import csv
import re
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def extract_employee_id(owner_name: Optional[str]) -> str:
    """Extract canonical employee ID from owner string e.g. 'Ganesh Dutt E1678' -> 'E1678'."""
    if not owner_name:
        return "UNKNOWN"
    m = re.search(r'([A-Z0-9]+)$', owner_name.strip())
    if m:
        return m.group(1)
    return owner_name.strip().upper()


def parse_counsellor_identity(owner_name: Optional[str]) -> tuple[str, Optional[str]]:
    """Parse counsellor display name and optional employee ID.
    
    Examples:
        'Shallu Rani E10630' -> ('Shallu Rani', 'E10630')
        'Sakshi Sharma' -> ('Sakshi Sharma', None)
        'Aakanksha Malhotra l100404' -> ('Aakanksha Malhotra', 'L100404')
        'Aananya Bhardwaj NL101' -> ('Aananya Bhardwaj', 'NL101')
    """
    if not owner_name or not owner_name.strip():
        return "Unassigned", None
    raw = owner_name.strip()
    m = re.match(r'^(.*?)(?:\s+([A-Za-z]{1,3}\d{2,7}))?$', raw)
    if m and m.group(2):
        name = m.group(1).strip()
        emp_id = m.group(2).upper()
        return (name if name else raw), emp_id
    return raw, None


def _build_lead_filter_where(
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    counsellor: Optional[str] = None,
    program: Optional[str] = None,
    cluster: Optional[str] = None,
    state: Optional[str] = None,
    source: Optional[str] = None,
    disposition: Optional[str] = None,
    sub_disposition: Optional[str] = None,
    attempt_bucket: Optional[str] = None,
    followup_status: Optional[str] = None,
    search: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> tuple[str, dict]:
    """Build PostgreSQL WHERE clause for lead activity queries."""
    conds = ["sd.workbook_type = 'RAW'"]
    params: dict[str, Any] = {}

    if dataset_id:
        conds.append("r.dataset_id = :ds_id")
        params["ds_id"] = str(dataset_id)

    if academic_year:
        conds.append("COALESCE(sd.academic_year, (CASE WHEN system.parse_month(COALESCE(NULLIF(TRIM(r.raw_data->>'CreatedOn'), ''), NULLIF(TRIM(r.raw_data->>'enquiry_date'), ''))) ~ '^[0-9]{4}' THEN CAST(SUBSTRING(system.parse_month(COALESCE(NULLIF(TRIM(r.raw_data->>'CreatedOn'), ''), NULLIF(TRIM(r.raw_data->>'enquiry_date'), ''))) FROM 1 FOR 4) AS INT) ELSE NULL END)) = :acad_year")
        params["acad_year"] = academic_year

    if campus and campus.lower() != "all":
        conds.append("LOWER(COALESCE(r.raw_data->>'mx_Campus', '')) = LOWER(:campus)")
        params["campus"] = campus

    if counsellor and counsellor.lower() != "all":
        conds.append("(LOWER(COALESCE(r.raw_data->>'OwnerIdName', '')) LIKE LOWER(:counsellor) OR UPPER(COALESCE(r.raw_data->>'OwnerIdName', '')) LIKE UPPER(:counsellor))")
        params["counsellor"] = f"%{counsellor}%"

    if program and program.lower() != "all":
        conds.append("(LOWER(COALESCE(r.raw_data->>'Program Code', '')) = LOWER(:prog) OR LOWER(COALESCE(r.raw_data->>'Program Name', '')) LIKE LOWER(:prog_like))")
        params["prog"] = program
        params["prog_like"] = f"%{program}%"

    if cluster and cluster.lower() != "all":
        conds.append("LOWER(COALESCE(cm.course_cluster, '')) = LOWER(:cluster)")
        params["cluster"] = cluster

    if state and state.lower() != "all":
        conds.append("LOWER(COALESCE(r.raw_data->>'mx_State_New', r.raw_data->>'mx_State', '')) = LOWER(:state)")
        params["state"] = state

    if source and source.lower() != "all":
        conds.append("LOWER(COALESCE(r.raw_data->>'Source', r.raw_data->>'Origin', '')) = LOWER(:source)")
        params["source"] = source

    if disposition and disposition.lower() != "all":
        conds.append("(LOWER(COALESCE(r.raw_data->>'mx_First_Call_Disposition', '')) = LOWER(:disp) OR LOWER(COALESCE(r.raw_data->>'mx_Call_Disposition', '')) = LOWER(:disp))")
        params["disp"] = disposition

    if sub_disposition and sub_disposition.lower() != "all":
        conds.append("(LOWER(COALESCE(r.raw_data->>'mx_First_Call_Sub_Disposition', '')) = LOWER(:sub_disp) OR LOWER(COALESCE(r.raw_data->>'mx_Call_Sub_Disposition', '')) = LOWER(:sub_disp))")
        params["sub_disp"] = sub_disposition

    if attempt_bucket and attempt_bucket.lower() != "all":
        if attempt_bucket == "0":
            conds.append("(r.raw_data->>'mx_Total_Call_Attempt' IS NULL OR CAST(COALESCE(NULLIF(NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), 'NULL'), ''), '0') AS numeric) = 0)")
        elif attempt_bucket == "1":
            conds.append("CAST(COALESCE(NULLIF(NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), 'NULL'), ''), '0') AS numeric) = 1")
        elif attempt_bucket == "2":
            conds.append("CAST(COALESCE(NULLIF(NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), 'NULL'), ''), '0') AS numeric) = 2")
        elif attempt_bucket == "3":
            conds.append("CAST(COALESCE(NULLIF(NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), 'NULL'), ''), '0') AS numeric) = 3")
        elif attempt_bucket == "4+":
            conds.append("CAST(COALESCE(NULLIF(NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), 'NULL'), ''), '0') AS numeric) >= 4")

    if followup_status and followup_status.lower() != "all":
        today_str = date.today().isoformat()
        if followup_status == "No Follow-up Date":
            conds.append("NULLIF(TRIM(r.raw_data->>'mx_Latest_Follow_Up_Date'), '') IS NULL")
        elif followup_status == "Overdue":
            conds.append("NULLIF(TRIM(r.raw_data->>'mx_Latest_Follow_Up_Date'), '') < :today_str AND r.raw_data->>'ProspectStage' != 'Enrolled'")
            params["today_str"] = today_str
        elif followup_status == "Due Today":
            conds.append("SUBSTRING(r.raw_data->>'mx_Latest_Follow_Up_Date' FROM 1 FOR 10) = :today_str")
            params["today_str"] = today_str
        elif followup_status == "Upcoming":
            conds.append("NULLIF(TRIM(r.raw_data->>'mx_Latest_Follow_Up_Date'), '') > :today_str")
            params["today_str"] = today_str

    if search and search.strip():
        conds.append("(LOWER(COALESCE(r.raw_data->>'ProspectID', '')) LIKE LOWER(:search) OR LOWER(COALESCE(r.raw_data->>'FirstName', '')) LIKE LOWER(:search) OR LOWER(COALESCE(r.raw_data->>'OwnerIdName', '')) LIKE LOWER(:search))")
        params["search"] = f"%{search.strip()}%"

    where_clause = " AND ".join(conds)
    return where_clause, params


def get_counsellor_summary(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    counsellor: Optional[str] = None,
    program: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate trusted counsellor performance summary grouped by owner/counsellor."""
    where_clause, params = _build_lead_filter_where(
        academic_year=academic_year, campus=campus, counsellor=counsellor, program=program, dataset_id=dataset_id
    )

    sql = f"""
        WITH lead_base AS (
            SELECT 
                r.raw_data->>'OwnerIdName' as owner_name,
                r.raw_data->>'ProspectID' as prospect_id,
                CAST(COALESCE(NULLIF(NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), 'NULL'), ''), '0') AS numeric) as attempts,
                r.raw_data->>'mx_First_Allocation_Date_and_Time' as alloc_time,
                r.raw_data->>'mx_First_Call_Disposition_Date' as first_call_time,
                r.raw_data->>'mx_Latest_Follow_Up_Date' as follow_up_date,
                r.raw_data->>'mx_First_Call_Disposition' as first_disp,
                r.raw_data->>'mx_Call_Disposition' as call_disp,
                r.raw_data->>'mx_AdmissionDate' as adm_date,
                r.raw_data->>'ProspectStage' as stage
            FROM staging.records r
            JOIN system.datasets sd ON r.dataset_id = sd.id
            LEFT JOIN organization.course_master cm ON LOWER(TRIM(r.raw_data->>'Program Code')) = LOWER(TRIM(cm.program_code))
            WHERE {where_clause}
        )
        SELECT 
            COALESCE(owner_name, 'Unassigned') as counsellor,
            COUNT(DISTINCT prospect_id) as leads_assigned,
            SUM(CASE WHEN attempts = 0 OR attempts IS NULL THEN 1 ELSE 0 END) as calls_0,
            SUM(CASE WHEN attempts = 1 THEN 1 ELSE 0 END) as calls_1,
            SUM(CASE WHEN attempts = 2 THEN 1 ELSE 0 END) as calls_2,
            SUM(CASE WHEN attempts = 3 THEN 1 ELSE 0 END) as calls_3,
            SUM(CASE WHEN attempts >= 4 THEN 1 ELSE 0 END) as calls_4_plus,
            SUM(attempts) as total_calls,
            AVG(attempts) as avg_calls_per_lead,
            
            -- Time to first call in minutes
            AVG(
                CASE 
                    WHEN NULLIF(NULLIF(TRIM(alloc_time), 'NULL'), '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' 
                     AND NULLIF(NULLIF(TRIM(first_call_time), 'NULL'), '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN EXTRACT(EPOCH FROM (CAST(first_call_time AS timestamp) - CAST(alloc_time AS timestamp))) / 60.0
                    ELSE NULL 
                END
            ) as avg_time_to_first_call_mins,

            -- Overdue & Due Today
            SUM(CASE WHEN NULLIF(TRIM(follow_up_date), '') < CURRENT_DATE::text AND stage != 'Enrolled' THEN 1 ELSE 0 END) as overdue_followups,
            SUM(CASE WHEN SUBSTRING(follow_up_date FROM 1 FOR 10) = CURRENT_DATE::text THEN 1 ELSE 0 END) as due_today_followups,
            
            -- Interested & Admissions
            SUM(CASE WHEN LOWER(COALESCE(first_disp, '')) = 'interested' OR LOWER(COALESCE(call_disp, '')) = 'interested' THEN 1 ELSE 0 END) as interested_leads,
            SUM(CASE WHEN NULLIF(TRIM(adm_date), '') IS NOT NULL AND LOWER(TRIM(adm_date)) != 'null' THEN 1 ELSE 0 END) as admissions
        FROM lead_base
        GROUP BY owner_name
        ORDER BY leads_assigned DESC;
    """

    rows = db.execute(text(sql), params).mappings().all()
    counsellors_list = []

    total_leads = 0
    total_calls_all = 0
    total_admissions_all = 0
    total_overdue_all = 0
    total_interested_all = 0

    for r in rows:
        c_name = r["counsellor"]
        emp_id = extract_employee_id(c_name)
        assigned = int(r["leads_assigned"] or 0)
        admissions = int(r["admissions"] or 0)
        conv_rate = round((admissions / assigned * 100), 2) if assigned > 0 else 0.0

        total_leads += assigned
        total_calls_all += int(r["total_calls"] or 0)
        total_admissions_all += admissions
        total_overdue_all += int(r["overdue_followups"] or 0)
        total_interested_all += int(r["interested_leads"] or 0)

        avg_mins = float(r["avg_time_to_first_call_mins"]) if r["avg_time_to_first_call_mins"] is not None else None
        avg_hours = round(avg_mins / 60.0, 1) if avg_mins is not None else None

        counsellors_list.append({
            "counsellor": c_name,
            "employee_id": emp_id,
            "leads_assigned": assigned,
            "calls_0": int(r["calls_0"] or 0),
            "calls_1": int(r["calls_1"] or 0),
            "calls_2": int(r["calls_2"] or 0),
            "calls_3": int(r["calls_3"] or 0),
            "calls_4_plus": int(r["calls_4_plus"] or 0),
            "total_calls": int(r["total_calls"] or 0),
            "avg_calls_per_lead": round(float(r["avg_calls_per_lead"] or 0), 1),
            "avg_time_to_first_call_mins": round(avg_mins, 1) if avg_mins is not None else None,
            "avg_time_to_first_call_hours": avg_hours,
            "overdue_followups": int(r["overdue_followups"] or 0),
            "due_today_followups": int(r["due_today_followups"] or 0),
            "interested_leads": int(r["interested_leads"] or 0),
            "admissions": admissions,
            "conversion_rate": conv_rate,
            "counsellor_name": parse_counsellor_identity(c_name)[0],
            "owner_id": parse_counsellor_identity(c_name)[1] or emp_id,
            "raw_counsellor": c_name,
            "conversion_rate_display": f"{conv_rate:.2f}%",
        })

    overall_conv = round((total_admissions_all / total_leads * 100), 2) if total_leads > 0 else 0.0

    return {
        "status": "success",
        "total_counsellors": len(counsellors_list),
        "summary": {
            "total_leads_assigned": total_leads,
            "total_admissions": total_admissions_all,
            "overall_conversion_rate": overall_conv,
            "conversion_rate_display": f"{overall_conv:.2f}%",
        },
        "summary_kpis": {
            "total_counsellors": len(counsellors_list),
            "total_leads_assigned": total_leads,
            "total_calls_made": total_calls_all,
            "total_admissions": total_admissions_all,
            "total_overdue_followups": total_overdue_all,
            "total_interested_leads": total_interested_all,
            "overall_conversion_rate": overall_conv,
        },
        "counsellors": counsellors_list,
    }


def get_counsellors_list(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Ultra-fast set-based aggregation returning the Level 1 list of all counsellors.
    
    Uses analytics.dashboard_agg when available for sub-second performance, with
    automatic fallback to staging.records.
    """
    has_agg = db.execute(text("SELECT 1 FROM analytics.dashboard_agg LIMIT 1")).scalar() is not None

    if has_agg:
        conds = ["owner IS NOT NULL", "TRIM(owner) != ''"]
        params: dict[str, Any] = {}

        if academic_year and str(academic_year).lower() != "all":
            conds.append("academic_year = :acad_year")
            params["acad_year"] = int(academic_year)

        if campus and campus.lower() != "all":
            conds.append("LOWER(COALESCE(campus_name, '')) = LOWER(:campus)")
            params["campus"] = campus

        if search and search.strip():
            conds.append("owner ILIKE :search")
            params["search"] = f"%{search.strip()}%"

        where_clause = " AND ".join(conds)
        sql = f"""
            SELECT 
                owner,
                SUM(leads_cy) as leads,
                SUM(admission_cy) as admissions
            FROM analytics.dashboard_agg
            WHERE {where_clause}
            GROUP BY owner
            ORDER BY leads DESC;
        """
        rows = db.execute(text(sql), params).mappings().all()
    else:
        conds = [
            "sd.workbook_type = 'RAW'",
            "r.raw_data->>'OwnerIdName' IS NOT NULL",
            "TRIM(r.raw_data->>'OwnerIdName') != ''"
        ]
        params = {}
        if academic_year and str(academic_year).lower() != "all":
            conds.append("sd.academic_year = :acad_year")
            params["acad_year"] = int(academic_year)
        if campus and campus.lower() != "all":
            conds.append("LOWER(COALESCE(r.raw_data->>'mx_Campus', '')) = LOWER(:campus)")
            params["campus"] = campus
        if search and search.strip():
            conds.append("r.raw_data->>'OwnerIdName' ILIKE :search")
            params["search"] = f"%{search.strip()}%"

        where_clause = " AND ".join(conds)
        sql = f"""
            SELECT 
                r.raw_data->>'OwnerIdName' as owner,
                COUNT(DISTINCT r.raw_data->>'ProspectID') as leads,
                COUNT(DISTINCT CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN r.raw_data->>'ProspectID' END) as admissions
            FROM staging.records r
            JOIN system.datasets sd ON r.dataset_id = sd.id
            WHERE {where_clause}
            GROUP BY 1
            ORDER BY 2 DESC;
        """
        rows = db.execute(text(sql), params).mappings().all()

    counsellors_list = []
    total_leads = 0
    total_admissions = 0

    for r in rows:
        raw_owner = r["owner"]
        name, emp_id = parse_counsellor_identity(raw_owner)
        leads = int(r["leads"] or 0)
        adms = int(r["admissions"] or 0)
        conv = round((adms / leads * 100), 2) if leads > 0 else 0.0

        total_leads += leads
        total_admissions += adms

        counsellors_list.append({
            "counsellor": raw_owner,
            "counsellor_name": name,
            "owner_id": emp_id,
            "raw_counsellor": raw_owner,
            "employee_id": emp_id or extract_employee_id(raw_owner),
            "leads_assigned": leads,
            "admissions": adms,
            "conversion_rate": conv,
            "conversion_rate_display": f"{conv:.2f}%",
        })

    overall_conv = round((total_admissions / total_leads * 100), 2) if total_leads > 0 else 0.0

    return {
        "status": "success",
        "total_counsellors": len(counsellors_list),
        "summary": {
            "total_leads_assigned": total_leads,
            "total_admissions": total_admissions,
            "overall_conversion_rate": overall_conv,
            "conversion_rate_display": f"{overall_conv:.2f}%",
        },
        "summary_kpis": {
            "total_counsellors": len(counsellors_list),
            "total_leads_assigned": total_leads,
            "total_admissions": total_admissions,
            "overall_conversion_rate": overall_conv,
        },
        "counsellors": counsellors_list,
    }


def get_counsellor_detail_report(
    db: Session,
    counsellor_id_or_name: str,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns the Level 2 detail report for a selected counsellor.
    
    Includes:
    - Counsellor profile (Name, Owner ID, canonical string)
    - KPI cards (Total Leads Assigned, Total Admissions, Conversion Rate, Best Source Category)
    - Dynamic Source Category table from organization.source_master (never hardcoded)
      ranked by conversion rate descending.
    - Zero-division rule: Categories with 0 leads show 'N/A' conversion rate and cannot
      be selected as best performing category.
    """
    if not counsellor_id_or_name:
        raise ValueError("counsellor_id_or_name is required")

    conds = ["sd.workbook_type = 'RAW'"]
    params: dict[str, Any] = {}

    if academic_year and str(academic_year).lower() != "all":
        conds.append("sd.academic_year = :acad_year")
        params["acad_year"] = int(academic_year)

    if campus and campus.lower() != "all":
        conds.append("LOWER(COALESCE(r.raw_data->>'mx_Campus', '')) = LOWER(:campus)")
        params["campus"] = campus

    where_base = " AND ".join(conds)

    # 1. Resolve canonical owner name
    owner_input = counsellor_id_or_name.strip()
    
    # Check if exact match in dashboard_agg
    chk = db.execute(text("""
        SELECT owner FROM analytics.dashboard_agg
        WHERE owner IS NOT NULL AND LOWER(TRIM(owner)) = LOWER(TRIM(:inp))
        LIMIT 1
    """), {"inp": owner_input}).scalar()

    if not chk:
        # Check by employee ID in dashboard_agg
        m = re.search(r'([A-Za-z]{1,3}\d{2,7})$', owner_input)
        emp_id_candidate = m.group(1).upper() if m else owner_input.upper()
        chk = db.execute(text("""
            SELECT owner FROM analytics.dashboard_agg
            WHERE owner IS NOT NULL AND (owner ILIKE :pat OR UPPER(owner) = :eid)
            GROUP BY owner
            ORDER BY LENGTH(owner) ASC
            LIMIT 1
        """), {"pat": f"%{emp_id_candidate}", "eid": emp_id_candidate}).scalar()

    try:
        db.execute(text("SET LOCAL jit = off;"))
    except Exception:
        pass

    if not chk:
        # Fuzzy match in dashboard_agg
        chk = db.execute(text("""
            SELECT owner FROM analytics.dashboard_agg
            WHERE owner IS NOT NULL AND LOWER(TRIM(owner)) LIKE LOWER(:pat)
            LIMIT 1
        """), {"pat": f"%{owner_input}%"}).scalar()

    resolved_owner = chk or owner_input
    c_name, emp_id = parse_counsellor_identity(resolved_owner)

    # 2. Get dynamic categories from organization.source_master (strictly data-driven, no hardcoding)
    all_cats_rows = db.execute(text("""
        SELECT DISTINCT lead_type 
        FROM organization.source_master 
        WHERE lead_type IS NOT NULL AND TRIM(lead_type) != '' 
        ORDER BY lead_type
    """)).fetchall()
    all_cats = [r[0] for r in all_cats_rows]

    # 3. Aggregate metrics for this counsellor by source category using dashboard_agg
    agg_conds = ["da.owner = :owner"]
    agg_params: dict[str, Any] = {"owner": resolved_owner}
    if academic_year and str(academic_year).lower() != "all":
        agg_conds.append("da.academic_year = :acad_year")
        agg_params["acad_year"] = int(academic_year)
    if campus and campus.lower() != "all":
        agg_conds.append("LOWER(COALESCE(da.campus_name, '')) = LOWER(:campus)")
        agg_params["campus"] = campus
    agg_where = " AND ".join(agg_conds)

    cat_sql = f"""
        SELECT 
            COALESCE(sm.lead_type, 'Others') as category,
            SUM(da.leads_cy) as leads,
            SUM(da.admission_cy) as admissions
        FROM analytics.dashboard_agg da
        LEFT JOIN organization.source_master sm ON LOWER(TRIM(da.source)) = LOWER(TRIM(sm.source))
        WHERE {agg_where}
        GROUP BY 1;
    """
    cat_rows = db.execute(text(cat_sql), agg_params).mappings().all()

    if not cat_rows:
        # Fallback to staging.records only if dashboard_agg yielded zero rows
        fallback_cat_sql = f"""
            SELECT 
                COALESCE(sm.lead_type, 'Others') as category,
                COUNT(DISTINCT r.raw_data->>'ProspectID') as leads,
                COUNT(DISTINCT CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN r.raw_data->>'ProspectID' END) as admissions
            FROM staging.records r
            JOIN system.datasets sd ON r.dataset_id = sd.id
            LEFT JOIN organization.source_master sm ON LOWER(TRIM(COALESCE(r.raw_data->>'MSSourcebi', r.raw_data->>'Source', r.raw_data->>'Origin', ''))) = LOWER(TRIM(sm.source))
            WHERE {where_base} AND r.raw_data->>'OwnerIdName' = :owner
            GROUP BY 1;
        """
        cat_rows = db.execute(text(fallback_cat_sql), {**params, "owner": resolved_owner}).mappings().all()

    cat_map = {r["category"]: (int(r["leads"] or 0), int(r["admissions"] or 0)) for r in cat_rows}

    # Ensure all dynamic categories from source_master are represented
    for cat in all_cats:
        if cat not in cat_map:
            cat_map[cat] = (0, 0)

    category_results = []
    total_leads = sum(v[0] for v in cat_map.values())
    total_admissions = sum(v[1] for v in cat_map.values())

    for cat_name, (leads, adms) in cat_map.items():
        if leads > 0:
            rate = round((adms / leads * 100), 2)
            display = f"{rate:.2f}%"
        else:
            # Zero-division rule: must be N/A, not 0%
            rate = None
            display = "N/A"

        category_results.append({
            "category": cat_name,
            "leads_assigned": leads,
            "admissions": adms,
            "conversion_rate": rate,
            "conversion_rate_display": display,
        })

    # Sort categories by conversion rate descending (valid rates first, then 0-lead N/A categories)
    def sort_key(item):
        r = item["conversion_rate"]
        has_rate = 1 if r is not None else 0
        val = r if r is not None else -1.0
        return (has_rate, val, item["leads_assigned"])

    category_results.sort(key=sort_key, reverse=True)

    # Determine best category: category with highest valid conversion rate with leads > 0
    valid_categories = [c for c in category_results if c["conversion_rate"] is not None and c["leads_assigned"] > 0]
    best_cat = valid_categories[0]["category"] if valid_categories else "N/A"

    overall_conv = round((total_admissions / total_leads * 100), 2) if total_leads > 0 else None
    overall_display = f"{overall_conv:.2f}%" if overall_conv is not None else "N/A"

    return {
        "status": "success",
        "counsellor": {
            "counsellor_name": c_name,
            "owner_id": emp_id,
            "raw_counsellor": resolved_owner,
        },
        "summary": {
            "total_leads_assigned": total_leads,
            "total_admissions": total_admissions,
            "conversion_rate": overall_conv,
            "conversion_rate_display": overall_display,
            "best_source_category": best_cat,
        },
        "categories": category_results,
    }


def get_lead_activity(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    counsellor: Optional[str] = None,
    program: Optional[str] = None,
    cluster: Optional[str] = None,
    state: Optional[str] = None,
    source: Optional[str] = None,
    disposition: Optional[str] = None,
    attempt_bucket: Optional[str] = None,
    followup_status: Optional[str] = None,
    search: Optional[str] = None,
    dataset_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "created_on",
    order: str = "desc",
) -> Dict[str, Any]:
    """Return paginated lead activity records with all 18 normalized fields."""
    where_clause, params = _build_lead_filter_where(
        academic_year=academic_year, campus=campus, counsellor=counsellor, program=program,
        cluster=cluster, state=state, source=source, disposition=disposition,
        attempt_bucket=attempt_bucket, followup_status=followup_status, search=search, dataset_id=dataset_id
    )

    offset = (page - 1) * page_size

    sort_map = {
        "created_on": "r.raw_data->>'CreatedOn'",
        "prospect_id": "r.raw_data->>'ProspectID'",
        "owner": "r.raw_data->>'OwnerIdName'",
        "program": "r.raw_data->>'Program Name'",
        "calls": "CAST(COALESCE(NULLIF(r.raw_data->>'mx_Total_Call_Attempt', ''), '0') AS numeric)",
    }
    sort_col = sort_map.get(sort_by, "r.raw_data->>'CreatedOn'")
    sort_order = "DESC" if order.lower() == "desc" else "ASC"

    count_sql = f"""
        SELECT COUNT(*) 
        FROM staging.records r
        JOIN system.datasets sd ON r.dataset_id = sd.id
        LEFT JOIN organization.course_master cm ON LOWER(TRIM(r.raw_data->>'Program Code')) = LOWER(TRIM(cm.program_code))
        WHERE {where_clause}
    """
    total_leads = db.execute(text(count_sql), params).scalar() or 0

    query_sql = f"""
        SELECT 
            r.raw_data->>'ProspectID' as prospect_id,
            r.raw_data->>'OwnerIdName' as owner_name,
            r.raw_data->>'Program Code' as raw_program_code,
            COALESCE(cm.program_name, r.raw_data->>'Program Name', r.raw_data->>'Program Code') as program_name,
            COALESCE(cm.course_cluster, r.raw_data->>'course_cluster') as course_cluster,
            COALESCE(cm.degree_type, 'Under Graduate') as degree_type,
            COALESCE(r.raw_data->>'mx_State_New', r.raw_data->>'mx_State') as state,
            COALESCE(r.raw_data->>'Source', r.raw_data->>'Origin') as source,
            r.raw_data->>'CreatedOn' as created_on,
            r.raw_data->>'mx_First_Allocation_Date_and_Time' as first_allocation_date,
            r.raw_data->>'mx_First_Call_Disposition_Date' as first_call_date,
            r.raw_data->>'mx_Last_Call_Date_and_Time' as last_call_date,
            CAST(COALESCE(NULLIF(NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), 'NULL'), ''), '0') AS numeric) as total_call_attempts,
            r.raw_data->>'mx_First_Call_Disposition' as first_call_disposition,
            r.raw_data->>'mx_First_Call_Sub_Disposition' as first_call_sub_disposition,
            r.raw_data->>'mx_Latest_Follow_Up_Date' as latest_follow_up_date,
            r.raw_data->>'mx_Call_Disposition' as latest_call_disposition,
            r.raw_data->>'mx_Call_Sub_Disposition' as latest_call_sub_disposition,
            r.raw_data->>'mx_AdmissionDate' as admission_date,
            r.raw_data->>'ProspectStage' as prospect_stage
        FROM staging.records r
        JOIN system.datasets sd ON r.dataset_id = sd.id
        LEFT JOIN organization.course_master cm ON LOWER(TRIM(r.raw_data->>'Program Code')) = LOWER(TRIM(cm.program_code))
        WHERE {where_clause}
        ORDER BY {sort_col} {sort_order} NULLS LAST
        LIMIT :limit OFFSET :offset;
    """
    params["limit"] = page_size
    params["offset"] = offset

    rows = db.execute(text(query_sql), params).mappings().all()
    today_str = date.today().isoformat()

    leads_list = []
    for r in rows:
        m = dict(r)
        f_date = m.get("latest_follow_up_date")
        adm_date = m.get("admission_date")
        is_admitted = adm_date is not None and str(adm_date).strip().lower() != "null" and str(adm_date).strip() != ""

        # Classify follow-up status
        if not f_date or str(f_date).strip() == "" or str(f_date).strip().lower() == "null":
            f_status = "No Follow-up Date"
        elif str(f_date)[:10] == today_str:
            f_status = "Due Today"
        elif str(f_date)[:10] < today_str and not is_admitted:
            f_status = "Overdue"
        else:
            f_status = "Upcoming"

        # Time to first call in minutes
        alloc_t = m.get("first_allocation_date")
        first_c_t = m.get("first_call_date")
        ttfc_mins = None
        if alloc_t and first_c_t and str(alloc_t).strip() != "" and str(first_c_t).strip() != "":
            try:
                dt_alloc = datetime.fromisoformat(str(alloc_t).replace("Z", ""))
                dt_call = datetime.fromisoformat(str(first_c_t).replace("Z", ""))
                ttfc_mins = round((dt_call - dt_alloc).total_seconds() / 60.0, 1)
            except Exception:
                pass

        m["followup_status"] = f_status
        m["total_call_attempts"] = int(m.get("total_call_attempts") or 0)
        m["time_to_first_call_mins"] = ttfc_mins
        m["is_admitted"] = is_admitted
        m["employee_id"] = extract_employee_id(m.get("owner_name"))
        leads_list.append(m)

    total_pages = (total_leads + page_size - 1) // page_size if page_size > 0 else 1

    return {
        "status": "success",
        "page": page,
        "page_size": page_size,
        "total_leads": total_leads,
        "total_pages": total_pages,
        "leads": leads_list,
    }


def generate_counsellor_report(
    db: Session,
    report_type: str = "counsellor_performance",
    export_format: str = "csv",
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    counsellor: Optional[str] = None,
) -> tuple[str, str]:
    """Generate CSV or XLSX report bytes for counsellor analytics."""
    if report_type in ("counsellor_performance", "counsellor_summary"):
        summary_data = get_counsellor_summary(db, academic_year=academic_year, campus=campus, counsellor=counsellor)
        c_list = summary_data.get("counsellors", [])
        
        headers = ["Counsellor Name", "Employee ID", "Leads Assigned", "0 Calls", "1 Call", "2 Calls", "3 Calls", "4+ Calls", "Total Calls", "Avg Calls/Lead", "Avg Time to First Call (hrs)", "Overdue Follow-ups", "Interested Leads", "Admissions", "Conversion Rate %"]
        rows_data = []
        for c in c_list:
            rows_data.append([
                c["counsellor"],
                c["employee_id"],
                c["leads_assigned"],
                c["calls_0"],
                c["calls_1"],
                c["calls_2"],
                c["calls_3"],
                c["calls_4_plus"],
                c["total_calls"],
                c["avg_calls_per_lead"],
                c["avg_time_to_first_call_hours"] if c["avg_time_to_first_call_hours"] is not None else "N/A",
                c["overdue_followups"],
                c["interested_leads"],
                c["admissions"],
                c["conversion_rate"],
            ])
    else:
        leads_data = get_lead_activity(db, academic_year=academic_year, campus=campus, counsellor=counsellor, page=1, page_size=5000)
        l_list = leads_data.get("leads", [])
        
        headers = ["Prospect ID", "Counsellor", "Program Code", "Program Name", "Course Cluster", "State", "Source", "Created On", "First Allocation", "First Call Date", "Last Call Date", "Total Attempts", "First Disposition", "Follow-up Date", "Follow-up Status", "Admission Status"]
        rows_data = []
        for l in l_list:
            rows_data.append([
                l.get("prospect_id"),
                l.get("owner_name"),
                l.get("raw_program_code"),
                l.get("program_name"),
                l.get("course_cluster"),
                l.get("state"),
                l.get("source"),
                l.get("created_on"),
                l.get("first_allocation_date"),
                l.get("first_call_date"),
                l.get("last_call_date"),
                l.get("total_call_attempts"),
                l.get("first_call_disposition"),
                l.get("latest_follow_up_date"),
                l.get("followup_status"),
                "Enrolled" if l.get("is_admitted") else "Pending",
            ])

    if export_format.lower() == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(headers)
        writer.writerows(rows_data)
        return out.getvalue(), "text/csv"
    else:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(headers)
        writer.writerows(rows_data)
        return out.getvalue(), "text/csv"


def get_lowest_avg_calls(db: Session, dataset_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """Calculate owners with the lowest average call attempts per lead."""
    where_clause, params = _build_lead_filter_where(dataset_id=dataset_id)
    sql = f"""
        SELECT 
            COALESCE(r.raw_data->>'OwnerIdName', 'Unassigned') as owner_name,
            COUNT(DISTINCT r.raw_data->>'ProspectID') as assigned_leads,
            SUM(CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_Total_Call_Attempt')) != 'null' THEN (r.raw_data->>'mx_Total_Call_Attempt')::numeric ELSE 0 END) as total_calls,
            AVG(CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_Total_Call_Attempt'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_Total_Call_Attempt')) != 'null' THEN (r.raw_data->>'mx_Total_Call_Attempt')::numeric ELSE 0 END) as avg_calls
        FROM staging.records r
        JOIN system.datasets sd ON r.dataset_id = sd.id
        WHERE {where_clause} AND NULLIF(TRIM(r.raw_data->>'OwnerIdName'), '') IS NOT NULL
        GROUP BY 1
        HAVING COUNT(DISTINCT r.raw_data->>'ProspectID') >= 5
        ORDER BY avg_calls ASC, assigned_leads DESC
        LIMIT :limit;
    """
    params["limit"] = limit
    rows = db.execute(text(sql), params).mappings().all()
    counsellors = []
    for r in rows:
        counsellors.append({
            "owner": r["owner_name"],
            "assigned_leads": int(r["assigned_leads"] or 0),
            "total_calls": int(r["total_calls"] or 0),
            "avg_calls_per_lead": round(float(r["avg_calls"] or 0.0), 2),
        })
    return {"counsellors": counsellors, "total_counsellors": len(counsellors)}
