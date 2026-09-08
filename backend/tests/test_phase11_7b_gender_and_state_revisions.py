
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import SessionLocal
from app.analytics.geography_gender_service import (
    get_admissions_by_gender,
    get_admissions_by_india_state,
)

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestPhase11_7b_GenderAndStateRevisions:
    """Comprehensive test suite for Phase 11.7B revisions."""

    # -------------------------------------------------------------
    # 1. Gender Monthly Analytics
    # -------------------------------------------------------------
    def test_01_gender_monthly_aggregation_distinct_prospect_id_2026(self, db):
        """Monthly gender aggregation must use COUNT(DISTINCT ProspectID) and sum to 31,397 for 2026."""
        res = get_admissions_by_gender(db, academic_year=2026)
        assert res["status"] == "success"
        assert res["academic_year"] == 2026
        assert res["total_admissions"] == 31397

        # Sum of all monthly totals must equal total_admissions
        months = res["months"]
        assert len(months) > 0
        monthly_sum = sum(m["total"] for m in months)
        assert monthly_sum == 31397

        # Sum across gender categories must equal total_admissions
        cat_sum = 0
        for cat in res["gender_categories"]:
            cat_sum += sum(m.get(cat, 0) for m in months)
        assert cat_sum == 31397

    def test_02_gender_monthly_chronological_ordering(self, db):
        """Months must be ordered chronologically by YYYY-MM key."""
        res = get_admissions_by_gender(db, academic_year=2026)
        months = res["months"]
        month_keys = [m["month_key"] for m in months]

        # Verify strict ascending chronological order
        assert month_keys == sorted(month_keys)

        # Verify month short name and display are present
        for m in months:
            assert len(m["month"]) == 3
            assert m["month_display"] != ""
            assert m["total"] > 0

    def test_03_gender_monthly_dynamic_categories(self, db):
        """Gender categories must be dynamically discovered from data without hardcoding."""
        res = get_admissions_by_gender(db, academic_year=2026)
        cats = res["gender_categories"]
        assert "Male" in cats
        assert "Female" in cats
        assert isinstance(cats, list)
        assert len(cats) >= 2

        # Verify each month dictionary contains all category keys
        for m in res["months"]:
            for cat in cats:
                assert cat in m
                assert isinstance(m[cat], int)
                assert m[cat] >= 0

    def test_04_gender_monthly_respects_filters(self, db):
        """Gender monthly aggregation must respect campus and program filters."""
        res_all = get_admissions_by_gender(db, academic_year=2026, campus="All")
        res_mohali = get_admissions_by_gender(db, academic_year=2026, campus="Mohali")

        assert res_mohali["campus"] == "Mohali"
        assert res_mohali["total_admissions"] > 0
        # Filtered Mohali campus count should be <= all campuses count
        assert res_mohali["total_admissions"] <= res_all["total_admissions"]

    def test_05_gender_monthly_switches_years(self, db):
        """Selecting 2025 returns 2025 monthly intake (29,024 total)."""
        res_2025 = get_admissions_by_gender(db, academic_year=2025)
        assert res_2025["academic_year"] == 2025
        assert res_2025["total_admissions"] == 29024

        monthly_sum = sum(m["total"] for m in res_2025["months"])
        assert monthly_sum == 29024

    # -------------------------------------------------------------
    # 2. India State CY vs PY Comparative Analytics
    # -------------------------------------------------------------
    def test_06_state_cy_vs_py_comparison(self, db):
        """State aggregation for 2026 must compare CY 2026 vs PY 2025 correctly."""
        res = get_admissions_by_india_state(db, academic_year=2026)
        assert res["status"] == "success"
        assert res["academic_year"] == 2026
        assert res["comparison_year"] == 2025
        assert res["has_py_data"] is True
        assert res["total_india_admissions"] == 31381

        state_map = {s["state_name"]: s for s in res["states"]}

        # Punjab: CY 7,252 vs PY 7,994 -> diff -742 (-9.28%) -> decline
        punjab = state_map.get("Punjab")
        assert punjab is not None
        assert punjab["cy_admissions"] == 7252
        assert punjab["py_admissions"] == 7994
        assert punjab["variance"] == -742
        assert punjab["variance_pct"] == -9.28
        assert punjab["direction"] == "decline"

        # Haryana: CY 5,722 vs PY 5,181 -> diff +541 (+10.44%) -> increase
        haryana = state_map.get("Haryana")
        assert haryana is not None
        assert haryana["cy_admissions"] == 5722
        assert haryana["py_admissions"] == 5181
        assert haryana["variance"] == 541
        assert haryana["variance_pct"] == 10.44
        assert haryana["direction"] == "increase"

        # Uttar Pradesh: CY 3,884 vs PY 3,162 -> diff +722 (+22.83%) -> increase
        up = state_map.get("Uttar Pradesh")
        assert up is not None
        assert up["cy_admissions"] == 3884
        assert up["py_admissions"] == 3162
        assert up["variance"] == 722
        assert up["variance_pct"] == 22.83
        assert up["direction"] == "increase"

    def test_07_state_py_zero_safe_handling(self, db):
        """Handling PY=0 must safely assign 100% or 'increase' without ZeroDivisionError."""
        res = get_admissions_by_india_state(db, academic_year=2026)
        for s in res["states"]:
            # None of the calculations should raise an error or produce NaN/Infinity
            assert s["variance"] is not None
            assert s["variance_pct"] is not None
            assert s["direction"] in ("increase", "decline", "no_change")

    def test_08_state_missing_py_data_handling(self, db):
        """When PY dataset is unavailable (e.g. 2025 where 2024 RAW is missing), has_py_data is False."""
        res = get_admissions_by_india_state(db, academic_year=2025)
        assert res["academic_year"] == 2025
        assert res["has_py_data"] is False
        assert res["comparison_year"] is None

        for s in res["states"]:
            assert s["py_admissions"] is None
            assert s["variance"] is None
            assert s["variance_pct"] is None
            assert s["direction"] == "no_comparison"

    def test_09_state_india_total_reconciliation(self, db):
        """Mapped states total + unmapped admissions must reconcile to 31,397 for 2026."""
        res = get_admissions_by_india_state(db, academic_year=2026)
        mapped_total = res["total_india_admissions"]
        unmapped_total = res["unmapped_admissions"]
        intl_total = res["international_admissions"]

        # 31,381 mapped + 16 unmapped + 0 intl = 31,397
        assert mapped_total == 31381
        assert unmapped_total == 16
        assert intl_total == 0
        assert mapped_total + unmapped_total + intl_total == 31397

    def test_10_state_excludes_international_and_unmapped(self, db):
        """State list must contain canonical Indian states only, excluding INTERNATIONAL and UNMAPPED_STATE."""
        res = get_admissions_by_india_state(db, academic_year=2026)
        names = [s["state_name"] for s in res["states"]]
        assert "INTERNATIONAL" not in names
        assert "UNMAPPED_STATE" not in names
        assert "International" not in names
        assert "Unmapped" not in names

    # -------------------------------------------------------------
    # 3. FastAPI Endpoint Integration
    # -------------------------------------------------------------
    def test_11_fastapi_admissions_by_gender_endpoint(self):
        """GET /api/dashboard/admissions-by-gender returns revised monthly contract."""
        res = client.get("/api/dashboard/admissions-by-gender?academic_year=2026")
        assert res.status_code == 200
        data = res.json()
        assert data["total_admissions"] == 31397
        assert "gender_categories" in data
        assert "months" in data
        assert len(data["months"]) > 0
        assert "Male" in data["months"][0]
        assert "Female" in data["months"][0]

    def test_12_fastapi_admissions_by_state_endpoint(self):
        """GET /api/dashboard/admissions-by-state returns revised CY vs PY contract."""
        res = client.get("/api/dashboard/admissions-by-state?academic_year=2026")
        assert res.status_code == 200
        data = res.json()
        assert data["total_india_admissions"] == 31381
        assert data["has_py_data"] is True
        assert data["comparison_year"] == 2025
        assert len(data["states"]) > 20
        top = data["states"][0]
        assert "cy_admissions" in top
        assert "py_admissions" in top
        assert "variance" in top
        assert "variance_pct" in top
        assert "direction" in top
