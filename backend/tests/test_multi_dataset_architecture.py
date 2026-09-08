"""
Comprehensive Automated Regression Suite for Multi-Year & Multi-Campus Analytics Architecture.
Validates end-to-end dataset metadata, query execution, ratio metric accuracy, and multi-dataset scope routing.
"""

import pytest
import os
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.analytics.scope_resolver import resolve_dataset_scope
from app.analytics.dashboard import get_dashboard_overview
from app.semantic.sql_builder import build_semantic_metric_query, build_semantic_breakdown_query
from app.agent.tools.metric_tool import MetricTool
from app.agent.tools.breakdown_tool import BreakdownTool
from app.agent.tools.base import ToolRequest
from app.database.repository import (
    enable_dataset_analytics,
    disable_dataset_analytics,
    update_dataset_metadata,
    get_enabled_datasets,
)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_1_dataset_metadata_integrity(db: Session):
    """Test that all 4 production datasets are assigned single reporting years and campuses."""
    rows = db.execute(text("""
        SELECT dataset_name, academic_year, campus_name, row_count, is_analytics_enabled
        FROM system.datasets
        WHERE is_analytics_enabled = TRUE
        ORDER BY academic_year, campus_name
    """)).mappings().all()

    assert len(rows) == 4, f"Expected 4 enabled production datasets, got {len(rows)}"

    dataset_map = {(r["academic_year"], r["campus_name"]): r["row_count"] for r in rows}
    
    assert dataset_map.get((2025, "Mohali")) == 940981
    assert dataset_map.get((2025, "Unnao")) == 302968
    assert dataset_map.get((2026, "Mohali")) == 974328
    assert dataset_map.get((2026, "Unnao")) == 390874


def test_2_mohali_2026_benchmark_preservation(db: Session):
    """Test that the 2026 Mohali validated benchmark metrics remain 100% accurate."""
    tool = MetricTool()

    # 1. Leads = 974,328
    res_leads = tool.execute(db, ToolRequest(metric="leads", year=2026, filters={"campus": "Mohali"}))
    assert res_leads.success
    assert res_leads.metadata["total_value"] == 974328

    # 2. CUCET = 52,107
    res_cucet = tool.execute(db, ToolRequest(metric="cucet", year=2026, filters={"campus": "Mohali"}))
    assert res_cucet.success
    assert res_cucet.metadata["total_value"] == 52107

    # 3. Admissions = 22,546
    res_adm = tool.execute(db, ToolRequest(metric="admission", year=2026, filters={"campus": "Mohali"}))
    assert res_adm.success
    assert res_adm.metadata["total_value"] == 22546

    # 4. Gross Admissions = 30,848
    res_gross = tool.execute(db, ToolRequest(metric="gross_admission", year=2026, filters={"campus": "Mohali"}))
    assert res_gross.success
    assert res_gross.metadata["total_value"] == 30848

    # 5. Refunded = 8,302
    res_ref = tool.execute(db, ToolRequest(metric="refunded", year=2026, filters={"campus": "Mohali"}))
    assert res_ref.success
    assert res_ref.metadata["total_value"] == 8302

    # 6. Conversion Rate = 2.31%
    res_conv = tool.execute(db, ToolRequest(metric="lead_admission_rate", year=2026, filters={"campus": "Mohali"}))
    assert res_conv.success
    assert res_conv.metadata["value"] == 2.31


# ============================================================
# Scope Regression Test Suite (Scopes A through I)
# ============================================================

def test_scope_a_mohali_2026(db: Session):
    """Scope A: Mohali 2026 single-year scope."""
    scope = resolve_dataset_scope(db, campus="Mohali", years=[2026])
    assert len(scope["datasets"]) == 1
    assert scope["cy_year"] == 2026
    assert scope["py_year"] is None

    overview = get_dashboard_overview(db, campus="Mohali", years=[2026])
    assert overview["kpis"]["leads"]["cy"] == 974328
    assert overview["kpis"]["cucet"]["cy"] == 52107
    assert overview["kpis"]["admissions"]["cy"] == 22546
    assert overview["kpis"]["conversion_rate"]["cy"] == 2.31
    assert overview["kpis"]["leads"]["py"] is None


def test_scope_b_mohali_2025(db: Session):
    """Scope B: Mohali 2025 single-year scope."""
    scope = resolve_dataset_scope(db, campus="Mohali", years=[2025])
    assert len(scope["datasets"]) == 1
    assert scope["cy_year"] == 2025
    assert scope["py_year"] is None

    overview = get_dashboard_overview(db, campus="Mohali", years=[2025])
    assert overview["kpis"]["leads"]["cy"] == 940981
    assert overview["kpis"]["leads"]["py"] is None


def test_scope_c_unnao_2026(db: Session):
    """Scope C: Unnao 2026 single-year scope."""
    scope = resolve_dataset_scope(db, campus="Unnao", years=[2026])
    assert len(scope["datasets"]) == 1
    assert scope["cy_year"] == 2026
    assert scope["py_year"] is None

    overview = get_dashboard_overview(db, campus="Unnao", years=[2026])
    assert overview["kpis"]["leads"]["cy"] == 390874
    assert overview["kpis"]["admissions"]["cy"] == 5706
    assert overview["kpis"]["conversion_rate"]["cy"] == 1.46


def test_scope_d_unnao_2025(db: Session):
    """Scope D: Unnao 2025 single-year scope."""
    scope = resolve_dataset_scope(db, campus="Unnao", years=[2025])
    assert len(scope["datasets"]) == 1
    assert scope["cy_year"] == 2025

    overview = get_dashboard_overview(db, campus="Unnao", years=[2025])
    assert overview["kpis"]["leads"]["cy"] == 302968


def test_scope_e_mohali_2025_vs_2026(db: Session):
    """Scope E: Mohali YoY scope (2025 vs 2026)."""
    scope = resolve_dataset_scope(db, campus="Mohali", years=[2025, 2026])
    assert len(scope["datasets"]) == 2
    assert scope["cy_year"] == 2026
    assert scope["py_year"] == 2025

    overview = get_dashboard_overview(db, campus="Mohali", years=[2025, 2026])
    assert overview["kpis"]["leads"]["cy"] == 974328
    assert overview["kpis"]["leads"]["py"] == 940981
    assert overview["kpis"]["admissions"]["cy"] == 22546


def test_scope_f_unnao_2025_vs_2026(db: Session):
    """Scope F: Unnao YoY scope (2025 vs 2026)."""
    scope = resolve_dataset_scope(db, campus="Unnao", years=[2025, 2026])
    assert len(scope["datasets"]) == 2
    assert scope["cy_year"] == 2026
    assert scope["py_year"] == 2025

    overview = get_dashboard_overview(db, campus="Unnao", years=[2025, 2026])
    assert overview["kpis"]["leads"]["cy"] == 390874
    assert overview["kpis"]["leads"]["py"] == 302968


def test_scope_g_all_campuses_2025_vs_2026(db: Session):
    """Scope G: All Campuses YoY scope (2025 vs 2026) - 4 Datasets."""
    scope = resolve_dataset_scope(db, campus="all", years=[2025, 2026])
    assert len(scope["datasets"]) == 4
    assert scope["cy_year"] == 2026
    assert scope["py_year"] == 2025

    overview = get_dashboard_overview(db, campus="all", years=[2025, 2026])
    # 2026 Leads = Mohali (974,328) + Unnao (390,874) = 1,365,202
    assert overview["kpis"]["leads"]["cy"] == 1365202
    # 2025 Leads = Mohali (940,981) + Unnao (302,968) = 1,243,949
    assert overview["kpis"]["leads"]["py"] == 1243949
    # 2026 Admissions = Mohali (22,546) + Unnao (5,706) = 28,252
    assert overview["kpis"]["admissions"]["cy"] == 28252
    # Aggregated conversion rate = 28,252 / 1,365,202 * 100 = 2.07%
    assert overview["kpis"]["conversion_rate"]["cy"] == 2.07


def test_scope_h_single_year_2026(db: Session):
    """Scope H: Single-year 2026 (All Campuses) - 2 Datasets."""
    scope = resolve_dataset_scope(db, campus="all", years=[2026])
    assert len(scope["datasets"]) == 2
    assert scope["cy_year"] == 2026
    assert scope["py_year"] is None

    overview = get_dashboard_overview(db, campus="all", years=[2026])
    assert overview["kpis"]["leads"]["cy"] == 1365202
    assert overview["kpis"]["leads"]["py"] is None


def test_scope_i_single_year_2025(db: Session):
    """Scope I: Single-year 2025 (All Campuses) - 2 Datasets."""
    scope = resolve_dataset_scope(db, campus="all", years=[2025])
    assert len(scope["datasets"]) == 2
    assert scope["cy_year"] == 2025
    assert scope["py_year"] is None

    overview = get_dashboard_overview(db, campus="all", years=[2025])
    assert overview["kpis"]["leads"]["cy"] == 1243949
    assert overview["kpis"]["leads"]["py"] is None


def test_monthly_trend_reconciliation_j_k_l_m(db: Session):
    """Test Scenarios J, K, L, M: Executive Dashboard monthly trend reconciliation across metrics and scopes."""
    from app.analytics.dashboard import get_monthly_trend

    # Scenario J: Mohali 2026 Admissions sum == 22,546
    trend_j = get_monthly_trend(db, campus="Mohali", years=[2026], metric="admissions")
    assert len(trend_j) == 12
    sum_j_adm = sum(m["cy_admission"] for m in trend_j)
    assert sum_j_adm == 22546

    # Scenario K: Mohali 2025 Admissions sum == 930,115
    trend_k = get_monthly_trend(db, campus="Mohali", years=[2025], metric="admissions")
    assert len(trend_k) == 12
    sum_k_adm = sum(m["cy_admission"] for m in trend_k)
    assert sum_k_adm == 930115

    # Scenario L: Mohali 2026 Leads sum == 974,328
    trend_l = get_monthly_trend(db, campus="Mohali", years=[2026], metric="leads")
    assert len(trend_l) == 12
    sum_l_leads = sum(m["cy_leads"] for m in trend_l)
    assert sum_l_leads == 974328

    # Scenario M: All Campuses YoY (2025 vs 2026) totals match scope overview exactly
    trend_m = get_monthly_trend(db, campus="all", years=[2025, 2026], metric="admissions")
    assert len(trend_m) == 12
    sum_m_cy_adm = sum(m["cy_admission"] for m in trend_m)
    sum_m_py_adm = sum(m["py_admission"] for m in trend_m)
    assert sum_m_cy_adm == 28252
    assert sum_m_py_adm == 1232085  # 930,115 (Mohali 2025) + 301,970 (Unnao 2025)


def test_dimension_resolution_and_filter_options(db: Session):
    """Verify get_dashboard_filter_options and dimension alias resolution ('program' -> 'program_name', 'source' -> 'source', 'campus' -> 'campus_name')."""
    from app.analytics.dashboard import get_dashboard_filter_options, get_performance_rankings

    options = get_dashboard_filter_options(db, campus="all", years=[2026])
    assert "campuses" in options
    assert len(options["campuses"]) > 0

    # Test alias resolution for 'source' dimension (returns non-empty improvements/declines for 2026 scope)
    rankings_source = get_performance_rankings(db, dimension="source", campus="all", years=[2026])
    assert isinstance(rankings_source, dict)
    assert "improvements" in rankings_source and "declines" in rankings_source
    assert len(rankings_source["improvements"]) > 0

    # Test alias resolution for 'campus' dimension
    rankings_campus = get_performance_rankings(db, dimension="campus", campus="all", years=[2026])
    assert isinstance(rankings_campus, dict)
    assert len(rankings_campus["improvements"]) > 0

    # Test alias resolution for 'program' dimension (returns dict without UndefinedColumn error)
    rankings_prog = get_performance_rankings(db, dimension="program", campus="all", years=[2026])
    assert isinstance(rankings_prog, dict)
    assert "improvements" in rankings_prog




