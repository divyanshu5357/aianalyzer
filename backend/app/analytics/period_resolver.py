"""
Period-aware analytics abstraction layer.

This module is the central bridge between the historical multi-period model
and the physical storage layout (cy_leads / py_leads columns in
analytics.uploaded_metrics).

Key design:
  - The physical table stores data with cy_* / py_* column names because the
    source Excel files label columns that way ("CY Leads", "PY Admission", etc.).
  - Each dataset row in system.datasets now carries period_start_year (PY) and
    period_end_year (CY) metadata.
  - THIS module translates high-level period queries into concrete SQL column
    references, WITHOUT changing the physical schema.

Usage examples:
    # Single-dataset (existing behaviour, unchanged)
    col = get_metric_column_for_period(metric="admissions", period_role="cy")
    # → "cy_admission"

    col = get_metric_column_for_period(metric="admissions", period_role="py")
    # → "py_admission"

    # Cross-dataset arbitrary comparison (new capability)
    results = compare_periods(
        db,
        metric="admissions",
        period_a_label="2023-24",
        period_b_label="2024-25",
        dimension="program_name",
    )
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.repository import (
    get_active_period_for_label,
    get_period_pair,
    list_all_periods,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric → physical column mapping
# (these are the actual column names in analytics.uploaded_metrics)
# ---------------------------------------------------------------------------

_CY_COLUMNS: dict[str, str] = {
    "leads":       "cy_leads",
    "lead":        "cy_leads",
    "enquiries":   "cy_leads",
    "cucet":       "cy_cucet",
    "registration": "cy_cucet",
    "admissions":  "cy_admission",
    "admission":   "cy_admission",
    "enrolled":    "cy_admission",
}

_PY_COLUMNS: dict[str, str] = {
    "leads":       "py_leads",
    "lead":        "py_leads",
    "enquiries":   "py_leads",
    "cucet":       "py_cucet",
    "registration": "py_cucet",
    "admissions":  "py_admission",
    "admission":   "py_admission",
    "enrolled":    "py_admission",
}

VALID_DIMENSIONS = frozenset(
    ["program_name", "campus_name", "source", "main_source", "state", "owner", "lead_type", "cluster"]
)


# ---------------------------------------------------------------------------
# Column resolution (single-dataset, backward-compatible)
# ---------------------------------------------------------------------------

def get_metric_column_for_period(
    metric: str,
    period_role: str,  # "cy" | "py"
) -> str:
    """
    Return the SQL column name for a metric and period role.

    This is the authoritative function for translating analytical intent
    ("admissions for PY") into physical column names ("py_admission").

    Args:
        metric:      One of "leads", "cucet", "admissions", "admission", etc.
        period_role: "cy" (current/later period) or "py" (previous/earlier period).

    Returns:
        Physical column name string, e.g. "cy_admission".

    Raises:
        ValueError: If metric is unrecognised.
    """
    key = metric.lower().strip()
    if period_role == "cy":
        col = _CY_COLUMNS.get(key)
    elif period_role == "py":
        col = _PY_COLUMNS.get(key)
    else:
        raise ValueError(f"period_role must be 'cy' or 'py', got: {period_role!r}")

    if col is None:
        raise ValueError(
            f"Unknown metric: {metric!r}. "
            f"Valid metrics: {sorted(set(_CY_COLUMNS) | set(_PY_COLUMNS))}"
        )
    return col


def resolve_period_role_for_year(
    requested_year: int | None,
    period_end_year: int,
    period_start_year: int,
) -> str:
    """
    Given an integer year (from a user query) and the dataset's period metadata,
    return whether it maps to "cy" or "py" in this dataset's columns.

    If the requested year cannot be determined, defaults to "cy".
    """
    if requested_year is None:
        return "cy"
    if requested_year == period_end_year:
        return "cy"
    if requested_year == period_start_year:
        return "py"
    # Year outside this dataset's range — default to cy
    return# ---------------------------------------------------------------------------
# Analytical year resolution (replaces single-dataset/hardcoded assumptions)
# ---------------------------------------------------------------------------

def parse_year_input(val: Any) -> int | None:
    """
    Parse integer or string inputs into an analytical year.
    Examples: 2025 -> 2025, "2025" -> 2025, "2025-26" -> 2026.
    """
    if val is None:
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if s.isdigit():
        return int(s)
    from app.ingestion.period_detector import parse_label
    parsed = parse_label(s)
    if parsed:
        return parsed[1]  # Return end year e.g. 2026
    return None


def list_all_analytical_years(db: Session) -> list[int]:
    """
    Return all distinct analytical years available across uploaded datasets.
    E.g. [2023, 2024, 2025, 2026]
    """
    try:
        rows = db.execute(
            text(
                "SELECT DISTINCT period_start_year, period_end_year "
                "FROM system.datasets "
                "WHERE period_start_year IS NOT NULL AND period_end_year IS NOT NULL"
            )
        ).mappings().all()

        years_set: set[int] = set()
        for r in rows:
            if r["period_start_year"]:
                years_set.add(int(r["period_start_year"]))
            if r["period_end_year"]:
                years_set.add(int(r["period_end_year"]))

        if years_set:
            return sorted(years_set)
    except Exception as exc:
        logger.warning("Failed to query analytical years: %s", exc)

    # Fallback if period metadata is missing on older rows
    from app.database.repository import get_active_dataset_info
    active_info = get_active_dataset_info(db)
    if active_info and active_info.get("academic_label"):
        from app.ingestion.period_detector import parse_label
        p = parse_label(active_info["academic_label"])
        if p:
            return sorted([p[0], p[1]])
    return []


def resolve_year_column(
    db: Session,
    year_val: int | str,
    metric: str,
) -> tuple[str, str, int, str]:
    """
    Resolve a requested analytical year (e.g. 2025 or 2026) to:
    (dataset_id, metric_column, year_int, role)

    Role is 'cy' or 'py'.
    """
    target_year = parse_year_input(year_val)
    if target_year is None:
        raise ValueError(f"Invalid analytical year: {year_val!r}")

    # Query datasets with period metadata, prioritising active/newer datasets
    rows = db.execute(
        text("""
            SELECT id, period_start_year, period_end_year, academic_label, is_period_active, is_active
            FROM system.datasets
            WHERE period_start_year IS NOT NULL AND period_end_year IS NOT NULL
            ORDER BY is_period_active DESC, is_active DESC, created_at DESC
        """)
    ).mappings().all()

    # 1. Match period_end_year (CY role)
    for r in rows:
        if int(r["period_end_year"]) == target_year:
            col = get_metric_column_for_period(metric, "cy")
            return (str(r["id"]), col, target_year, "cy")

    # 2. Match period_start_year (PY role)
    for r in rows:
        if int(r["period_start_year"]) == target_year:
            col = get_metric_column_for_period(metric, "py")
            return (str(r["id"]), col, target_year, "py")

    # Fallback to active dataset if target_year matches active dataset's period metadata
    from app.database.repository import get_active_dataset_info
    active = get_active_dataset_info(db)
    if active:
        ds_id = str(active["id"])
        py = active.get("period_start_year")
        cy = active.get("period_end_year")
        if py and target_year == int(py):
            return (ds_id, get_metric_column_for_period(metric, "py"), target_year, "py")
        elif cy and target_year == int(cy):
            return (ds_id, get_metric_column_for_period(metric, "cy"), target_year, "cy")

    raise ValueError(f"No dataset found for analytical year {target_year}")


# ---------------------------------------------------------------------------
# Cross-dataset period comparison (year-wise abstraction)
# ---------------------------------------------------------------------------

def compare_periods(
    db: Session,
    metric: str,
    period_a_label: str | int,
    period_b_label: str | int,
    dimension: str,
    limit: int = 50,
) -> dict[str, Any]:
    if str(period_a_label).strip() == str(period_b_label).strip():
        raise ValueError("Please select two different years for comparison.")

    year_a = parse_year_input(period_a_label)
    year_b = parse_year_input(period_b_label)

    if year_a is not None and year_a == year_b:
        raise ValueError("Please select two different years for comparison.")

    if dimension not in VALID_DIMENSIONS:
        raise ValueError(f"Invalid dimension: {dimension!r}. Valid: {sorted(VALID_DIMENSIONS)}")

    is_conversion = metric == "conversion_rate"

    try:
        if is_conversion:
            cy_id, cy_col1, year_a_val, cy_role = resolve_year_column(db, period_a_label, "admissions")
            cy_col2 = get_metric_column_for_period("leads", cy_role)

            py_id, py_col1, year_b_val, py_role = resolve_year_column(db, period_b_label, "admissions")
            py_col2 = get_metric_column_for_period("leads", py_role)
        else:
            cy_id, cy_col1, year_a_val, _ = resolve_year_column(db, period_a_label, metric)
            cy_col2 = None

            py_id, py_col1, year_b_val, _ = resolve_year_column(db, period_b_label, metric)
            py_col2 = None
    except ValueError:
        return {
            "period_a": str(period_a_label),
            "period_b": str(period_b_label),
            "year_a": parse_year_input(period_a_label),
            "year_b": parse_year_input(period_b_label),
            "dimension": dimension,
            "metric": metric,
            "columns": ["name", "period_a_value", "period_b_value", "absolute_change", "growth_percent"],
            "data": [],
        }

    def _query_period(dataset_id: str | None, col1: str, col2: str | None = None) -> dict[str, Any]:
        if not dataset_id:
            return {}
        if is_conversion and col2:
            query = text(f"""
                SELECT "{dimension}" AS dim_value, COALESCE(SUM({col1}), 0) AS val1, COALESCE(SUM({col2}), 0) AS val2
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds AND "{dimension}" IS NOT NULL
                GROUP BY "{dimension}"
            """)
        else:
            query = text(f"""
                SELECT "{dimension}" AS dim_value, COALESCE(SUM({col1}), 0) AS val1, 0 AS val2
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds AND "{dimension}" IS NOT NULL
                GROUP BY "{dimension}"
            """)

        rows = db.execute(query, {"ds": dataset_id}).mappings().all()
        return {r["dim_value"]: {"val1": float(r["val1"]), "val2": float(r["val2"])} for r in rows}

    cy_data = _query_period(cy_id, cy_col1, cy_col2)
    py_data = _query_period(py_id, py_col1, py_col2)

    all_keys = set(cy_data.keys()) | set(py_data.keys())

    # Sort keys based on period A (CY) value or conversion rate
    def sort_key(k):
        c = cy_data.get(k, {"val1": 0.0, "val2": 0.0})
        if is_conversion:
            return (c["val1"] / c["val2"] * 100) if c["val2"] else 0.0
        return c["val1"]

    sorted_keys = sorted(all_keys, key=sort_key, reverse=True)[:limit]

    data = []
    for k in sorted_keys:
        cy_vals = cy_data.get(k, {"val1": 0.0, "val2": 0.0})
        py_vals = py_data.get(k, {"val1": 0.0, "val2": 0.0})

        if is_conversion:
            cy_rate = round((cy_vals["val1"] / cy_vals["val2"] * 100), 2) if cy_vals["val2"] else 0.0
            py_rate = round((py_vals["val1"] / py_vals["val2"] * 100), 2) if py_vals["val2"] else 0.0
            change = round(cy_rate - py_rate, 2)
            pct = round((change / py_rate * 100), 2) if py_rate else None
            data.append({
                "name": k,
                "period_a_rate": cy_rate,
                "period_b_rate": py_rate,
                "period_a_value": cy_rate,  # standard contract fallback
                "period_b_value": py_rate,
                "absolute_change": change,
                "change": change,
                "rate_change_percentage_points": change,
                "growth_percent": pct,
            })
        else:
            cy_val = cy_vals["val1"]
            py_val = py_vals["val1"]
            change = cy_val - py_val
            pct = round((change / py_val * 100), 2) if py_val else None
            data.append({
                "name": k,
                "period_a_value": int(cy_val),
                "period_b_value": int(py_val),
                "absolute_change": int(change),
                "change": int(change),
                "growth_percent": pct,
            })

    cols = ["name", "period_a_value", "period_b_value", "absolute_change", "growth_percent"]
    if is_conversion:
        cols.extend(["period_a_rate", "period_b_rate", "rate_change_percentage_points"])

    return {
        "period_a": str(year_a_val),
        "period_b": str(year_b_val),
        "year_a": year_a_val,
        "year_b": year_b_val,
        "dimension": dimension,
        "metric": metric,
        "columns": cols,
        "data": data,
    }

def get_historical_trend(db: Session, metric: str, dimension: str) -> dict[str, Any]:
    if dimension not in VALID_DIMENSIONS:
        raise ValueError(f"Invalid dimension: {dimension!r}. Valid: {sorted(VALID_DIMENSIONS)}")
        
    is_conversion = metric == "conversion_rate"
    periods = list_all_periods(db)
    
    results: dict[str, dict[str, float]] = {}
    years_set: set[str] = set()

    for p in periods:
        if not p.get("active_dataset_id"):
            continue
        ds_id = p["active_dataset_id"]
        label = p["academic_label"]
        start_year = p.get("period_start_year")
        end_year = p.get("period_end_year")

        if not start_year or not end_year:
            from app.ingestion.period_detector import parse_label
            parsed = parse_label(label)
            if parsed:
                start_year, end_year = parsed

        py_year_str = str(start_year) if start_year else None
        cy_year_str = str(end_year) if end_year else None

        if py_year_str:
            years_set.add(py_year_str)
        if cy_year_str:
            years_set.add(cy_year_str)

        py_c1 = get_metric_column_for_period("admissions" if is_conversion else metric, "py")
        cy_c1 = get_metric_column_for_period("admissions" if is_conversion else metric, "cy")

        if is_conversion:
            py_c2 = get_metric_column_for_period("leads", "py")
            cy_c2 = get_metric_column_for_period("leads", "cy")
            query = text(f"""
                SELECT "{dimension}" AS dim_value,
                       COALESCE(SUM({py_c1}), 0) AS py_val1,
                       COALESCE(SUM({py_c2}), 0) AS py_val2,
                       COALESCE(SUM({cy_c1}), 0) AS cy_val1,
                       COALESCE(SUM({cy_c2}), 0) AS cy_val2
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds AND "{dimension}" IS NOT NULL
                GROUP BY "{dimension}"
            """)
        else:
            query = text(f"""
                SELECT "{dimension}" AS dim_value,
                       COALESCE(SUM({py_c1}), 0) AS py_val1,
                       COALESCE(SUM({cy_c1}), 0) AS cy_val1
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds AND "{dimension}" IS NOT NULL
                GROUP BY "{dimension}"
            """)
            
        rows = db.execute(query, {"ds": ds_id}).mappings().all()
        for r in rows:
            dim_val = r["dim_value"]
            if dim_val not in results:
                results[dim_val] = {}
                
            if is_conversion:
                py_rate = round((float(r["py_val1"]) / float(r["py_val2"]) * 100), 2) if float(r["py_val2"]) else 0.0
                cy_rate = round((float(r["cy_val1"]) / float(r["cy_val2"]) * 100), 2) if float(r["cy_val2"]) else 0.0
                if py_year_str:
                    results[dim_val][py_year_str] = py_rate
                if cy_year_str:
                    results[dim_val][cy_year_str] = cy_rate
            else:
                if py_year_str:
                    results[dim_val][py_year_str] = float(r["py_val1"])
                if cy_year_str:
                    results[dim_val][cy_year_str] = float(r["cy_val1"])

    ordered_years = sorted(list(years_set), key=lambda y: int(y) if y.isdigit() else y)

    trend_data = []
    for dim_val, vals in results.items():
        row = {"name": dim_val}
        for year in ordered_years:
            row[year] = vals.get(year, 0.0)
        trend_data.append(row)
        
    latest_year = ordered_years[-1] if ordered_years else None
    if latest_year:
        trend_data.sort(key=lambda x: x.get(latest_year, 0), reverse=True)
        
    return {
        "dimension": dimension,
        "metric": metric,
        "periods": ordered_years,
        "data": trend_data[:50]
    }


# ---------------------------------------------------------------------------
# Year derivation from period metadata (replaces get_active_dataset_years)
# ---------------------------------------------------------------------------

def get_years_from_period_metadata(
    db: Session,
    dataset_id: Any,
) -> tuple[int, int] | None:
    """
    Read period_end_year (CY) and period_start_year (PY) directly from
    system.datasets metadata.

    Returns (cy, py) tuple or None if period columns are not yet populated.
    """
    try:
        row = db.execute(
            text(
                """
                SELECT period_start_year, period_end_year
                FROM system.datasets
                WHERE id = :id
                """
            ),
            {"id": str(dataset_id)},
        ).mappings().first()

        if row and row["period_end_year"] and row["period_start_year"]:
            return int(row["period_end_year"]), int(row["period_start_year"])
    except Exception as exc:
        logger.warning("Failed to read period metadata for dataset %s: %s", dataset_id, exc)

    return None
