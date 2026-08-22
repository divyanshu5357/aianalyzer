"""Server-side BI workspace queries for source and program analytics.

The historical-period resolver owns the mapping from period labels to active
datasets.  This module builds on that resolver and keeps the potentially large
comparison entirely in PostgreSQL: each dataset is aggregated first, the two
aggregates are joined, then filtering, sorting, and pagination are applied.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.repository import get_active_period_for_label, get_period_pair


WORKSPACE_DIMENSIONS = {
    "source": {
        "group_columns": (("source", "source"), ("state", "state")),
        "response_dimension": "source",
    },
    "program": {
        "group_columns": (("program", "program_name"), ("specialization", "cluster")),
        "response_dimension": "program",
    },
}

# API filter names deliberately differ from physical column names where that
# makes the BI UI clearer (e.g. ``campus`` and optional program detail).
FILTER_COLUMNS = {
    "state": "state",
    "source": "source",
    "campus": "campus_name",
    "owner": "owner",
    "program": "program_name",
    "specialization": "cluster",
}

VALID_METRICS = frozenset({"leads", "admissions", "conversion_rate"})
VALID_PERFORMANCE = frozenset({"all", "increased", "decreased"})
VALID_DISPLAY_MODES = frozenset({"exact", "percentage", "both"})

# The values are SQL aliases defined in the comparison CTE.  They are not
# request text, which prevents an ORDER BY injection surface.
SORT_FIELDS = {
    "name": "entity_name",
    "source": "source",
    "state": "state",
    "program": "program",
    "specialization": "specialization",
    "period_a_value": "period_a_value",
    "period_b_value": "period_b_value",
    "absolute_change": "absolute_change",
    "growth_percent": "growth_percent",
    "py_leads": "period_a_leads",
    "cy_leads": "period_b_leads",
    "period_a_leads": "period_a_leads",
    "period_b_leads": "period_b_leads",
    "lead_change": "lead_change",
    "lead_change_percent": "lead_change_percent",
    "py_admissions": "period_a_admissions",
    "cy_admissions": "period_b_admissions",
    "period_a_admissions": "period_a_admissions",
    "period_b_admissions": "period_b_admissions",
    "admission_change": "admission_change",
    "admission_change_percent": "admission_change_percent",
    "py_conversion": "period_a_conversion",
    "cy_conversion": "period_b_conversion",
    "period_a_conversion": "period_a_conversion",
    "period_b_conversion": "period_b_conversion",
    "conversion_change": "conversion_change_percentage_points",
    "conversion_change_percentage_points": "conversion_change_percentage_points",
}

WORKSPACE_SORT_FIELDS = {
    "source": frozenset(
        {
            "name", "source", "state", "period_a_value", "period_b_value", "absolute_change", "growth_percent",
            "py_leads", "cy_leads", "period_a_leads", "period_b_leads", "lead_change", "lead_change_percent",
            "py_admissions", "cy_admissions", "period_a_admissions", "period_b_admissions",
            "admission_change", "admission_change_percent", "py_conversion", "cy_conversion",
            "period_a_conversion", "period_b_conversion", "conversion_change", "conversion_change_percentage_points",
        }
    ),
    "program": frozenset(
        {
            "name", "program", "specialization", "period_a_value", "period_b_value", "absolute_change", "growth_percent",
            "py_leads", "cy_leads", "period_a_leads", "period_b_leads", "lead_change", "lead_change_percent",
            "py_admissions", "cy_admissions", "period_a_admissions", "period_b_admissions",
            "admission_change", "admission_change_percent", "py_conversion", "cy_conversion",
            "period_a_conversion", "period_b_conversion", "conversion_change", "conversion_change_percentage_points",
        }
    ),
}


def _normalised_dimension(column: str) -> str:
    """Use a stable key so blank/null values join between the two periods."""
    return f"COALESCE(NULLIF(BTRIM({column}), ''), 'Unspecified')"



def _validated_workspace(workspace: str) -> dict[str, Any]:
    config = WORKSPACE_DIMENSIONS.get(workspace)
    if config is None:
        raise ValueError("workspace must be 'source' or 'program'")
    return config


def _build_filter_clause(filters: dict[str, str | None], prefix: str) -> tuple[str, dict[str, str]]:
    clauses: list[str] = []
    params: dict[str, str] = {}

    for filter_name, column in FILTER_COLUMNS.items():
        value = filters.get(filter_name)
        if value is None or not value.strip():
            continue

        parameter = f"{prefix}_{filter_name}"
        clauses.append(f"LOWER({_normalised_dimension(column)}) = LOWER(:{parameter})")
        params[parameter] = value.strip()

    return (f"\n              AND {' AND '.join(clauses)}" if clauses else ""), params


def _serialise_row(row: dict[str, Any], workspace: str, metric: str) -> dict[str, Any]:
    """Convert PostgreSQL numerics to JSON-friendly Python values."""
    integer_fields = {
        "period_a_leads",
        "period_b_leads",
        "lead_change",
        "period_a_admissions",
        "period_b_admissions",
        "admission_change",
    }
    float_fields = {
        "lead_change_percent",
        "admission_change_percent",
        "period_a_conversion",
        "period_b_conversion",
        "conversion_change_percentage_points",
        "growth_percent",
    }
    selected_metric_fields = {"period_a_value", "period_b_value", "absolute_change"}
    if metric == "conversion_rate":
        float_fields.update(selected_metric_fields)
    else:
        integer_fields.update(selected_metric_fields)

    data = dict(row)
    for field in integer_fields:
        if field in data and data[field] is not None:
            data[field] = int(data[field])
    for field in float_fields:
        if field in data and data[field] is not None:
            data[field] = float(data[field])

    if workspace == "program" and data.get("specialization") == "Unspecified":
        data["specialization"] = None
    if workspace == "source" and data.get("state") == "Unspecified":
        data["state"] = None
    return data


def query_workspace_comparison(
    db: Session,
    *,
    workspace: str,
    period_a_label: str,
    period_b_label: str,
    metric: str = "leads",
    performance: str = "all",
    sort_field: str = "absolute_change",
    sort_direction: str = "desc",
    display: str = "both",
    limit: int = 50,
    offset: int = 0,
    filters: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Return one server-paginated page of a source/program period comparison.

    Period A is the baseline (PY-style) dataset and Period B is the comparison
    (CY-style) dataset.  The table always carries every aggregate; ``display``
    lets the client decide which already-aggregated columns to render without
    another request or a raw-row download.
    """
    if str(period_a_label).strip() == str(period_b_label).strip():
        raise ValueError("Please select two different years for comparison.")
    workspace_config = _validated_workspace(workspace)
    if metric not in VALID_METRICS:
        raise ValueError(f"Invalid metric '{metric}'")
    if performance not in VALID_PERFORMANCE:
        raise ValueError(f"Invalid performance filter '{performance}'")
    if display not in VALID_DISPLAY_MODES:
        raise ValueError(f"Invalid display mode '{display}'")
    if sort_field not in WORKSPACE_SORT_FIELDS[workspace]:
        raise ValueError(f"Invalid sort field '{sort_field}'")

    direction = sort_direction.lower()
    if direction not in {"asc", "desc"}:
        raise ValueError("sort_direction must be 'asc' or 'desc'")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if offset < 0:
        raise ValueError("offset must be zero or greater")

    from app.analytics.period_resolver import resolve_year_column, parse_year_input
    year_a = parse_year_input(period_a_label)
    year_b = parse_year_input(period_b_label)
    if year_a is not None and year_a == year_b:
        raise ValueError("Please select two different years for comparison.")

    col_a_leads = "cy_leads"
    col_a_admissions = "cy_admission"
    col_b_leads = "cy_leads"
    col_b_admissions = "cy_admission"

    try:
        period_a_id, col_a_leads, _, _ = resolve_year_column(db, period_a_label, "leads")
        _, col_a_admissions, _, _ = resolve_year_column(db, period_a_label, "admissions")
        period_b_id, col_b_leads, _, _ = resolve_year_column(db, period_b_label, "leads")
        _, col_b_admissions, _, _ = resolve_year_column(db, period_b_label, "admissions")
    except Exception:
        period_a_id, period_b_id = get_period_pair(db, period_a_label, period_b_label)

    if not period_a_id or not period_b_id:
        raise ValueError("Both selected periods must have an active dataset")

    requested_filters = filters or {}
    filter_clause_a, filter_params_a = _build_filter_clause(requested_filters, "a")
    filter_clause_b, filter_params_b = _build_filter_clause(requested_filters, "b")

    group_columns = workspace_config["group_columns"]
    group_select = ",\n                ".join(
        f"{_normalised_dimension(column)} AS {alias}" for alias, column in group_columns
    )
    group_by = ", ".join(str(index) for index in range(1, len(group_columns) + 1))
    join_using = ", ".join(alias for alias, _ in group_columns)
    joined_dimensions = ",\n                ".join(
        f"COALESCE(period_a.{alias}, period_b.{alias}) AS {alias}" for alias, _ in group_columns
    )

    if workspace == "source":
        entity_name = "source"
    else:
        entity_name = "program"

    selected_metric_a = {
        "leads": "period_a_leads",
        "admissions": "period_a_admissions",
        "conversion_rate": "period_a_conversion",
    }[metric]
    selected_metric_b = {
        "leads": "period_b_leads",
        "admissions": "period_b_admissions",
        "conversion_rate": "period_b_conversion",
    }[metric]
    selected_metric_change = {
        "leads": "lead_change",
        "admissions": "admission_change",
        "conversion_rate": "conversion_change_percentage_points",
    }[metric]

    # ``sort_column`` is from the static mapping above, never from client SQL.
    sort_column = SORT_FIELDS[sort_field]
    sql = text(
        f"""
        WITH period_a AS (
            SELECT
                {group_select},
                COALESCE(SUM({col_a_leads}), 0)::bigint AS period_a_leads,
                COALESCE(SUM({col_a_admissions}), 0)::bigint AS period_a_admissions
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :period_a_id{filter_clause_a}
            GROUP BY {group_by}
        ),
        period_b AS (
            SELECT
                {group_select},
                COALESCE(SUM({col_b_leads}), 0)::bigint AS period_b_leads,
                COALESCE(SUM({col_b_admissions}), 0)::bigint AS period_b_admissions
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :period_b_id{filter_clause_b}
            GROUP BY {group_by}
        ),
        joined AS (
            SELECT
                {joined_dimensions},
                COALESCE(period_a.period_a_leads, 0)::bigint AS period_a_leads,
                COALESCE(period_b.period_b_leads, 0)::bigint AS period_b_leads,
                COALESCE(period_a.period_a_admissions, 0)::bigint AS period_a_admissions,
                COALESCE(period_b.period_b_admissions, 0)::bigint AS period_b_admissions
            FROM period_a
            FULL OUTER JOIN period_b USING ({join_using})
        ),
        calculated AS (
            SELECT
                *,
                (period_b_leads - period_a_leads)::bigint AS lead_change,
                CASE
                    WHEN period_a_leads = 0 THEN NULL
                    ELSE ROUND(((period_b_leads - period_a_leads)::numeric / period_a_leads) * 100, 2)::double precision
                END AS lead_change_percent,
                (period_b_admissions - period_a_admissions)::bigint AS admission_change,
                CASE
                    WHEN period_a_admissions = 0 THEN NULL
                    ELSE ROUND(((period_b_admissions - period_a_admissions)::numeric / period_a_admissions) * 100, 2)::double precision
                END AS admission_change_percent,
                CASE
                    WHEN period_a_leads = 0 THEN 0::double precision
                    ELSE ROUND((period_a_admissions::numeric / period_a_leads) * 100, 2)::double precision
                END AS period_a_conversion,
                CASE
                    WHEN period_b_leads = 0 THEN 0::double precision
                    ELSE ROUND((period_b_admissions::numeric / period_b_leads) * 100, 2)::double precision
                END AS period_b_conversion
            FROM joined
        ),
        comparison AS (
            SELECT
                *,
                (period_b_conversion - period_a_conversion)::double precision AS conversion_change_percentage_points,
                {selected_metric_a} AS period_a_value,
                {selected_metric_b} AS period_b_value,
                {selected_metric_change} AS absolute_change
            FROM calculated
        ),
        filtered AS (
            SELECT
                *,
                CASE
                    WHEN period_a_value = 0 THEN NULL
                    ELSE ROUND((absolute_change::numeric / period_a_value) * 100, 2)::double precision
                END AS growth_percent
            FROM comparison
            WHERE :performance = 'all'
               OR (:performance = 'increased' AND absolute_change > 0)
               OR (:performance = 'decreased' AND absolute_change < 0)
        )
        SELECT
            *,
            {entity_name} AS entity_name
        FROM filtered
        ORDER BY {sort_column} {direction.upper()} NULLS LAST, entity_name ASC
        LIMIT :page_size_plus_one OFFSET :offset
        """
    )

    params: dict[str, Any] = {
        "period_a_id": str(period_a_id),
        "period_b_id": str(period_b_id),
        "performance": performance,
        "page_size_plus_one": limit + 1,
        "offset": offset,
        **filter_params_a,
        **filter_params_b,
    }
    result_rows = db.execute(sql, params).mappings().all()
    has_more = len(result_rows) > limit
    result_rows = result_rows[:limit]

    rows = [_serialise_row(row, workspace, metric) for row in result_rows]
    has_specialization = workspace == "program" and any(row.get("specialization") for row in rows)

    return {
        "workspace": workspace,
        "dimension": workspace_config["response_dimension"],
        "period_a": period_a_label,
        "period_b": period_b_label,
        "metric": metric,
        "display": display,
        "performance": performance,
        "filters": {key: value for key, value in requested_filters.items() if value},
        "has_specialization": has_specialization,
        "rows": rows,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
        },
    }


def get_workspace_filter_options(
    db: Session,
    *,
    workspace: str,
    period_a_label: str,
    period_b_label: str,
) -> dict[str, Any]:
    """Return bounded, distinct filter values for the two selected datasets."""
    _validated_workspace(workspace)
    period_a_id, period_b_id = get_period_pair(db, period_a_label, period_b_label)
    if not period_a_id or not period_b_id:
        raise ValueError("Both selected periods must have an active dataset")

    options: dict[str, list[str]] = {}
    for filter_name, column in FILTER_COLUMNS.items():
        query = text(
            f"""
            SELECT DISTINCT value
            FROM (
                SELECT NULLIF(BTRIM(\"{column}\"), '') AS value
                FROM analytics.uploaded_metrics
                WHERE dataset_id IN (:period_a_id, :period_b_id)
            ) values_for_periods
            WHERE value IS NOT NULL
            ORDER BY value
            LIMIT 500
            """
        )
        values = db.execute(
            query,
            {"period_a_id": str(period_a_id), "period_b_id": str(period_b_id)},
        ).scalars().all()
        options[filter_name] = [str(value) for value in values]

    return {"workspace": workspace, "period_a": period_a_label, "period_b": period_b_label, "options": options}
