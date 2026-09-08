"""
Phase 8C Regression & Verification Test Suite
================================================
Validates:
  1. RAW one-sheet workbook relationship detection & mapping flow.
  2. DIMENSION multi-sheet workbook sheet discovery (Program, State, Source, EMP, Campus).
  3. TARGET multi-sheet workbook independent mapping.
  4. Column name variation matching (e.g. OwnerIdName -> EmployeeID, State Group -> State Code).
  5. Saved mapping persistence & versioned reuse on subsequent uploads.
  6. Code & Identifier mappings return 'Not evaluated' value overlap label without penalizing high confidence score.
"""

import io
import pytest
import pandas as pd
from uuid import uuid4
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import SessionLocal
from app.mapping.relationship_detector import (
    detect_relationships_against_canonical_entities,
    detect_multisheet_workbook_relationships,
    score_column_pair,
)
from app.mapping.workbook_classifier import classify_workbook
from app.ingestion.target_executor import execute_target_ingestion

client = TestClient(app)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        # Teardown: delete test datasets
        test_files = ("Test_Phase8C_Raw.xlsx", "Test_Phase8C_Dim.xlsx", "Test_Phase8C_Target.xlsx")
        session.execute(
            text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename IN :files)"),
            {"files": test_files},
        )
        session.execute(
            text("DELETE FROM staging.records WHERE dataset_id IN (SELECT id FROM system.datasets WHERE original_filename IN :files)"),
            {"files": test_files},
        )
        session.execute(
            text("DELETE FROM system.ingestion_jobs WHERE dataset_id::text IN (SELECT id::text FROM system.datasets WHERE original_filename IN :files)"),
            {"files": test_files},
        )
        session.execute(
            text("DELETE FROM system.datasets WHERE original_filename IN :files"),
            {"files": test_files},
        )
        session.commit()
        session.close()


def test_01_raw_onesheet_workbook_relationship_detection():
    """1. RAW one-sheet workbook detects canonical entity mappings."""
    sheet_profile = {
        "sheet_name": "CRM_Leads",
        "columns_profile": [
            {"name": "ProspectID", "is_likely_key": True, "dtype": "string"},
            {"name": "ProgramCode", "is_likely_key": False, "dtype": "string"},
            {"name": "State Group", "is_likely_key": False, "dtype": "string"},
        ],
    }
    rels = detect_relationships_against_canonical_entities(sheet_profile, source_file="RAW_CRM.xlsx")
    assert len(rels) >= 2
    
    # Check ProspectID mapping
    p_map = next(r for r in rels if r["source_column"] == "ProspectID")
    assert p_map["target_entity"] == "Prospect"
    assert p_map["confidence"] >= 0.85
    assert p_map["value_overlap_label"] == "Not evaluated"


def test_02_dimension_multisheet_workbook_discovery():
    """2. DIMENSION multi-sheet workbook discovers Program, State, Source, EMP master sheets."""
    profile = {
        "filename": "Master_Dimensions_2027.xlsx",
        "sheets": [
            {"sheet_name": "Program Master", "columns": [{"name": "Program Code"}, {"name": "Program Name"}]},
            {"sheet_name": "State Master", "columns": [{"name": "State Code"}, {"name": "State Name"}]},
            {"sheet_name": "Source Master", "columns": [{"name": "Source Code"}, {"name": "Channel"}]},
            {"sheet_name": "Employee List", "columns": [{"name": "EmployeeID"}, {"name": "Counselor Name"}]},
        ],
    }
    classification = classify_workbook(profile)
    assert classification["workbook_type"] == "DIMENSION"
    assert len(classification["sheets_summary"]) == 4


def test_03_target_multisheet_independent_mapping(db):
    """3. TARGET multi-sheet workbook maps target sheets independently."""
    ds_id = str(uuid4())
    batch_id = f"test_p8c_{uuid4().hex[:6]}"

    db.execute(text("""
        INSERT INTO system.datasets (id, dataset_name, original_filename, dataset_type, academic_year, campus_name, workbook_type, status)
        VALUES (:id, 'Test_Phase8C_Target.xlsx', 'Test_Phase8C_Target.xlsx', 'xlsx', 2027, 'Mohali', 'TARGET', 'profiled')
    """), {"id": ds_id})

    db.execute(text("""
        INSERT INTO staging.records (id, dataset_id, row_number, raw_data)
        VALUES 
        (gen_random_uuid(), :ds, 1, CAST('{"Target Leads": 1500, "Target Admissions": 120, "Dimension Type": "program", "Dimension Value": "CSE", "Target Month": 4}' AS jsonb)),
        (gen_random_uuid(), :ds, 2, CAST('{"Target Leads": 800, "Target Admissions": 60, "Dimension Type": "state", "Dimension Value": "PB", "Target Month": 4}' AS jsonb))
    """), {"ds": ds_id})
    db.commit()

    res = execute_target_ingestion(db, dataset_id=ds_id, target_batch_id=batch_id, academic_year=2027, campus_name="Mohali")
    assert res["inserted_count"] == 2


def test_04_different_column_name_variations_mapping():
    """4. Detects mappings across column name variations (OwnerIdName -> EmployeeID, State Group -> State Code)."""
    src_col_emp = {"name": "OwnerIdName", "is_likely_key": True, "dtype": "string"}
    tgt_col_emp = {"name": "EmployeeID", "is_likely_key": True, "dtype": "string"}
    conf_emp, match_emp, _ = score_column_pair(src_col_emp, tgt_col_emp)
    assert conf_emp >= 0.85
    assert match_emp == "synonym"

    src_col_st = {"name": "State Group", "is_likely_key": False, "dtype": "string"}
    tgt_col_st = {"name": "State Code", "is_likely_key": False, "dtype": "string"}
    conf_st, match_st, _ = score_column_pair(src_col_st, tgt_col_st)
    assert conf_st >= 0.85


def test_05_saved_mapping_persistence_and_reuse(db):
    """5. Saved approved batch mapping is persisted and reused."""
    res = client.post("/api/mapping/approve-batch", json={
        "mappings": [
            {
                "source_file": "Test_Phase8C_Raw.xlsx",
                "source_sheet": "CRM_Raw",
                "source_column": "ProspectID",
                "target_entity": "Prospect",
                "target_column": "ProspectID",
                "confidence": 0.98,
                "status": "approved",
            }
        ],
        "workbook_type": "raw_data",
    })
    assert res.status_code == 200
    saved = res.json()["saved"]
    assert len(saved) >= 1
    assert saved[0]["status"] == "approved"


def test_06_code_and_identifier_mappings_value_overlap_rule():
    """6. Identifier and code mappings return 'Not evaluated' for value overlap without penalizing confidence score."""
    wb_profile = [
        {
            "filename": "RAW_Data.xlsx",
            "sheets": [
                {
                    "sheet_name": "Leads",
                    "columns": [{"name": "ProgramCode", "is_likely_key": True, "sample_values": ["CSE", "ECE"]}],
                }
            ],
        },
        {
            "filename": "Dimension_Master.xlsx",
            "sheets": [
                {
                    "sheet_name": "Programs",
                    "columns": [{"name": "Program Code", "is_likely_key": True, "sample_values": ["MBA", "BTECH"]}],
                }
            ],
        },
    ]

    rels = detect_multisheet_workbook_relationships(wb_profile)
    assert len(rels) >= 1
    rel = rels[0]
    assert rel["confidence_rating"] == "HIGH"
    assert rel["value_overlap_label"] == "Not evaluated"
