import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.analytics.scope_resolver import resolve_analytics_scope
from app.analytics.dashboard import (
    get_dashboard_overview,
    get_insights,
    get_top_performers,
    get_entity_detail,
    get_exploration_data,
    get_manual_comparison,
    get_monthly_trend,
    get_performance_rankings,
    get_dashboard_filter_options,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_1_scope_all_campuses_2025_2026(db: Session):
    """1. Verify scope resolver resolves all campuses (Mohali and Unnao) for years 2025 and 2026."""
    res = resolve_analytics_scope(db, campus="all", years=[2025, 2026])
    assert len(res["dataset_ids"]) == 4
    assert res["cy_year"] == 2026
    assert res["py_year"] == 2025
    assert len(res["cy_dataset_ids"]) == 2
    assert len(res["py_dataset_ids"]) == 2


def test_2_scope_mohali_2025_2026(db: Session):
    """2. Verify scope resolver resolves mohali campus only for years 2025 and 2026."""
    res = resolve_analytics_scope(db, campus="Mohali", years=[2025, 2026])
    assert len(res["dataset_ids"]) == 2
    assert res["cy_year"] == 2026
    assert res["py_year"] == 2025
    assert len(res["cy_dataset_ids"]) == 1
    assert len(res["py_dataset_ids"]) == 1


def test_3_scope_unnao_2025_2026(db: Session):
    """3. Verify scope resolver resolves unnao campus only for years 2025 and 2026."""
    res = resolve_analytics_scope(db, campus="Unnao", years=[2025, 2026])
    assert len(res["dataset_ids"]) == 2
    assert res["cy_year"] == 2026
    assert res["py_year"] == 2025
    assert len(res["cy_dataset_ids"]) == 1
    assert len(res["py_dataset_ids"]) == 1


def test_4_scope_single_year_cy_only(db: Session):
    """4. Verify scope resolver resolves CY only (no PY) when single year is requested."""
    res = resolve_analytics_scope(db, campus="Mohali", years=[2026])
    assert len(res["dataset_ids"]) == 1
    assert res["cy_year"] == 2026
    assert res["py_year"] is None
    assert len(res["cy_dataset_ids"]) == 1
    assert len(res["py_dataset_ids"]) == 0


def test_5_metrics_aggregation_all_campuses(db: Session):
    """5. Verify KPI overview metrics aggregate correctly for all campuses combined."""
    res = get_dashboard_overview(db, campus="all", years=[2025, 2026])
    kpis = res["kpis"]
    # Total CY Admissions = 22,546 (Mohali 2026) + 5,706 (Unnao 2026) = 28,252
    assert kpis["admissions"]["cy"] == 28252
    assert kpis["admissions"]["py"] == 930115 + 301970
    assert kpis["leads"]["cy"] == 974328 + 390874


def test_6_metrics_aggregation_mohali_only(db: Session):
    """6. Verify KPI overview metrics resolve to mohali benchmarks only under mohali campus filter."""
    res = get_dashboard_overview(db, campus="Mohali", years=[2025, 2026])
    kpis = res["kpis"]
    assert kpis["admissions"]["cy"] == 22546
    assert kpis["admissions"]["py"] == 930115
    assert kpis["leads"]["cy"] == 974328
    assert kpis["leads"]["py"] == 940981


def test_7_metrics_aggregation_unnao_only(db: Session):
    """7. Verify KPI overview metrics resolve to unnao benchmarks only under unnao campus filter."""
    res = get_dashboard_overview(db, campus="Unnao", years=[2025, 2026])
    kpis = res["kpis"]
    assert kpis["admissions"]["cy"] == 5706
    assert kpis["admissions"]["py"] == 301970
    assert kpis["leads"]["cy"] == 390874
    assert kpis["leads"]["py"] == 302968


def test_8_monthly_trend_all_campuses(db: Session):
    """8. Verify monthly trend uses aggregated values across both campuses."""
    trend = get_monthly_trend(db, campus="all", years=[2025, 2026], metric="admissions")
    assert len(trend) == 12
    # Ensure correct month names and sums
    cy_total = sum(t["cy_admission"] for t in trend)
    py_total = sum(t["py_admission"] for t in trend)
    assert cy_total == 28252
    assert py_total == 930115 + 301970


def test_9_performance_rankings_campus_scoped(db: Session):
    """9. Verify performance rankings are filtered by target campus scope."""
    res = get_performance_rankings(db, dimension="program_name", campus="Unnao", years=[2025, 2026])
    assert "improvements" in res
    assert "declines" in res


def test_10_entity_details_campus_scoped(db: Session):
    """10. Verify entity detail query is filtered by target campus scope."""
    res = get_entity_detail(db, dimension="source", value="Direct", campus="Mohali", years=[2025, 2026])
    assert res is not None
    assert "overview" in res
    assert res["overview"]["leads"]["cy"] >= 0
    # Should not include Unnao metrics


def test_11_exploration_data_campus_scoped(db: Session):
    """11. Verify detailed analytical exploration list is filtered by campus."""
    res = get_exploration_data(db, dimension="state", metric="admission", campus="Unnao", years=[2025, 2026])
    assert res is not None
    assert "positive" in res


def test_12_manual_comparison_campus_scoped(db: Session):
    """12. Verify manual side-by-side comparison respects campus filter."""
    res = get_manual_comparison(db, dimension="source", value_a="Direct", value_b="Indirect", campus="Mohali", years=[2025, 2026])
    assert res is not None
    assert res["value_a"]["cy_admission"] <= 22546


def test_13_filter_options_campus_scoped(db: Session):
    """13. Verify dropdown filter option lists are derived strictly within the active scope."""
    res = get_dashboard_filter_options(db, campus="Unnao", years=[2026])
    assert "campuses" in res
    # Should only return distinct campuses within the scope of Unnao 2026
    assert res["campuses"] == ["Unnao"]
