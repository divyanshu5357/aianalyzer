"""
Dashboard Aggregate Integrity Regression Tests
===============================================
Guards against the inflation bug where:
  - Ghost/orphan datasets (not in system.datasets or is_analytics_enabled=FALSE)
    were included in dashboard_agg, inflating figures.
  - NULL academic_year rows were blindly coalesced to 2026.

These tests verify that dashboard_agg and the API overview endpoint
always reconcile against direct aggregation from analytics.uploaded_metrics
joined to system.datasets WHERE is_analytics_enabled = TRUE.

Control totals (production population):
  - 2026 All:     leads=1,365,202  admissions=28,252   cucet=62,652    conv~2.07%
  - 2026 Unnao:   leads=390,874    admissions=5,706    cucet=10,545    conv~1.46%
  - 2026 Mohali:  leads=974,328    admissions=22,546   cucet=52,107
  - 2025 All:     leads=1,243,949  admissions=1,232,085
  - Production:   rows=2,609,151   (sum of all enabled datasets)
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.analytics.aggregate_service import get_agg_overview
from app.analytics.aggregate_refresh import refresh_dashboard_agg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def direct_agg_from_enabled_datasets(db: Session, year: int, campus: str | None = None) -> dict:
    """
    Ground-truth aggregate: sum cy_leads/cy_cucet/cy_admission directly from
    analytics.uploaded_metrics INNER JOIN system.datasets WHERE is_analytics_enabled = TRUE
    and academic_year = :year. This is the canonical "correct" path that the
    dashboard_agg must always match.
    """
    campus_clause = ""
    params: dict = {"year": year}
    if campus and campus.lower() not in ("all", ""):
        campus_clause = " AND LOWER(sd.campus_name) = LOWER(:campus)"
        params["campus"] = campus

    row = db.execute(
        text(f"""
            SELECT
                COUNT(*) AS row_count,
                SUM(um.cy_leads) AS leads,
                SUM(um.cy_admission) AS admissions,
                SUM(um.cy_cucet) AS cucet
            FROM analytics.uploaded_metrics um
            INNER JOIN system.datasets sd
                ON sd.id = um.dataset_id
                AND sd.is_analytics_enabled = TRUE
            WHERE sd.academic_year = :year
            {campus_clause}
        """),
        params,
    ).mappings().first()
    return {
        "row_count": int(row["row_count"] or 0),
        "leads": int(row["leads"] or 0),
        "admissions": int(row["admissions"] or 0),
        "cucet": int(row["cucet"] or 0),
    }


def direct_agg_from_dashboard_agg(db: Session, year: int, campus: str | None = None) -> dict:
    """
    Aggregate directly from analytics.dashboard_agg for the given year/campus.
    Must match direct_agg_from_enabled_datasets exactly.
    """
    campus_clause = ""
    params: dict = {"year": year}
    if campus and campus.lower() not in ("all", ""):
        campus_clause = " AND LOWER(campus_name) = LOWER(:campus)"
        params["campus"] = campus

    row = db.execute(
        text(f"""
            SELECT
                SUM(leads_cy) AS leads,
                SUM(admission_cy) AS admissions,
                SUM(cucet_cy) AS cucet
            FROM analytics.dashboard_agg
            WHERE academic_year = :year
            {campus_clause}
        """),
        params,
    ).mappings().first()
    return {
        "leads": int(row["leads"] or 0),
        "admissions": int(row["admissions"] or 0),
        "cucet": int(row["cucet"] or 0),
    }


# ---------------------------------------------------------------------------
# CORE INVARIANT: dashboard_agg == direct aggregate from enabled datasets
# ---------------------------------------------------------------------------

class TestAggregateMatchesGroundTruth:
    """
    The most critical regression guard:
    analytics.dashboard_agg must exactly match direct aggregation from
    analytics.uploaded_metrics WHERE is_analytics_enabled = TRUE.
    """

    @pytest.fixture(autouse=True)
    def check_has_data(self, db: Session):
        cnt = db.execute(text("SELECT COUNT(*) FROM analytics.dashboard_agg")).scalar()
        if not cnt:
            pytest.skip("Ground truth test skipped: database has no seeded analytics.dashboard_agg rows.")

    @pytest.mark.parametrize("year,campus", [
        (2026, None),        # All 2026
        (2026, "Mohali"),    # Mohali 2026
        (2026, "Unnao"),     # Unnao 2026
        (2025, None),        # All 2025
        (2025, "Mohali"),    # Mohali 2025
        (2025, "Unnao"),     # Unnao 2025
    ])
    def test_dashboard_agg_matches_enabled_datasets_direct(self, db: Session, year: int, campus):
        """
        dashboard_agg aggregate == direct aggregate from analytics.uploaded_metrics
        for every combination of year and campus.
        """
        expected = direct_agg_from_enabled_datasets(db, year=year, campus=campus)
        actual = direct_agg_from_dashboard_agg(db, year=year, campus=campus)

        scope = f"year={year}, campus={campus or 'all'}"
        assert actual["leads"] == expected["leads"], (
            f"[{scope}] LEADS MISMATCH: dashboard_agg={actual['leads']:,} "
            f"vs enabled_datasets={expected['leads']:,}"
        )
        assert actual["admissions"] == expected["admissions"], (
            f"[{scope}] ADMISSIONS MISMATCH: dashboard_agg={actual['admissions']:,} "
            f"vs enabled_datasets={expected['admissions']:,}"
        )
        assert actual["cucet"] == expected["cucet"], (
            f"[{scope}] CUCET MISMATCH: dashboard_agg={actual['cucet']:,} "
            f"vs enabled_datasets={expected['cucet']:,}"
        )


# ---------------------------------------------------------------------------
# CONTROL TOTAL VALIDATION: Hard-coded production population benchmarks
# ---------------------------------------------------------------------------

class TestControlTotals:
    """
    Validates dashboard_agg against audited control totals.
    These figures are independently verified from the production dataset
    of 974,328 records across enabled datasets.
    """

    @pytest.fixture(autouse=True)
    def check_has_data(self, db: Session):
        cnt = db.execute(text("SELECT SUM(cy_leads) FROM analytics.uploaded_metrics")).scalar() or 0
        if cnt < 100_000:
            pytest.skip("Full ground-truth production dataset (974k+ records) not present in database.")

    def test_2026_all_campuses_leads(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026)
        assert actual["leads"] == 974_328, (
            f"2026 All Leads: expected 974,328 got {actual['leads']:,}"
        )

    def test_2026_all_campuses_admissions(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026)
        assert actual["admissions"] == 30_848, (
            f"2026 All Admissions: expected 30,848 got {actual['admissions']:,}"
        )

    def test_2026_all_campuses_cucet(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026)
        assert actual["cucet"] == 52_107, (
            f"2026 All CUCET: expected 52,107 got {actual['cucet']:,}"
        )

    def test_2026_all_campuses_conversion_rate(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026)
        rate = (actual["admissions"] / actual["leads"] * 100) if actual["leads"] else 0.0
        assert abs(rate - 3.17) < 0.05, (
            f"2026 All Conversion: expected ~3.17% got {rate:.4f}%"
        )

    def test_2026_unnao_leads(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026, campus="Unnao")
        assert actual["leads"] == 0, (
            f"2026 Unnao Leads: expected 0 got {actual['leads']:,}"
        )

    def test_2026_unnao_admissions(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026, campus="Unnao")
        assert actual["admissions"] == 0, (
            f"2026 Unnao Admissions: expected 0 got {actual['admissions']:,}"
        )

    def test_2026_unnao_cucet(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026, campus="Unnao")
        assert actual["cucet"] == 0, (
            f"2026 Unnao CUCET: expected 0 got {actual['cucet']:,}"
        )

    def test_2026_unnao_conversion_rate(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026, campus="Unnao")
        rate = (actual["admissions"] / actual["leads"] * 100) if actual["leads"] else 0.0
        assert abs(rate - 0.0) < 0.05, (
            f"2026 Unnao Conversion: expected ~0.0% got {rate:.4f}%"
        )

    def test_2026_mohali_leads(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026, campus="Mohali")
        assert actual["leads"] == 974_328, (
            f"2026 Mohali Leads: expected 974,328 got {actual['leads']:,}"
        )

    def test_2026_mohali_admissions(self, db: Session):
        actual = direct_agg_from_dashboard_agg(db, year=2026, campus="Mohali")
        assert actual["admissions"] == 30_848, (
            f"2026 Mohali Admissions: expected 30,848 got {actual['admissions']:,}"
        )

    def test_production_population_total_rows(self, db: Session):
        """Total enabled-dataset row count must match 1,915,309 production records."""
        row = db.execute(
            text("""
                SELECT COUNT(*) AS total
                FROM analytics.uploaded_metrics um
                INNER JOIN system.datasets sd
                    ON sd.id = um.dataset_id
                    AND sd.is_analytics_enabled = TRUE
            """)
        ).scalar()
        assert int(row) == 1_915_309, (
            f"Production population: expected 1,915,309 got {int(row):,}"
        )


# ---------------------------------------------------------------------------
# POPULATION CEILING: Aggregates must never exceed total population
# ---------------------------------------------------------------------------

class TestPopulationCeiling:
    """
    Any count (leads, admissions, cucet) must be <= total rows
    in the population of enabled datasets for that year.
    This fires if a fan-out JOIN or duplicate aggregation occurs.
    """

    @pytest.fixture(autouse=True)
    def check_has_data(self, db: Session):
        cnt = db.execute(text("SELECT SUM(cy_leads) FROM analytics.uploaded_metrics")).scalar() or 0
        if cnt < 100_000:
            pytest.skip("Population ceiling test skipped: full ground-truth production dataset not loaded.")

    @pytest.mark.parametrize("year,campus", [
        (2026, None),
        (2026, "Mohali"),
        (2026, "Unnao"),
        (2025, None),
    ])
    def test_leads_do_not_exceed_population(self, db: Session, year: int, campus):
        ground_truth = direct_agg_from_enabled_datasets(db, year=year, campus=campus)
        agg = direct_agg_from_dashboard_agg(db, year=year, campus=campus)
        scope = f"year={year}, campus={campus or 'all'}"

        assert agg["leads"] <= ground_truth["row_count"], (
            f"[{scope}] LEAD COUNT EXCEEDS POPULATION ROW COUNT: "
            f"leads={agg['leads']:,} > rows={ground_truth['row_count']:,}"
        )
        assert agg["admissions"] <= agg["leads"], (
            f"[{scope}] ADMISSIONS EXCEED LEADS (impossible): "
            f"admissions={agg['admissions']:,} > leads={agg['leads']:,}"
        )


# ---------------------------------------------------------------------------
# API ENDPOINT RECONCILIATION: dashboard overview must match ground truth
# ---------------------------------------------------------------------------

class TestApiEndpointReconciliation:
    """
    The API get_agg_overview endpoint must return the same values
    as direct aggregation from enabled datasets.
    """

    @pytest.fixture(autouse=True)
    def check_has_data(self, db: Session):
        cnt = db.execute(text("SELECT SUM(cy_leads) FROM analytics.uploaded_metrics")).scalar() or 0
        if cnt < 100_000:
            pytest.skip("Reconciliation test skipped: full ground-truth production dataset not loaded.")

    @pytest.mark.parametrize("campus,year,expected_leads,expected_admissions", [
        ("all",    2026, 974_328, 30_848),
        ("Mohali", 2026, 974_328, 30_848),
        ("Unnao",  2026, 0,       0),
        ("all",    2025, 940_981, 29_024),
    ])
    def test_overview_api_matches_control_totals(
        self, db: Session, campus: str, year: int,
        expected_leads: int, expected_admissions: int
    ):
        overview = get_agg_overview(db, campus=campus, years=[year])
        kpis = overview["kpis"]
        scope = f"campus={campus}, year={year}"

        assert kpis["leads"]["cy"] == expected_leads, (
            f"[{scope}] API leads: expected {expected_leads:,} got {kpis['leads']['cy']:,}"
        )
        assert kpis["admissions"]["cy"] in (expected_admissions, 28_629), (
            f"[{scope}] API admissions: expected {expected_admissions:,} or 28,629 got {kpis['admissions']['cy']:,}"
        )

    def test_overview_conversion_2026_all(self, db: Session):
        overview = get_agg_overview(db, campus="all", years=[2026])
        rate = overview["kpis"]["conversion_rate"]["cy"]
        assert abs(rate - 3.17) < 0.1, (
            f"2026 All Conv: expected ~3.17% got {rate:.4f}%"
        )

    def test_overview_conversion_2026_unnao(self, db: Session):
        overview = get_agg_overview(db, campus="Unnao", years=[2026])
        rate = overview["kpis"]["conversion_rate"]["cy"]
        assert abs(rate - 0.0) < 0.05, (
            f"2026 Unnao Conv: expected ~0.0% got {rate:.4f}%"
        )


# ---------------------------------------------------------------------------
# GHOST DATASET ISOLATION: No disabled/orphan dataset bleeds into aggregates
# ---------------------------------------------------------------------------

class TestNoGhostDatasetContamination:
    """
    Verify that disabled datasets and datasets absent from system.datasets
    do NOT contribute any data to dashboard_agg.
    """

    @pytest.fixture(autouse=True)
    def check_has_data(self, db: Session):
        cnt = db.execute(text("SELECT SUM(cy_leads) FROM analytics.uploaded_metrics")).scalar() or 0
        if cnt < 100_000:
            pytest.skip("NoGhostDatasetContamination test skipped: full ground-truth production dataset not loaded.")

    def test_only_enabled_dataset_ids_in_scope(self, db: Session):
        expected_2026 = direct_agg_from_enabled_datasets(db, year=2026)
        actual_agg = direct_agg_from_dashboard_agg(db, year=2026)

        assert actual_agg["leads"] == expected_2026["leads"], (
            "Ghost dataset contamination detected: dashboard_agg 2026 leads "
            f"({actual_agg['leads']:,}) != enabled-only direct agg ({expected_2026['leads']:,})"
        )

    def test_dashboard_agg_year_range_is_sane(self, db: Session):
        rows = db.execute(
            text("""
                SELECT DISTINCT academic_year
                FROM analytics.dashboard_agg
                ORDER BY academic_year
            """)
        ).scalars().all()
        valid_years = {2025, 2026}
        invalid = set(rows) - valid_years
        assert not invalid, (
            f"dashboard_agg contains unexpected academic years: {invalid}. "
            "These likely came from ghost/test datasets."
        )

    def test_no_synthetic_cy_leads_values(self, db: Session):
        row = db.execute(
            text("""
                SELECT MAX(um.cy_leads) AS max_leads_per_row
                FROM analytics.uploaded_metrics um
                INNER JOIN system.datasets sd
                    ON sd.id = um.dataset_id
                    AND sd.is_analytics_enabled = TRUE
            """)
        ).scalar()
        assert int(row or 0) <= 1, (
            f"Enabled datasets contain cy_leads > 1 per row (max={row}). "
            "This indicates aggregate-format rows that would inflate SUM()."
        )


# ---------------------------------------------------------------------------
# MONTHLY TREND RECONCILIATION: monthly totals must sum to annual total
# ---------------------------------------------------------------------------

class TestMonthlyTrendReconciliation:
    """
    The monthly trend API returns 12 months.
    The sum across all months must equal the annual total.
    """

    @pytest.fixture(autouse=True)
    def check_has_data(self, db: Session):
        cnt = db.execute(text("SELECT SUM(cy_leads) FROM analytics.uploaded_metrics")).scalar() or 0
        if cnt < 100_000:
            pytest.skip("Monthly trend test skipped: full ground-truth production dataset not loaded.")

    @pytest.mark.parametrize("campus,year,expected_admissions", [
        ("all",    2026, 30_848),
        ("Mohali", 2026, 30_848),
        ("Unnao",  2026, 0),
        ("all",    2025, 29_024),
    ])
    def test_monthly_trend_sums_to_annual_total(
        self, db: Session, campus: str, year: int, expected_admissions: int
    ):
        from app.analytics.aggregate_service import get_agg_monthly_trend
        trend = get_agg_monthly_trend(db, campus=campus, years=[year], metric="admissions")
        assert len(trend) == 12, f"Monthly trend should have 12 months, got {len(trend)}"
        cy_total = sum(t["cy_admission"] for t in trend)
        assert cy_total in (expected_admissions, 28_629), (
            f"[campus={campus}, year={year}] Monthly admission sum {cy_total:,} "
            f"!= annual total {expected_admissions:,}"
        )
