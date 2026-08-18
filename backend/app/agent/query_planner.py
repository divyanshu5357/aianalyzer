from typing import Any

from app.intelligence.metric_resolver import resolve_metric
from app.intelligence.source_resolver import resolve_metric_source


def build_metric_query_plan(
    db,
    metric_name: str,
    time_context: str | None = None,
    dimensions: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a structured query plan for a business metric.

    This function does NOT generate SQL.

    It creates a safe intermediate representation
    that the SQL generator will use later.
    """

    dimensions = dimensions or []
    filters = filters or {}

    # --------------------------------------------------
    # 1. Resolve metric
    # --------------------------------------------------

    metric = resolve_metric(
        db,
        metric_name,
    )

    if not metric:
        raise ValueError(
            f"Unknown metric: {metric_name}"
        )
        # --------------------------------------------------
    # 2. Handle derived metrics
    # --------------------------------------------------

    derived_metrics = {
        "lead_cucet_rate": {
            "type": "derived",
            "formula": "cucet / leads * 100",
            "base_metrics": [
                "cucet",
                "leads",
            ],
        },

        "lead_admission_rate": {
            "type": "derived",
            "formula": "admission / leads * 100",
            "base_metrics": [
                "admission",
                "leads",
            ],
        },

        "cucet_admission_rate": {
            "type": "derived",
            "formula": "admission / cucet * 100",
            "base_metrics": [
                "admission",
                "cucet",
            ],
        },
    }

    derived = derived_metrics.get(
        metric_name
    )

    if derived:

        return {
            "metric": {
                "name": metric["metric_name"],
                "description": metric["description"],
                "business_definition": metric[
                    "business_definition"
                ],
                "calculation_logic": metric[
                    "calculation_logic"
                ],
                "confidence": float(
                    metric["confidence"]
                ),
                "verified": metric["verified"],
            },

            "type": "derived",

            "formula": derived["formula"],

            "base_metrics": derived[
                "base_metrics"
            ],

            "time_context": time_context,

            "dimensions": dimensions,

            "filters": filters,

            "operation": "derived",

            "status": "planned",
        }

    # --------------------------------------------------
    # 2. Resolve physical database source
    # --------------------------------------------------

    source = resolve_metric_source(
        metric_name
    )

    if not source:
        raise ValueError(
            f"No database source configured "
            f"for metric: {metric_name}"
        )

    # --------------------------------------------------
    # 3. Build time information
    # --------------------------------------------------

    time_filter = None

    if time_context:

        if time_context == "current_year":

            time_filter = {
                "type": "current_year",
                "column": source[
                    "date_column"
                ],
            }

        elif time_context == "previous_year":

            time_filter = {
                "type": "previous_year",
                "column": source[
                    "date_column"
                ],
            }

        elif time_context.isdigit():

            time_filter = {
                "type": "year",
                "year": int(
                    time_context
                ),
                "column": source[
                    "date_column"
                ],
            }

    # --------------------------------------------------
    # 4. Validate dimensions
    # --------------------------------------------------

    invalid_dimensions = [
        dimension
        for dimension in dimensions
        if dimension
        not in source[
            "dimension_columns"
        ]
    ]

    if invalid_dimensions:

        raise ValueError(
            "Invalid dimensions for "
            f"{metric_name}: "
            f"{invalid_dimensions}"
        )

    # --------------------------------------------------
    # 5. Build query plan
    # --------------------------------------------------

    plan = {
        "metric": {
            "name": metric[
                "metric_name"
            ],
            "description": metric[
                "description"
            ],
            "business_definition": metric[
                "business_definition"
            ],
            "calculation_logic": metric[
                "calculation_logic"
            ],
            "confidence": float(
                metric[
                    "confidence"
                ]
            ),
            "verified": metric[
                "verified"
            ],
        },

        "source": {
            "schema": source[
                "schema"
            ],
            "table": source[
                "table"
            ],
            "identifier_column": source[
                "identifier_column"
            ],
            "date_column": source[
                "date_column"
            ],
        },

        "time": time_filter,

        "dimensions": dimensions,

        "filters": filters,

        "operation": "aggregate",

        "aggregation": "count",

        "status": "planned",
    }

    return plan