"""
Geography and Gender Analytics Service

Provides server-side PostgreSQL aggregation for:
1. Admissions by Gender (Male, Female, Unspecified, etc.)
2. Admissions by Indian States (India choropleth map & state leaderboard)
3. International Admissions (Outside-India countries, strictly excluding India)
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.repository import resolve_raw_dataset
from app.normalization.state_resolver import CANONICAL_INDIAN_STATES, FOREIGN_LOCATIONS

logger = logging.getLogger(__name__)

# Standard ISO 3166-2:IN state codes for all 36 Indian States and Union Territories
STATE_CODES: Dict[str, str] = {
    "Andhra Pradesh": "AP",
    "Arunachal Pradesh": "AR",
    "Assam": "AS",
    "Bihar": "BR",
    "Chhattisgarh": "CG",
    "Goa": "GA",
    "Gujarat": "GJ",
    "Haryana": "HR",
    "Himachal Pradesh": "HP",
    "Jharkhand": "JH",
    "Karnataka": "KA",
    "Kerala": "KL",
    "Madhya Pradesh": "MP",
    "Maharashtra": "MH",
    "Manipur": "MN",
    "Meghalaya": "ML",
    "Mizoram": "MZ",
    "Nagaland": "NL",
    "Odisha": "OD",
    "Punjab": "PB",
    "Rajasthan": "RJ",
    "Sikkim": "SK",
    "Tamil Nadu": "TN",
    "Telangana": "TG",
    "Tripura": "TR",
    "Uttar Pradesh": "UP",
    "Uttarakhand": "UK",
    "West Bengal": "WB",
    "Andaman & Nicobar": "AN",
    "Chandigarh": "CH",
    "Dadra & Nagar Haveli and Daman & Diu": "DN",
    "Delhi": "DL",
    "Jammu & Kashmir": "JK",
    "Ladakh": "LA",
    "Lakshadweep": "LD",
    "Puducherry": "PY",
}

# Country mapping for foreign locations (ISO alpha-3 codes)
COUNTRY_MAPPING: Dict[str, Dict[str, str]] = {
    "nepal": {"code": "NPL", "name": "Nepal"},
    "kathmandu": {"code": "NPL", "name": "Nepal"},
    "pokhara": {"code": "NPL", "name": "Nepal"},
    "mahendranagar": {"code": "NPL", "name": "Nepal"},
    "uae": {"code": "ARE", "name": "United Arab Emirates"},
    "dubai": {"code": "ARE", "name": "United Arab Emirates"},
    "abu dhabi": {"code": "ARE", "name": "United Arab Emirates"},
    "bangladesh": {"code": "BGD", "name": "Bangladesh"},
    "dhaka": {"code": "BGD", "name": "Bangladesh"},
    "dhaka division": {"code": "BGD", "name": "Bangladesh"},
    "canada": {"code": "CAN", "name": "Canada"},
    "ontario": {"code": "CAN", "name": "Canada"},
    "toronto": {"code": "CAN", "name": "Canada"},
    "vancouver": {"code": "CAN", "name": "Canada"},
    "uk": {"code": "GBR", "name": "United Kingdom"},
    "united kingdom": {"code": "GBR", "name": "United Kingdom"},
    "london": {"code": "GBR", "name": "United Kingdom"},
    "usa": {"code": "USA", "name": "United States"},
    "united states": {"code": "USA", "name": "United States"},
    "us": {"code": "USA", "name": "United States"},
    "marondera": {"code": "ZWE", "name": "Zimbabwe"},
    "zimbabwe": {"code": "ZWE", "name": "Zimbabwe"},
    "australia": {"code": "AUS", "name": "Australia"},
    "sydney": {"code": "AUS", "name": "Australia"},
    "melbourne": {"code": "AUS", "name": "Australia"},
    "bhutan": {"code": "BTN", "name": "Bhutan"},
    "thimphu": {"code": "BTN", "name": "Bhutan"},
    "sri lanka": {"code": "LKA", "name": "Sri Lanka"},
    "colombo": {"code": "LKA", "name": "Sri Lanka"},
    "kenya": {"code": "KEN", "name": "Kenya"},
    "nairobi": {"code": "KEN", "name": "Kenya"},
    "nigeria": {"code": "NGA", "name": "Nigeria"},
    "lagos": {"code": "NGA", "name": "Nigeria"},
    "kuwait": {"code": "KWT", "name": "Kuwait"},
    "qatar": {"code": "QAT", "name": "Qatar"},
    "oman": {"code": "OMN", "name": "Oman"},
    "muscat": {"code": "OMN", "name": "Oman"},
    "saudi arabia": {"code": "SAU", "name": "Saudi Arabia"},
    "afghanistan": {"code": "AFG", "name": "Afghanistan"},
    "singapore": {"code": "SGP", "name": "Singapore"},
    "malaysia": {"code": "MYS", "name": "Malaysia"},
    "japan": {"code": "JPN", "name": "Japan"},
    "germany": {"code": "DEU", "name": "Germany"},
    "france": {"code": "FRA", "name": "France"},
    "china": {"code": "CHN", "name": "China"},
    "thailand": {"code": "THA", "name": "Thailand"},
    "indonesia": {"code": "IDN", "name": "Indonesia"},
    "maldives": {"code": "MDV", "name": "Maldives"},
    "bahrain": {"code": "BHR", "name": "Bahrain"},
}

MONTH_NAMES: Dict[str, str] = {
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def get_admissions_by_gender(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    month: Optional[str] = None,
    lead_type: Optional[str] = None,
    program: Optional[str] = None,
    source: Optional[str] = None,
    state: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate admissions breakdown by canonical gender, month by month.
    
    Admissions = COUNT(DISTINCT ProspectID)
    WHERE mx_AdmissionDate is valid and not null
      AND dataset is active RAW dataset for selected academic_year/campus.
    
    Supports dynamic from_date and to_date range filtering.
    Returns chronological month-by-month grouped bars and dynamic gender categories.
    """
    from app.analytics.period_helper import get_active_or_max_academic_year
    year = academic_year or get_active_or_max_academic_year(db)
    ds_id, cy_yr, py_yr = resolve_raw_dataset(db, target_year=year)
    if not ds_id:
        return {
            "status": "success",
            "academic_year": year,
            "campus": campus or "All",
            "total_admissions": 0,
            "gender_categories": [],
            "months": [],
            "genders": [],
            "from_date": from_date,
            "to_date": to_date,
        }

    conds = ["academic_year = :academic_year"]
    params: Dict[str, Any] = {"academic_year": year}

    if campus and campus.lower() != "all":
        conds.append("LOWER(campus_name) = LOWER(:campus)")
        params["campus"] = campus

    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    if has_date_filter:
        from_m = from_date.strip()[:7]
        to_m = to_date.strip()[:7]
        conds.append("admission_month >= :from_m AND admission_month <= :to_m")
        params["from_m"] = from_m
        params["to_m"] = to_m
    elif month and month.lower() != "all":
        conds.append("admission_month LIKE :month")
        params["month"] = f"%{month}%"

    where_clause = " AND ".join(conds)

    sql = f"""
        SELECT 
            admission_month AS month_key,
            gender,
            SUM(admissions) AS admissions
        FROM analytics.gender_monthly_agg
        WHERE {where_clause}
        GROUP BY 1, 2
        ORDER BY 1, admissions DESC;
    """
    try:
        rows = db.execute(text(sql), params).fetchall()

        # Safe Fallback: if no aggregate rows found, check dataset status
        if not rows:
            ds_status = db.execute(
                text("""
                    SELECT analytics_status FROM system.datasets
                    WHERE is_analytics_enabled = TRUE
                      AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                      AND academic_year = :yr
                    LIMIT 1
                """),
                {"yr": year},
            ).scalar()
            return {
                "status": "aggregating" if ds_status == "AGGREGATING" else "success",
                "academic_year": year,
                "campus": campus or "All",
                "total_admissions": 0,
                "gender_categories": ["Male", "Female"],
                "months": [],
                "genders": [],
                "from_date": from_date,
                "to_date": to_date,
            }

        # Track discovered canonical genders dynamically
        genders_found = set()
        gender_totals: Dict[str, int] = {}
        months_dict: Dict[str, Dict[str, Any]] = {}

        for r in rows:
            m_key = str(r[0] or "")
            if not m_key:
                continue
            g_name = str(r[1])
            adm_count = int(r[2])

            genders_found.add(g_name)
            gender_totals[g_name] = gender_totals.get(g_name, 0) + adm_count

            if m_key not in months_dict:
                m_parts = m_key.split("-")
                m_num = m_parts[1] if len(m_parts) > 1 else "01"
                y_num = m_parts[0] if len(m_parts) > 0 else str(year)
                short_name = MONTH_NAMES.get(m_num, m_num)
                months_dict[m_key] = {
                    "month_key": m_key,
                    "month": short_name,
                    "month_display": f"{short_name} {y_num}",
                    "total": 0,
                }

            months_dict[m_key][g_name] = adm_count
            months_dict[m_key]["total"] += adm_count

        # Prefer canonical order: Male, Female, then others
        ordered_genders = []
        if "Male" in genders_found:
            ordered_genders.append("Male")
        if "Female" in genders_found:
            ordered_genders.append("Female")
        for g in sorted(genders_found):
            if g not in ordered_genders:
                ordered_genders.append(g)

        # Sort months chronologically
        sorted_months = sorted(months_dict.values(), key=lambda x: x["month_key"])

        # Ensure all gender keys exist with 0 default in each month item
        for m in sorted_months:
            for g in ordered_genders:
                if g not in m:
                    m[g] = 0

        total_admissions = sum(gender_totals.values())

        # Build summary list for backwards compatibility
        genders_summary = []
        for g in ordered_genders:
            cnt = gender_totals.get(g, 0)
            share = round((cnt / total_admissions * 100), 2) if total_admissions > 0 else 0.0
            genders_summary.append({
                "gender": g,
                "admissions": cnt,
                "share_pct": share,
            })

        return {
            "status": "success",
            "academic_year": year,
            "campus": campus or "All",
            "total_admissions": total_admissions,
            "gender_categories": ordered_genders,
            "months": sorted_months,
            "genders": genders_summary,
            "from_date": from_date,
            "to_date": to_date,
        }
    except Exception as e:
        logger.warning("Error fetching admissions by gender for year=%s: %s", year, e)
        return {
            "status": "success",
            "academic_year": year,
            "campus": campus or "All",
            "total_admissions": 0,
            "gender_categories": [],
            "months": [],
            "genders": [],
            "from_date": from_date,
            "to_date": to_date,
        }


def get_admissions_by_india_state(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    month: Optional[str] = None,
    lead_type: Optional[str] = None,
    program: Optional[str] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate admissions by Indian state from analytics.dashboard_agg with CY vs PY comparison.
    
    Includes all Indian states and union territories.
    Strictly excludes 'INTERNATIONAL' and 'UNMAPPED_STATE' from state list.
    Computes CY admissions, PY admissions, variance, variance %, and performance direction.
    Supports dynamic from_date and to_date range filtering.
    """
    from app.analytics.aggregate_service import get_py_date

    from app.analytics.period_helper import get_active_or_max_academic_year
    year = academic_year or get_active_or_max_academic_year(db)
    ds_id, cy_yr, py_yr = resolve_raw_dataset(db, target_year=year)
    cy_year = cy_yr or year
    comp_year = py_yr or (cy_year - 1)

    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    from_m = from_date.strip()[:7] if has_date_filter else None
    to_m = to_date.strip()[:7] if has_date_filter else None
    py_from_date = None
    py_to_date = None
    py_from_m = None
    py_to_m = None

    if has_date_filter:
        year_diff = (cy_year - comp_year) if (cy_year and comp_year) else 1
        py_from_date = get_py_date(from_date.strip(), year_diff)
        py_to_date = get_py_date(to_date.strip(), year_diff)
        py_from_m = py_from_date[:7]
        py_to_m = py_to_date[:7]

    try:
        # Base filter builder for dashboard_agg
        def _build_agg_filters(filter_params: Dict[str, Any]) -> str:
            f_conds = []
            if campus and campus.lower() != "all":
                f_conds.append("LOWER(COALESCE(campus_name, '')) = LOWER(:campus)")
                filter_params["campus"] = campus
            if month and month.lower() != "all" and not has_date_filter:
                f_conds.append("LOWER(COALESCE(admission_month, '')) = LOWER(:month)")
                filter_params["month"] = month
            if lead_type and lead_type.lower() != "all":
                f_conds.append("LOWER(COALESCE(lead_type, '')) = LOWER(:lead_type)")
                filter_params["lead_type"] = lead_type
            if program and program.lower() != "all":
                f_conds.append("LOWER(COALESCE(program_name, '')) = LOWER(:program)")
                filter_params["program"] = program
            if source and source.lower() != "all":
                f_conds.append("LOWER(COALESCE(source, '')) = LOWER(:source)")
                filter_params["source"] = source
            return (" AND " + " AND ".join(f_conds)) if f_conds else ""

        # 1. Consolidated CY and PY state aggregation query
        state_params: Dict[str, Any] = {"cy_year": cy_year, "comp_year": comp_year}
        state_filter_str = _build_agg_filters(state_params)
        if has_date_filter:
            state_params["from_m"] = from_m
            state_params["to_m"] = to_m
            state_params["py_from_m"] = py_from_m
            state_params["py_to_m"] = py_to_m
            state_sql = f"""
                SELECT 
                    academic_year,
                    state,
                    SUM(CASE 
                        WHEN academic_year = :cy_year AND admission_month >= :from_m AND admission_month <= :to_m THEN admission_cy
                        WHEN academic_year = :comp_year AND admission_month >= :py_from_m AND admission_month <= :py_to_m THEN admission_cy
                        ELSE 0 
                    END) AS admissions,
                    SUM(CASE 
                        WHEN academic_year = :cy_year AND created_month >= :from_m AND created_month <= :to_m THEN leads_cy
                        WHEN academic_year = :comp_year AND created_month >= :py_from_m AND created_month <= :py_to_m THEN leads_cy
                        ELSE 0 
                    END) AS leads
                FROM analytics.dashboard_agg
                WHERE academic_year IN (:cy_year, :comp_year)
                  AND state IS NOT NULL
                  AND state NOT IN ('INTERNATIONAL', 'UNMAPPED_STATE', '')
                  {state_filter_str}
                GROUP BY academic_year, state
            """
        else:
            state_sql = f"""
                SELECT 
                    academic_year,
                    state,
                    SUM(admission_cy) AS admissions,
                    SUM(leads_cy) AS leads
                FROM analytics.dashboard_agg
                WHERE academic_year IN (:cy_year, :comp_year)
                  AND state IS NOT NULL
                  AND state NOT IN ('INTERNATIONAL', 'UNMAPPED_STATE', '')
                  {state_filter_str}
                GROUP BY academic_year, state
            """
        rows = db.execute(text(state_sql), state_params).fetchall()
        cy_state_map = {}
        py_state_map = {}
        for r in rows:
            ay, st, adm, ld = int(r[0]), str(r[1]), int(r[2] or 0), int(r[3] or 0)
            if ay == cy_year:
                cy_state_map[st] = {"admissions": adm, "leads": ld}
            elif ay == comp_year:
                py_state_map[st] = {"admissions": adm, "leads": ld}

        has_py_data = len(py_state_map) > 0 and sum(v["admissions"] for v in py_state_map.values()) > 0

        # 2. Query unmapped and international metadata for reconciliation
        meta_params: Dict[str, Any] = {"cy_year": cy_year}
        meta_filter_str = _build_agg_filters(meta_params)
        if has_date_filter:
            meta_params["from_m"] = from_m
            meta_params["to_m"] = to_m
            meta_sql = f"""
                SELECT 
                    CASE 
                        WHEN state = 'INTERNATIONAL' THEN 'INTERNATIONAL'
                        WHEN state = 'UNMAPPED_STATE' OR state IS NULL OR state = '' THEN 'UNMAPPED'
                        ELSE 'MAPPED'
                    END AS loc_type,
                    SUM(CASE WHEN admission_month >= :from_m AND admission_month <= :to_m THEN admission_cy ELSE 0 END) AS admissions
                FROM analytics.dashboard_agg
                WHERE academic_year = :cy_year
                  {meta_filter_str}
                GROUP BY 1
            """
        else:
            meta_sql = f"""
                SELECT 
                    CASE 
                        WHEN state = 'INTERNATIONAL' THEN 'INTERNATIONAL'
                        WHEN state = 'UNMAPPED_STATE' OR state IS NULL OR state = '' THEN 'UNMAPPED'
                        ELSE 'MAPPED'
                    END AS loc_type,
                    SUM(admission_cy) AS admissions
                FROM analytics.dashboard_agg
                WHERE academic_year = :cy_year
                  {meta_filter_str}
                GROUP BY 1
            """
        meta_rows = db.execute(text(meta_sql), meta_params).fetchall()
        meta_map = {r[0]: int(r[1] or 0) for r in meta_rows}
        unmapped_admissions = meta_map.get("UNMAPPED", 0)
        international_admissions = meta_map.get("INTERNATIONAL", 0)

        # 3. Combine all states
        all_state_names = set(cy_state_map.keys()) | set(py_state_map.keys())
        total_india_admissions = sum(item["admissions"] for item in cy_state_map.values())
        total_india_leads = sum(item["leads"] for item in cy_state_map.values())

        states_list = []
        for st_name in all_state_names:
            cy_info = cy_state_map.get(st_name, {"admissions": 0, "leads": 0})
            cy_adm = cy_info["admissions"]
            cy_ld = cy_info["leads"]
            st_code = STATE_CODES.get(st_name, "")
            share = round((cy_adm / total_india_admissions * 100), 2) if total_india_admissions > 0 else 0.0

            if has_py_data:
                py_info = py_state_map.get(st_name, {"admissions": 0, "leads": 0})
                py_adm = py_info["admissions"]
                py_ld = py_info["leads"]
                diff = cy_adm - py_adm

                if py_adm > 0:
                    diff_pct = round((diff / py_adm) * 100, 2)
                elif cy_adm > 0:
                    diff_pct = 100.0
                else:
                    diff_pct = 0.0

                if diff > 0:
                    direction = "increase"
                elif diff < 0:
                    direction = "decline"
                else:
                    direction = "no_change"
            else:
                py_adm = None
                py_ld = None
                diff = None
                diff_pct = None
                direction = "no_comparison"

            states_list.append({
                "state_code": st_code,
                "state_name": st_name,
                "admissions": cy_adm,
                "leads": cy_ld,
                "cy_admissions": cy_adm,
                "cy_leads": cy_ld,
                "py_admissions": py_adm,
                "py_leads": py_ld,
                "variance": diff,
                "variance_pct": diff_pct,
                "direction": direction,
                "share_pct": share,
            })

        # Sort by CY admissions descending, then CY leads descending
        states_list.sort(key=lambda x: (x["cy_admissions"], x["cy_leads"]), reverse=True)

        return {
            "status": "success",
            "academic_year": cy_year,
            "comparison_year": comp_year if has_py_data else None,
            "has_py_data": has_py_data,
            "campus": campus or "All",
            "from_date": from_date,
            "to_date": to_date,
            "py_from_date": py_from_date,
            "py_to_date": py_to_date,
            "total_india_admissions": total_india_admissions,
            "total_india_leads": total_india_leads,
            "unmapped_admissions": unmapped_admissions,
            "international_admissions": international_admissions,
            "states": states_list,
            "top_states": states_list[:5],
        }
    except Exception as exc:
        logger.warning("Error in get_admissions_by_india_state for year=%s: %s", cy_year, exc)
        return {
            "status": "success",
            "academic_year": cy_year,
            "comparison_year": comp_year,
            "has_py_data": False,
            "campus": campus or "All",
            "from_date": from_date,
            "to_date": to_date,
            "py_from_date": py_from_date,
            "py_to_date": py_to_date,
            "total_india_admissions": 0,
            "total_india_leads": 0,
            "unmapped_admissions": 0,
            "international_admissions": 0,
            "states": [],
            "top_states": [],
        }


def get_international_admissions(
    db: Session,
    academic_year: Optional[int] = None,
    campus: Optional[str] = None,
    month: Optional[str] = None,
    lead_type: Optional[str] = None,
    program: Optional[str] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate admissions and leads from outside India.
    
    STRICT RULE: India is completely excluded.
    Returns country-level breakdown ranked by admissions, then leads descending.
    Supports dynamic from_date and to_date range filtering.
    """
    from app.analytics.period_helper import get_active_or_max_academic_year
    year = academic_year or get_active_or_max_academic_year(db)
    ds_id, cy_yr, py_yr = resolve_raw_dataset(db, target_year=year)
    if not ds_id:
        return {
            "status": "success",
            "academic_year": year,
            "campus": campus or "All",
            "total_international_admissions": 0,
            "total_international_leads": 0,
            "countries": [],
            "top_countries": [],
            "from_date": from_date,
            "to_date": to_date,
            "limitation_note": "No active dataset found for selected year.",
        }

    dataset_id = ds_id

    foreign_terms = list(COUNTRY_MAPPING.keys())
    foreign_keys_sql = ", ".join(f"'{k}'" for k in foreign_terms)

    has_date_filter = bool(from_date and to_date and from_date.strip() and to_date.strip())
    where_clauses = ["d.academic_year = :year"]
    params: Dict[str, Any] = {"year": year}

    if campus and campus.strip() and campus.strip().lower() not in ("all", "all campuses"):
        where_clauses.append("LOWER(d.campus_name) = :campus")
        params["campus"] = campus.strip().lower()

    if month and month.strip():
        where_clauses.append("d.admission_month = :month")
        params["month"] = month.strip()

    if has_date_filter:
        where_clauses.append("d.created_month >= :from_m AND d.created_month <= :to_m")
        params["from_m"] = from_date.strip()[:7]
        params["to_m"] = to_date.strip()[:7]

    where_clauses.append(f"LOWER(TRIM(COALESCE(d.state, ''))) IN ({foreign_keys_sql}, 'international')")

    sql = f"""
        SELECT 
            LOWER(TRIM(COALESCE(d.state, ''))) AS raw_state,
            SUM(d.leads_cy) AS leads,
            SUM(d.admission_cy) AS admissions
        FROM analytics.dashboard_agg d
        WHERE {" AND ".join(where_clauses)}
        GROUP BY LOWER(TRIM(COALESCE(d.state, '')))
    """
    rows = db.execute(text(sql), params).fetchall()

    country_stats: Dict[str, Dict[str, Any]] = {}
    total_intl_admissions = 0
    total_intl_leads = 0

    for r in rows:
        raw_st = str(r[0] or "")
        leads_cnt = int(r[1] or 0)
        adm_cnt = int(r[2] or 0)

        matched_country = None
        if raw_st in COUNTRY_MAPPING:
            matched_country = COUNTRY_MAPPING[raw_st]
        elif raw_st == "international":
            matched_country = {"code": "OTH", "name": "Other International"}

        if not matched_country:
            continue

        c_code = matched_country["code"]
        c_name = matched_country["name"]

        if c_code not in country_stats:
            country_stats[c_code] = {
                "country_code": c_code,
                "country_name": c_name,
                "admissions": 0,
                "leads": 0,
            }

        country_stats[c_code]["leads"] += leads_cnt
        country_stats[c_code]["admissions"] += adm_cnt
        total_intl_leads += leads_cnt
        total_intl_admissions += adm_cnt

    countries_list = []
    for c_code, data in country_stats.items():
        adm_cnt = data["admissions"]
        lead_cnt = data["leads"]
        share = round((adm_cnt / total_intl_admissions * 100), 2) if total_intl_admissions > 0 else (
            round((lead_cnt / total_intl_leads * 100), 2) if total_intl_leads > 0 else 0.0
        )
        countries_list.append({
            "country_code": c_code,
            "country_name": data["country_name"],
            "admissions": adm_cnt,
            "leads": lead_cnt,
            "share_pct": share,
        })

    # Sort countries by admissions descending, then leads descending
    countries_list.sort(key=lambda x: (x["admissions"], x["leads"]), reverse=True)
    top_countries = countries_list[:10]

    return {
        "status": "success",
        "academic_year": year,
        "campus": campus or "All",
        "total_international_admissions": total_intl_admissions,
        "total_international_leads": total_intl_leads,
        "countries": countries_list,
        "top_countries": top_countries,
        "limitation_note": (
            "International student metrics are derived dynamically from foreign state and city registration records. "
            "Domestic Indian admissions and leads are strictly excluded."
        ),
    }
