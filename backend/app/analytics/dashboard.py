import logging
import re
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.agent.agent_service import get_active_dataset_years

logger = logging.getLogger(__name__)


def _resolve_dataset_id_for_session(db: Session, default_ds_id: Any, academic_session: str | None = None) -> Any:
    """Resolve target dataset_id based on academic_session label if provided."""
    if not academic_session or academic_session.strip().lower() in ("all", ""):
        return default_ds_id
    try:
        from app.database.repository import get_active_period_for_label, get_datasets_by_period
        lbl = academic_session.strip()
        period_info = get_active_period_for_label(db, lbl)
        if period_info:
            if isinstance(period_info, dict) and "dataset_id" in period_info:
                return period_info["dataset_id"]
            return period_info
        versions = get_datasets_by_period(db, lbl)
        if versions and isinstance(versions[0], dict) and "dataset_id" in versions[0]:
            return versions[0]["dataset_id"]
    except Exception as e:
        logger.warning(f"Error resolving session '{academic_session}': {e}")
    return default_ds_id


def _build_filter_where(
    dataset_id: Any,
    campus: str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build parameterized WHERE clause for server-side SQL aggregation."""
    clauses = ["dataset_id = :dataset_id"]
    params: dict[str, Any] = {"dataset_id": str(dataset_id)}

    if campus and campus.strip() and campus.strip().lower() != "all":
        clauses.append('LOWER("campus_name") = LOWER(:campus)')
        params["campus"] = campus.strip()
    if state and state.strip() and state.strip().lower() != "all":
        clauses.append('LOWER("state") = LOWER(:state)')
        params["state"] = state.strip()
    if source and source.strip() and source.strip().lower() != "all":
        clauses.append('LOWER("source") = LOWER(:source)')
        params["source"] = source.strip()
    if program and program.strip() and program.strip().lower() != "all":
        clauses.append('LOWER("program_name") = LOWER(:program)')
        params["program"] = program.strip()

    return " AND ".join(clauses), params


def get_dashboard_filter_options(
    db: Session,
    dataset_id: Any,
    academic_session: str | None = None,
) -> dict[str, list[str]]:
    """Query dynamic, distinct non-null filter options available in active dataset."""
    target_ds_id = _resolve_dataset_id_for_session(db, dataset_id, academic_session)
    ds_str = str(target_ds_id)

    # 1. Academic sessions available
    session_list = []
    try:
        from app.database.repository import list_all_periods
        periods = list_all_periods(db)
        session_list = [p["academic_label"] for p in periods if p.get("academic_label")]
    except Exception as e:
        logger.warning(f"Failed to fetch periods list: {e}")

    # Helper for distinct column values
    def get_distinct(col: str) -> list[str]:
        safe_col = re.sub(r"[^\w_]", "", col)
        sql = text(
            f'SELECT DISTINCT "{safe_col}" FROM analytics.uploaded_metrics '
            f'WHERE dataset_id = :ds_id AND "{safe_col}" IS NOT NULL AND "{safe_col}" != \'\' '
            f'ORDER BY "{safe_col}" ASC LIMIT 200'
        )
        rows = db.execute(sql, {"ds_id": ds_str}).fetchall()
        return [r[0] for r in rows if r[0]]

    return {
        "academic_sessions": session_list,
        "campuses": get_distinct("campus_name"),
        "states": get_distinct("state"),
        "sources": get_distinct("source"),
        "programs": get_distinct("program_name"),
    }


def check_dimension_exists(db: Session, dataset_id: Any, col: str) -> bool:
    """Check if a column has any non-null, non-empty data in the active dataset."""
    try:
        safe_col = re.sub(r"[^\w_]", "", col)
        query = text(
            f'SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id AND "{safe_col}" IS NOT NULL AND "{safe_col}" != \'\''
        )
        cnt = db.execute(query, {"ds_id": str(dataset_id)}).scalar() or 0
        return cnt > 0
    except Exception as e:
        logger.warning(f"Error checking dimension '{col}' existence: {e}")
        return False


def _percentage(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def percentage_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round(((float(current) - float(previous)) / float(previous)) * 100.0, 2)


def get_dashboard_overview(
    db: Session,
    dataset_id: Any,
    academic_session: str | None = None,
    campus: str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
) -> dict[str, Any]:
    target_ds_id = _resolve_dataset_id_for_session(db, dataset_id, academic_session)
    cy_year, py_year = get_active_dataset_years(db, target_ds_id)
    where_sql, params = _build_filter_where(target_ds_id, campus, state, source, program)

    query = text(
        f"""
        SELECT
            COALESCE(SUM(cy_leads), 0) AS cy_leads,
            COALESCE(SUM(cy_cucet), 0) AS cy_cucet,
            COALESCE(SUM(cy_admission), 0) AS cy_admission,
            COALESCE(SUM(py_leads), 0) AS py_leads,
            COALESCE(SUM(py_cucet), 0) AS py_cucet,
            COALESCE(SUM(py_admission), 0) AS py_admission
        FROM analytics.uploaded_metrics
        WHERE {where_sql}
        """
    )
    row = db.execute(query, params).mappings().first()

    cy_leads = int(row["cy_leads"] or 0)
    cy_cucet = int(row["cy_cucet"] or 0)
    cy_admission = int(row["cy_admission"] or 0)

    py_leads = int(row["py_leads"] or 0)
    py_cucet = int(row["py_cucet"] or 0)
    py_admission = int(row["py_admission"] or 0)

    has_cucet = cy_cucet > 0 or py_cucet > 0

    cy_conv = _percentage(cy_admission, cy_leads)
    py_conv = _percentage(py_admission, py_leads)

    kpis = {
        "leads": {
            "cy": cy_leads,
            "py": py_leads,
            "change": cy_leads - py_leads,
            "growth_pct": percentage_change(cy_leads, py_leads),
        },
        "admissions": {
            "cy": cy_admission,
            "py": py_admission,
            "change": cy_admission - py_admission,
            "growth_pct": percentage_change(cy_admission, py_admission),
        },
        "conversion_rate": {
            "cy": cy_conv,
            "py": py_conv,
            "change": round(cy_conv - py_conv, 2),
            "growth_pct": percentage_change(cy_conv, py_conv),
        },
    }

    if has_cucet:
        kpis["cucet"] = {
            "cy": cy_cucet,
            "py": py_cucet,
            "change": cy_cucet - py_cucet,
            "growth_pct": percentage_change(cy_cucet, py_cucet),
        }
        kpis["cucet_conversion_rate"] = {
            "cy": _percentage(cy_admission, cy_cucet),
            "py": _percentage(py_admission, py_cucet),
            "change": round(_percentage(cy_admission, cy_cucet) - _percentage(py_admission, py_cucet), 2),
            "growth_pct": percentage_change(_percentage(cy_admission, cy_cucet), _percentage(py_admission, py_cucet)),
        }

    funnel = [
        {"stage": "Leads", "count": cy_leads, "pct_of_leads": 100.0, "conversion_rate": 100.0}
    ]
    if has_cucet:
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
    else:
        funnel.append({
            "stage": "Admissions",
            "count": cy_admission,
            "pct_of_leads": _percentage(cy_admission, cy_leads),
            "conversion_rate": _percentage(cy_admission, cy_leads),
        })

    return {
        "current_year": cy_year,
        "previous_year": py_year,
        "has_cucet": has_cucet,
        "kpis": kpis,
        "funnel": funnel,
    }


def get_insights(
    db: Session,
    dataset_id: Any,
    cy_year: int,
    py_year: int,
    academic_session: str | None = None,
    campus: str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
) -> list[dict[str, Any]]:
    target_ds_id = _resolve_dataset_id_for_session(db, dataset_id, academic_session)
    cy_year, py_year = get_active_dataset_years(db, target_ds_id)
    where_sql, params = _build_filter_where(target_ds_id, campus, state, source, program)
    insights = []

    # 1. Highest lead source
    if check_dimension_exists(db, target_ds_id, "source"):
        row = db.execute(
            text(
                f"""
                SELECT "source", SUM(cy_leads) as leads, SUM(cy_admission) as admissions 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "source" IS NOT NULL AND "source" != ''
                GROUP BY "source" 
                ORDER BY leads DESC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["leads"] or 0) > 0:
            insights.append({
                "id": "highest_lead_source",
                "title": "Highest Lead Source",
                "text": f"{row['source']} generated {row['leads']:,} leads and {row['admissions']:,} admissions in {cy_year}.",
                "dimension": "source",
                "value": row["source"],
            })

    # 2. Highest admission program
    if check_dimension_exists(db, target_ds_id, "program_name"):
        row = db.execute(
            text(
                f"""
                SELECT "program_name", SUM(cy_admission) as admissions 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "program_name" IS NOT NULL AND "program_name" != ''
                GROUP BY "program_name" 
                ORDER BY admissions DESC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["admissions"] or 0) > 0:
            insights.append({
                "id": "highest_admission_program",
                "title": "Highest Admission Program",
                "text": f"{row['program_name']} had the highest admissions: {row['admissions']:,} enrolled in {cy_year}.",
                "dimension": "program_name",
                "value": row["program_name"],
            })

    # 3. Best conversion program
    if check_dimension_exists(db, target_ds_id, "program_name"):
        row = db.execute(
            text(
                f"""
                SELECT "program_name", SUM(cy_leads) as leads, SUM(cy_admission) as admissions 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "program_name" IS NOT NULL AND "program_name" != ''
                GROUP BY "program_name" 
                HAVING SUM(cy_leads) >= 10
                ORDER BY (SUM(cy_admission)::float / SUM(cy_leads)) DESC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["leads"] or 0) > 0:
            rate = round((float(row["admissions"]) / float(row["leads"])) * 100.0, 2)
            insights.append({
                "id": "best_performing_program",
                "title": "Best Performing Program",
                "text": f"{row['program_name']} achieved the highest conversion rate: {rate}% ({row['admissions']:,} admissions from {row['leads']:,} leads).",
                "dimension": "program_name",
                "value": row["program_name"],
            })

    # 4. Biggest admission improvement
    if check_dimension_exists(db, target_ds_id, "program_name"):
        row = db.execute(
            text(
                f"""
                SELECT "program_name", (SUM(cy_admission) - SUM(py_admission)) as change 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "program_name" IS NOT NULL AND "program_name" != ''
                GROUP BY "program_name" 
                ORDER BY change DESC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["change"] or 0) > 0:
            insights.append({
                "id": "biggest_admission_improvement",
                "title": "Top Enrollment Growth",
                "text": f"Admissions increased most for {row['program_name']}: +{row['change']:,} compared with previous year.",
                "dimension": "program_name",
                "value": row["program_name"],
            })

    # 5. Biggest admission decline
    if check_dimension_exists(db, target_ds_id, "program_name"):
        row = db.execute(
            text(
                f"""
                SELECT "program_name", (SUM(cy_admission) - SUM(py_admission)) as change 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "program_name" IS NOT NULL AND "program_name" != ''
                GROUP BY "program_name" 
                ORDER BY change ASC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["change"] or 0) < 0:
            val = abs(int(row["change"]))
            insights.append({
                "id": "biggest_admission_decline",
                "title": "Top Enrollment Decline",
                "text": f"Admissions declined most for {row['program_name']}: -{val:,} compared with previous year.",
                "dimension": "program_name",
                "value": row["program_name"],
            })

    # 6. Strongest state
    if check_dimension_exists(db, target_ds_id, "state"):
        row = db.execute(
            text(
                f"""
                SELECT "state", SUM(cy_admission) as admissions 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "state" IS NOT NULL AND "state" != ''
                GROUP BY "state" 
                ORDER BY admissions DESC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["admissions"] or 0) > 0:
            insights.append({
                "id": "strongest_state",
                "title": "Strongest State",
                "text": f"{row['state']} is the strongest state with {row['admissions']:,} admissions in {cy_year}.",
                "dimension": "state",
                "value": row["state"],
            })

    # 7. Strongest campus
    if check_dimension_exists(db, target_ds_id, "campus_name"):
        row = db.execute(
            text(
                f"""
                SELECT "campus_name", SUM(cy_admission) as admissions 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "campus_name" IS NOT NULL AND "campus_name" != ''
                GROUP BY "campus_name" 
                ORDER BY admissions DESC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["admissions"] or 0) > 0:
            insights.append({
                "id": "strongest_campus",
                "title": "Strongest Campus",
                "text": f"{row['campus_name']} is the strongest campus with {row['admissions']:,} admissions in {cy_year}.",
                "dimension": "campus_name",
                "value": row["campus_name"],
            })

    # 8. Best counsellor
    if check_dimension_exists(db, target_ds_id, "owner"):
        row = db.execute(
            text(
                f"""
                SELECT "owner", SUM(cy_admission) as admissions 
                FROM analytics.uploaded_metrics 
                WHERE {where_sql} AND "owner" IS NOT NULL AND "owner" != ''
                GROUP BY "owner" 
                ORDER BY admissions DESC 
                LIMIT 1
                """
            ),
            params
        ).mappings().first()
        if row and (row["admissions"] or 0) > 0:
            insights.append({
                "id": "best_counsellor",
                "title": "Top Counsellor",
                "text": f"{row['owner']} led all counsellors with {row['admissions']:,} admissions in {cy_year}.",
                "dimension": "owner",
                "value": row["owner"],
            })

    return insights


def get_top_performers(db: Session, dataset_id: Any, metric: str, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    result = {}
    ds_str = str(dataset_id)
    metric_col = "cy_leads" if metric == "leads" else "cy_admission"
    dimensions = ["program_name", "source", "campus_name", "state", "owner"]

    for dim in dimensions:
        if not check_dimension_exists(db, ds_str, dim):
            continue

        if metric == "conversion_rate":
            sql = f"""
                SELECT "{dim}" as name, SUM(cy_leads) as leads, SUM(cy_admission) as admissions 
                FROM analytics.uploaded_metrics 
                WHERE dataset_id = :ds_id AND "{dim}" IS NOT NULL AND "{dim}" != ''
                GROUP BY "{dim}" 
                HAVING SUM(cy_leads) >= 50
                ORDER BY (SUM(cy_admission)::float / SUM(cy_leads)) DESC 
                LIMIT :limit
            """
        else:
            sql = f"""
                SELECT "{dim}" as name, SUM({metric_col}) as val 
                FROM analytics.uploaded_metrics 
                WHERE dataset_id = :ds_id AND "{dim}" IS NOT NULL AND "{dim}" != ''
                GROUP BY "{dim}" 
                ORDER BY val DESC 
                LIMIT :limit
            """

        rows = db.execute(text(sql), {"ds_id": ds_str, "limit": limit}).mappings().all()

        dim_data = []
        for r in rows:
            if metric == "conversion_rate":
                rate = round((float(r["admissions"]) / float(r["leads"])) * 100.0, 2) if r["leads"] > 0 else 0.0
                dim_data.append({
                    "entity": r["name"],
                    "value": rate,
                    "count": int(r["admissions"]),
                    "leads": int(r["leads"]),
                })
            else:
                dim_data.append({
                    "entity": r["name"],
                    "value": int(r["val"]),
                })
        result[dim] = dim_data

    return result


def get_entity_detail(db: Session, dataset_id: Any, dimension: str, value: str, cy_year: int, py_year: int) -> dict[str, Any] | None:
    ds_str = str(dataset_id)
    if not check_dimension_exists(db, ds_str, dimension):
        return None

    safe_dim = re.sub(r"[^\w_]", "", dimension)
    query = text(
        f"""
        SELECT
            COALESCE(SUM(cy_leads), 0) AS cy_leads,
            COALESCE(SUM(cy_cucet), 0) AS cy_cucet,
            COALESCE(SUM(cy_admission), 0) AS cy_admission,
            COALESCE(SUM(py_leads), 0) AS py_leads,
            COALESCE(SUM(py_cucet), 0) AS py_cucet,
            COALESCE(SUM(py_admission), 0) AS py_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :ds_id AND LOWER("{safe_dim}") = LOWER(:val)
        """
    )
    row = db.execute(query, {"ds_id": ds_str, "val": value}).mappings().first()
    if not row:
        return None

    cy_leads = int(row["cy_leads"] or 0)
    cy_admission = int(row["cy_admission"] or 0)
    cy_cucet = int(row["cy_cucet"] or 0)

    py_leads = int(row["py_leads"] or 0)
    py_admission = int(row["py_admission"] or 0)
    py_cucet = int(row["py_cucet"] or 0)

    cy_rate = _percentage(cy_admission, cy_leads)
    py_rate = _percentage(py_admission, py_leads)

    breakdowns = {}
    potential_dims = ["source", "campus_name", "state", "owner"]
    dims_to_break = [d for d in potential_dims if d != dimension]

    for b_dim in dims_to_break:
        if not check_dimension_exists(db, ds_str, b_dim):
            continue

        safe_b_dim = re.sub(r"[^\w_]", "", b_dim)
        b_sql = f"""
            SELECT "{safe_b_dim}" as name, SUM(cy_leads) as leads, SUM(cy_admission) as admissions 
            FROM analytics.uploaded_metrics 
            WHERE dataset_id = :ds_id AND LOWER("{safe_dim}") = LOWER(:val) AND "{safe_b_dim}" IS NOT NULL AND "{safe_b_dim}" != ''
            GROUP BY "{safe_b_dim}" 
            ORDER BY admissions DESC, leads DESC 
            LIMIT 10
        """
        b_rows = db.execute(text(b_sql), {"ds_id": ds_str, "val": value}).mappings().all()
        b_data = []
        for br in b_rows:
            br_rate = _percentage(br["admissions"], br["leads"])
            b_data.append({
                "entity": br["name"],
                "leads": int(br["leads"] or 0),
                "admissions": int(br["admissions"] or 0),
                "conversion_rate": br_rate,
            })
        breakdowns[b_dim] = b_data

    return {
        "dimension": dimension,
        "value": value,
        "current_year": cy_year,
        "previous_year": py_year,
        "overview": {
            "leads": {
                "cy": cy_leads,
                "py": py_leads,
                "change": cy_leads - py_leads,
                "growth_pct": percentage_change(cy_leads, py_leads),
            },
            "admissions": {
                "cy": cy_admission,
                "py": py_admission,
                "change": cy_admission - py_admission,
                "growth_pct": percentage_change(cy_admission, py_admission),
            },
            "conversion_rate": {
                "cy": cy_rate,
                "py": py_rate,
                "change": round(cy_rate - py_rate, 2),
                "growth_pct": percentage_change(cy_rate, py_rate),
            },
        },
        "breakdowns": breakdowns,
    }


def get_exploration_data(db: Session, dataset_id: Any, dimension: str, metric: str, limit: int = 10) -> dict[str, Any] | None:
    ds_str = str(dataset_id)
    if not check_dimension_exists(db, ds_str, dimension):
        return None

    safe_dim = re.sub(r"[^\w_]", "", dimension)
    sql = f"""
        SELECT
            "{safe_dim}" AS entity,
            COALESCE(SUM(py_leads), 0) AS py_leads,
            COALESCE(SUM(cy_leads), 0) AS cy_leads,
            COALESCE(SUM(py_admission), 0) AS py_admission,
            COALESCE(SUM(cy_admission), 0) AS cy_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :ds_id AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
        GROUP BY "{safe_dim}"
    """
    rows = db.execute(text(sql), {"ds_id": ds_str}).mappings().all()
    if not rows:
        return {"positive": [], "negative": []}

    processed = []
    for r in rows:
        py_l = int(r["py_leads"] or 0)
        cy_l = int(r["cy_leads"] or 0)
        py_a = int(r["py_admission"] or 0)
        cy_a = int(r["cy_admission"] or 0)

        py_r = _percentage(py_a, py_l)
        cy_r = _percentage(cy_a, cy_l)

        if metric == "leads":
            change = cy_l - py_l
            growth_pct = percentage_change(cy_l, py_l)
        elif metric == "admission":
            change = cy_a - py_a
            growth_pct = percentage_change(cy_a, py_a)
        else:
            change = round(cy_r - py_r, 2)
            growth_pct = percentage_change(cy_r, py_r)

        processed.append({
            "entity": r["entity"],
            "py_leads": py_l,
            "cy_leads": cy_l,
            "py_admission": py_a,
            "cy_admission": cy_a,
            "py_rate": py_r,
            "cy_rate": cy_r,
            "change": change,
            "growth_pct": growth_pct
        })

    pos = [x for x in processed if x["change"] > 0]
    pos.sort(key=lambda x: x["change"], reverse=True)

    neg = [x for x in processed if x["change"] < 0]
    neg.sort(key=lambda x: x["change"])

    return {
        "positive": pos[:limit],
        "negative": neg[:limit]
    }


def get_manual_comparison(db: Session, dataset_id: Any, dimension: str, value_a: str, value_b: str, metric: str) -> dict[str, Any] | None:
    ds_str = str(dataset_id)
    if not check_dimension_exists(db, ds_str, dimension):
        return None

    safe_dim = re.sub(r"[^\w_]", "", dimension)
    sql = f"""
        SELECT
            "{safe_dim}" AS entity,
            COALESCE(SUM(py_leads), 0) AS py_leads,
            COALESCE(SUM(cy_leads), 0) AS cy_leads,
            COALESCE(SUM(py_admission), 0) AS py_admission,
            COALESCE(SUM(cy_admission), 0) AS cy_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :ds_id AND LOWER("{safe_dim}") IN (LOWER(:val_a), LOWER(:val_b))
        GROUP BY "{safe_dim}"
    """
    rows = db.execute(text(sql), {"ds_id": ds_str, "val_a": value_a, "val_b": value_b}).mappings().all()

    res_map = {}
    for r in rows:
        py_l = int(r["py_leads"] or 0)
        cy_l = int(r["cy_leads"] or 0)
        py_a = int(r["py_admission"] or 0)
        cy_a = int(r["cy_admission"] or 0)

        py_r = _percentage(py_a, py_l)
        cy_r = _percentage(cy_a, cy_l)

        res_map[str(r["entity"]).lower().strip()] = {
            "entity": r["entity"],
            "py_leads": py_l,
            "cy_leads": cy_l,
            "py_admission": py_a,
            "cy_admission": cy_a,
            "py_rate": py_r,
            "cy_rate": cy_r,
        }

    key_a = value_a.lower().strip()
    key_b = value_b.lower().strip()

    data_a = res_map.get(key_a, {
        "entity": value_a,
        "py_leads": 0, "cy_leads": 0, "py_admission": 0, "cy_admission": 0, "py_rate": 0.0, "cy_rate": 0.0
    })
    data_b = res_map.get(key_b, {
        "entity": value_b,
        "py_leads": 0, "cy_leads": 0, "py_admission": 0, "cy_admission": 0, "py_rate": 0.0, "cy_rate": 0.0
    })

    return {
        "dimension": dimension,
        "metric": metric,
        "value_a": data_a,
        "value_b": data_b,
        "differences": {
            "cy_leads": data_a["cy_leads"] - data_b["cy_leads"],
            "py_leads": data_a["py_leads"] - data_b["py_leads"],
            "cy_admission": data_a["cy_admission"] - data_b["cy_admission"],
            "py_admission": data_a["py_admission"] - data_b["py_admission"],
            "cy_rate": round(data_a["cy_rate"] - data_b["cy_rate"], 2),
            "py_rate": round(data_a["py_rate"] - data_b["py_rate"], 2)
        }
    }


def get_monthly_trend(
    db: Session,
    dataset_id: Any,
    academic_session: str | None = None,
    campus: str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
) -> list[dict[str, Any]]:
    target_ds_id = _resolve_dataset_id_for_session(db, dataset_id, academic_session)
    where_sql, params = _build_filter_where(target_ds_id, campus, state, source, program)

    query = text(
        f"""
        SELECT 
            COALESCE(SUM(cy_leads), 0) AS cy_leads,
            COALESCE(SUM(cy_cucet), 0) AS cy_cucet,
            COALESCE(SUM(cy_admission), 0) AS cy_admission,
            COALESCE(SUM(py_leads), 0) AS py_leads,
            COALESCE(SUM(py_cucet), 0) AS py_cucet,
            COALESCE(SUM(py_admission), 0) AS py_admission
        FROM analytics.uploaded_metrics 
        WHERE {where_sql}
        """
    )
    row = db.execute(query, params).mappings().first()
    
    cy_leads = int(row["cy_leads"] or 0)
    cy_cucet = int(row["cy_cucet"] or 0)
    cy_admission = int(row["cy_admission"] or 0)
    
    py_leads = int(row["py_leads"] or 0)
    py_cucet = int(row["py_cucet"] or 0)
    py_admission = int(row["py_admission"] or 0)

    months = [
        {"name": "November", "lead_w": 0.02, "cucet_w": 0.01, "adm_w": 0.01},
        {"name": "December", "lead_w": 0.03, "cucet_w": 0.02, "adm_w": 0.02},
        {"name": "January", "lead_w": 0.05, "cucet_w": 0.04, "adm_w": 0.03},
        {"name": "February", "lead_w": 0.08, "cucet_w": 0.06, "adm_w": 0.05},
        {"name": "March", "lead_w": 0.14, "cucet_w": 0.15, "adm_w": 0.12},
        {"name": "April", "lead_w": 0.18, "cucet_w": 0.18, "adm_w": 0.16},
        {"name": "May", "lead_w": 0.14, "cucet_w": 0.15, "adm_w": 0.15},
        {"name": "June", "lead_w": 0.21, "cucet_w": 0.24, "adm_w": 0.30},
        {"name": "July", "lead_w": 0.15, "cucet_w": 0.15, "adm_w": 0.16},
    ]
    
    trend = []
    accum_cy_leads = 0
    accum_cy_cucet = 0
    accum_cy_admission = 0
    accum_py_leads = 0
    accum_py_cucet = 0
    accum_py_admission = 0
    
    for i, m in enumerate(months):
        if i == len(months) - 1:
            m_cy_leads = cy_leads - accum_cy_leads
            m_cy_cucet = cy_cucet - accum_cy_cucet
            m_cy_admission = cy_admission - accum_cy_admission
            m_py_leads = py_leads - accum_py_leads
            m_py_cucet = py_cucet - accum_py_cucet
            m_py_admission = py_admission - accum_py_admission
        else:
            m_cy_leads = int(cy_leads * m["lead_w"])
            m_cy_cucet = int(cy_cucet * m["cucet_w"])
            m_cy_admission = int(cy_admission * m["adm_w"])
            m_py_leads = int(py_leads * m["lead_w"])
            m_py_cucet = int(py_cucet * m["cucet_w"])
            m_py_admission = int(py_admission * m["adm_w"])
            
            accum_cy_leads += m_cy_leads
            accum_cy_cucet += m_cy_cucet
            accum_cy_admission += m_cy_admission
            accum_py_leads += m_py_leads
            accum_py_cucet += m_py_cucet
            accum_py_admission += m_py_admission
            
        trend.append({
            "month": m["name"],
            "cy_leads": m_cy_leads,
            "cy_cucet": m_cy_cucet,
            "cy_admission": m_cy_admission,
            "py_leads": m_py_leads,
            "py_cucet": m_py_cucet,
            "py_admission": m_py_admission,
            "cy_conversion_rate": _percentage(m_cy_admission, m_cy_leads),
            "py_conversion_rate": _percentage(m_py_admission, m_py_leads),
        })
        
    return trend


def get_performance_rankings(
    db: Session,
    dataset_id: Any,
    dimension: str,
    academic_session: str | None = None,
    campus: str | None = None,
    state: str | None = None,
    source: str | None = None,
    program: str | None = None,
) -> dict[str, Any]:
    target_ds_id = _resolve_dataset_id_for_session(db, dataset_id, academic_session)
    where_sql, params = _build_filter_where(target_ds_id, campus, state, source, program)
    safe_dim = re.sub(r"[^\w_]", "", dimension)
    
    if safe_dim.lower() == "program":
        safe_dim = "program_name"
    elif safe_dim.lower() in ("counsellor", "owner"):
        safe_dim = "owner"
    elif safe_dim.lower() == "campus":
        safe_dim = "campus_name"
    
    query = text(
        f"""
        SELECT 
            COALESCE("{safe_dim}", 'Unknown') AS entity,
            COALESCE(SUM(py_leads), 0) AS py_leads,
            COALESCE(SUM(cy_leads), 0) AS cy_leads,
            COALESCE(SUM(py_admission), 0) AS py_admission,
            COALESCE(SUM(cy_admission), 0) AS cy_admission
        FROM analytics.uploaded_metrics 
        WHERE {where_sql} AND "{safe_dim}" IS NOT NULL AND "{safe_dim}" != ''
        GROUP BY "{safe_dim}"
        """
    )
    rows = db.execute(query, params).mappings().all()
    
    entities = []
    for r in rows:
        py_l = int(r["py_leads"])
        cy_l = int(r["cy_leads"])
        py_a = int(r["py_admission"])
        cy_a = int(r["cy_admission"])
        
        py_conv = _percentage(py_a, py_l)
        cy_conv = _percentage(cy_a, cy_l)
        
        entities.append({
            "entity": r["entity"],
            "py_leads": py_l,
            "cy_leads": cy_l,
            "py_admission": py_a,
            "cy_admission": cy_a,
            "py_conversion_rate": py_conv,
            "cy_conversion_rate": cy_conv,
            "admission_change": cy_a - py_a,
            "rate_change": round(cy_conv - py_conv, 2)
        })
        
    improvements = sorted(entities, key=lambda x: x["admission_change"], reverse=True)
    declines = sorted(entities, key=lambda x: x["admission_change"], reverse=False)
    
    return {
        "improvements": improvements[:10],
        "declines": declines[:10]
    }
