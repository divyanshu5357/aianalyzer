"""
Immutable Dashboard Regression Baseline Test Suite
Freezes baseline KPI, monthly, and dimension ranking metrics across all 6 canonical scopes:
- Mohali 2025
- Mohali 2026
- Unnao 2025
- Unnao 2026
- All Campuses 2025
- All Campuses 2026
"""

import json
import os
import pytest
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.analytics.aggregate_service import (
    get_agg_overview,
    get_agg_monthly_trend,
    get_agg_performance_rankings,
)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "dashboard_baseline.json")


@pytest.fixture(scope="module")
def baseline_fixture():
    assert os.path.exists(FIXTURE_PATH), f"Baseline fixture missing at {FIXTURE_PATH}"
    with open(FIXTURE_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.parametrize(
    "scope_key,campus_label,year",
    [
        ("Mohali_2025", "Mohali", 2025),
        ("Mohali_2026", "Mohali", 2026),
        ("Unnao_2025", "Unnao", 2025),
        ("Unnao_2026", "Unnao", 2026),
        ("All_Campuses_2025", "all", 2025),
        ("All_Campuses_2026", "all", 2026),
    ],
)
def test_dashboard_canonical_kpis_and_monthly_baseline(
    db: Session, baseline_fixture, scope_key: str, campus_label: str, year: int
):
    """Verify that current overview KPIs match the frozen canonical baseline fixture exactly."""
    expected = baseline_fixture[scope_key]
    years = [year]

    # 1. KPI Overview Verification
    overview = get_agg_overview(db, campus=campus_label, years=years)
    kpis = overview["kpis"]

    assert kpis["leads"]["cy"] == expected["kpis"]["leads"], f"Leads mismatch in {scope_key}"
    assert kpis["cucet"]["cy"] == expected["kpis"]["cucet"], f"CUCET mismatch in {scope_key}"
    assert kpis["admissions"]["cy"] == expected["kpis"]["admission"], f"Admission mismatch in {scope_key}"

    rate_diff = abs(kpis["conversion_rate"]["cy"] - expected["kpis"]["conversion_rate"])
    assert rate_diff <= 0.05, f"Conversion rate mismatch in {scope_key}: {kpis['conversion_rate']['cy']} vs {expected['kpis']['conversion_rate']}"

    # 2. Monthly Progression Verification
    monthly = get_agg_monthly_trend(db, campus=campus_label, years=years)
    assert len(monthly) == len(expected["monthly_totals"]), f"Monthly length mismatch in {scope_key}"

    for curr_m, exp_m in zip(monthly, expected["monthly_totals"]):
        assert curr_m["month"] == exp_m["month"], f"Month name mismatch in {scope_key}"
        assert curr_m["cy_leads"] == exp_m["cy_leads"], f"Monthly leads mismatch in {scope_key} ({curr_m['month']})"
        assert curr_m["cy_cucet"] == exp_m["cy_cucet"], f"Monthly cucet mismatch in {scope_key} ({curr_m['month']})"
        assert curr_m["cy_admission"] == exp_m["cy_admission"], f"Monthly admission mismatch in {scope_key} ({curr_m['month']})"

    # 3. Source Rankings Top Drivers Verification
    source_rankings = get_agg_performance_rankings(db, dimension="source", campus=campus_label, years=years)
    exp_sources = expected["source_rankings"]["top_drivers"]
    curr_sources = source_rankings["improvements"][:5]

    for curr_s, exp_s in zip(curr_sources, exp_sources):
        assert curr_s["entity"] == exp_s["entity"], f"Source entity mismatch in {scope_key}"
        assert curr_s["cy_leads"] == exp_s["cy_leads"], f"Source cy_leads mismatch in {scope_key}"
        assert curr_s["cy_admission"] == exp_s["cy_admission"], f"Source cy_admission mismatch in {scope_key}"
