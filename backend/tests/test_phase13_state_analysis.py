"""
Phase 13 — State-Wise Analysis automated test suite.
Tests lazy hierarchical loading (State -> Source Category -> Sub-Source),
PY/CY comparison, date/campus filtering, server-side sorting, status indicators,
total row percentage correctness, zero-denominator safety, and large-scale performance.
"""

import time
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://ai_admin:ai_password@localhost:5433/ai_agent"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.analytics.state_service import (
    get_state_report_top_level,
    get_state_hierarchy_children,
    _calculate_row_metrics,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ─── 1. State-Level Aggregation & Structure ──────────────────────────────────

def test_state_report_top_level(db):
    """Verify initial request returns only top-level states and scope total row."""
    result = get_state_report_top_level(db, academic_year=2026)
    rows = result["rows"]
    total = result["total"]

    assert len(rows) >= 10, f"Expected at least 10 states, got {len(rows)}"
    assert result["count"] == len(rows)

    # All Level 1 rows must have level=1 and has_children=True
    for r in rows:
        assert r["level"] == 1, f"Expected level 1, got {r['level']} for {r['name']}"
        assert r["has_children"] is True
        assert r["status_indicator"] in ("positive", "negative", "neutral")
        assert "lead_trend" in r
        assert isinstance(r["lead_trend"], list)

    # Total row must be level 0 and has_children=False
    assert total["id"] == "TOTAL"
    assert total["level"] == 0
    assert total["has_children"] is False
    assert total["cy_leads"] > 0
    assert total["cy_adm"] > 0


# ─── 2. PY vs CY Comparison & Variances ──────────────────────────────────────

def test_py_vs_cy_comparison(db):
    """Verify PY and CY lead and admission metrics and variance calculations."""
    result = get_state_report_top_level(db, academic_year=2026)
    total = result["total"]

    # In 2026 dataset, total CY leads are 982,913 and PY leads are 940,981
    assert total["cy_leads"] == 982913
    assert total["py_leads"] == 940981
    assert total["var_leads"] == total["cy_leads"] - total["py_leads"]
    assert total["var_adm"] == total["cy_adm"] - total["py_adm"]


# ─── 3. Dynamic Date Range Filtering ─────────────────────────────────────────

def test_date_range_filtering(db):
    """Verify real backend date filtering updates lead and admission counts."""
    # Filter for first quarter only (2026-01 to 2026-03)
    filtered = get_state_report_top_level(
        db,
        academic_year=2026,
        from_date="2026-01-01",
        to_date="2026-03-31",
    )
    unfiltered = get_state_report_top_level(db, academic_year=2026)

    filt_leads = filtered["total"]["cy_leads"]
    unfilt_leads = unfiltered["total"]["cy_leads"]

    assert filt_leads > 0, "Filtered period should have non-zero leads"
    assert filt_leads < unfilt_leads, f"Filtered leads ({filt_leads}) must be less than full year ({unfilt_leads})"
    assert filtered["scope"]["from_date"] == "2026-01-01"
    assert filtered["scope"]["to_date"] == "2026-03-31"


# ─── 4. Campus Filtering ─────────────────────────────────────────────────────

def test_campus_filtering(db):
    """Verify filtering by campus restricts metrics to that campus."""
    mohali_res = get_state_report_top_level(db, academic_year=2026, campus="Mohali")
    all_res = get_state_report_top_level(db, academic_year=2026, campus="All Campuses")

    assert mohali_res["total"]["cy_leads"] > 0
    assert mohali_res["total"]["cy_leads"] <= all_res["total"]["cy_leads"]
    assert mohali_res["scope"]["campus"].lower() == "mohali"


# ─── 5. Level 2: State Expansion (Source Category) ───────────────────────────

def test_state_expansion_punjab(db):
    """Verify Level 2 expansion returns source categories for Punjab."""
    result = get_state_hierarchy_children(
        db,
        level="source_category",
        state="Punjab",
        academic_year=2026,
    )
    rows = result["rows"]

    assert len(rows) >= 1, "Expected at least 1 source category for Punjab"
    categories = {r["name"] for r in rows}
    # Should contain standard categories
    assert bool(categories & {"IN HOUSE", "OUT SOURCED", "OTHERS"}), f"Unexpected categories: {categories}"

    for r in rows:
        assert r["level"] == 2
        assert r["has_children"] is True
        assert r["cy_leads"] > 0
        assert r["state"] == "Punjab"


# ─── 6. Level 3: Source Category Expansion (Sub-Source) ──────────────────────

def test_source_category_expansion_in_house(db):
    """Verify Level 3 expansion returns sub-sources for Punjab + IN HOUSE."""
    result = get_state_hierarchy_children(
        db,
        level="sub_source",
        state="Punjab",
        source_category="IN HOUSE",
        academic_year=2026,
    )
    rows = result["rows"]

    assert len(rows) >= 3, f"Expected at least 3 sub-sources, got {len(rows)}"
    sub_source_names = {r["name"] for r in rows}
    # Expected known in-house sub-sources like Google, Website, Direct, etc.
    assert bool(sub_source_names & {"Google", "Website", "Direct", "Quick Add Form"}), f"Unexpected sub-sources: {sub_source_names}"

    for r in rows:
        assert r["level"] == 3
        assert r["has_children"] is False, "Level 3 sub-sources must be leaf nodes"
        assert r["state"] == "Punjab"
        assert r["source_category"] == "IN HOUSE"


# ─── 7. Server-Side Sorting ──────────────────────────────────────────────────

def test_sorting_ascending_and_descending(db):
    """Verify server-side sorting works for ascending and descending directions."""
    # Descending cy_leads
    desc_res = get_state_report_top_level(db, academic_year=2026, sort_by="cy_leads", sort_order="desc")
    desc_leads = [r["cy_leads"] for r in desc_res["rows"]]
    assert desc_leads == sorted(desc_leads, reverse=True)

    # Ascending cy_leads
    asc_res = get_state_report_top_level(db, academic_year=2026, sort_by="cy_leads", sort_order="asc")
    asc_leads = [r["cy_leads"] for r in asc_res["rows"]]
    assert asc_leads == sorted(asc_leads)

    # State name alphabetical sorting
    name_asc_res = get_state_report_top_level(db, academic_year=2026, sort_by="state", sort_order="asc")
    names = [r["name"] for r in name_asc_res["rows"]]
    assert names == sorted(names)


# ─── 8. Total Row Math Correctness ───────────────────────────────────────────

def test_total_row_percentage_math(db):
    """Verify total row conversion rates are computed from total distinct sums, NOT averaged."""
    res = get_state_report_top_level(db, academic_year=2026)
    tot = res["total"]

    # Total CUCET / Total Leads
    expected_cucet_pct = round((tot["cy_cucet"] / tot["cy_leads"]) * 100, 1)
    assert tot["lead_cucet_pct"] == expected_cucet_pct

    # Total Adm / Total Leads
    expected_adm_pct = round((tot["cy_adm"] / tot["cy_leads"]) * 100, 1)
    assert tot["lead_adm_pct"] == expected_adm_pct

    # Total Adm / Total CUCET
    expected_cucet_adm_pct = round((tot["cy_adm"] / tot["cy_cucet"]) * 100, 1)
    assert tot["cucet_adm_pct"] == expected_cucet_adm_pct


# ─── 9. Zero Denominator Safety ──────────────────────────────────────────────

def test_zero_denominator_handling():
    """Verify helper handles zero leads and zero admissions gracefully without ZeroDivisionError."""
    row = _calculate_row_metrics(
        name="TEST_ZERO",
        py_leads=0,
        cy_leads=0,
        py_cucet=0,
        cy_cucet=0,
        py_adm=0,
        cy_adm=0,
        py_refunds=0,
        cy_refunds=0,
        lead_trend=[],
        node_id="test:zero",
        level=1,
        has_children=False,
    )
    assert row["lead_cucet_pct"] == 0.0
    assert row["lead_adm_pct"] == 0.0
    assert row["cucet_adm_pct"] == 0.0
    assert row["var_leads_pct"] == 0.0
    assert row["status_indicator"] == "neutral"


# ─── 10. Status Indicator Logic ──────────────────────────────────────────────

def test_status_indicator_logic(db):
    """Verify green/red/neutral status indicators reflect CY vs PY performance."""
    res = get_state_report_top_level(db, academic_year=2026)
    for r in res["rows"]:
        if r["cy_leads"] > r["py_leads"]:
            assert r["status_indicator"] == "positive"
        elif r["cy_leads"] < r["py_leads"]:
            assert r["status_indicator"] == "negative"
        else:
            assert r["status_indicator"] == "neutral"


# ─── 11. Missing PY Period Handling ──────────────────────────────────────────

def test_missing_py_period(db):
    """Verify when PY period is unavailable (e.g. year 2024 with no 2023 data), returns None/neutral."""
    res = get_state_report_top_level(db, academic_year=2024)
    # 2023 has no data in dashboard_agg
    assert res["scope"]["py_available"] is False
    total = res["total"]
    assert total["status_indicator"] == "neutral"


# ─── 12. Query Latency Performance on 1.25M records ──────────────────────────

def test_query_performance_on_large_scale(db):
    """Verify top-level state query completes in under 600ms on 1.25M records."""
    # Warmup cache
    get_state_report_top_level(db, academic_year=2026)
    t0 = time.time()
    res = get_state_report_top_level(db, academic_year=2026)
    dur = time.time() - t0
    assert dur < 0.6, f"State report query took {dur:.3f}s (must be < 0.6s)"
    assert res["count"] > 0


# ─── 13. API Route Tests ─────────────────────────────────────────────────────

def test_api_state_report_endpoint():
    """Verify GET /api/states/report endpoint returns 200 with complete data structure."""
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/states/report?academic_year=2026&sort_by=cy_leads&sort_order=desc")
    assert resp.status_code == 200
    json_data = resp.json()
    assert json_data["success"] is True
    assert "data" in json_data
    data = json_data["data"]
    assert len(data["rows"]) >= 10
    assert data["total"]["cy_leads"] == 982913


def test_api_state_children_endpoint():
    """Verify GET /api/states/report/children returns children for valid level."""
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # Level 2
    resp_l2 = client.get("/api/states/report/children?level=source_category&state=Punjab&academic_year=2026")
    assert resp_l2.status_code == 200
    assert resp_l2.json()["success"] is True
    assert len(resp_l2.json()["data"]["rows"]) >= 1

    # Level 3
    resp_l3 = client.get("/api/states/report/children?level=sub_source&state=Punjab&source_category=IN%20HOUSE&academic_year=2026")
    assert resp_l3.status_code == 200
    assert resp_l3.json()["success"] is True
    assert len(resp_l3.json()["data"]["rows"]) >= 1


def test_api_state_validation_errors():
    """Verify bad requests return clean 400 errors, not 500 crashes."""
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # Invalid level
    resp_bad_level = client.get("/api/states/report/children?level=bad_level&state=Punjab")
    assert resp_bad_level.status_code == 400
    assert "Invalid hierarchy level" in resp_bad_level.json()["detail"]

    # Missing source_category for sub_source
    resp_missing_cat = client.get("/api/states/report/children?level=sub_source&state=Punjab")
    assert resp_missing_cat.status_code == 400
    assert "Parameter 'source_category' is required" in resp_missing_cat.json()["detail"]

