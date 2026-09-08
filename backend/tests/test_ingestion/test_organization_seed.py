import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.database.schema_init import ensure_all_database_tables
from app.database.organization_seed import generate_dry_run_report, import_client_master_data

@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    ensure_all_database_tables(session)
    yield session
    session.close()

def test_dry_run_report_structure():
    report = generate_dry_run_report()
    assert "Source" in report
    assert "Course" in report
    assert "State" in report
    assert "Employee" in report
    
    assert report["Source"]["rows"] == 1001
    assert report["Source"]["valid_mappings"] == 1000
    assert report["Course"]["rows"] == 423
    assert report["Course"]["valid_mappings"] == 423
    assert report["State"]["rows"] == 657
    assert report["State"]["valid_states"] == 654
    assert report["Employee"]["rows"] == 1278
    assert report["Employee"]["valid_employees"] == 1278

def test_master_data_import_and_idempotency(db):
    # Import
    stats1 = import_client_master_data(db)
    assert stats1["inserted"] + stats1["updated"] == 3355
    assert stats1["skipped"] == 4
    
    # Check counts in DB
    src_cnt = db.execute(text("SELECT COUNT(*) FROM organization.source_master")).scalar()
    course_cnt = db.execute(text("SELECT COUNT(*) FROM organization.course_master")).scalar()
    state_cnt = db.execute(text("SELECT COUNT(*) FROM organization.state_master")).scalar()
    emp_cnt = db.execute(text("SELECT COUNT(*) FROM organization.employee_master")).scalar()
    
    assert src_cnt == 1000
    assert course_cnt == 423
    assert state_cnt == 654
    assert emp_cnt == 1278
    
    # Idempotent re-run
    stats2 = import_client_master_data(db)
    assert stats2["inserted"] == 0
    assert stats2["updated"] == 3355
    assert stats2["skipped"] == 4
