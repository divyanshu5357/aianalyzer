from typing import Any

from app.intelligence.source_resolver import (
    resolve_metric_source,
)


def _generate_derived_sql(
    plan: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    Generate SQL for derived metrics.

    Supported:

        lead_cucet_rate
            = cucet / leads * 100

        lead_admission_rate
            = admission / leads * 100

        cucet_admission_rate
            = admission / cucet * 100
    """

    base_metrics = plan["base_metrics"]
    time_context = plan.get("time_context")

    if len(base_metrics) != 2:
        raise ValueError(
            "Derived metrics require exactly two base metrics."
        )

    # --------------------------------------------------
    # Resolve physical sources
    # --------------------------------------------------

    sources = {}

    for metric_name in base_metrics:

        source = resolve_metric_source(
            metric_name
        )

        if not source:
            raise ValueError(
                f"No database source configured "
                f"for base metric: {metric_name}"
            )

        sources[metric_name] = source

    # --------------------------------------------------
    # Derived metrics currently don't support
    # dimensions or filters.
    # --------------------------------------------------

    if plan.get("dimensions"):
        raise ValueError(
            "Dimensions are not yet supported "
            "for derived metrics."
        )

    if plan.get("filters"):
        raise ValueError(
            "Filters are not yet supported "
            "for derived metrics."
        )

    # --------------------------------------------------
    # Build CTEs
    # --------------------------------------------------

    parameters: dict[str, Any] = {}
    ctes = []

    for metric_name in base_metrics:

        source = sources[metric_name]

        schema = source["schema"]
        table = source["table"]
        identifier = source["identifier_column"]
        date_column = source["date_column"]

        where_clause = ""

        if time_context:

            if time_context.isdigit():

                year = int(
                    time_context
                )

                start_param = (
                    f"{metric_name}_start_date"
                )

                end_param = (
                    f"{metric_name}_end_date"
                )

                where_clause = f"""
                    WHERE "{date_column}" >=
                    :{start_param}
                    AND "{date_column}" <
                    :{end_param}
                """

                parameters[
                    start_param
                ] = f"{year}-01-01"

                parameters[
                    end_param
                ] = f"{year + 1}-01-01"

            elif time_context == "current_year":

                where_clause = f"""
                    WHERE EXTRACT(
                        YEAR FROM "{date_column}"
                    ) = EXTRACT(
                        YEAR FROM CURRENT_DATE
                    )
                """

            elif time_context == "previous_year":

                where_clause = f"""
                    WHERE EXTRACT(
                        YEAR FROM "{date_column}"
                    ) = EXTRACT(
                        YEAR FROM CURRENT_DATE
                    ) - 1
                """

            else:

                raise ValueError(
                    f"Unsupported time context: "
                    f"{time_context}"
                )

        ctes.append(
            f"""
            {metric_name}_count AS (
                SELECT
                    COUNT("{identifier}") AS value
                FROM "{schema}"."{table}"
                {where_clause}
            )
            """
        )

    # --------------------------------------------------
    # Formula
    # --------------------------------------------------

    numerator = base_metrics[0]
    denominator = base_metrics[1]

    sql = (
        "WITH "
        + ", ".join(
            cte.strip()
            for cte in ctes
        )
        + f"""
        SELECT
            ROUND(
                (
                    {numerator}_count.value::numeric
                    /
                    NULLIF(
                        {denominator}_count.value,
                        0
                    )
                ) * 100,
                2
            ) AS metric_value
        FROM {numerator}_count
        CROSS JOIN {denominator}_count;
        """
    )

    return sql.strip(), parameters


def generate_sql(
    plan: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    Convert a validated query plan into SQL.

    Supports both:

    1. Normal/base metrics
    2. Derived metrics
    """

    # --------------------------------------------------
    # Derived metric
    # --------------------------------------------------

    if plan.get("type") == "derived":

        return _generate_derived_sql(
            plan
        )

    # --------------------------------------------------
    # Normal/base metric
    # --------------------------------------------------

    source = plan["source"]

    schema = source["schema"]
    table = source["table"]
    identifier = source["identifier_column"]
    date_column = source["date_column"]

    dimensions = plan.get(
        "dimensions",
        [],
    )

    time_filter = plan.get(
        "time"
    )

    filters = plan.get(
        "filters",
        {},
    )

    # --------------------------------------------------
    # Validate identifiers
    # --------------------------------------------------

    allowed_identifier_chars = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_"
    )

    identifiers = [
        schema,
        table,
        identifier,
        date_column,
        *dimensions,
    ]

    for value in identifiers:

        if not value:
            raise ValueError(
                "Empty SQL identifier."
            )

        if not all(
            char in allowed_identifier_chars
            for char in value
        ):
            raise ValueError(
                f"Unsafe SQL identifier: {value}"
            )

    # --------------------------------------------------
    # SELECT
    # --------------------------------------------------

    select_parts = []

    for dimension in dimensions:

        select_parts.append(
            f'"{dimension}"'
        )

    select_parts.append(
        f'COUNT("{identifier}") AS metric_value'
    )

    sql = (
        "SELECT "
        + ", ".join(select_parts)
        + f' FROM "{schema}"."{table}"'
    )

    # --------------------------------------------------
    # WHERE
    # --------------------------------------------------

    where_clauses = []
    parameters: dict[str, Any] = {}

    if time_filter:

        time_type = time_filter["type"]

        if time_type == "year":

            year = time_filter["year"]

            where_clauses.append(
                f"""
                "{date_column}" >=
                :start_date
                AND
                "{date_column}" < :end_date
                """
            )

            parameters[
                "start_date"
            ] = f"{year}-01-01"

            parameters[
                "end_date"
            ] = f"{year + 1}-01-01"

        elif time_type == "current_year":

            where_clauses.append(
                f"""
                EXTRACT(
                    YEAR FROM "{date_column}"
                ) = EXTRACT(
                    YEAR FROM CURRENT_DATE
                )
                """
            )

        elif time_type == "previous_year":

            where_clauses.append(
                f"""
                EXTRACT(
                    YEAR FROM "{date_column}"
                ) = EXTRACT(
                    YEAR FROM CURRENT_DATE
                ) - 1
                """
            )

        else:

            raise ValueError(
                f"Unsupported time type: {time_type}"
            )

    # --------------------------------------------------
    # Additional filters
    # --------------------------------------------------

    allowed_filter_columns = set(
        source.get(
            "dimension_columns",
            [],
        )
    )

    for column, value in filters.items():

        if column not in allowed_filter_columns:

            raise ValueError(
                f"Invalid filter column: {column}"
            )

        where_clauses.append(
            f'"{column}" = :filter_{column}'
        )

        parameters[
            f"filter_{column}"
        ] = value

    # --------------------------------------------------
    # WHERE clause
    # --------------------------------------------------

    if where_clauses:

        sql += (
            " WHERE "
            + " AND ".join(
                clause.strip()
                for clause in where_clauses
            )
        )

    # --------------------------------------------------
    # GROUP BY
    # --------------------------------------------------

    if dimensions:

        sql += (
            " GROUP BY "
            + ", ".join(
                f'"{dimension}"'
                for dimension in dimensions
            )
        )

        sql += (
            " ORDER BY metric_value DESC"
        )

    sql += ";"

    return sql, parameters