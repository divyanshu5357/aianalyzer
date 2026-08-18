from typing import Any

from app.intelligence.metric_sources import (
    METRIC_SOURCES,
)


def resolve_metric_source(
    metric_name: str,
) -> dict[str, Any] | None:
    """
    Resolve the physical database source
    for a business metric.
    """

    source = METRIC_SOURCES.get(
        metric_name
    )

    if source is None:
        return None

    return {
        "metric_name": metric_name,
        **source,
    }


def resolve_metric_sources(
    metric_names: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Resolve multiple metric sources.
    """

    result = {}

    for metric_name in metric_names:

        source = resolve_metric_source(
            metric_name
        )

        if source:
            result[metric_name] = source

    return result