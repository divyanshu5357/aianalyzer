"""
Deterministic Semantic SQL Builder for AI Analyst.
Maps structured analytical query plans into exact, benchmark-aligned PostgreSQL queries
using metric_registry, dimension_registry, and canonical master table joins.
Supports multi-dataset routing (filtering by enabled datasets, academic_year, and campus).
"""

import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.semantic.metric_registry import METRIC_REGISTRY, get_metric, calculate_ratio, resolve_metric_name
from app.semantic.dimension_registry import DIMENSION_REGISTRY, get_dimension, resolve_dimension_name

logger = logging.getLogger(__name__)


def build_semantic_metric_query(
    metric_name: str,
    filters: dict[str, Any] | None = None,
    dataset_id: str | None = None,
    academic_year: int | None = None,
    campus_name: str | None = None,
) -> tuple[str, dict[str, Any], bool]:
    """
    Build SQL query for single metric calculation across enabled datasets.
    Returns: (sql_string, params_dict, is_ratio)
    """
    canonical_metric = resolve_metric_name(metric_name) or metric_name
    metric_spec = get_metric(canonical_metric)
    where_clauses = ["d.is_analytics_enabled = TRUE"]
    params = {}

    if dataset_id:
        where_clauses.append("a.dataset_id = :dataset_id")
        params["dataset_id"] = str(dataset_id)

    if academic_year is not None and not dataset_id:
        where_clauses.append("d.academic_year = :academic_year")
        params["academic_year"] = int(academic_year)

    if campus_name is not None and str(campus_name).lower() not in ("all", "all campuses", ""):
        where_clauses.append("LOWER(d.campus_name) = LOWER(:campus_name)")
        params["campus_name"] = str(campus_name).strip()

    if filters:
        for f_dim, f_val in filters.items():
            if not f_val:
                continue
            if f_dim in ("academic_year", "year"):
                where_clauses.append("d.academic_year = :filter_year")
                try:
                    params["filter_year"] = int(f_val)
                except ValueError:
                    pass
                continue
            if f_dim in ("campus", "campus_name"):
                where_clauses.append("LOWER(d.campus_name) = LOWER(:filter_campus)")
                params["filter_campus"] = str(f_val).strip()
                continue

            canonical_dim = resolve_dimension_name(f_dim) or f_dim
            dim_spec = get_dimension(canonical_dim)
            col_name = dim_spec["column_name"] if dim_spec else canonical_dim
            param_key = f"filter_{col_name}"
            where_clauses.append(f'LOWER(a."{col_name}") = LOWER(:{param_key})')
            params[param_key] = str(f_val)

    where_sql = " WHERE " + " AND ".join(where_clauses)

    if metric_spec["is_ratio"]:
        num_metric = get_metric(metric_spec["numerator"]) if metric_spec.get("numerator") else None
        den_metric = get_metric(metric_spec["denominator"]) if metric_spec.get("denominator") else None

        num_col = (num_metric and num_metric.get("column")) or "cy_admission"
        den_col = (den_metric and den_metric.get("column")) or "cy_leads"

        sql = f"""
        SELECT 
            COALESCE(SUM(a.{num_col}), 0) AS numerator,
            COALESCE(SUM(a.{den_col}), 0) AS denominator
        FROM analytics.uploaded_metrics a
        JOIN system.datasets d ON a.dataset_id = d.id
        {where_sql}
        """
        return sql, params, True
    else:
        metric_expr = metric_spec["sql_expression"].replace('cy_admission', 'a.cy_admission').replace('cy_leads', 'a.cy_leads').replace('cy_cucet', 'a.cy_cucet').replace('lead_type', 'a.lead_type')
        sql = f"""
        SELECT COALESCE({metric_expr}, 0) AS total_value
        FROM analytics.uploaded_metrics a
        JOIN system.datasets d ON a.dataset_id = d.id
        {where_sql}
        """
        return sql, params, False


def build_semantic_breakdown_query(
    metric_name: str,
    dimension_name: str,
    filters: dict[str, Any] | None = None,
    dataset_id: str | None = None,
    academic_year: int | None = None,
    campus_name: str | None = None,
    limit: int | None = None,
    sort_dir: str = "DESC",
) -> tuple[str, dict[str, Any], bool]:
    """
    Build SQL query for dimensional breakdown across enabled datasets.
    Returns: (sql_string, params_dict, is_ratio)
    """
    canonical_metric = resolve_metric_name(metric_name) or metric_name
    metric_spec = get_metric(canonical_metric)

    canonical_dim = resolve_dimension_name(dimension_name) or dimension_name
    dim_spec = get_dimension(canonical_dim)
    
    col_name = dim_spec["column_name"] if dim_spec else canonical_dim
    null_fallback = dim_spec["default_null_value"] if dim_spec else "Unassigned"

    where_clauses = ["d.is_analytics_enabled = TRUE", f'a."{col_name}" IS NOT NULL', f'TRIM(a."{col_name}") != \'\'']
    params = {}

    if dataset_id:
        where_clauses.append("a.dataset_id = :dataset_id")
        params["dataset_id"] = str(dataset_id)

    if academic_year is not None and not dataset_id:
        where_clauses.append("d.academic_year = :academic_year")
        params["academic_year"] = int(academic_year)

    if campus_name is not None and str(campus_name).lower() not in ("all", "all campuses", ""):
        where_clauses.append("LOWER(d.campus_name) = LOWER(:campus_name)")
        params["campus_name"] = str(campus_name).strip()

    if filters:
        for f_dim, f_val in filters.items():
            if not f_val:
                continue
            if f_dim in ("academic_year", "year"):
                where_clauses.append("d.academic_year = :filter_year")
                try:
                    params["filter_year"] = int(f_val)
                except ValueError:
                    pass
                continue
            if f_dim in ("campus", "campus_name"):
                where_clauses.append("LOWER(d.campus_name) = LOWER(:filter_campus)")
                params["filter_campus"] = str(f_val).strip()
                continue

            cdim = resolve_dimension_name(f_dim) or f_dim
            dspec = get_dimension(cdim)
            f_col = dspec["column_name"] if dspec else cdim
            param_key = f"filter_{f_col}"
            where_clauses.append(f'LOWER(a."{f_col}") = LOWER(:{param_key})')
            params[param_key] = str(f_val)

    where_sql = " WHERE " + " AND ".join(where_clauses)

    join_sql = ""
    select_dim_expr = f'INITCAP(TRIM(a."{col_name}"))'

    if canonical_dim == "source":
        join_sql = " LEFT JOIN organization.source_master sm ON LOWER(TRIM(a.source)) = LOWER(TRIM(sm.source)) "
        select_dim_expr = f"COALESCE(sm.source, INITCAP(TRIM(a.source)), '{null_fallback}')"
    elif canonical_dim == "lead_type":
        join_sql = " LEFT JOIN organization.source_master sm ON LOWER(TRIM(a.source)) = LOWER(TRIM(sm.source)) "
        select_dim_expr = f"COALESCE(sm.lead_type, INITCAP(TRIM(a.lead_type)), 'Unmapped')"
    elif canonical_dim == "state":
        join_sql = " LEFT JOIN organization.state_master stm ON LOWER(TRIM(a.state)) = LOWER(TRIM(stm.state_name)) "
        select_dim_expr = f"COALESCE(stm.state_name, INITCAP(TRIM(a.state)), '{null_fallback}')"
    elif canonical_dim == "owner":
        join_sql = " LEFT JOIN organization.employee_master em ON LOWER(TRIM(a.owner)) = LOWER(TRIM(em.employee_name)) "
        select_dim_expr = f"COALESCE(em.employee_name, INITCAP(TRIM(a.owner)), '{null_fallback}')"
    elif canonical_dim == "program_name":
        join_sql = " LEFT JOIN organization.course_master cm ON LOWER(TRIM(a.program_name)) = LOWER(TRIM(cm.program_name)) "
        select_dim_expr = f"COALESCE(cm.program_name, INITCAP(TRIM(a.program_name)), '{null_fallback}')"
    elif canonical_dim in ("academic_year", "year"):
        select_dim_expr = "COALESCE(a.academic_year, d.academic_year)::text"
    elif canonical_dim in ("campus", "campus_name"):
        select_dim_expr = "INITCAP(TRIM(COALESCE(a.campus_name, d.campus_name)))"

    order_direction = "ASC" if str(sort_dir).upper() == "ASC" else "DESC"
    limit_sql = f" LIMIT {int(limit)}" if limit and limit > 0 else ""

    if metric_spec["is_ratio"]:
        num_metric = get_metric(metric_spec["numerator"]) if metric_spec.get("numerator") else None
        den_metric = get_metric(metric_spec["denominator"]) if metric_spec.get("denominator") else None

        num_col = (num_metric and num_metric.get("column")) or "cy_admission"
        den_col = (den_metric and den_metric.get("column")) or "cy_leads"

        sql = f"""
        SELECT 
            {select_dim_expr} AS "{canonical_dim}",
            COALESCE(SUM(a.{num_col}), 0) AS numerator,
            COALESCE(SUM(a.{den_col}), 0) AS denominator,
            ROUND(
                (COALESCE(SUM(a.{num_col}), 0)::float / 
                 NULLIF(COALESCE(SUM(a.{den_col}), 0), 0) * 100)::numeric, 
                2
            ) AS metric_val
        FROM analytics.uploaded_metrics a
        JOIN system.datasets d ON a.dataset_id = d.id
        {join_sql}
        {where_sql}
        GROUP BY 1
        ORDER BY metric_val {order_direction} NULLS LAST
        {limit_sql}
        """
        return sql, params, True
    else:
        metric_expr = metric_spec["sql_expression"].replace('cy_admission', 'a.cy_admission').replace('cy_leads', 'a.cy_leads').replace('cy_cucet', 'a.cy_cucet').replace('lead_type', 'a.lead_type')
        sql = f"""
        SELECT 
            {select_dim_expr} AS "{canonical_dim}",
            COALESCE({metric_expr}, 0) AS metric_val
        FROM analytics.uploaded_metrics a
        JOIN system.datasets d ON a.dataset_id = d.id
        {join_sql}
        {where_sql}
        GROUP BY 1
        ORDER BY metric_val {order_direction} NULLS LAST
        {limit_sql}
        """
        return sql, params, False
