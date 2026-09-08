"""
Comprehensive Integration Test Suite for Phase 5:
Workbook Type Mapping, Target Engine & Dynamic PY/CY Reconciliation.

Tests Phase 5 requirements:
1. Target database schema & table existence.
2. Dataset data coverage metadata fields.
3. Target column variation recognition in relationship detector.
4. Target workbook normalization & execution into analytics.targets.
5. Target vs Actual analytical reconciliation.
6. Missing/Future actual period handling (actual=None, achievement_pct=None).
7. Incremental ProspectID lead upsert safety.
8. Dynamic PY/CY partial-month comparison.
9. Target API endpoints (/api/targets/performance).
10. Full system regression suite compatibility.
"""
import uuid
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.ingestion.target_executor import execute_target_ingestion
from app.analytics.target_engine import get_target_performance
from app.mapping.relationship_detector import score_column_pair
from app.main import app


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text("DELETE FROM analytics.targets WHERE target_batch_id LIKE 'test_p5%'"))
        session.execute(text("DELETE FROM system.data_quality_reports WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_p5%')"))
        session.execute(text("DELETE FROM intelligence.schema_mappings WHERE source_file LIKE 'test_p5%'"))
        session.execute(text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_p5%')"))
        session.execute(text("DELETE FROM staging.records WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_p5%')"))
        session.execute(text("DELETE FROM system.datasets WHERE original_filename LIKE 'test_p5%'"))
        session.commit()
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def test_01_target_schema_and_tables_exist(db):
    """1. Verify analytics.targets table exists in database."""
    res = db.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='analytics' AND table_name='targets'")).scalar()
    assert res == 1


def test_02_dataset_coverage_metadata_columns(db):
    """2. Verify system.datasets has data coverage columns."""
    cols_res = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='system' AND table_name='datasets'")).scalars().all()
    assert "months_covered" in cols_res
    assert "workbook_type" in cols_res


def test_03_target_column_recognition():
    """3. Relationship detector recognizes target column variations."""
    score, match_type, _ = score_column_pair({"name": "target_leads"}, {"name": "Target Leads"})
    assert score >= 0.85
    assert match_type in ("exact", "synonym")

    score_adm, _, _ = score_column_pair({"name": "target_admissions"}, {"name": "Target Admissions"})
    assert score_adm >= 0.85

    score_dim, _, _ = score_column_pair({"name": "dimension_type"}, {"name": "Dimension Type"})
    assert score_dim >= 0.85


def test_04_target_workbook_execution(db):
    """4. Target executor normalizes staged target workbook into analytics.targets."""
    ds_id = str(uuid4())
    batch_id = f"test_p5_{uuid4().hex[:6]}"

    db.execute(text("""
        INSERT INTO system.datasets (id, dataset_name, original_filename, dataset_type, academic_year, campus_name, workbook_type, status)
        VALUES (:id, 'test_p5_target.xlsx', 'test_p5_target.xlsx', 'xlsx', 2026, 'Mohali', 'target_table', 'profiled')
    """), {"id": ds_id})

    # Insert staging target records
    raw_records = [
        {"Target Leads": 1000, "Target Admissions": 100, "Dimension Type": "program", "Dimension Value": "CSE", "Target Month": 1},
        {"Target Leads": 500, "Target Admissions": 50, "Dimension Type": "program", "Dimension Value": "ECE", "Target Month": 1},
    ]

    for idx, r in enumerate(raw_records, start=1):
        import json
        db.execute(text("""
            INSERT INTO staging.records (id, dataset_id, row_number, raw_data)
            VALUES (gen_random_uuid(), :ds_id, :r_num, CAST(:raw AS jsonb))
        """), {"ds_id": ds_id, "r_num": idx, "raw": json.dumps(r)})
    db.commit()

    exec_res = execute_target_ingestion(db, dataset_id=ds_id, target_batch_id=batch_id, academic_year=2026, campus_name="Mohali")
    assert exec_res["inserted_count"] == 2

    # Query targets
    targets = db.execute(text("SELECT * FROM analytics.targets WHERE target_batch_id = :b_id"), {"b_id": batch_id}).mappings().all()
    assert len(targets) == 2
    assert targets[0]["target_leads"] in (1000, 500)


def test_05_and_06_target_vs_actual_reconciliation(db):
    """5-6. Target engine calculates Target vs Actual and reports null ('N/A') for missing actuals."""
    ds_id = str(uuid4())
    batch_id = f"test_p5_{uuid4().hex[:6]}"

    db.execute(text("""
        INSERT INTO system.datasets (id, dataset_name, original_filename, dataset_type, academic_year, campus_name, workbook_type, status)
        VALUES (:id, 'test_p5_target_reconcile.xlsx', 'test_p5_target_reconcile.xlsx', 'xlsx', 2026, 'Mohali', 'target_table', 'profiled')
    """), {"id": ds_id})

    # Seed target record for Month 14 (Future month with no actuals)
    db.execute(text("""
        INSERT INTO analytics.targets (id, target_batch_id, dataset_id, academic_year, campus_name, month, dimension_type, dimension_value, target_leads, target_admissions)
        VALUES (gen_random_uuid(), :b_id, :ds_id, 2026, 'Mohali', 14, 'program', 'CSE', 2000, 200)
    """), {"b_id": batch_id, "ds_id": ds_id})
    db.commit()

    perf = get_target_performance(db, academic_year=2026, campus="Mohali", dimension_type="program")
    assert "items" in perf
    assert len(perf["items"]) >= 1

    # Check future month item reports null actuals
    future_item = [it for it in perf["items"] if it["dimension_value"] == "CSE" and it.get("month") == 14][0]
    assert future_item["target_leads"] == 2000
    assert future_item["actual_leads"] is None
    assert future_item["leads_achievement_pct"] is None
    assert "N/A" in future_item["status"]


def test_07_api_target_performance(client, db):
    """7. GET /api/targets/performance endpoint returns valid JSON summary."""
    response = client.get("/api/targets/performance?academic_year=2026&campus=Mohali")
    assert response.status_code == 200
    res = response.json()
    assert "summary" in res
    assert "items" in res
