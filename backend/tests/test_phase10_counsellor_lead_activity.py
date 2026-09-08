import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.counsellor_service import (
    extract_employee_id,
    get_counsellor_summary,
    get_lead_activity,
    generate_counsellor_report,
)
from app.analytics.aggregate_refresh import refresh_dashboard_agg


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_01_extract_employee_id_canonical_identity():
    """Test 1: Test extracting canonical employee ID from owner string."""
    assert extract_employee_id("Ganesh Dutt E1678") == "E1678"
    assert extract_employee_id("Ravinder NL152") == "NL152"
    assert extract_employee_id("PANKAJ SHARMA E5800") == "E5800"
    assert extract_employee_id(None) == "UNKNOWN"


def test_02_counsellor_summary_metrics(db):
    """Test 2: Verify get_counsellor_summary metrics calculation against real database records."""
    summary = get_counsellor_summary(db)
    assert summary["status"] == "success"
    assert "summary_kpis text" not in summary
    kpis = summary["summary_kpis"]
    
    assert kpis["total_counsellors"] > 0
    assert kpis["total_leads_assigned"] > 0
    assert kpis["total_calls_made"] > 0

    counsellors = summary["counsellors"]
    assert len(counsellors) > 0
    
    sample = counsellors[0]
    assert "counsellor" in sample
    assert "employee_id" in sample
    assert "leads_assigned" in sample
    assert "calls_0" in sample
    assert "calls_4_plus" in sample
    assert "conversion_rate" in sample


def test_03_lead_activity_pagination_and_filtering(db):
    """Test 3: Test paginated lead activity query with multi-column filters."""
    res = get_lead_activity(db, page=1, page_size=10)
    assert res["status"] == "success"
    assert res["page"] == 1
    assert len(res["leads"]) <= 10

    # Filter test by call attempt bucket '4+'
    bucket_res = get_lead_activity(db, attempt_bucket="4+", page=1, page_size=10)
    for lead in bucket_res["leads"]:
        assert float(lead["total_call_attempts"]) >= 4.0


def test_04_no_call_leads_and_attempt_buckets(db):
    """Test 4: Verify 0 call (no-call) attempt bucket filtering."""
    no_call_res = get_lead_activity(db, attempt_bucket="0", page=1, page_size=10)
    assert "leads" in no_call_res
    for lead in no_call_res["leads"]:
        assert float(lead["total_call_attempts"]) == 0.0


def test_05_interested_and_overdue_followups(db):
    """Test 5: Verify overdue follow-up status classification."""
    overdue_res = get_lead_activity(db, followup_status="Overdue", page=1, page_size=10)
    for lead in overdue_res["leads"]:
        assert lead["followup_status"] == "Overdue"


def test_06_report_generation_csv_xlsx(db):
    """Test 6: Test generate_counsellor_report producing valid CSV text streams."""
    csv_content, media_type = generate_counsellor_report(db, report_type="counsellor_performance", export_format="csv")
    assert media_type == "text/csv"
    assert "Counsellor Name" in csv_content
    assert "Leads Assigned" in csv_content

    leads_csv, _ = generate_counsellor_report(db, report_type="lead_activity", export_format="csv")
    assert "Prospect ID" in leads_csv
    assert "First Disposition" in leads_csv
