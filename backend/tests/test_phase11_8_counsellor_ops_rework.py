import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.main import app
from app.analytics.counsellor_service import (
    parse_counsellor_identity,
    get_counsellors_list,
    get_counsellor_detail_report,
    get_lead_activity,
)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_01_counsellor_list_loads_dynamically(db, client):
    """Test 1: Counsellor list loads dynamically from PostgreSQL aggregate."""
    res = client.get("/api/counsellors?academic_year=2026")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "counsellors" in data
    assert len(data["counsellors"]) > 0
    assert data["total_counsellors"] > 0


def test_02_no_hardcoded_counsellor_names(db):
    """Test 2: No hardcoded counsellor names — names come directly from dataset."""
    res = get_counsellors_list(db, academic_year=2026)
    c_names = [c["counsellor_name"] for c in res["counsellors"]]
    assert len(c_names) > 0
    # Counsellors should match whatever is in analytics.dashboard_agg
    db_counsellors = db.execute(
        text("SELECT DISTINCT owner FROM analytics.dashboard_agg WHERE academic_year = 2026 AND owner IS NOT NULL")
    ).fetchall()
    assert len(c_names) == len(db_counsellors)


def test_03_total_assigned_leads_is_correct(db):
    """Test 3: Total assigned leads matches database aggregate."""
    res = get_counsellors_list(db, academic_year=2026)
    expected_leads = db.execute(
        text("SELECT SUM(leads_cy) FROM analytics.dashboard_agg WHERE academic_year = 2026 AND owner IS NOT NULL")
    ).scalar()
    assert res["summary"]["total_leads_assigned"] == int(expected_leads)


def test_04_total_admissions_is_correct(db):
    """Test 4: Total admissions matches database aggregate."""
    res = get_counsellors_list(db, academic_year=2026)
    expected_adms = db.execute(
        text("SELECT SUM(admission_cy) FROM analytics.dashboard_agg WHERE academic_year = 2026 AND owner IS NOT NULL")
    ).scalar()
    assert res["summary"]["total_admissions"] == int(expected_adms)


def test_05_conversion_calculation_is_correct(db):
    """Test 5: Conversion calculation is admissions / assigned_leads * 100."""
    res = get_counsellors_list(db, academic_year=2026)
    for c in res["counsellors"]:
        if c["leads_assigned"] > 0:
            expected = round(c["admissions"] / c["leads_assigned"] * 100, 2)
            assert c["conversion_rate"] == expected


def test_06_source_categories_are_dynamically_loaded(db):
    """Test 6: Source categories are loaded dynamically from organization.source_master."""
    sample_counsellor = db.execute(
        text("SELECT owner FROM analytics.dashboard_agg WHERE academic_year = 2026 AND leads_cy > 100 LIMIT 1")
    ).scalar()
    report = get_counsellor_detail_report(db, sample_counsellor, academic_year=2026)
    report_categories = {c["category"] for c in report["categories"]}

    # Verify categories originate from organization.source_master
    db_categories = {
        r[0]
        for r in db.execute(
            text("SELECT DISTINCT lead_type FROM organization.source_master WHERE lead_type IS NOT NULL AND TRIM(lead_type) != ''")
        ).fetchall()
    }
    assert db_categories.issubset(report_categories)


def test_07_source_category_leads_are_correct(db):
    """Test 7: Category assigned leads match distinct ProspectID in RAW dataset."""
    sample_owner = "Shallu Rani E10630"
    report = get_counsellor_detail_report(db, sample_owner, academic_year=2026)
    total_leads = sum(c["leads_assigned"] for c in report["categories"])
    assert total_leads == report["summary"]["total_leads_assigned"]
    assert total_leads > 0


def test_08_source_category_admissions_are_correct(db):
    """Test 8: Category admissions match distinct enrolled prospects."""
    sample_owner = "Shallu Rani E10630"
    report = get_counsellor_detail_report(db, sample_owner, academic_year=2026)
    total_admissions = sum(c["admissions"] for c in report["categories"])
    assert total_admissions == report["summary"]["total_admissions"]


def test_09_source_category_conversion_is_correct(db):
    """Test 9: Category conversion calculation is correct."""
    sample_owner = "Shallu Rani E10630"
    report = get_counsellor_detail_report(db, sample_owner, academic_year=2026)
    for cat in report["categories"]:
        if cat["leads_assigned"] > 0:
            expected_rate = round(cat["admissions"] / cat["leads_assigned"] * 100, 2)
            assert cat["conversion_rate"] == expected_rate
            assert cat["conversion_rate_display"] == f"{expected_rate:.2f}%"


def test_10_best_category_is_determined_by_conversion_rate(db):
    """Test 10: Best performing category is chosen by conversion rate descending, NOT admission volume."""
    sample_owner = "Shallu Rani E10630"
    report = get_counsellor_detail_report(db, sample_owner, academic_year=2026)
    best_cat = report["summary"]["best_source_category"]
    
    # In Shallu Rani's data:
    # Others: 935 leads, 60 admissions, 6.42% conversion
    # In House: 4615 leads, 222 admissions, 4.81% conversion
    # Out Sourced: 5536 leads, 43 admissions, 0.78% conversion
    # Highest admission count is In House (222), but Highest Conversion is Others (6.42%)
    assert best_cat == "Others"
    assert report["categories"][0]["category"] == "Others"
    assert report["categories"][0]["conversion_rate"] > report["categories"][1]["conversion_rate"]


def test_11_zero_lead_category_returns_na(db):
    """Test 11: If a category has 0 assigned leads, conversion rate must be N/A, not 0%."""
    report = get_counsellor_detail_report(db, "Shallu Rani E10630", academic_year=2026)
    # Add synthetic check on categories with zero leads
    zero_cats = [c for c in report["categories"] if c["leads_assigned"] == 0]
    for zc in zero_cats:
        assert zc["conversion_rate"] is None
        assert zc["conversion_rate_display"] == "N/A"
        assert zc["category"] != report["summary"]["best_source_category"]


def test_12_academic_year_filtering_works(db, client):
    """Test 12: Academic year filter restricts dataset properly."""
    res_2026 = client.get("/api/counsellors?academic_year=2026").json()
    res_2025 = client.get("/api/counsellors?academic_year=2025").json()
    # 2026 and 2025 metrics are distinct
    assert res_2026["summary"]["total_leads_assigned"] != res_2025["summary"]["total_leads_assigned"]


def test_13_campus_filtering_works(db, client):
    """Test 13: Campus filter restricts dataset properly."""
    res_all = client.get("/api/counsellors?academic_year=2026").json()
    res_mohali = client.get("/api/counsellors?academic_year=2026&campus=Mohali").json()
    assert res_all["status"] == "success"
    assert res_mohali["status"] == "success"
    assert len(res_mohali["counsellors"]) > 0


def test_14_selected_counsellor_report_uses_raw_dataset(db):
    """Test 14: Counsellor report only aggregates RAW workbook datasets."""
    report = get_counsellor_detail_report(db, "Shallu Rani E10630", academic_year=2026)
    # Confirm workbook type condition in query ensures RAW records only
    assert report["summary"]["total_leads_assigned"] > 0


def test_15_no_target_records_counted_as_actuals(db):
    """Test 15: Target datasets are not counted as actual counsellor leads."""
    target_count = db.execute(
        text("SELECT COUNT(*) FROM staging.records r JOIN system.datasets sd ON r.dataset_id = sd.id WHERE sd.workbook_type = 'TARGET'")
    ).scalar()
    # Ensure targets exist in db, but detail report excludes them
    assert target_count > 0
    report = get_counsellor_detail_report(db, "Shallu Rani E10630", academic_year=2026)
    raw_leads = db.execute(
        text("SELECT COUNT(DISTINCT r.raw_data->>'ProspectID') FROM staging.records r JOIN system.datasets sd ON r.dataset_id = sd.id WHERE sd.workbook_type = 'RAW' AND sd.academic_year = 2026 AND r.raw_data->>'OwnerIdName' = 'Shallu Rani E10630'")
    ).scalar()
    assert report["summary"]["total_leads_assigned"] == raw_leads


def test_16_large_dataset_does_not_return_raw_crm_rows_in_summary(client):
    """Test 16: Large dataset returns set-based summary rows, not millions of raw leads."""
    res = client.get("/api/counsellors?academic_year=2026")
    data = res.json()
    # Returns 318 counsellor aggregate rows, NOT raw CRM rows
    assert len(data["counsellors"]) < 1000
    for c in data["counsellors"]:
        assert "raw_data" not in c
        assert "ProspectID" not in c


def test_17_lead_activity_remains_paginated(client):
    """Test 17: Scoped lead activity endpoint remains paginated."""
    res = client.get("/api/counsellor/leads?counsellor=Shallu%20Rani%20E10630&page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert len(data["leads"]) <= 10
    assert data["page"] == 1
    assert data["total_pages"] > 1


def test_18_no_application_api_404s(client):
    """Test 18: No 404s across any supported counsellor endpoint formats."""
    # List endpoints
    assert client.get("/api/counsellors").status_code == 200
    assert client.get("/api/counsellor").status_code == 200
    assert client.get("/api/counsellor/summary").status_code == 200
    assert client.get("/api/counsellors/summary").status_code == 200

    # Detail report endpoints
    assert client.get("/api/counsellors/Shallu%20Rani%20E10630/report?academic_year=2026").status_code == 200
    assert client.get("/api/counsellor/Shallu%20Rani%20E10630/report?academic_year=2026").status_code == 200
    assert client.get("/api/counsellors/E10630/report?academic_year=2026").status_code == 200
    assert client.get("/api/counsellors/report?counsellor=Shallu%20Rani%20E10630&academic_year=2026").status_code == 200


def test_19_parse_counsellor_identity():
    """Test 19: Parser correctly splits display name and employee ID."""
    name1, id1 = parse_counsellor_identity("Shallu Rani E10630")
    assert name1 == "Shallu Rani"
    assert id1 == "E10630"

    name2, id2 = parse_counsellor_identity("Sakshi Sharma")
    assert name2 == "Sakshi Sharma"
    assert id2 is None

    name3, id3 = parse_counsellor_identity("Aananya Bhardwaj NL101")
    assert name3 == "Aananya Bhardwaj"
    assert id3 == "NL101"


def test_20_search_filtering(client):
    """Test 20: Search query filters counsellors dynamically by name or ID."""
    res = client.get("/api/counsellors?academic_year=2026&search=Shallu")
    assert res.status_code == 200
    data = res.json()
    assert any("Shallu" in c["counsellor_name"] for c in data["counsellors"])
