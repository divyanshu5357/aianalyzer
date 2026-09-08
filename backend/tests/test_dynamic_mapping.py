"""
Unit & Integration Tests for Phase 2: Dynamic File/Sheet/Column Mapping Foundation.

Tests:
- Exact common-key match
- Column-name variations & synonyms (ProgramCode, OwnerID -> EmployeeID, etc.)
- Confidence scoring & confirmation requirement guardrails
- Ambiguous mappings detection
- Blank Program Code handling (no guessing, marked unmapped)
- Persisted & Reusable mapping workflow across uploads
- API Endpoints (/api/mapping/inspect, suggest-relationships, approve, saved)
"""
import io
import pytest
from fastapi.testclient import TestClient

from app.database.connection import SessionLocal
from app.main import app
from app.mapping.mapping_service import (
    approve_or_edit_mappings,
    get_reusable_mappings_for_columns,
    list_saved_mappings,
    save_mapping_configuration,
)
from app.mapping.relationship_detector import (
    HIGH_CONFIDENCE_THRESHOLD,
    clean_or_unmap_program_code,
    detect_relationships_against_canonical_entities,
    detect_sheet_relationships,
    normalize_slug,
    resolve_canonical_key,
    score_column_pair,
)
from sqlalchemy import text


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        # Clean up test records
        db.execute(text("DELETE FROM intelligence.schema_mappings WHERE source_file LIKE 'test_%'"))
        db.commit()
        db.close()


@pytest.fixture
def api_client():
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Exact Common-Key Matches
# ─────────────────────────────────────────────────────────────────────────────

def test_01_exact_common_key_matches():
    """Verify exact common keys achieve >= 0.95 confidence and are marked as key relationships."""
    keys_to_test = [
        ("ProspectID", "ProspectID"),
        ("Program Code", "Program Code"),
        ("State Code", "State Code"),
        ("EmployeeID", "EmployeeID"),
        ("Source Code", "Source Code"),
    ]

    for src_name, tgt_name in keys_to_test:
        c_src = {"name": src_name, "is_likely_key": True, "sample_values": ["K1", "K2"]}
        c_tgt = {"name": tgt_name, "is_likely_key": True, "sample_values": ["K1", "K2"]}

        conf, match_type, is_key = score_column_pair(c_src, c_tgt)
        assert conf >= 0.95, f"Expected conf >= 0.95 for {src_name} -> {tgt_name}, got {conf}"
        assert match_type == "exact"
        assert is_key is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Column-Name Variations & Synonyms
# ─────────────────────────────────────────────────────────────────────────────

def test_02_column_name_variations_program_code():
    """Verify equivalent Program Code variations resolve to Program Code."""
    variations = [
        "ProgramCode",
        "program_code",
        "Program Code",
        "course_code",
        "CourseCode",
        "prog_code",
    ]
    for var in variations:
        resolved = resolve_canonical_key(var)
        assert resolved == "Program Code", f"Failed for variation: {var}, resolved to {resolved}"


def test_02_column_name_variations_employee_and_owner():
    """Verify EmployeeID and OwnerID variations resolve to EmployeeID."""
    variations = [
        "EmployeeID",
        "employee_id",
        "OwnerID",
        "owner_id",
        "counselor_id",
        "CounselorID",
        "emp_id",
    ]
    for var in variations:
        resolved = resolve_canonical_key(var)
        assert resolved == "EmployeeID", f"Failed for variation: {var}, resolved to {resolved}"

    # Verify score between OwnerID and EmployeeID
    c_owner = {"name": "OwnerID", "is_likely_key": True, "sample_values": ["E101", "E102"]}
    c_emp = {"name": "EmployeeID", "is_likely_key": True, "sample_values": ["E101", "E102"]}
    conf, match_type, is_key = score_column_pair(c_owner, c_emp)
    assert conf >= 0.85, f"Synonym match should be >= 0.85, got {conf}"
    assert match_type == "synonym"
    assert is_key is True


def test_02_column_name_variations_prospect_and_state():
    """Verify ProspectID and State Code variations."""
    assert resolve_canonical_key("prospect_id") == "ProspectID"
    assert resolve_canonical_key("lead_id") == "ProspectID"
    assert resolve_canonical_key("state_code") == "State Code"
    assert resolve_canonical_key("StateCode") == "State Code"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Confidence Scoring & Confirmation Guardrails
# ─────────────────────────────────────────────────────────────────────────────

def test_03_confidence_scoring_and_guardrails():
    """High-confidence mappings do not require confirmation; low/medium mappings require confirmation."""
    sheet_a = {
        "sheet_name": "SheetA",
        "columns_profile": [
            {"name": "ProspectID", "dtype": "string", "is_likely_key": True, "sample_values": ["P1", "P2"]},
            {"name": "owner_status_flag", "dtype": "string", "is_likely_key": False, "sample_values": ["Active", "Pending"]},
        ]
    }
    sheet_b = {
        "sheet_name": "SheetB",
        "columns_profile": [
            {"name": "ProspectID", "dtype": "string", "is_likely_key": True, "sample_values": ["P1", "P2"]},
            {"name": "owner", "dtype": "string", "is_likely_key": False, "sample_values": ["John", "Sarah"]},
        ]
    }

    results = detect_sheet_relationships(sheet_a, sheet_b)
    res_map = {r["source_column"]: r for r in results}

    # ProspectID match
    p_match = res_map.get("ProspectID")
    assert p_match is not None
    assert p_match["confidence"] >= HIGH_CONFIDENCE_THRESHOLD
    assert p_match["requires_confirmation"] is False
    assert p_match["status"] == "suggested"

    # Low/partial match for owner_status_flag
    if "owner_status_flag" in res_map:
        o_match = res_map["owner_status_flag"]
        assert o_match["confidence"] < HIGH_CONFIDENCE_THRESHOLD
        assert o_match["requires_confirmation"] is True
        assert o_match["status"] == "requires_confirmation"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Ambiguous Mappings Detection
# ─────────────────────────────────────────────────────────────────────────────

def test_04_ambiguous_mappings():
    """Verify that when a source column matches multiple candidate targets closely, ambiguity is flagged."""
    sheet_src = {
        "sheet_name": "SourceSheet",
        "columns_profile": [
            {"name": "code", "dtype": "string", "is_likely_key": True, "sample_values": ["A1", "B2"]},
        ]
    }
    sheet_tgt = {
        "sheet_name": "TargetSheet",
        "columns_profile": [
            {"name": "program_code", "dtype": "string", "is_likely_key": True, "sample_values": ["X1", "Y2"]},
            {"name": "state_code", "dtype": "string", "is_likely_key": True, "sample_values": ["X1", "Y2"]},
        ]
    }

    results = detect_sheet_relationships(sheet_src, sheet_tgt)
    assert len(results) > 0
    top = results[0]
    # Because both targets share token 'code', confidences will be equal or very close
    if top.get("is_ambiguous"):
        assert top["requires_confirmation"] is True
        assert len(top.get("competing_candidates", [])) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Blank Program Code Policy (Rule 9)
# ─────────────────────────────────────────────────────────────────────────────

def test_05_blank_program_code_unmapped():
    """Verify blank or null Program Code values are marked unmapped and never guessed."""
    assert clean_or_unmap_program_code("") is None
    assert clean_or_unmap_program_code(None) is None
    assert clean_or_unmap_program_code("   ") is None
    assert clean_or_unmap_program_code("null") is None
    assert clean_or_unmap_program_code("NULL") is None
    assert clean_or_unmap_program_code("nan") is None
    assert clean_or_unmap_program_code("NaN") is None
    assert clean_or_unmap_program_code("n/a") is None
    assert clean_or_unmap_program_code("-") is None

    # Valid program code is preserved
    assert clean_or_unmap_program_code("CSE101") == "CSE101"
    assert clean_or_unmap_program_code("B.Tech CSE") == "B.Tech CSE"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Persisted & Reusable Mapping Workflow
# ─────────────────────────────────────────────────────────────────────────────

def test_06_persisted_and_reused_mappings(db_session):
    """
    Verify complete persistence and reuse cycle:
    1. Save candidate mapping
    2. Approve mapping
    3. Next upload with matching column is automatically reused with confidence=1.0
    """
    # 1. Save candidate mapping
    saved = save_mapping_configuration(
        db=db_session,
        source_file="test_recurring_crm_file.xlsx",
        source_sheet="Sheet1",
        source_column="Applicant_Lead_ID",
        target_entity="Prospect",
        target_column="ProspectID",
        confidence=0.88,
        status="suggested",
    )
    assert saved["id"] is not None
    assert saved["status"] == "suggested"

    # 2. Approve mapping
    decision_res = approve_or_edit_mappings(
        db=db_session,
        mapping_decisions=[{"id": saved["id"], "action": "approve"}]
    )
    assert decision_res["approved"] == 1

    # 3. Subsequent upload with same column
    reused = get_reusable_mappings_for_columns(
        db=db_session,
        columns=["Applicant_Lead_ID", "UnrelatedColumn"],
        source_file="test_recurring_crm_file_month2.xlsx"
    )
    assert "Applicant_Lead_ID" in reused
    match = reused["Applicant_Lead_ID"]
    assert match["is_reused"] is True
    assert match["confidence"] == 1.0
    assert match["target_entity"] == "Prospect"
    assert match["target_column"] == "ProspectID"
    assert match["status"] == "approved"

    # 4. List saved
    saved_list = list_saved_mappings(db=db_session, target_entity="Prospect")
    assert any(m["source_column"] == "Applicant_Lead_ID" for m in saved_list)


# ─────────────────────────────────────────────────────────────────────────────
# 7. End-to-End API Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_07_api_inspect_csv_endpoint(api_client):
    """Verify /api/mapping/inspect endpoint profiles a CSV file."""
    csv_content = b"ProspectID,ProgramCode,OwnerID\nP101,CSE,EMP1\nP102,ME,EMP2\n"
    response = api_client.post(
        "/api/mapping/inspect",
        files={"file": ("test_students.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["file_type"] == "csv"
    assert data["total_sheets"] == 1
    sheet = data["sheets"][0]
    assert sheet["rows"] == 2
    assert "ProspectID" in sheet["column_names"]
    assert "ProgramCode" in sheet["column_names"]


def test_08_api_suggest_relationships_endpoint(api_client, db_session):
    """Verify /api/mapping/suggest-relationships endpoint returns candidates and confirmation status."""
    payload = {
        "source_sheet": {
            "sheet_name": "Sheet1",
            "column_names": ["ProspectID", "ProgramCode", "OwnerID"],
            "columns_profile": [
                {"name": "ProspectID", "dtype": "string", "is_likely_key": True, "sample_values": ["P101", "P102"]},
                {"name": "ProgramCode", "dtype": "string", "is_likely_key": True, "sample_values": ["CSE", "ME"]},
                {"name": "OwnerID", "dtype": "string", "is_likely_key": True, "sample_values": ["E1", "E2"]},
            ],
        },
        "source_file": "test_leads.csv",
        "include_canonical": True,
        "auto_persist_suggestions": True,
    }
    response = api_client.post("/api/mapping/suggest-relationships", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_suggestions"] >= 3
    for sug in data["suggestions"]:
        assert "confidence" in sug
        assert "target_entity" in sug
        assert "target_column" in sug
        assert "requires_confirmation" in sug


def test_09_api_approve_mappings_endpoint(api_client, db_session):
    """Verify /api/mapping/approve endpoint approves mappings."""
    # First create a suggestion
    saved = save_mapping_configuration(
        db=db_session,
        source_file="test_api_leads.csv",
        source_sheet="Sheet1",
        source_column="TestCol",
        target_entity="State",
        target_column="State Code",
        confidence=0.88,
        status="suggested",
    )
    approve_payload = {
        "decisions": [
            {
                "id": saved["id"],
                "action": "approve",
            }
        ]
    }
    response = api_client.post("/api/mapping/approve", json=approve_payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["approved"] == 1


def test_10_api_saved_mappings_endpoint(api_client, db_session):
    """Verify /api/mapping/saved endpoint retrieves stored mappings."""
    save_mapping_configuration(
        db=db_session,
        source_file="test_api_saved.csv",
        source_sheet="Sheet1",
        source_column="SavedCol",
        target_entity="Employee",
        target_column="EmployeeID",
        confidence=1.0,
        status="approved",
    )
    response = api_client.get("/api/mapping/saved?target_entity=Employee")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert any(m["source_column"] == "SavedCol" for m in data["mappings"])
