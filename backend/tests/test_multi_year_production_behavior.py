"""
Regression Test Suite for Multi-Year & Multi-Dataset Production Behavior
Validates:
1. Dynamic period discovery from system.datasets (no hardcoding).
2. Year switching isolation between enabled 2025 and 2026 RAW datasets.
3. Parameter parity: academic_year vs years query parameters across all endpoints.
4. Active dataset metadata scoping by academic_year.
5. Scoped aggregate refresh (O(1) dataset-scoped delete + insert, zero cross-contamination).
6. Programs and State reports multi-year dynamic querying.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.database.connection import SessionLocal
from app.analytics.aggregate_refresh import refresh_dashboard_agg_scoped, refresh_gender_agg_scoped

client = TestClient(app)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_dynamic_period_discovery(db):
    """Available academic years must come dynamically from enabled RAW datasets."""
    response = client.get("/api/periods")
    assert response.status_code == 200
    data = response.json()
    assert "periods" in data
    assert "years" in data
    assert len(data["periods"]) >= 2

    discovered_years = [p["period_end_year"] or p["period_start_year"] for p in data["periods"]]
    assert 2025 in discovered_years
    assert 2026 in discovered_years

    # Verify no null labels
    for p in data["periods"]:
        assert p["academic_label"] is not None
        assert str(p["academic_label"]).strip() != ""


def test_active_dataset_scoped_resolution(db):
    """GET /api/data/active returns correct dataset metadata for selected academic_year."""
    # 2025
    res_2025 = client.get("/api/data/active?academic_year=2025")
    assert res_2025.status_code == 200
    d_2025 = res_2025.json()
    assert d_2025["active"] is True
    assert d_2025["dataset"]["academic_year"] == 2025
    assert d_2025["dataset"]["row_count"] >= 900000

    # 2026
    res_2026 = client.get("/api/data/active?academic_year=2026")
    assert res_2026.status_code == 200
    d_2026 = res_2026.json()
    assert d_2026["active"] is True
    assert d_2026["dataset"]["academic_year"] == 2026
    assert d_2026["dataset"]["row_count"] >= 900000


def test_multi_year_overview_isolation(db):
    """Ensure selecting 2025 queries 2025 and selecting 2026 queries 2026 without data mixing."""
    # Query 2025 explicitly
    ov_2025 = client.get("/api/dashboard/overview?years=2025").json()
    assert ov_2025["current_year"] == 2025
    assert ov_2025["kpis"]["admissions"]["cy"] == 29024
    assert ov_2025["kpis"]["leads"]["cy"] == 940981

    # Query 2026 explicitly
    ov_2026 = client.get("/api/dashboard/overview?years=2026").json()
    assert ov_2026["current_year"] == 2026
    assert ov_2026["kpis"]["admissions"]["cy"] == 31397
    assert ov_2026["kpis"]["leads"]["cy"] == 982913
    assert ov_2026["previous_year"] == 2025
    assert ov_2026["kpis"]["admissions"]["py"] == 29024


def test_academic_year_query_param_parity(db):
    """Ensure academic_year query param behaves identically to years param."""
    res_years = client.get("/api/dashboard/overview?years=2026").json()
    res_ay = client.get("/api/dashboard/overview?academic_year=2026").json()

    assert res_years["current_year"] == res_ay["current_year"]
    assert res_years["kpis"]["admissions"]["cy"] == res_ay["kpis"]["admissions"]["cy"]
    assert res_years["kpis"]["leads"]["cy"] == res_ay["kpis"]["leads"]["cy"]

    trend_years = client.get("/api/dashboard/monthly-trend?years=2026").json()
    trend_ay = client.get("/api/dashboard/monthly-trend?academic_year=2026").json()
    assert len(trend_years) == len(trend_ay)


def test_gender_and_geography_multi_year_isolation(db):
    """Verify gender and state endpoints query the correct year without table scans."""
    # Gender 2025
    g_2025 = client.get("/api/dashboard/admissions-by-gender?academic_year=2025").json()
    assert g_2025["academic_year"] == 2025
    assert g_2025["total_admissions"] == 29024

    # Gender 2026
    g_2026 = client.get("/api/dashboard/admissions-by-gender?academic_year=2026").json()
    assert g_2026["academic_year"] == 2026
    assert g_2026["total_admissions"] == 31397

    # State 2025
    s_2025 = client.get("/api/dashboard/admissions-by-state?academic_year=2025").json()
    assert s_2025["academic_year"] == 2025
    assert s_2025["total_india_admissions"] > 0

    # State 2026
    s_2026 = client.get("/api/dashboard/admissions-by-state?academic_year=2026").json()
    assert s_2026["academic_year"] == 2026
    assert s_2026["total_india_admissions"] > 0


def test_scoped_aggregate_refresh_isolation(db):
    """Scoped aggregate refresh should only refresh the target dataset and leave other years intact."""
    row_2026 = db.execute(
        text("SELECT id FROM system.datasets WHERE academic_year = 2026 AND UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW' LIMIT 1")
    ).scalar()
    assert row_2026 is not None

    # Refresh 2026 scoped
    res = refresh_dashboard_agg_scoped(db, dataset_id=str(row_2026))
    assert res["inserted_rows"] > 0

    # Verify 2025 data was NOT deleted or disturbed
    adm_2025 = db.execute(
        text("SELECT SUM(admission_cy) FROM analytics.dashboard_agg WHERE academic_year = 2025")
    ).scalar()
    assert int(adm_2025 or 0) == 29024

    # Verify 2026 data is complete
    adm_2026 = db.execute(
        text("SELECT SUM(admission_cy) FROM analytics.dashboard_agg WHERE academic_year = 2026")
    ).scalar()
    assert int(adm_2026 or 0) == 31397


def test_programs_and_states_dynamic_multi_year(db):
    """Programs and States reports should dynamically respond to academic_year."""
    prog_2025 = client.get("/api/programs/report?academic_year=2025").json()
    assert prog_2025["success"] is True
    assert prog_2025["data"]["total"]["cy_adm"] == 29024

    prog_2026 = client.get("/api/programs/report?academic_year=2026").json()
    assert prog_2026["success"] is True
    assert prog_2026["data"]["total"]["cy_adm"] == 31397

    state_2025 = client.get("/api/states/report?academic_year=2025").json()
    assert state_2025["success"] is True
    assert state_2025["data"]["total"]["cy_adm"] == 29024

    state_2026 = client.get("/api/states/report?academic_year=2026").json()
    assert state_2026["success"] is True
    assert state_2026["data"]["total"]["cy_adm"] == 31397
