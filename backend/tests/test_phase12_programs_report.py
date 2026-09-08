"""
Phase 12 — Program Performance Report automated tests.
Tests lazy hierarchical loading, date/campus filtering, sorting, SQL-injection safety, and refund tracking.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://ai_admin:ai_password@localhost:5433/ai_agent"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.analytics.program_service import get_program_report_top_level, get_program_hierarchy_children


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ─── Level 1: Top-Level ───────────────────────────────────────────────────────

def test_program_report_top_level(db):
    """Verify initial request returns only top-level program groups (~30 rows) and total row."""
    result = get_program_report_top_level(db, academic_year=2026)
    rows = result["rows"]
    total = result["total"]

    # Should return ~33 distinct program groups
    assert len(rows) >= 5, f"Expected at least 5 program groups, got {len(rows)}"
    assert len(rows) <= 50, f"Expected at most 50 program groups, got {len(rows)}"

    # All rows should be level 1 with has_children=True
    for r in rows:
        assert r["level"] == 1, f"Expected level 1, got {r['level']} for {r['program']}"
        assert r["has_children"] is True

    # Total row must exist
    assert total["id"] == "TOTAL"
    assert total["cy_leads"] > 0, "Total CY leads should be positive"
    assert total["cy_adm"] > 0, "Total CY admissions should be positive"
    assert total["net_admissions"] <= total["cy_adm"], "Net admissions cannot exceed gross admissions"


def test_program_report_sorted_by_cy_leads(db):
    """Verify default sort order is cy_leads descending."""
    result = get_program_report_top_level(db, academic_year=2026, sort_by="cy_leads", sort_order="desc")
    leads = [r["cy_leads"] for r in result["rows"]]
    assert leads == sorted(leads, reverse=True), "Rows should be sorted by cy_leads descending"


# ─── Level 2: Branches ───────────────────────────────────────────────────────

def test_program_hierarchy_branch_expansion(db):
    """Verify Level 2 lazy expansion returns branches for B.COM."""
    result = get_program_hierarchy_children(db, level="branch", program_group="B.COM", academic_year=2026)
    rows = result["rows"]

    assert len(rows) >= 3, f"Expected at least 3 B.COM branches, got {len(rows)}"
    for r in rows:
        assert r["level"] == 2
        assert r["has_children"] is True
        assert r["program_group"] == "B.COM"
        assert r["program_code"] is not None


def test_program_hierarchy_branch_expansion_cse(db):
    """Verify Level 2 lazy expansion returns branches for CSE (highest traffic group)."""
    result = get_program_hierarchy_children(db, level="branch", program_group="CSE", academic_year=2026)
    rows = result["rows"]

    assert len(rows) >= 1, "CSE should have at least 1 branch"
    total_cy = sum(r["cy_leads"] for r in rows)
    assert total_cy > 0, "CSE branches should have positive CY leads"


# ─── Level 3: Source Category ─────────────────────────────────────────────────

def test_program_hierarchy_source_category_expansion(db):
    """Verify Level 3 lazy expansion returns source categories for CM201."""
    result = get_program_hierarchy_children(
        db, level="source_category", program_code="CM201", academic_year=2026
    )
    rows = result["rows"]

    assert len(rows) >= 1, "Expected at least 1 source category"
    categories = {r["program"] for r in rows}
    # Should contain at least one known category
    assert bool(categories & {"IN HOUSE", "OUT SOURCED", "OTHERS"}), f"Unexpected categories: {categories}"

    for r in rows:
        assert r["level"] == 3
        assert r["has_children"] is True
        assert r["program_code"] == "CM201"


# ─── Level 4: Sub-Source ─────────────────────────────────────────────────────

def test_program_hierarchy_sub_source_expansion(db):
    """Verify Level 4 lazy expansion returns sub-sources for CM201 + IN HOUSE."""
    result = get_program_hierarchy_children(
        db,
        level="sub_source",
        program_code="CM201",
        source_category="IN HOUSE",
        academic_year=2026,
    )
    rows = result["rows"]

    assert len(rows) >= 1, "Expected at least 1 sub-source"
    for r in rows:
        assert r["level"] == 4
        assert r["has_children"] is False
        assert r["program_code"] == "CM201"
        assert r["source_category"] == "IN HOUSE"


# ─── Date Filtering ───────────────────────────────────────────────────────────

def test_program_report_date_filtering(db):
    """Verify metrics adjust to CY and equivalent PY date window."""
    full = get_program_report_top_level(db, academic_year=2026)
    filtered = get_program_report_top_level(
        db, academic_year=2026, from_date="2026-01-01", to_date="2026-06-30"
    )

    # Date-filtered CY leads should be less than or equal to full-year
    assert filtered["total"]["cy_leads"] <= full["total"]["cy_leads"], \
        "Date-filtered leads should not exceed full-year leads"
    assert filtered["total"]["cy_leads"] > 0, "Filtered leads should still be positive"


def test_program_hierarchy_date_filtering(db):
    """Verify branch-level also respects date filtering."""
    full = get_program_hierarchy_children(db, level="branch", program_group="B.COM", academic_year=2026)
    filtered = get_program_hierarchy_children(
        db, level="branch", program_group="B.COM", academic_year=2026,
        from_date="2026-01-01", to_date="2026-03-31"
    )
    full_total = sum(r["cy_leads"] for r in full["rows"])
    filtered_total = sum(r["cy_leads"] for r in filtered["rows"])

    assert filtered_total <= full_total, "Date-filtered branch leads should not exceed full-year"


# ─── Campus Filtering ─────────────────────────────────────────────────────────

def test_program_report_campus_filtering(db):
    """Verify metrics update when campus is filtered."""
    with engine.connect() as conn:
        campuses = [r[0] for r in conn.execute(
            text("SELECT DISTINCT campus_name FROM analytics.dashboard_agg WHERE academic_year = 2026 LIMIT 3")
        ).fetchall() if r[0]]

    if not campuses:
        pytest.skip("No campuses available for filtering test")

    campus = campuses[0]
    filtered = get_program_report_top_level(db, academic_year=2026, campus=campus)
    assert filtered["total"]["cy_leads"] > 0, f"Campus {campus} should have some leads"
    assert filtered["scope"]["campus"] == campus


# ─── Sorting ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sort_col,sort_order", [
    ("cy_leads", "desc"),
    ("cy_leads", "asc"),
    ("cy_adm", "desc"),
    ("net_admissions", "desc"),
])
def test_program_report_sorting(db, sort_col, sort_order):
    """Verify server-side sorting for all numeric columns (ascending and descending)."""
    result = get_program_report_top_level(db, academic_year=2026, sort_by=sort_col, sort_order=sort_order)
    vals = [r[sort_col] for r in result["rows"]]
    if sort_order == "desc":
        assert vals == sorted(vals, reverse=True), f"Expected desc order for {sort_col}"
    else:
        assert vals == sorted(vals), f"Expected asc order for {sort_col}"


# ─── Total Row ───────────────────────────────────────────────────────────────

def test_total_row_aggregate_percentages(db):
    """Verify total percentage is calculated from aggregate sums, not averaged."""
    result = get_program_report_top_level(db, academic_year=2026)
    total = result["total"]
    rows = result["rows"]

    # Total cy_leads must equal sum of row cy_leads
    row_sum_leads = sum(r["cy_leads"] for r in rows)
    assert total["cy_leads"] == row_sum_leads, \
        f"Total cy_leads {total['cy_leads']} != sum of rows {row_sum_leads}"

    # Total lead_cucet_pct must be computed from aggregate (not average of row pcts)
    expected_pct = round((total["cy_cucet"] / total["cy_leads"]) * 100, 1) if total["cy_leads"] > 0 else 0.0
    assert abs(total["lead_cucet_pct"] - expected_pct) < 0.2, \
        f"Total lead_cucet_pct {total['lead_cucet_pct']} differs from expected {expected_pct}"


# ─── N/A Fee Columns ─────────────────────────────────────────────────────────

def test_fee_paid_na_handling(db):
    """Verify fee paid and net fee paid return clean N/A status for all rows."""
    result = get_program_report_top_level(db, academic_year=2026)
    for r in result["rows"]:
        assert r["fee_paid"] == "N/A", f"Expected 'N/A' for fee_paid in {r['program']}"
        assert r["net_fee_paid_pct"] == "N/A", f"Expected 'N/A' for net_fee_paid_pct in {r['program']}"


# ─── SQL Injection Safety ─────────────────────────────────────────────────────

def test_sql_injection_safety(db):
    """Verify malicious sort columns are rejected and fall back to default."""
    malicious_sort = "1; DROP TABLE users; --"
    result = get_program_report_top_level(db, academic_year=2026, sort_by=malicious_sort)
    # Should not raise an exception and should fall back to cy_leads
    assert result["scope"]["sort_by"] == "cy_leads", \
        f"Expected fallback to cy_leads, got {result['scope']['sort_by']}"


# ─── Refund Tracking ─────────────────────────────────────────────────────────

def test_refund_tracking(db):
    """Verify refund data is tracked and displayed correctly."""
    result = get_program_report_top_level(db, academic_year=2026)
    total = result["total"]

    assert "refund_py_vs_cy" in total
    assert "refund_pct_py_vs_cy" in total
    # Total CY refunds should be non-negative
    assert total["refund_py_vs_cy"]["cy"] >= 0
    # Net admissions = CY admissions - CY refunds
    expected_net = total["cy_adm"] - total["refund_py_vs_cy"]["cy"]
    assert total["net_admissions"] == expected_net, \
        f"Net admissions {total['net_admissions']} != {total['cy_adm']} - {total['refund_py_vs_cy']['cy']} = {expected_net}"
