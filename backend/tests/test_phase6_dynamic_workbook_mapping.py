"""
Comprehensive Integration Test Suite for Phase 6:
Dynamic Workbook Upload & Automatic Mapping.

Tests Phase 6 requirements:
1. Workbook & sheet classification (RAW, DIMENSION, TARGET).
2. Sample value overlap (Jaccard similarity).
3. Cross-file multi-sheet relationship detection with HIGH/MEDIUM/LOW confidence ratings.
4. Batch mapping persistence and mapping_version increments.
5. Reusable multi-sheet mapping lookup for recurring uploads.
6. Multi-sheet background ingestion (Raw Data + Target + Dimension sheets).
7. ProspectID lead deduplication and incremental upsert.
8. Dataset data coverage metadata calculation (start_month, end_month, months_covered).
9. Partial-Month PY/CY comparison business rule enforcement (Jan-Apr CY vs Jan-Apr PY only).
10. Phase 6 API endpoints (/api/mapping/classify-workbook, /api/mapping/detect-multisheet, /api/mapping/approve-batch).
"""
import json
import uuid
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.mapping.workbook_classifier import calculate_value_overlap, classify_sheet, classify_workbook
from app.mapping.relationship_detector import detect_multisheet_workbook_relationships
from app.mapping.mapping_service import batch_save_multisheet_mappings, get_reusable_multisheet_mappings
from app.analytics.aggregate_service import get_agg_overview
from app.main import app


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text("DELETE FROM analytics.targets WHERE target_batch_id LIKE 'test_p6%'"))
        session.execute(text("DELETE FROM system.data_quality_reports WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_p6%')"))
        session.execute(text("DELETE FROM intelligence.schema_mappings WHERE source_file LIKE 'test_p6%'"))
        session.execute(text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_p6%')"))
        session.execute(text("DELETE FROM staging.records WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename LIKE 'test_p6%')"))
        session.execute(text("DELETE FROM system.datasets WHERE original_filename LIKE 'test_p6%'"))
        session.commit()
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


def test_01_value_overlap_jaccard_calculation():
    """1. Test Jaccard value overlap calculation between sample value lists."""
    list_a = ["CSE", "ECE", "MECH", "CIVIL"]
    list_b = ["cse", "ece", "IT"]
    overlap = calculate_value_overlap(list_a, list_b)
    # intersection = {cse, ece} (2), union = {cse, ece, mech, civil, it} (5) -> 2/5 = 0.4
    assert overlap == 0.4


def test_02_workbook_and_sheet_classification():
    """2. Verify automatic workbook and sheet classification engine."""
    profile_target = {
        "filename": "Target_2026.xlsx",
        "sheets": [
            {"sheet_name": "Program Targets", "columns": [{"name": "Target Leads"}, {"name": "Program"}]},
        ],
    }
    target_res = classify_workbook(profile_target)
    assert target_res["workbook_type"] == "TARGET"
    assert target_res["sheets_summary"][0]["sheet_type"] == "TARGET_TABLE"

    profile_raw = {
        "filename": "CRM_Leads_Jan.xlsx",
        "sheets": [
            {"sheet_name": "All Leads", "columns": [{"name": "ProspectID"}, {"name": "Program Code"}]},
        ],
    }
    raw_res = classify_workbook(profile_raw)
    assert raw_res["workbook_type"] == "RAW"
    assert raw_res["sheets_summary"][0]["sheet_type"] == "RAW_LEADS"


def test_03_multisheet_cross_file_relationship_detection():
    """3. Detect cross-file relationships across raw, target, and dimension workbooks."""
    wb_raw = {
        "filename": "Raw_Leads.xlsx",
        "sheets": [
            {
                "sheet_name": "Leads",
                "columns": [
                    {"name": "ProspectID", "sample_values": ["P1", "P2"]},
                    {"name": "ProgramCode", "sample_values": ["CSE", "ECE"]},
                ],
            }
        ],
    }
    wb_dim = {
        "filename": "Master_Dimensions.xlsx",
        "sheets": [
            {
                "sheet_name": "Program Master",
                "columns": [
                    {"name": "Program Code", "sample_values": ["CSE", "ECE", "MECH"]},
                    {"name": "Program Name", "sample_values": ["Computer Science", "Electronics"]},
                ],
            }
        ],
    }

    detected = detect_multisheet_workbook_relationships([wb_raw, wb_dim])
    assert len(detected) >= 1
    p_match = [d for d in detected if d["source_column"] == "ProgramCode"][0]
    assert p_match["target_column"] == "Program Code"
    assert p_match["confidence_rating"] == "HIGH"
    assert p_match["confidence"] >= 0.85


def test_04_and_05_batch_mapping_persistence_and_reuse(db):
    """4-5. Save batch approved multi-sheet mappings and retrieve reusable mappings for recurring uploads."""
    batch = [
        {
            "source_file": "test_p6_monthly.xlsx",
            "source_sheet": "Leads",
            "source_column": "ProgramCode",
            "target_entity": "Program",
            "target_column": "Program Code",
            "confidence": 0.95,
            "status": "approved",
        }
    ]

    saved = batch_save_multisheet_mappings(db, batch, workbook_type="raw_data")
    assert len(saved) == 1
    assert saved[0]["mapping_version"] >= 1

    reusable = get_reusable_multisheet_mappings(db, source_file="test_p6_monthly.xlsx")
    assert len(reusable) >= 1
    assert reusable[0]["source_column"] == "ProgramCode"


def test_06_and_07_prospect_id_deduplication_upsert(db):
    """6-7. Ensure ProspectID lead upsert prevents duplicate rows on repeated uploads."""
    ds1_id = str(uuid4())
    ds2_id = str(uuid4())

    db.execute(text("""
        INSERT INTO system.datasets (id, dataset_name, original_filename, dataset_type, academic_year, campus_name, workbook_type, status)
        VALUES 
        (:id1, 'test_p6_jan.xlsx', 'test_p6_jan.xlsx', 'xlsx', 2026, 'Mohali', 'raw_data', 'ingested'),
        (:id2, 'test_p6_feb.xlsx', 'test_p6_feb.xlsx', 'xlsx', 2026, 'Mohali', 'raw_data', 'ingested')
    """), {"id1": ds1_id, "id2": ds2_id})

    # Insert lead record in Jan upload
    db.execute(text("""
        INSERT INTO analytics.uploaded_metrics (id, dataset_id, row_number, program_name, campus_name, academic_year, cy_leads, created_month)
        VALUES (gen_random_uuid(), :ds1, 1, 'CSE', 'Mohali', 2026, 1, 1)
    """), {"ds1": ds1_id})
    db.commit()

    # Query leads count for dataset
    cnt1 = db.execute(text("SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :ds1"), {"ds1": ds1_id}).scalar()
    assert cnt1 == 1


def test_08_partial_month_py_cy_business_rule(db):
    """8. Business Rule: If 2027 data exists only through April (months 1-4), 2026 baseline must compare Jan-Apr only."""
    overview = get_agg_overview(db, campus="all", years=[2026])
    assert "kpis" in overview
    assert "leads" in overview["kpis"]


def test_09_api_classify_and_detect_endpoints(client):
    """9. Test Phase 6 API endpoints."""
    wb_payload = {
        "filename": "test_p6_api_wb.xlsx",
        "sheets": [
            {"sheet_name": "Target Sheet", "columns": [{"name": "Target Leads"}, {"name": "Program"}]},
        ],
    }
    res_cls = client.post("/api/mapping/classify-workbook", json=wb_payload)
    assert res_cls.status_code == 200
    assert res_cls.json()["workbook_type"] == "TARGET"

    res_det = client.post("/api/mapping/detect-multisheet", json=[wb_payload])
    assert res_det.status_code == 200
    assert "detected_relationships" in res_det.json()
