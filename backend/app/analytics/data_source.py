from typing import Any
from sqlalchemy.orm import Session

from app.analytics.funnel import calculate_funnel as calculate_funnel_org
from app.analytics.source_performance import (
    calculate_source_performance as calculate_source_performance_org,
)
from app.analytics.source_hierarchy import (
    calculate_source_hierarchy as calculate_source_hierarchy_org,
)
from app.analytics.source_detail import (
    calculate_source_detail as calculate_source_detail_org,
)

from app.analytics.uploaded_analytics import (
    get_latest_dataset_id,
    calculate_funnel_uploaded,
    calculate_source_performance_uploaded,
    calculate_source_hierarchy_uploaded,
    calculate_source_detail_uploaded,
)


def get_analytics_funnel(
    db: Session,
    year: int,
    dataset_id: Any = None,
    source_type: str = "auto",
) -> dict[str, Any]:
    active_dataset = dataset_id or get_latest_dataset_id(db)

    if (source_type == "auto" and active_dataset) or source_type == "uploaded":
        return calculate_funnel_uploaded(db, active_dataset, year)

    return calculate_funnel_org(db, year)


def get_analytics_source_performance(
    db: Session,
    year: int,
    dataset_id: Any = None,
    source_type: str = "auto",
) -> list[dict[str, Any]]:
    active_dataset = dataset_id or get_latest_dataset_id(db)

    if (source_type == "auto" and active_dataset) or source_type == "uploaded":
        return calculate_source_performance_uploaded(db, active_dataset, year)

    return calculate_source_performance_org(db, year)


def get_analytics_source_hierarchy(
    db: Session,
    year: int,
    dataset_id: Any = None,
    source_type: str = "auto",
) -> list[dict[str, Any]]:
    active_dataset = dataset_id or get_latest_dataset_id(db)

    if (source_type == "auto" and active_dataset) or source_type == "uploaded":
        return calculate_source_hierarchy_uploaded(db, active_dataset, year)

    return calculate_source_hierarchy_org(db, year)


def get_analytics_source_detail(
    db: Session,
    year: int,
    main_source: str,
    source: str,
    dataset_id: Any = None,
    source_type: str = "auto",
) -> dict[str, Any] | None:
    active_dataset = dataset_id or get_latest_dataset_id(db)

    if (source_type == "auto" and active_dataset) or source_type == "uploaded":
        return calculate_source_detail_uploaded(
            db, active_dataset, year, main_source, source
        )

    return calculate_source_detail_org(db, year, main_source, source)
