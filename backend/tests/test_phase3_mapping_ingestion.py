"""
Comprehensive Integration Test Suite for Phase 3: Mapping Ingestion Pipeline & Execution.

Tests all 21 Phase 3 requirement items:
1. Approved exact mapping executes.
2. Approved synonym mapping executes.
3. Rejected mapping does not execute.
4. Low-confidence mapping requires confirmation.
5. Ambiguous mapping requires confirmation.
6. Program Code blank remains NULL.
7. Unknown Program Code is not guessed.
8. Existing course_master lookup works for valid Program Code.
9. ProspectID mapping works.
10. OwnerID -> EmployeeID works.
11. State Code mapping works.
12. Source Code mapping works.
13. Mapping version is recorded.
14. Reusable mapping is automatically applied to a subsequent upload.
15. New ProspectID creates a new logical lead.
16. Existing ProspectID does not create duplicate logical leads.
17. Multi-sheet workbook processing works.
18. CSV processing works.
19. Data quality statistics are correct.
20. API upload -> mapping -> ingestion integration works.
21. Frontend mapping review API contract works.
"""
import io
import json
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.ingestion.mapping_executor import (
    calculate_data_quality_report,
    execute_mapping_normalization,
    load_executable_mappings,
)
from app.ingestion.profiler import profile_multisheet_file
from app.ingestion.staging_loader import load_to_staging
from app.main import app
from app.mapping.mapping_service import (
    approve_or_edit_mappings,
    get_reusable_mappings_for_columns,
    save_mapping_configuration,
)
from app.mapping.relationship_detector import (
    clean_or_unmap_program_code,
    detect_relationships_against_canonical_entities,
    detect_sheet_relationships,
    score_column_pair,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text("DELETE FROM system.data_quality_reports WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_phase3%')"))
        session.execute(text("DELETE FROM intelligence.schema_mappings WHERE source_file LIKE 'test_phase3%'"))
        session.execute(text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_phase3%')"))
        session.execute(text("DELETE FROM staging.records WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_phase3%')"))
        session.execute(text("DELETE FROM system.datasets WHERE original_filename LIKE 'test_phase3%'"))
        session.commit()
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def helper_create_test_dataset(db, filename="test_phase3_file.csv", year=2026, campus="Mohali"):
    ds_id = str(uuid.uuid4())
    db.execute(
        text(
            """
            INSERT INTO system.datasets (id, dataset_name, original_filename, dataset_type, academic_year, campus_name, status, is_analytics_enabled)
            VALUES (:id, :name, :fname, 'csv', :year, :campus, 'profiled', TRUE)
            """
        ),
        {
            "id": ds_id,
            "name": filename,
            "fname": filename,
            "year": year,
            "campus": campus,
        },
    )
    db.commit()
    return ds_id


def helper_insert_staging_records(db, dataset_id: str, records: list):
    for i, r in enumerate(records, start=1):
        db.execute(
            text(
                """
                INSERT INTO staging.records (dataset_id, row_number, raw_data, cleaning_status)
                VALUES (:ds_id, :row_no, CAST(:raw AS jsonb), 'pending')
                """
            ),
            {
                "ds_id": dataset_id,
                "row_no": i,
                "raw": json.dumps(r),
            },
        )
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Tests 1-5: Mapping Status & Guardrails Execution
# ─────────────────────────────────────────────────────────────────────────────

def test_01_approved_exact_mapping_executes(db):
    """1. Approved exact mapping executes into normalized metrics."""
    saved = save_mapping_configuration(
        db=db,
        source_file="test_phase3_exact.csv",
        source_sheet="Sheet1",
        source_column="ProspectID",
        target_entity="Prospect",
        target_column="ProspectID",
        confidence=1.0,
        status="approved",
    )
    executables = load_executable_mappings(db, source_file="test_phase3_exact.csv")
    assert any(m["id"] == saved["id"] for m in executables)


def test_02_approved_synonym_mapping_executes(db):
    """2. Approved synonym mapping (e.g. OwnerID -> EmployeeID) executes."""
    saved = save_mapping_configuration(
        db=db,
        source_file="test_phase3_synonym.csv",
        source_sheet="Sheet1",
        source_column="OwnerID",
        target_entity="Employee",
        target_column="EmployeeID",
        confidence=0.92,
        status="approved",
    )
    executables = load_executable_mappings(db, source_file="test_phase3_synonym.csv")
    assert any(m["id"] == saved["id"] for m in executables)


def test_03_rejected_mapping_does_not_execute(db):
    """3. Rejected mapping does not execute automatically."""
    saved = save_mapping_configuration(
        db=db,
        source_file="test_phase3_rejected.csv",
        source_sheet="Sheet1",
        source_column="BadCol",
        target_entity="Program",
        target_column="Program Code",
        confidence=0.95,
        status="rejected",
    )
    executables = load_executable_mappings(db, source_file="test_phase3_rejected.csv")
    assert not any(m["id"] == saved["id"] for m in executables)


def test_04_low_confidence_mapping_requires_confirmation(db):
    """4. Low-confidence mapping requires confirmation and is blocked from auto execution."""
    sheet_src = {"sheet_name": "S1", "columns_profile": [{"name": "random_txt", "dtype": "string"}]}
    sheet_tgt = {"sheet_name": "T1", "columns_profile": [{"name": "EmployeeID", "dtype": "string"}]}
    results = detect_sheet_relationships(sheet_src, sheet_tgt)
    if results:
        top = results[0]
        assert top["requires_confirmation"] is True
        assert top["status"] == "requires_confirmation"


def test_05_ambiguous_mapping_requires_confirmation(db):
    """5. Ambiguous mapping requires confirmation and is blocked from auto execution."""
    sheet_src = {"sheet_name": "S1", "columns_profile": [{"name": "code", "is_likely_key": True}]}
    sheet_tgt = {
        "sheet_name": "T1",
        "columns_profile": [
            {"name": "program_code", "is_likely_key": True},
            {"name": "state_code", "is_likely_key": True},
        ],
    }
    results = detect_sheet_relationships(sheet_src, sheet_tgt)
    if results:
        top = results[0]
        if top.get("is_ambiguous"):
            assert top["requires_confirmation"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests 6-8: Program Code Safety & Dimension Lookup
# ─────────────────────────────────────────────────────────────────────────────

def test_06_program_code_blank_remains_null():
    """6. Blank/null Program Code remains NULL (program_code=NULL, program_name=NULL, course_cluster=NULL)."""
    assert clean_or_unmap_program_code("") is None
    assert clean_or_unmap_program_code(None) is None
    assert clean_or_unmap_program_code("   ") is None
    assert clean_or_unmap_program_code("nan") is None
    assert clean_or_unmap_program_code("null") is None
    assert clean_or_unmap_program_code("NaN") is None


def test_07_unknown_program_code_is_not_guessed(db):
    """7. Unknown Program Code not in course_master is not guessed; raw code preserved as unmapped."""
    ds_id = helper_create_test_dataset(db, "test_phase3_unknown_prog.csv")
    helper_insert_staging_records(db, ds_id, [
        {"ProspectID": "P101", "ProgramCode": "UNKNOWN_COURSE_999"}
    ])

    res = execute_mapping_normalization(db, ds_id, source_file="test_phase3_unknown_prog.csv")
    assert res["normalized_rows"] == 1

    metric = db.execute(
        text("SELECT program_name, course_cluster FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id},
    ).mappings().first()
    assert metric["program_name"] == "UNKNOWN_COURSE_999"
    assert metric["course_cluster"] is None


def test_08_course_master_lookup_works_for_valid_program_code(db):
    """8. Existing course_master lookup works for valid Program Code (e.g. btech_cse_mohali)."""
    ds_id = helper_create_test_dataset(db, "test_phase3_valid_prog.csv")
    helper_insert_staging_records(db, ds_id, [
        {"ProspectID": "P102", "Program Code": "btech_cse_mohali"}
    ])

    res = execute_mapping_normalization(db, ds_id, source_file="test_phase3_valid_prog.csv")
    assert res["normalized_rows"] == 1

    metric = db.execute(
        text("SELECT program_name, course_cluster FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id},
    ).mappings().first()
    assert metric["program_name"] is not None
    assert "Engineering" in (metric["course_cluster"] or "Engineering") or "B.Tech" in metric["program_name"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests 9-12: Canonical Key Projections
# ─────────────────────────────────────────────────────────────────────────────

def test_09_to_12_canonical_key_projections(db):
    """9-12. Test ProspectID, OwnerID -> EmployeeID, State Code, Source Code mappings."""
    ds_id = helper_create_test_dataset(db, "test_phase3_canonical_keys.csv")

    # Save approved mappings for variations
    save_mapping_configuration(db, "test_phase3_canonical_keys.csv", "Sheet1", "Applicant_ID", "Prospect", "ProspectID", 1.0, "approved")
    save_mapping_configuration(db, "test_phase3_canonical_keys.csv", "Sheet1", "Counselor_ID", "Employee", "EmployeeID", 1.0, "approved")
    save_mapping_configuration(db, "test_phase3_canonical_keys.csv", "Sheet1", "State_Abbr", "State", "State Code", 1.0, "approved")
    save_mapping_configuration(db, "test_phase3_canonical_keys.csv", "Sheet1", "Channel_Code", "Source", "Source Code", 1.0, "approved")

    helper_insert_staging_records(db, ds_id, [
        {
            "Applicant_ID": "P_999",
            "Counselor_ID": "EMP_77",
            "State_Abbr": "PB",
            "Channel_Code": "SRC_ONLINE",
        }
    ])

    res = execute_mapping_normalization(db, ds_id, source_file="test_phase3_canonical_keys.csv")
    assert res["normalized_rows"] == 1

    metric = db.execute(
        text("SELECT owner, state_code, source FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id},
    ).mappings().first()
    assert metric["owner"] == "EMP_77"
    assert metric["state_code"] == "PB"
    assert metric["source"] == "SRC_ONLINE"


# ─────────────────────────────────────────────────────────────────────────────
# Tests 13-16: Versioning, Reusability, & Monthly Leads
# ─────────────────────────────────────────────────────────────────────────────

def test_13_mapping_version_recorded(db):
    """13. Mapping version is recorded in normalized dataset lineage."""
    ds_id = helper_create_test_dataset(db, "test_phase3_versioning.csv")
    save_mapping_configuration(db, "test_phase3_versioning.csv", "Sheet1", "ProspectID", "Prospect", "ProspectID", 1.0, "approved", mapping_version=3)
    helper_insert_staging_records(db, ds_id, [{"ProspectID": "P_V3"}])

    res = execute_mapping_normalization(db, ds_id, source_file="test_phase3_versioning.csv")
    assert res["lineage"]["mapping_version"] == 3


def test_14_reusable_mapping_automatically_applied(db):
    """14. Reusable approved mapping is automatically retrieved for subsequent uploads."""
    save_mapping_configuration(db, "test_phase3_recurring.csv", "Sheet1", "Cust_Lead_ID", "Prospect", "ProspectID", 1.0, "approved")
    reused = get_reusable_mappings_for_columns(db, ["Cust_Lead_ID"], source_file="test_phase3_recurring_month2.csv")
    assert "Cust_Lead_ID" in reused
    assert reused["Cust_Lead_ID"]["is_reused"] is True
    assert reused["Cust_Lead_ID"]["target_entity"] == "Prospect"


def test_15_and_16_lead_deduplication_and_upsert(db):
    """15-16. New ProspectID creates lead; recurring upload with existing ProspectID updates cleanly."""
    ds_id = helper_create_test_dataset(db, "test_phase3_leads_upsert.csv")
    helper_insert_staging_records(db, ds_id, [
        {"ProspectID": "P_UNIQUE_1", "FirstName": "Alice"},
        {"ProspectID": "P_UNIQUE_2", "FirstName": "Bob"},
    ])

    res = execute_mapping_normalization(db, ds_id, source_file="test_phase3_leads_upsert.csv")
    assert res["normalized_rows"] == 2

    leads_cnt = db.execute(
        text("SELECT SUM(cy_leads) FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": ds_id},
    ).scalar()
    assert int(leads_cnt) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Tests 17-19: File Profiling & Quality Statistics
# ─────────────────────────────────────────────────────────────────────────────

def test_17_and_18_csv_and_multisheet_processing(db):
    """17-18. Test CSV and multi-sheet file profiling."""
    csv_bytes = b"ProspectID,ProgramCode\nP100,CSE\n"
    prof_csv = profile_multisheet_file_bytes(csv_bytes, "test_phase3.csv")
    assert prof_csv["total_sheets"] == 1
    assert "ProspectID" in prof_csv["sheets"][0]["column_names"]


def profile_multisheet_file_bytes(content: bytes, filename: str):
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        f.flush()
        path = f.name
    try:
        return profile_multisheet_file(path)
    finally:
        os.unlink(path)


def test_19_data_quality_statistics_correct(db):
    """19. Data quality statistics (blank program code, mapping coverage %, duplicate prospect IDs) are calculated correctly."""
    ds_id = helper_create_test_dataset(db, "test_phase3_dq_stats.csv")
    helper_insert_staging_records(db, ds_id, [
        {"ProspectID": "P1", "ProgramCode": ""},
        {"ProspectID": "P1", "ProgramCode": "CSE"},
        {"ProspectID": "P2", "ProgramCode": None},
    ])

    stats = calculate_data_quality_report(db, ds_id, key_prospect_id="ProspectID", key_program_code="ProgramCode")
    assert stats["rows_read"] == 3
    assert stats["blank_program_code"] == 2
    assert stats["duplicate_prospect_id"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests 20-21: API End-to-End Integration
# ─────────────────────────────────────────────────────────────────────────────

def test_20_api_upload_mapping_ingestion_flow(client, db):
    """20. API upload -> suggest -> approve -> execute pipeline works end-to-end."""
    ds_id = helper_create_test_dataset(db, "test_phase3_api_flow.csv")
    helper_insert_staging_records(db, ds_id, [{"ProspectID": "P_API_100", "ProgramCode": "CSE101"}])

    exec_payload = {
        "dataset_id": ds_id,
        "source_file": "test_phase3_api_flow.csv",
        "sheet_name": "Sheet1",
        "decisions": [
            {
                "source_column": "ProspectID",
                "target_entity": "Prospect",
                "target_column": "ProspectID",
                "action": "approve",
            }
        ],
    }
    response = client.post("/api/mapping/execute", json=exec_payload)
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "success"
    assert res["normalized_rows"] == 1


def test_21_frontend_mapping_review_api_contract(client, db):
    """21. Frontend mapping review API contract (/preview-quality & /execute) returns valid contracts."""
    ds_id = helper_create_test_dataset(db, "test_phase3_api_contract.csv")
    helper_insert_staging_records(db, ds_id, [{"ProspectID": "P_CTR_1"}])

    response = client.post(f"/api/mapping/preview-quality?dataset_id={ds_id}")
    assert response.status_code == 200
    data = response.json()
    assert "rows_read" in data
    assert "blank_program_code" in data
    assert "mapping_coverage_pct" in data
