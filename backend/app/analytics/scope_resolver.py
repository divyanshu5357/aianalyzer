"""
Dataset Analysis Scope Resolver.
Resolves enabled reporting datasets matching campus and academic year filters.
Returns dataset UUIDs and scope metadata for multi-dataset metric aggregation.
"""

import logging
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def resolve_analytics_scope(
    db: Session,
    campus: str | None = None,
    years: list[int] | str | None = None,
    dataset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Unified analytics scope resolver aligning with multi-campus dataset filtering.
    """
    # 1. Parse years parameter
    parsed_years: list[int] = []
    if years:
        if isinstance(years, str):
            for y_str in years.split(","):
                y_str = y_str.strip()
                if y_str.isdigit():
                    parsed_years.append(int(y_str))
        elif isinstance(years, (list, tuple)):
            for y in years:
                try:
                    parsed_years.append(int(y))
                except (ValueError, TypeError):
                    pass

    # Resolve all available RAW academic years dynamically
    all_avail_years: list[int] = []
    try:
        y_rows = db.execute(text("""
            SELECT DISTINCT academic_year FROM system.datasets
            WHERE is_analytics_enabled = TRUE 
              AND academic_year IS NOT NULL 
              AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
              AND COALESCE(row_count, 0) > 0
            ORDER BY academic_year DESC
        """)).fetchall()
        all_avail_years = [int(r[0]) for r in y_rows if r[0] is not None]
    except Exception as e:
        logger.warning("Failed to query distinct available academic years: %s", e)

    if not all_avail_years:
        try:
            y_rows = db.execute(text("""
                SELECT DISTINCT academic_year FROM analytics.dashboard_agg
                WHERE academic_year IS NOT NULL
                ORDER BY academic_year DESC
            """)).fetchall()
            all_avail_years = [int(r[0]) for r in y_rows if r[0] is not None]
        except Exception:
            pass

    # Determine CY (Current Year) and PY (Previous Year) dynamically
    from app.analytics.period_helper import get_active_or_max_academic_year
    if parsed_years:
        cy_year = max(parsed_years)
        if len(parsed_years) > 1:
            py_year = sorted(parsed_years)[-2]
        else:
            # Single year requested (e.g. 2027 or 2026 selected by user)
            # Find the true previous available year < cy_year
            candidates = [y for y in all_avail_years if y < cy_year]
            py_year = max(candidates) if candidates else cy_year - 1
    else:
        if all_avail_years:
            cy_year = max(all_avail_years)
            py_year = all_avail_years[1] if len(all_avail_years) > 1 else cy_year - 1
        else:
            cy_year = get_active_or_max_academic_year(db)
            py_year = cy_year - 1

    effective_years = sorted(list(set([cy_year] + ([py_year] if py_year else []))))

    # 2. Normalize campus
    campus_filter = "all"
    if campus and str(campus).strip().lower() not in ("all", "all campuses", ""):
        campus_filter = str(campus).strip()

    # 3. Query system.datasets for enabled datasets
    # Include both CY and PY RAW datasets as well as active DIMENSION and TARGET masters
    where_clauses = ["is_analytics_enabled = TRUE"]
    params: dict[str, Any] = {}

    if campus_filter != "all":
        where_clauses.append("(LOWER(campus_name) = LOWER(:campus) OR campus_name IS NULL OR UPPER(COALESCE(workbook_type, 'RAW')) != 'RAW')")
        params["campus"] = campus_filter

    years_in_str = ",".join(str(int(y)) for y in effective_years)
    where_clauses.append(f"(academic_year IN ({years_in_str}) OR academic_year IS NULL OR UPPER(COALESCE(workbook_type, 'RAW')) != 'RAW')")

    sql = text(f"""
        SELECT id, dataset_name, original_filename, academic_year, campus_name, row_count, is_active, is_analytics_enabled, analytics_status, workbook_type
        FROM system.datasets
        WHERE {" AND ".join(where_clauses)}
        ORDER BY academic_year DESC NULLS LAST, campus_name ASC
    """)

    rows = db.execute(sql, params).mappings().all()

    datasets = []
    resolved_ids = []
    cy_dataset_ids = []
    py_dataset_ids = []
    total_rows = 0

    # Construct the base set of allowed datasets from query
    for r in rows:
        ds_id = str(r["id"])
        ds_year = int(r["academic_year"]) if r["academic_year"] is not None else cy_year
        ds_campus = r["campus_name"] or "Unknown"
        ds_rows = int(r["row_count"] or 0)

        # Apply dataset_ids intersection if provided
        if dataset_ids is not None:
            if ds_id not in [str(d) for d in dataset_ids]:
                continue

        resolved_ids.append(ds_id)
        total_rows += ds_rows

        if ds_year == cy_year:
            cy_dataset_ids.append(ds_id)
        elif py_year is not None and ds_year == py_year:
            py_dataset_ids.append(ds_id)

        datasets.append({
            "id": ds_id,
            "dataset_name": r["dataset_name"] or r["original_filename"],
            "campus": ds_campus,
            "academic_year": ds_year,
            "row_count": ds_rows,
            "is_analytics_enabled": bool(r["is_analytics_enabled"]),
            "analytics_status": r.get("analytics_status") or "ANALYTICS_READY",
        })

    return {
        "scope": {
            "campus": campus_filter,
            "years": parsed_years,
        },
        "datasets": datasets,
        "dataset_ids": resolved_ids,
        "cy_year": cy_year,
        "py_year": py_year,
        "cy_dataset_ids": cy_dataset_ids,
        "py_dataset_ids": py_dataset_ids,
        "total_rows": total_rows,
    }


def resolve_dataset_scope(
    db: Session,
    campus: str | None = None,
    years: list[int] | str | None = None,
) -> dict[str, Any]:
    """
    Suboptimal backward-compatible delegate for legacy code paths.
    """
    return resolve_analytics_scope(db, campus=campus, years=years)

