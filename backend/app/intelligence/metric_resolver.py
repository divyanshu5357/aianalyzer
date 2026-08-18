from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def resolve_metric(
    db: Session,
    metric_name: str,
) -> dict[str, Any] | None:
    """
    Resolve a business metric from the metric registry.
    """

    normalized_name = (
        metric_name
        .lower()
        .strip()
        .replace("-", "_")
        .replace(" ", "_")
    )

    query = text(
        """
        SELECT
            id,
            metric_name,
            description,
            business_definition,
            calculation_logic,
            source_tables,
            filters,
            time_dimension,
            confidence,
            verified
        FROM intelligence.metrics
        WHERE LOWER(metric_name) = :metric_name
        LIMIT 1
        """
    )

    row = db.execute(
        query,
        {
            "metric_name": normalized_name,
        },
    ).mappings().first()

    if not row:
        return None

    return dict(row)


def list_metrics(
    db: Session,
) -> list[dict[str, Any]]:
    """
    Return all registered business metrics.
    """

    query = text(
        """
        SELECT
            id,
            metric_name,
            description,
            business_definition,
            calculation_logic,
            source_tables,
            filters,
            time_dimension,
            confidence,
            verified
        FROM intelligence.metrics
        ORDER BY metric_name
        """
    )

    rows = db.execute(
        query
    ).mappings().all()

    return [
        dict(row)
        for row in rows
    ]