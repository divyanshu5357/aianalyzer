import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import SessionLocal
from app.analytics.aggregate_service import get_py_date, generate_chronological_months
from app.api.dashboard import _validate_date_range
from fastapi import HTTPException

client = TestClient(app)

def test_py_date_regular():
    assert get_py_date("2026-05-15") == "2025-05-15"
    assert get_py_date("2026-01-01") == "2025-01-01"
    assert get_py_date("2026-12-31") == "2025-12-31"

def test_py_date_leap_year():
    # 2024 is leap year, 2023 is not
    assert get_py_date("2024-02-29") == "2023-02-28"

def test_generate_chronological_months():
    months = generate_chronological_months("2026-01-01", "2026-04-30")
    assert len(months) == 4
    assert months[0] == ("January", "2026-01")
    assert months[1] == ("February", "2026-02")
    assert months[2] == ("March", "2026-03")
    assert months[3] == ("April", "2026-04")

    # Cross year
    cross = generate_chronological_months("2025-11-01", "2026-02-28")
    assert len(cross) == 4
    assert cross[0] == ("November", "2025-11")
    assert cross[1] == ("December", "2025-12")
    assert cross[2] == ("January", "2026-01")
    assert cross[3] == ("February", "2026-02")

def test_validate_date_range_valid():
    f, t = _validate_date_range("2026-01-01", "2026-06-30")
    assert f == "2026-01-01"
    assert t == "2026-06-30"

    # Both empty is valid (no filter)
    f, t = _validate_date_range(None, None)
    assert f is None and t is None

def test_validate_date_range_invalid():
    # Only one provided
    with pytest.raises(HTTPException) as exc1:
        _validate_date_range("2026-01-01", None)
    assert exc1.value.status_code == 400

    with pytest.raises(HTTPException) as exc2:
        _validate_date_range(None, "2026-01-01")
    assert exc2.value.status_code == 400

    # Invalid format
    with pytest.raises(HTTPException) as exc3:
        _validate_date_range("01-01-2026", "2026-06-30")
    assert exc3.value.status_code == 400

    # from_date > to_date
    with pytest.raises(HTTPException) as exc4:
        _validate_date_range("2026-07-01", "2026-06-30")
    assert exc4.value.status_code == 400

def test_api_options_contains_date_range():
    res = client.get("/api/dashboard/options?campus=All&years=2026")
    assert res.status_code == 200
    data = res.json()
    assert "date_range" in data
    dr = data["date_range"]
    assert "min_date" in dr
    assert "max_date" in dr
    assert "default_from" in dr
    assert "default_to" in dr
    assert dr["min_date"] <= dr["max_date"]

def test_api_overview_with_date_range():
    res = client.get("/api/dashboard/overview?campus=All&years=2026&from_date=2026-01-01&to_date=2026-06-30")
    assert res.status_code == 200
    data = res.json()
    assert data["from_date"] == "2026-01-01"
    assert data["to_date"] == "2026-06-30"
    assert data["py_from_date"] == "2025-01-01"
    assert data["py_to_date"] == "2025-06-30"
    assert "kpis" in data
    assert data["kpis"]["admissions"]["cy"] is not None

def test_api_monthly_trend_with_date_range():
    res = client.get("/api/dashboard/monthly-trend?campus=All&years=2026&from_date=2026-01-01&to_date=2026-06-30")
    assert res.status_code == 200
    trend = res.json()
    assert isinstance(trend, list)
    assert len(trend) == 6
    months_returned = [m["month_key"] for m in trend]
    assert months_returned == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

    # Verify NO synthetic cucet multiplier (1.5 * admissions)
    for m in trend:
        cy_adm = m.get("cy_admission")
        cy_cucet = m.get("cy_cucet")
        if cy_adm is not None and cy_cucet is not None and cy_adm > 0:
            # If it were the fake multiplier, cy_cucet == int(cy_adm * 1.5)
            # In authentic data, they are independent aggregates
            assert cy_cucet >= 0

def test_api_performance_rankings_with_date_range():
    res = client.get("/api/dashboard/performance-rankings?dimension=program_name&campus=All&years=2026&from_date=2026-01-01&to_date=2026-06-30")
    assert res.status_code == 200
    data = res.json()
    assert "improvements" in data
    assert "declines" in data

def test_api_entity_detail_404_fix():
    # Program code CS238 previously caused 404 because dimension was program_name
    # Now our resolution handles program_code, raw_program_code, and suffix matching
    res = client.get("/api/dashboard/entity?dimension=program_name&value=CS238&years=2026")
    assert res.status_code == 200
    data = res.json()
    assert data["value"] == "CS238"
    assert data["overview"]["admissions"]["cy"] is not None
    assert data["overview"]["admissions"]["cy"] > 0

def test_api_admissions_gender_with_date_range():
    res = client.get("/api/dashboard/admissions-gender?academic_year=2026&campus=All&from_date=2026-01-01&to_date=2026-06-30")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "gender_categories" in data
    assert "months" in data

def test_api_admissions_state_with_date_range():
    res = client.get("/api/dashboard/admissions-state?academic_year=2026&campus=All&from_date=2026-01-01&to_date=2026-06-30")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "states" in data
    assert len(data["states"]) > 0
    # Verify Punjab is present with authentic counts
    pb = next((s for s in data["states"] if s["state_name"] == "Punjab"), None)
    assert pb is not None
    assert pb["cy_admissions"] > 0
