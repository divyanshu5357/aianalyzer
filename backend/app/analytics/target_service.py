"""
Hierarchical Target Engine Service (Power BI Reconciled)
Queries target dataset master workbooks (tgt.xlsx) across Source, Program, and State target sheets.
Respects Target For grain, Date/Month ranges, Campus, State, Program, and Source dimensions.
Strictly database-driven without hardcoded values.
"""
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TARGET_DATASET_ID = "0a991108-876e-42b2-8978-5e5ea2049a14"

MONTH_MAP = {
    "jan": "Jan", "january": "Jan",
    "feb": "Feb", "february": "Feb",
    "mar": "Mar", "march": "Mar",
    "apr": "Apr", "april": "Apr",
    "may": "May",
    "jun": "Jun", "june": "Jun",
    "jul": "Jul", "july": "Jul",
    "aug": "Aug", "august": "Aug",
    "sep": "Sep", "september": "Sep",
    "oct": "Oct", "october": "Oct",
    "nov": "Nov", "november": "Nov",
    "dec": "Dec", "december": "Dec",
}

MONTH_NUMBERS = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}


def _unwrap_dataset_id(ds: Any) -> Optional[str]:
    if not ds:
        return None
    if isinstance(ds, (tuple, list)):
        return str(ds[0])
    return str(ds)


def _is_all_campus(campus: Optional[str]) -> bool:
    if not campus:
        return True
    return str(campus).strip().lower() in ("all", "all campuses", "all_campuses", "none", "")


def get_target_performance(
    db: Session,
    target_for: str = "Admission",
    campus: Optional[str] = None,
    month: Optional[str] = None,
    year: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    program_code: Optional[str] = None,
    source: Optional[str] = None,
    state: Optional[str] = None,
    raw_dataset_id: Any = None,
    sheet_name: str = "Source",
) -> Dict[str, Any]:
    """
    Authoritative Target calculation service.
    Target For: 'Admission', 'Leads', 'CUCET'.
    Queries sheet 'Source' (or specified target sheet) for target allocations.
    """
    # 1. Standardize Target For
    tf_clean = "Admission"
    tf_lower = (target_for or "admission").lower()
    if "lead" in tf_lower:
        tf_clean = "Leads"
    elif "cucet" in tf_lower:
        tf_clean = "CUCET"

    try:
        db.execute(text("SET LOCAL jit = off;"))
    except Exception:
        pass

    from app.database.repository import resolve_target_dataset, resolve_raw_dataset
    target_ds_id = resolve_target_dataset(db)

    # 2. Build Target Query against staging.records
    target_conds = [
        "r.dataset_id = :tgt_ds",
        "r.raw_data->>'Target For' = :tf"
    ]
    target_params: Dict[str, Any] = {"tgt_ds": str(target_ds_id), "tf": tf_clean}

    # Filter target sheet if explicitly tagged
    if sheet_name:
        target_conds.append("r.raw_data->>'sheet_name' = :sheet")
        target_params["sheet"] = sheet_name

    if not _is_all_campus(campus):
        target_conds.append("LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) = LOWER(:campus)")
        target_params["campus"] = campus

    if month and month.lower() in MONTH_MAP:
        target_conds.append("LOWER(TRIM(COALESCE(r.raw_data->>'Month', ''))) = LOWER(:month)")
        target_params["month"] = MONTH_MAP[month.lower()]

    if year:
        target_conds.append("(r.raw_data->>'Date' LIKE :year_like OR r.raw_data->>'CreatedOn' LIKE :year_like)")
        target_params["year_like"] = f"{year}-%"

    if start_date:
        target_conds.append("(CASE WHEN r.raw_data->>'Date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN CAST(SUBSTRING(r.raw_data->>'Date' FROM 1 FOR 10) AS DATE) ELSE NULL END) >= CAST(:start_date AS DATE)")
        target_params["start_date"] = start_date

    if end_date:
        target_conds.append("(CASE WHEN r.raw_data->>'Date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN CAST(SUBSTRING(r.raw_data->>'Date' FROM 1 FOR 10) AS DATE) ELSE NULL END) <= CAST(:end_date AS DATE)")
        target_params["end_date"] = end_date

    if source and source.lower() != "all":
        target_conds.append("LOWER(TRIM(COALESCE(r.raw_data->>'Source', ''))) = LOWER(:source)")
        target_params["source"] = source

    if program_code:
        target_conds.append("LOWER(TRIM(COALESCE(r.raw_data->>'Program Code', ''))) = LOWER(:prog)")
        target_params["prog"] = program_code

    if state:
        target_conds.append("(LOWER(TRIM(COALESCE(r.raw_data->>'State', ''))) = LOWER(:st) OR LOWER(TRIM(COALESCE(r.raw_data->>'Program Code', ''))) = LOWER(:st))")
        target_params["st"] = state

    tgt_where = " AND ".join(target_conds)
    tgt_sql = f"""
        SELECT SUM(CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric)) as total_target
        FROM staging.records r
        WHERE {tgt_where};
    """
    tgt_val = db.execute(text(tgt_sql), target_params).scalar() if target_ds_id else None
    target_num = round(float(tgt_val), 2) if tgt_val is not None else None

    # 3. Resolve RAW Dataset ID safely
    raw_ds_str = _unwrap_dataset_id(raw_dataset_id)
    if not raw_ds_str:
        from app.analytics.period_helper import get_active_or_max_academic_year
        req_year = year or get_active_or_max_academic_year(db)
        raw_ds_resolved = resolve_raw_dataset(db, req_year)
        raw_ds_str = _unwrap_dataset_id(raw_ds_resolved)

    # 4. Calculate Actuals from RAW dataset
    raw_conds = []
    raw_params: Dict[str, Any] = {}
    if raw_ds_str:
        raw_conds.append("r.dataset_id = :raw_ds")
        raw_params["raw_ds"] = str(raw_ds_str)
    else:
        raw_conds.append("r.dataset_id IN (SELECT id FROM system.datasets WHERE is_analytics_enabled = TRUE AND workbook_type = 'RAW')")

    if not _is_all_campus(campus):
        raw_conds.append("LOWER(TRIM(COALESCE(r.raw_data->>'mx_Campus', ''))) = LOWER(:campus)")
        raw_params["campus"] = campus

    if month and month.lower() in MONTH_NUMBERS:
        m_num = MONTH_NUMBERS[month.lower()]
        raw_conds.append("system.parse_month(COALESCE(NULLIF(TRIM(r.raw_data->>'CreatedOn'), ''), NULLIF(TRIM(r.raw_data->>'enquiry_date'), ''))) LIKE :month_like")
        raw_params["month_like"] = f"%-{m_num}"

    raw_where = " AND ".join(raw_conds)

    # Fast Path: Check pre-aggregated dashboard_agg first (< 1ms vs seconds of staging scan)
    try:
        agg_conds = ["academic_year = :year"]
        agg_params = {"year": req_year}
        if raw_ds_str:
            agg_conds.append("(dataset_id = :raw_ds OR (dataset_id IS NULL AND academic_year = :year))")
            agg_params["raw_ds"] = str(raw_ds_str)

        if not _is_all_campus(campus):
            agg_conds.append("LOWER(TRIM(COALESCE(campus_name, ''))) = LOWER(:campus)")
            agg_params["campus"] = campus

        if month and month.lower() in MONTH_NUMBERS:
            m_num = MONTH_NUMBERS[month.lower()]
            agg_conds.append("(created_month LIKE :m_like OR admission_month LIKE :m_like)")
            agg_params["m_like"] = f"%-{m_num}"

        agg_where = " AND ".join(agg_conds)
        metric_col = "leads_cy"
        if tf_clean == "Admission":
            metric_col = "admission_cy"
        elif tf_clean == "CUCET":
            metric_col = "cucet_cy"

        agg_val = db.execute(
            text(f"SELECT COALESCE(SUM({metric_col}), 0) FROM analytics.dashboard_agg WHERE {agg_where}"),
            agg_params
        ).scalar()

        if agg_val is not None and agg_val > 0:
            actual_num = int(agg_val)
            variance = round(actual_num - target_num, 2) if target_num is not None else "N/A"
            achieve_pct = f"{round((actual_num / target_num * 100.0), 1)}%" if (target_num and target_num > 0) else "N/A"
            return {
                "success": True,
                "target_for": tf_clean,
                "target": target_num if target_num is not None else "N/A",
                "actual": actual_num,
                "variance": variance,
                "achievement_pct": achieve_pct,
                "campus": campus or "All",
                "month": month or "All",
                "year": year,
                "raw_dataset_id": str(raw_ds_str),
                "target_dataset_id": str(target_ds_id) if target_ds_id else None,
                "actual_available": True,
                "message": None,
            }
    except Exception as _e:
        logger.debug("dashboard_agg target actuals fast-path notice: %s", _e)

    # First check if RAW records exist for this period/campus in the dataset
    raw_count = int(db.execute(text(f"SELECT COUNT(*) FROM staging.records r WHERE {raw_where}"), raw_params).scalar() or 0)

    if raw_count == 0:
        msg = f"Actual data for {month.title() if month else ''} {year or ''} is not available in the uploaded RAW dataset."
        return {
            "success": True,
            "target_for": tf_clean,
            "target": target_num if target_num is not None else "N/A",
            "actual": "N/A",
            "variance": "N/A",
            "achievement_pct": "N/A",
            "campus": campus or "All",
            "month": month or "All",
            "year": year,
            "raw_dataset_id": str(raw_ds_str),
            "target_dataset_id": str(target_ds_id) if target_ds_id else None,
            "actual_available": False,
            "message": msg,
        }

    if tf_clean == "Admission":
        raw_sql = f"""
            SELECT COUNT(DISTINCT r.raw_data->>'ProspectID')
            FROM staging.records r
            WHERE {raw_where}
              AND NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL
              AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null';
        """
    elif tf_clean == "Leads":
        raw_sql = f"""
            SELECT COUNT(DISTINCT r.raw_data->>'ProspectID')
            FROM staging.records r
            WHERE {raw_where};
        """
    else:  # CUCET
        raw_sql = f"""
            SELECT COUNT(DISTINCT r.raw_data->>'ProspectID')
            FROM staging.records r
            WHERE {raw_where}
              AND (NULLIF(TRIM(r.raw_data->>'mx_CUCET_Score'), '') IS NOT NULL OR r.raw_data->>'mx_CUCET_Exam_Status' IS NOT NULL);
        """

    actual_num = int(db.execute(text(raw_sql), raw_params).scalar() or 0)
    variance = round(actual_num - target_num, 2) if target_num is not None else "N/A"
    achieve_pct = f"{round((actual_num / target_num * 100.0), 1)}%" if (target_num and target_num > 0) else "N/A"

    return {
        "success": True,
        "target_for": tf_clean,
        "target": target_num if target_num is not None else "N/A",
        "actual": actual_num,
        "variance": variance,
        "achievement_pct": achieve_pct,
        "campus": campus or "All",
        "month": month or "All",
        "year": year,
        "raw_dataset_id": str(raw_ds_str),
        "target_dataset_id": str(target_ds_id) if target_ds_id else None,
        "actual_available": True,
        "message": None,
    }


def get_program_target_breakdown(
    db: Session,
    target_for: str = "Leads",
    campus: Optional[str] = None,
    month: Optional[str] = None,
    year: Optional[int] = None,
    raw_dataset_id: Any = None,
) -> Dict[str, Any]:
    """
    Program-wise target performance querying Sheet 2 ('Program').
    Returns target vs actual breakdown grouped by Program Code.
    """
    tf_clean = "Leads" if "lead" in (target_for or "").lower() else ("Admission" if "adm" in (target_for or "").lower() else "CUCET")
    from app.database.repository import resolve_target_dataset, resolve_raw_dataset
    from app.analytics.period_helper import get_active_or_max_academic_year
    target_ds_id = resolve_target_dataset(db)
    target_year = year or get_active_or_max_academic_year(db)
    raw_ds_str = _unwrap_dataset_id(raw_dataset_id) or _unwrap_dataset_id(resolve_raw_dataset(db, target_year))

    sql = text("""
        SELECT
            r.raw_data->>'Program Code' as program_code,
            SUM(CAST(COALESCE(NULLIF(r.raw_data->>'Target', ''), NULLIF(r.raw_data->>'Final Target', ''), '0') AS numeric)) as total_target
        FROM staging.records r
        WHERE r.dataset_id = :tgt_ds
          AND (r.raw_data->>'sheet_name' IS NULL OR LOWER(r.raw_data->>'sheet_name') = 'program')
          AND LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) = LOWER(:tf)
          AND (:campus IS NULL OR LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) = LOWER(:campus))
          AND (:month IS NULL OR LOWER(TRIM(COALESCE(r.raw_data->>'Month', ''))) = LOWER(:month))
        GROUP BY 1
        HAVING SUM(CAST(COALESCE(NULLIF(r.raw_data->>'Target', ''), '0') AS numeric)) > 0
        ORDER BY total_target DESC
        LIMIT 15;
    """)
    params = {
        "tgt_ds": str(target_ds_id),
        "tf": tf_clean,
        "campus": None if _is_all_campus(campus) else campus,
        "month": MONTH_MAP.get(month.lower()) if month and month.lower() in MONTH_MAP else None,
    }
    rows = db.execute(sql, params).mappings().all()
    data = []
    for r in rows:
        prog = r["program_code"] or "Unknown"
        tgt_val = round(float(r["total_target"] or 0.0), 2)
        data.append({"program_code": prog, "target": tgt_val, "target_for": tf_clean})

    return {
        "success": True,
        "target_for": tf_clean,
        "campus": campus or "All",
        "month": month or "All",
        "data": data,
        "columns": ["program_code", "target", "target_for"],
    }


def get_state_target_breakdown(
    db: Session,
    target_for: str = "Leads",
    campus: Optional[str] = None,
    month: Optional[str] = None,
    year: Optional[int] = None,
    raw_dataset_id: Any = None,
) -> Dict[str, Any]:
    """
    State-wise target performance querying Sheet 3 ('State').
    Returns target vs actual breakdown grouped by State.
    """
    tf_clean = "Leads" if "lead" in (target_for or "").lower() else ("Admission" if "adm" in (target_for or "").lower() else "CUCET")
    from app.database.repository import resolve_target_dataset, resolve_raw_dataset
    target_ds_id = resolve_target_dataset(db)

    sql = text("""
        SELECT
            COALESCE(NULLIF(TRIM(r.raw_data->>'State'), ''), NULLIF(TRIM(r.raw_data->>'Program Code'), '')) as state_name,
            SUM(CAST(COALESCE(NULLIF(r.raw_data->>'Target', ''), NULLIF(r.raw_data->>'Final Target', ''), '0') AS numeric)) as total_target
        FROM staging.records r
        WHERE r.dataset_id = :tgt_ds
          AND (r.raw_data->>'sheet_name' IS NULL OR LOWER(r.raw_data->>'sheet_name') = 'state')
          AND LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) = LOWER(:tf)
          AND (:campus IS NULL OR LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) = LOWER(:campus))
          AND (:month IS NULL OR LOWER(TRIM(COALESCE(r.raw_data->>'Month', ''))) = LOWER(:month))
        GROUP BY 1
        HAVING SUM(CAST(COALESCE(NULLIF(r.raw_data->>'Target', ''), '0') AS numeric)) > 0
        ORDER BY total_target DESC
        LIMIT 15;
    """)
    params = {
        "tgt_ds": str(target_ds_id),
        "tf": tf_clean,
        "campus": None if _is_all_campus(campus) else campus,
        "month": MONTH_MAP.get(month.lower()) if month and month.lower() in MONTH_MAP else None,
    }
    rows = db.execute(sql, params).mappings().all()
    data = []
    for r in rows:
        st = r["state_name"] or "Unknown"
        tgt_val = round(float(r["total_target"] or 0.0), 2)
        data.append({"state": st, "target": tgt_val, "target_for": tf_clean})

    return {
        "success": True,
        "target_for": tf_clean,
        "campus": campus or "All",
        "month": month or "All",
        "data": data,
        "columns": ["state", "target", "target_for"],
    }
