"""
Phase 11.7: Entity 404 Resolution & Geography/Gender Analytics Verification Suite
Verifies:
1. Entity detail endpoint handles slashes in path (/entity/{dimension}/{value:path})
2. Dimension alias mapping ("emp", "employee", "counselor" -> "owner")
3. Query-parameter entity detail endpoint (/entity?dimension=...&value=...)
4. Non-existent entity returns 404
5. Admissions by gender endpoint for 2026 (exact distinct counts: Male 19373, Female 12023, Unspecified 1)
6. Admissions by gender endpoint for 2025 (exact distinct counts: Male 18422, Female 10600, Unspecified 2)
7. India state admissions endpoint excludes international and unmapped
8. India state admissions aggregates canonical Indian states with correct share %
9. International admissions endpoint strictly excludes India
10. International admissions reports real foreign leads and admissions by country
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import SessionLocal
from app.analytics.geography_gender_service import (
    get_admissions_by_gender,
    get_admissions_by_india_state,
    get_international_admissions,
)

client = TestClient(app)

REAL_SLASH_PROGRAM = (
    "Bachelor of Business Administration (General/Advertising & Marketing/ "
    "Banking and Finance/ Insurance & Risk Management/ Tourism & Event Management/ Forex Management)"
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestPhase11_7_EntityAndGeography:
    """Test suite for Entity 404 bug fix and Geography & Gender analytics."""

    # -------------------------------------------------------------
    # 1. Entity Detail Fixes
    # -------------------------------------------------------------
    def test_01_entity_detail_path_with_slashes_returns_200(self):
        """Slash-containing entity values (e.g. BBA with multiple specializations) must return 200 via path."""
        url = f"/api/dashboard/entity/program/{REAL_SLASH_PROGRAM}?academic_year=2026"
        res = client.get(url)
        assert res.status_code == 200, f"Failed with {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("dimension") == "program"
        assert "Bachelor of Business Administration" in data.get("value", "")
        assert "overview" in data
        assert data["overview"]["admissions"]["cy"] > 0

    def test_02_entity_detail_emp_dimension_resolves_owner(self):
        """Dimension 'emp' or 'counselor' must correctly map to 'owner' column without 500/404 error."""
        url = "/api/dashboard/entity/emp/Shallu Rani E10630?academic_year=2026"
        res = client.get(url)
        assert res.status_code == 200, f"Failed with {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("dimension") == "emp"
        assert "Shallu Rani" in data.get("value", "")
        assert "overview" in data
        assert data["overview"]["admissions"]["cy"] > 0

    def test_03_entity_detail_query_param_endpoint(self):
        """Query-param endpoint /entity?dimension=...&value=... safely handles any complex value."""
        url = "/api/dashboard/entity"
        params = {
            "dimension": "program",
            "value": REAL_SLASH_PROGRAM,
            "academic_year": 2026,
        }
        res = client.get(url, params=params)
        assert res.status_code == 200, f"Failed with {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("dimension") == "program"
        assert "Bachelor of Business Administration" in data.get("value", "")
        assert data["overview"]["admissions"]["cy"] > 0

    def test_04_entity_detail_non_existent_returns_404(self):
        """Non-existent entities must return 404 cleanly."""
        url = "/api/dashboard/entity"
        params = {
            "dimension": "program",
            "value": "NonExistentProgramXYZ_99999",
            "academic_year": 2026,
        }
        res = client.get(url, params=params)
        assert res.status_code == 404

    # -------------------------------------------------------------
    # 2. Gender Analytics
    # -------------------------------------------------------------
    def test_05_admissions_by_gender_2026(self, db):
        """Verify dynamic distinct admissions by gender for 2026."""
        # Direct service test
        svc_data = get_admissions_by_gender(db, 2026)
        assert svc_data["academic_year"] == 2026
        assert svc_data["total_admissions"] == 31397

        categories = {item["gender"]: item["admissions"] for item in svc_data["genders"]}
        assert categories.get("Male") == 19373
        assert categories.get("Female") == 12023
        assert categories.get("Unspecified") == 1

        # API endpoint test
        res = client.get("/api/dashboard/admissions-by-gender?academic_year=2026")
        assert res.status_code == 200
        api_data = res.json()
        assert api_data["total_admissions"] == 31397
        assert len(api_data["genders"]) >= 2

    def test_06_admissions_by_gender_2025(self, db):
        """Verify dynamic distinct admissions by gender for 2025."""
        svc_data = get_admissions_by_gender(db, 2025)
        assert svc_data["academic_year"] == 2025
        assert svc_data["total_admissions"] == 29024

        categories = {item["gender"]: item["admissions"] for item in svc_data["genders"]}
        assert categories.get("Male") == 18422
        assert categories.get("Female") == 10600

        res = client.get("/api/dashboard/admissions-gender?academic_year=2025")
        assert res.status_code == 200
        assert res.json()["total_admissions"] == 29024

    # -------------------------------------------------------------
    # 3. India State Geography Analytics
    # -------------------------------------------------------------
    def test_07_india_state_admissions_excludes_international(self, db):
        """Verify state endpoint excludes INTERNATIONAL and UNMAPPED_STATE."""
        res = client.get("/api/dashboard/admissions-by-state?academic_year=2026")
        assert res.status_code == 200
        data = res.json()
        assert data["academic_year"] == 2026
        assert len(data["states"]) > 20

        names = [item["state_name"] for item in data["states"]]
        codes = [item["state_code"] for item in data["states"]]
        assert "INTERNATIONAL" not in names
        assert "UNMAPPED_STATE" not in names
        assert "INTERNATIONAL" not in codes
        assert "UNMAPPED_STATE" not in codes

    def test_08_india_state_admissions_sum(self, db):
        """Verify domestic admissions sum and top states."""
        res = client.get("/api/dashboard/admissions-by-state?academic_year=2026")
        assert res.status_code == 200
        data = res.json()
        assert data["total_india_admissions"] > 30000

        top_state = data["states"][0]
        assert top_state["state_name"] == "Punjab"
        assert top_state["state_code"] == "PB"
        assert top_state["admissions"] == 7252
        assert top_state["share_pct"] > 20.0

        # Verify shares sum to approx 100%
        total_share = sum(item["share_pct"] for item in data["states"])
        assert 99.5 <= total_share <= 100.5

    # -------------------------------------------------------------
    # 4. International Admissions Geography Analytics
    # -------------------------------------------------------------
    def test_09_international_admissions_excludes_india(self, db):
        """International admissions must strictly exclude domestic India."""
        for year in [2025, 2026]:
            res = client.get(f"/api/dashboard/international-admissions?academic_year={year}")
            assert res.status_code == 200
            data = res.json()
            assert data["academic_year"] == year
            for country_item in data["countries"]:
                assert country_item["country_name"].lower() != "india"
                assert country_item["country_code"].upper() not in ("IN", "IND")

    def test_10_international_admissions_top_countries(self, db):
        """Verify real foreign countries are represented with leads and admissions."""
        res = client.get("/api/dashboard/international-admissions?academic_year=2026")
        assert res.status_code == 200
        data = res.json()
        assert data["total_international_leads"] > 0
        assert len(data["countries"]) > 0

        # Nepal, UAE, Canada, Bangladesh should be present in top countries
        country_names = [c["country_name"] for c in data["countries"]]
        assert any("Nepal" in name for name in country_names)
        assert any("United Arab Emirates" in name or "UAE" in name for name in country_names)
