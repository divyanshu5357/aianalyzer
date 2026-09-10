"""
Analytical service for State-Wise Analysis with strict Lazy Hierarchical Loading.
Provides aggregated metrics across 3 hierarchy levels:
  Level 1: State (e.g. PUNJAB, HARYANA, UTTAR PRADESH, HIMACHAL PRADESH)
  Level 2: Source Category (e.g. IN HOUSE, OUT SOURCED, OTHERS)
  Level 3: Sub-Source (e.g. Google, CollegeDekho, Shiksha, Website, Direct)
All aggregations are computed 100% on PostgreSQL (GROUP BY, SUM). Zero raw CRM records are loaded.
"""

from typing import Dict, Any, List, Optional, Set
import os
import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.analytics.aggregate_service import get_py_date
from app.config.settings import settings

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

CANONICAL_STATE_GROUPS = [
    "PUNJAB",
    "HARYANA",
    "UTTAR PRADESH",
    "HIMACHAL PRADESH",
    "BIHAR",
    "UTTARAKHAND",
    "JAMMU AND KASHMIR",
    "CHANDIGARH",
    "INTERNATIONAL",
    "JHARKHAND",
    "DELHI",
    "RAJASTHAN",
    "WEST BENGAL",
    "MADHYA PRADESH",
    "ODISHA",
    "NORTH EAST",
    "CHHATTISGARH",
    "MAHARASHTRA",
    "ANDHRA PRADESH",
    "KERALA",
    "TAMIL NADU",
    "GUJARAT",
    "TELANGANA",
    "A&N / DNH / DD / GOA / LAK",
    "KARNATAKA",
    "NO STATE MENTIONED",
]

_STATE_GROUP_CACHE: Optional[Dict[str, Any]] = None
_GEMINI_LOCATION_CACHE: Dict[str, str] = {}


def _resolve_location_with_gemini(raw_loc: str) -> Optional[str]:
    """Use Gemini to map unmapped location or city strings to one of the 26 State Groups."""
    if not raw_loc or not raw_loc.strip():
        return "NO STATE MENTIONED"

    clean_loc = raw_loc.strip()
    loc_key = clean_loc.lower()
    if loc_key in _GEMINI_LOCATION_CACHE:
        return _GEMINI_LOCATION_CACHE[loc_key]

    if not getattr(settings, "gemini_enabled", False) or not getattr(settings, "gemini_api_key", None):
        return None

    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        groups_str = ", ".join(CANONICAL_STATE_GROUPS)
        prompt = (
            f"You are a geographic data classifier for an admissions system in India.\n"
            f"Classify the following city, state, country, or location into EXACTLY ONE of the 26 canonical state groups:\n"
            f"{groups_str}\n"
            f"Rules:\n"
            f"- Any foreign country or international city (e.g. Dubai, Dhaka, Lagos, Kathmandu, Abu Dhabi) MUST be mapped to 'INTERNATIONAL'.\n"
            f"- Any city in Assam, Meghalaya, Sikkim, Arunachal Pradesh, Nagaland, Mizoram, Manipur, or Tripura MUST be mapped to 'NORTH EAST'.\n"
            f"- Goa, Ladakh, Lakshadweep, Puducherry, A&N, DNH, DD MUST be mapped to 'A&N / DNH / DD / GOA / LAK'.\n"
            f"- Any invalid string, noise, person name, or phone/email MUST be mapped to 'NO STATE MENTIONED'.\n"
            f"- Any other Indian city MUST be mapped to its respective Indian state group (e.g. Bangalore -> KARNATAKA, Pune -> MAHARASHTRA, Lucknow -> UTTAR PRADESH).\n\n"
            f"Location: '{clean_loc}'\n"
            f"Respond with ONLY the exact group name in uppercase, nothing else."
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        text_resp = (response.text or "").strip().upper()
        for grp in CANONICAL_STATE_GROUPS:
            if grp in text_resp:
                _GEMINI_LOCATION_CACHE[loc_key] = grp
                logger.info("Gemini mapped unmapped location '%s' -> '%s'", clean_loc, grp)
                return grp
    except Exception as e:
        logger.debug("Gemini location classification notice for '%s': %s", clean_loc, e)

    return None


def _get_state_group_master_lookup(db: Session) -> Dict[str, Any]:
    """
    Builds the master State Group dimension lookup:
    - alias_to_group: raw alias/city/state (lowercase) -> canonical State Group (uppercase)
    - group_to_constituents: canonical State Group -> set of lowercase raw constituent strings
    - group_meta: state codes, zones
    """
    global _STATE_GROUP_CACHE
    if _STATE_GROUP_CACHE is not None:
        return _STATE_GROUP_CACHE

    alias_to_group: Dict[str, str] = {}
    group_to_constituents: Dict[str, Set[str]] = {g: set() for g in CANONICAL_STATE_GROUPS}
    group_meta: Dict[str, Dict[str, Any]] = {}

    # 1. Base Indian States
    base_states = {
        "punjab": "PUNJAB",
        "pb/chd": "PUNJAB",
        "haryana": "HARYANA",
        "uttar pradesh": "UTTAR PRADESH",
        "up": "UTTAR PRADESH",
        "himachal pradesh": "HIMACHAL PRADESH",
        "bihar": "BIHAR",
        "uttarakhand": "UTTARAKHAND",
        "utrakhand": "UTTARAKHAND",
        "uttarchal": "UTTARAKHAND",
        "jammu and kashmir": "JAMMU AND KASHMIR",
        "jammu & kashmir": "JAMMU AND KASHMIR",
        "chandigarh": "CHANDIGARH",
        "jharkhand": "JHARKHAND",
        "jahrkhand": "JHARKHAND",
        "delhi": "DELHI",
        "delhi ncr": "DELHI",
        "new delhi": "DELHI",
        "rajasthan": "RAJASTHAN",
        "rajsthan": "RAJASTHAN",
        "west bengal": "WEST BENGAL",
        "w bengal": "WEST BENGAL",
        "west begal": "WEST BENGAL",
        "madhya pradesh": "MADHYA PRADESH",
        "madhy pradesh": "MADHYA PRADESH",
        "madhya predesh": "MADHYA PRADESH",
        "odisha": "ODISHA",
        "orissa": "ODISHA",
        "orrissa": "ODISHA",
        "chhattisgarh": "CHHATTISGARH",
        "chattisgarh": "CHHATTISGARH",
        "maharashtra": "MAHARASHTRA",
        "maharastra": "MAHARASHTRA",
        "mh": "MAHARASHTRA",
        "mumbai": "MAHARASHTRA",
        "andhra pradesh": "ANDHRA PRADESH",
        "ap + telengana": "ANDHRA PRADESH",
        "godawari": "ANDHRA PRADESH",
        "kerala": "KERALA",
        "tamil nadu": "TAMIL NADU",
        "gujarat": "GUJARAT",
        "gujrat": "GUJARAT",
        "gj": "GUJARAT",
        "patan": "GUJARAT",
        "telangana": "TELANGANA",
        "karnataka": "KARNATAKA",
    }
    for k, v in base_states.items():
        alias_to_group[k] = v
        group_to_constituents[v].add(k)

    # 2. North East states
    ne_states = [
        "assam", "tripura", "tripur", "manipur", "meghalaya",
        "sikkim", "arunachal pradesh", "nagaland", "mizoram", "north east"
    ]
    for st in ne_states:
        alias_to_group[st] = "NORTH EAST"
        group_to_constituents["NORTH EAST"].add(st)

    # 3. UTs & Goa
    ut_states = [
        "goa", "gao", "ladakh", "puducherry", "pondicherry", "lakshadweep",
        "andaman and nicobar", "andaman and nicobar islands", "dadra and nagar hav",
        "dadra and nagar haveli", "daman & diu", "daman and diu",
        "a&n / dnh / dd / goa / lak", "a&n / dnh / dd / goa / lak "
    ]
    for st in ut_states:
        alias_to_group[st] = "A&N / DNH / DD / GOA / LAK"
        group_to_constituents["A&N / DNH / DD / GOA / LAK"].add(st)

    # 4. International
    alias_to_group["international"] = "INTERNATIONAL"
    group_to_constituents["INTERNATIONAL"].add("international")

    # 5. No State Mentioned
    no_state_aliases = [
        "unmapped_state", "no state mentioned", "not updated",
        "state not given", "state not available", "", "none", "nan", "unknown"
    ]
    for n in no_state_aliases:
        alias_to_group[n] = "NO STATE MENTIONED"
        group_to_constituents["NO STATE MENTIONED"].add(n)

    # 6. Load Dimension Tables 2026(State).csv (master CSV)
    csv_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "masterdata", "Dimension Tables 2026(State).csv"),
        os.path.join(os.getcwd(), "backend", "masterdata", "Dimension Tables 2026(State).csv"),
        os.path.join(os.getcwd(), "masterdata", "Dimension Tables 2026(State).csv"),
    ]
    for p in csv_paths:
        if os.path.exists(p):
            try:
                df = pd.read_csv(p, encoding="latin1")
                for _, row in df.iterrows():
                    s_name = str(row.get("State Name") or "").strip()
                    s_grp = str(row.get("State Group") or "").strip()
                    s_code = str(row.get("State Code") or "").strip()
                    zone = str(row.get("Zone") or "").strip()

                    if not s_name or s_name.lower() == "nan":
                        continue

                    grp_u = s_grp.upper()
                    if grp_u.startswith("A&N"):
                        canonical = "A&N / DNH / DD / GOA / LAK"
                    elif grp_u == "NORTH EAST":
                        canonical = "NORTH EAST"
                    elif grp_u == "INTERNATIONAL":
                        canonical = "INTERNATIONAL"
                    elif grp_u in ("NO STATE MENTIONED", "UNMAPPED_STATE", "NOT UPDATED", "STATE NOT GIVEN"):
                        canonical = "NO STATE MENTIONED"
                    elif grp_u in CANONICAL_STATE_GROUPS:
                        canonical = grp_u
                    else:
                        canonical = "NO STATE MENTIONED"

                    alias_to_group[s_name.lower()] = canonical
                    group_to_constituents[canonical].add(s_name.lower())

                    if canonical not in group_meta:
                        group_meta[canonical] = {"state_code": s_code, "zone": zone}
                logger.info("Loaded %d rows from master state dimension CSV: %s", len(df), p)
                break
            except Exception as e:
                logger.warning("Could not load state dimension CSV %s: %s", p, e)

    # 7. Query organization.state_master table if populated
    try:
        rows = db.execute(
            text("SELECT state_name, state_group, state_code, zone FROM organization.state_master")
        ).fetchall()
        for r in rows:
            s_name = (r[0] or "").strip()
            s_grp = (r[1] or "").strip()
            s_code = (r[2] or "").strip()
            zone = (r[3] or "").strip()
            if not s_name:
                continue

            grp_u = s_grp.upper()
            if grp_u.startswith("A&N"):
                canonical = "A&N / DNH / DD / GOA / LAK"
            elif grp_u == "NORTH EAST":
                canonical = "NORTH EAST"
            elif grp_u == "INTERNATIONAL":
                canonical = "INTERNATIONAL"
            elif grp_u in CANONICAL_STATE_GROUPS:
                canonical = grp_u
            else:
                canonical = alias_to_group.get(s_name.lower(), "NO STATE MENTIONED")

            alias_to_group[s_name.lower()] = canonical
            group_to_constituents[canonical].add(s_name.lower())
            if canonical not in group_meta:
                group_meta[canonical] = {"state_code": s_code, "zone": zone}
    except Exception:
        pass

    # Ensure all North East states are strictly assigned to NORTH EAST (override any CSV miscategorization like row 10 Nagaland)
    for st in ne_states:
        old_grp = alias_to_group.get(st)
        if old_grp and old_grp != "NORTH EAST":
            group_to_constituents.get(old_grp, set()).discard(st)
        alias_to_group[st] = "NORTH EAST"
        group_to_constituents["NORTH EAST"].add(st)

    # Ensure self-mapping for all canonical groups
    for g in CANONICAL_STATE_GROUPS:
        alias_to_group[g.lower()] = g
        group_to_constituents[g].add(g.lower())

    _STATE_GROUP_CACHE = {
        "alias_to_group": alias_to_group,
        "group_to_constituents": group_to_constituents,
        "group_meta": group_meta,
    }
    return _STATE_GROUP_CACHE


def _map_to_state_group(raw_name: Optional[str], lookup: Dict[str, Any]) -> str:
    """Maps any raw state / city / country string to one of the 26 canonical State Groups."""
    if not raw_name or not str(raw_name).strip():
        return "NO STATE MENTIONED"
    clean = str(raw_name).strip().lower()
    if clean in lookup["alias_to_group"]:
        return lookup["alias_to_group"][clean]

    # Try Gemini fallback for unmapped location
    gemini_res = _resolve_location_with_gemini(raw_name)
    if gemini_res:
        lookup["alias_to_group"][clean] = gemini_res
        lookup["group_to_constituents"].setdefault(gemini_res, set()).add(clean)
        return gemini_res

    # Default fallback
    lookup["alias_to_group"][clean] = "NO STATE MENTIONED"
    lookup["group_to_constituents"]["NO STATE MENTIONED"].add(clean)
    return "NO STATE MENTIONED"


def _get_constituent_states(state_name: str, lookup: Dict[str, Any]) -> List[str]:
    """Returns all lowercase raw state strings corresponding to a State Group or individual state."""
    clean_u = (state_name or "").strip().upper()
    constituents = lookup["group_to_constituents"].get(clean_u)
    if constituents:
        return list(constituents)
    clean_l = (state_name or "").strip().lower()
    return [clean_l] if clean_l else ["unmapped_state"]


def _get_state_master_lookup(db: Session) -> Dict[str, Dict[str, Any]]:
    lookup = _get_state_group_master_lookup(db)
    return {
        k: {"state_name": v, "state_code": lookup["group_meta"].get(v, {}).get("state_code")}
        for k, v in lookup["alias_to_group"].items()
    }


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

    lookup = _get_state_group_master_lookup(db)

    # 1. Group result_rows by state_group
    group_metrics: Dict[str, Dict[str, Any]] = {}
    group_constituents: Dict[str, List[str]] = {}

    for r in result_rows:
        raw_st = str(r[0]).strip()
        grp_name = _map_to_state_group(raw_st, lookup)

        gm = group_metrics.setdefault(
            grp_name,
            {
                "py_leads": 0 if py_available else None,
                "cy_leads": 0,
                "py_cucet": 0 if py_available else None,
                "cy_cucet": 0,
                "py_adm": 0 if py_available else None,
                "cy_adm": 0,
            },
        )
        py_l = int(r[1] or 0) if py_available else None
        cy_l = int(r[2] or 0)
        py_c = int(r[3] or 0) if py_available else None
        cy_c = int(r[4] or 0)
        py_a = int(r[5] or 0) if py_available else None
        cy_a = int(r[6] or 0)

        if py_available and py_l is not None:
            gm["py_leads"] = (gm["py_leads"] or 0) + py_l
            gm["py_cucet"] = (gm["py_cucet"] or 0) + (py_c or 0)
            gm["py_adm"] = (gm["py_adm"] or 0) + (py_a or 0)

        gm["cy_leads"] += cy_l
        gm["cy_cucet"] += cy_c
        gm["cy_adm"] += cy_a

        group_constituents.setdefault(grp_name, []).append(raw_st)

    # 2. Group monthly trends by state_group
    group_trends: Dict[str, Dict[str, int]] = {}
    distinct_months = set()
    tot_monthly: Dict[str, int] = {}
    for tr in trend_rows:
        raw_st = str(tr[0]).strip()
        m_key = str(tr[1])
        cnt = int(tr[2] or 0)
        grp_name = _map_to_state_group(raw_st, lookup)
        gt = group_trends.setdefault(grp_name, {})
        gt[m_key] = gt.get(m_key, 0) + cnt
        tot_monthly[m_key] = tot_monthly.get(m_key, 0) + cnt
        distinct_months.add(m_key)

    sorted_months = sorted(list(distinct_months))

    # 3. Calculate Scope Totals
    tot_py_leads = (
        sum(gm["py_leads"] for gm in group_metrics.values() if gm["py_leads"] is not None)
        if py_available
        else None
    )
    tot_cy_leads = sum(gm["cy_leads"] for gm in group_metrics.values())
    tot_py_cucet = (
        sum(gm["py_cucet"] for gm in group_metrics.values() if gm["py_cucet"] is not None)
        if py_available
        else None
    )
    tot_cy_cucet = sum(gm["cy_cucet"] for gm in group_metrics.values())
    tot_py_adm = (
        sum(gm["py_adm"] for gm in group_metrics.values() if gm["py_adm"] is not None)
        if py_available
        else None
    )
    tot_cy_adm = sum(gm["cy_adm"] for gm in group_metrics.values())

    # 4. Build processed_rows for canonical State Groups
    processed_rows = []
    meta = lookup.get("group_meta", {})
    for grp_name, gm in group_metrics.items():
        st_trend_dict = group_trends.get(grp_name, {})
        row_trend = [st_trend_dict.get(m, 0) for m in sorted_months]
        state_code = meta.get(grp_name, {}).get("state_code")

        node_id = f"state:{grp_name}"
        item = _calculate_row_metrics(
            name=grp_name,
            py_leads=gm["py_leads"],
            cy_leads=gm["cy_leads"],
            py_cucet=gm["py_cucet"],
            cy_cucet=gm["cy_cucet"],
            py_adm=gm["py_adm"],
            cy_adm=gm["cy_adm"],
            py_refunds=0,
            cy_refunds=0,
            lead_trend=row_trend,
            node_id=node_id,
            level=1,
            has_children=True,
            extra_props={
                "state_key": grp_name,
                "canonical_name": grp_name,
                "state_code": state_code,
                "state_group": grp_name,
                "constituent_states": group_constituents.get(grp_name, []),
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

    lookup = _get_state_group_master_lookup(db)
    st_name = (state or "").strip()
    constituents = _get_constituent_states(st_name, lookup)

    st_placeholders = []
    st_params: Dict[str, Any] = {}
    for idx, c in enumerate(constituents):
        p_name = f"st_f_{idx}"
        st_placeholders.append(f":{p_name}")
        st_params[p_name] = c.lower().strip()

    if st_placeholders:
        where_clauses.append(f"LOWER(TRIM(d.state)) IN ({', '.join(st_placeholders)})")
        params.update(st_params)

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
        ]
        trend_params: Dict[str, Any] = {"cy_year": academic_year}
        if st_placeholders:
            trend_where.append(f"LOWER(TRIM(d.state)) IN ({', '.join(st_placeholders)})")
            trend_params.update(st_params)
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
            "COALESCE(NULLIF(TRIM(d.lead_type), ''), 'OTHERS') = :src_cat",
        ]
        trend_params = {
            "cy_year": academic_year,
            "src_cat": src_cat,
        }
        if st_placeholders:
            trend_where.append(f"LOWER(TRIM(d.state)) IN ({', '.join(st_placeholders)})")
            trend_params.update(st_params)
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
