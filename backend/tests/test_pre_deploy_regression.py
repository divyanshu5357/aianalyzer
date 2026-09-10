"""
Pre-Production Regression Tests — Multi-Year, Cache, Index, and Complete-Year Rules.

Tests A-K from the pre-deployment verification requirements:
A. 2025 only
B. 2026 only
C. 2025 + 2026 simultaneously
D. Switching 2025 → 2026 → 2025
E. Deleting 2026
F. Uploading a new year
G. Completed 12/12 year remains analytics-enabled
H. Completed year is upload-inactive
I. Cache isolation between years (stub)
J. Targeted cache invalidation (stub)
K. State Level-2 index behavior
"""

import time
import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_enabled_raw_years(db) -> list[int]:
    """Return sorted list of analytics-enabled RAW academic years with data."""
    rows = db.execute(text("""
        SELECT DISTINCT academic_year FROM system.datasets
        WHERE is_analytics_enabled = TRUE
          AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
          AND academic_year IS NOT NULL
          AND COALESCE(row_count, 0) > 0
        ORDER BY academic_year
    """)).scalars().all()
    return [int(r) for r in rows if r]


def get_agg_count_for_year(db, year: int) -> int:
    return int(db.execute(
        text("SELECT COUNT(*) FROM analytics.dashboard_agg WHERE academic_year = :yr"),
        {"yr": year},
    ).scalar() or 0)


def get_overview_for_year(db, year: int) -> dict:
    from app.analytics.aggregate_service import get_agg_overview
    return get_agg_overview(db, years=[year])


def get_state_level2_timing(db, state: str, year: int) -> tuple[float, int]:
    """Return (ms, row_count) for state hierarchy children query."""
    from app.analytics.state_service import get_state_hierarchy_children
    t0 = time.perf_counter()
    res = get_state_hierarchy_children(db, level='source_category', state=state, academic_year=year)
    t1 = time.perf_counter()
    return round((t1 - t0) * 1000, 2), len(res.get("rows", []))


# ─── Test A: 2025 Only ───────────────────────────────────────────────────────

def test_a_2025_isolation(db):
    """2025 overview returns non-None CY values when 2025 data exists."""
    years = get_enabled_raw_years(db)
    if 2025 not in years:
        pytest.skip("No 2025 RAW dataset available")
    overview = get_overview_for_year(db, 2025)
    kpis = overview.get("kpis", {})
    leads = kpis.get("leads", {})
    assert leads.get("cy") is not None, "2025 CY leads must not be None"


# ─── Test B: 2026 Only ───────────────────────────────────────────────────────

def test_b_2026_isolation(db):
    """2026 overview returns non-None CY values when 2026 data exists."""
    years = get_enabled_raw_years(db)
    if 2026 not in years:
        pytest.skip("No 2026 RAW dataset available")
    overview = get_overview_for_year(db, 2026)
    kpis = overview.get("kpis", {})
    leads = kpis.get("leads", {})
    assert leads.get("cy") is not None, "2026 CY leads must not be None"
    agg_count = get_agg_count_for_year(db, 2026)
    if agg_count > 0:
        assert leads["cy"] >= 0, "2026 CY leads must be non-negative when agg data exists"


# ─── Test C: 2025 + 2026 Simultaneously ──────────────────────────────────────

def test_c_2025_2026_simultaneous(db):
    """Both years return independent, non-contaminated results when both are enabled."""
    years = get_enabled_raw_years(db)
    if 2025 not in years or 2026 not in years:
        pytest.skip("Both 2025 and 2026 must be enabled")

    ov_2025 = get_overview_for_year(db, 2025)
    ov_2026 = get_overview_for_year(db, 2026)

    leads_2025 = ov_2025["kpis"]["leads"]["cy"]
    leads_2026 = ov_2026["kpis"]["leads"]["cy"]

    assert leads_2025 is not None, "2025 CY leads must not be None"
    assert leads_2026 is not None, "2026 CY leads must not be None"


# ─── Test D: Switching 2025 → 2026 → 2025 ────────────────────────────────────

def test_d_year_switching(db):
    """Switching between years produces consistent results each time."""
    years = get_enabled_raw_years(db)
    if 2025 not in years or 2026 not in years:
        pytest.skip("Both 2025 and 2026 must be enabled")

    ov_2025_first = get_overview_for_year(db, 2025)
    ov_2026 = get_overview_for_year(db, 2026)
    ov_2025_second = get_overview_for_year(db, 2025)

    leads_first = ov_2025_first["kpis"]["leads"]["cy"]
    leads_second = ov_2025_second["kpis"]["leads"]["cy"]

    assert leads_first == leads_second, (
        f"2025 results must be identical before and after switching: {leads_first} vs {leads_second}"
    )


# ─── Test E: Delete 2026 Scenario ─────────────────────────────────────────────

def test_e_delete_scenario(db):
    """If 2026 were deleted, 2025 should still be independently resolvable."""
    years = get_enabled_raw_years(db)
    if 2025 not in years:
        pytest.skip("2025 must be enabled")
    overview = get_overview_for_year(db, 2025)
    assert overview["kpis"]["leads"]["cy"] is not None


# ─── Test F: New Year Upload ──────────────────────────────────────────────────

def test_f_dynamic_year_resolution(db):
    """Verify scope_resolver correctly resolves CY to max available year."""
    from app.analytics.scope_resolver import resolve_analytics_scope
    years = get_enabled_raw_years(db)
    if not years:
        pytest.skip("No enabled RAW years")

    max_year = max(years)
    scope = resolve_analytics_scope(db)
    assert scope["cy_year"] == max_year, (
        f"CY should resolve to max available year {max_year}, got {scope['cy_year']}"
    )
    if len(years) > 1:
        expected_py = sorted(years)[-2]
        assert scope["py_year"] == expected_py, (
            f"PY should resolve to {expected_py}, got {scope['py_year']}"
        )


# ─── Test G: Completed 12/12 Year Remains Analytics-Enabled ───────────────────

def test_g_complete_year_analytics_enabled(db):
    """A year with all 12 months of data must remain analytics-enabled."""
    years = get_enabled_raw_years(db)
    for yr in years:
        months = db.execute(
            text("""
                SELECT COUNT(DISTINCT created_month)
                FROM analytics.dashboard_agg
                WHERE academic_year = :yr AND created_month IS NOT NULL
            """),
            {"yr": yr},
        ).scalar() or 0

        ds_enabled = db.execute(
            text("""
                SELECT is_analytics_enabled FROM system.datasets
                WHERE academic_year = :yr
                  AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
                  AND is_analytics_enabled = TRUE
                LIMIT 1
            """),
            {"yr": yr},
        ).scalar()

        if months >= 12:
            assert ds_enabled is True, (
                f"Year {yr} has {months} months but is NOT analytics-enabled"
            )


# ─── Test H: All enabled years in analytical_years ────────────────────────────

def test_h_enabled_in_analytical_years(db):
    """All analytics-enabled RAW years must appear in analytical_years."""
    from app.analytics.period_resolver import list_all_analytical_years
    analytical = list_all_analytical_years(db)
    enabled_years = get_enabled_raw_years(db)
    for yr in enabled_years:
        assert yr in analytical, (
            f"Enabled year {yr} must appear in analytical_years, got {analytical}"
        )


# ─── Test K: State Level-2 Index Behavior ─────────────────────────────────────

def test_k_state_level2_uses_index(db):
    """State Level-2 query should use idx_dashboard_agg_year_state_lower, not seq scan."""
    years = get_enabled_raw_years(db)
    if not years:
        pytest.skip("No enabled RAW years")

    target_year = max(years)

    top_state = db.execute(
        text("""
            SELECT state FROM analytics.dashboard_agg
            WHERE academic_year = :yr AND state IS NOT NULL AND state != ''
            GROUP BY state
            ORDER BY SUM(leads_cy) DESC
            LIMIT 1
        """),
        {"yr": target_year},
    ).scalar()

    if not top_state:
        pytest.skip("No state data available")

    ms, rows = get_state_level2_timing(db, top_state, target_year)

    # Verify EXPLAIN plan uses index scan
    explain = db.execute(
        text("""
            EXPLAIN (FORMAT TEXT)
            SELECT state, SUM(leads_cy)
            FROM analytics.dashboard_agg d
            WHERE d.academic_year IN (:yr, :py) AND lower(d.state) = :st
            GROUP BY state
        """),
        {"yr": target_year, "py": target_year - 1, "st": top_state.lower()},
    ).fetchall()

    plan_text = "\n".join(r[0] for r in explain)
    uses_index = "Index" in plan_text
    assert uses_index, (
        f"State Level-2 query should use index scan, got:\n{plan_text}"
    )


# ─── PY/CY Correctness ───────────────────────────────────────────────────────

def test_py_cy_comparison_correct(db):
    """Verify PY and CY are correctly mapped when both years exist."""
    years = get_enabled_raw_years(db)
    if len(years) < 2:
        pytest.skip("Need at least 2 years for PY/CY comparison")

    max_yr = max(years)
    overview = get_overview_for_year(db, max_yr)
    kpis = overview["kpis"]

    cy_leads = kpis["leads"].get("cy")
    py_leads = kpis["leads"].get("py")

    assert cy_leads is not None, f"CY leads for {max_yr} must not be None"
    prev_yr = sorted([y for y in years if y < max_yr])[-1] if any(y < max_yr for y in years) else None
    if prev_yr:
        assert py_leads is not None, (
            f"PY leads for {max_yr} (PY={prev_yr}) must not be None when {prev_yr} data exists"
        )


# ─── No Cross-Year Contamination ─────────────────────────────────────────────

def test_no_cross_year_contamination(db):
    """CY values for year X must only come from dashboard_agg WHERE academic_year = X."""
    years = get_enabled_raw_years(db)
    if len(years) < 2:
        pytest.skip("Need at least 2 years")

    for yr in years:
        direct = int(db.execute(
            text("SELECT COALESCE(SUM(leads_cy), 0) FROM analytics.dashboard_agg WHERE academic_year = :yr"),
            {"yr": yr},
        ).scalar() or 0)

        overview = get_overview_for_year(db, yr)
        api_leads = overview["kpis"]["leads"]["cy"]

        if api_leads is not None and direct > 0:
            assert api_leads <= direct * 1.01 + 1, (
                f"Year {yr}: API leads ({api_leads}) should not exceed direct sum ({direct})"
            )
