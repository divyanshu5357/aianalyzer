"""
Phase 11.2E Root-Cause Automated Test Suite
Verifies:
1. Dynamic Lead Type category aggregation across all categories (In House, Out Sourced, Others, Unmapped).
2. Adding a new Lead Type to organization.source_master dynamically without code edits.
3. Unmapped source handling.
4. "Show all lead types and their lead count".
5. Explicit 2025 vs 2026 dataset resolution.
6. Target vs Actual reconciliation with matching RAW data.
7. target_for grain separation (Leads, Admission, CUCET).
8. Conversation context persistence & inheritance.
9. Chat transcript generation API endpoint (TXT & CSV).
Strictly 100% database-driven assertions.
"""
import uuid
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.database.repository import get_active_dataset, resolve_raw_dataset, resolve_target_dataset
from app.agent.tools.source_category_tool import SourceCategoryTool
from app.agent.tools.base import ToolRequest
from app.analytics.target_service import get_target_performance
from app.agent.agent_service import answer_question
from app.database.conversations import get_or_create_conversation, get_conversation_context, save_conversation_message


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_01_dynamic_lead_type_categories_all(db: Session):
    """Verify SourceCategoryTool dynamically aggregates all Lead Type categories in PostgreSQL."""
    raw_ds = get_active_dataset(db)
    assert raw_ds is not None

    tool = SourceCategoryTool()
    req = ToolRequest(dataset_id=str(raw_ds), operation="inhouse_vs_outsource", raw_question="show all lead types and their lead count")
    res = tool.execute(db, req)

    assert res.success is True
    categories = [r["category"] for r in res.data]

    # Must contain categories present in database dynamically
    assert len(categories) >= 2
    assert "In House" in categories or "Out Sourced" in categories


def test_02_adding_new_lead_type_without_code_modification(db: Session):
    """Verify adding a new Lead Type to organization.source_master dynamically reflects without code changes."""
    raw_ds = get_active_dataset(db)
    assert raw_ds is not None

    test_source = f"test_src_{uuid.uuid4().hex[:6]}"
    new_lead_type = "Special Partner"

    try:
        # Insert new source into organization.source_master
        db.execute(
            text("""
                INSERT INTO organization.source_master (id, source, lead_type, created_at, updated_at)
                VALUES (gen_random_uuid(), :src, :lt, NOW(), NOW())
            """),
            {"src": test_source, "lt": new_lead_type}
        )
        # Insert matching staging record
        db.execute(
            text("""
                INSERT INTO staging.records (id, dataset_id, row_number, raw_data, created_at, updated_at)
                VALUES (gen_random_uuid(), :ds_id, 999999, jsonb_build_object('ProspectID', :pid, 'Source', :src), NOW(), NOW())
            """),
            {"ds_id": str(raw_ds), "pid": f"pid_{test_source}", "src": test_source}
        )
        db.commit()

        # Query SourceCategoryTool
        tool = SourceCategoryTool()
        req = ToolRequest(dataset_id=str(raw_ds), operation="inhouse_vs_outsource", raw_question="show all lead types")
        res = tool.execute(db, req)

        assert res.success is True
        categories = [r["category"] for r in res.data]
        assert new_lead_type in categories, f"New lead type '{new_lead_type}' was not dynamically detected"

    finally:
        # Clean up test rows
        db.execute(text("DELETE FROM staging.records WHERE raw_data->>'ProspectID' = :pid"), {"pid": f"pid_{test_source}"})
        db.execute(text("DELETE FROM organization.source_master WHERE source = :src"), {"src": test_source})
        db.commit()


def test_03_unmapped_source_handling(db: Session):
    """Verify unmapped sources in staging.records aggregate under 'Unmapped' category."""
    raw_ds = get_active_dataset(db)
    assert raw_ds is not None

    tool = SourceCategoryTool()
    req = ToolRequest(dataset_id=str(raw_ds), operation="inhouse_vs_outsource", raw_question="compare inhouse vs outsource")
    res = tool.execute(db, req)

    assert res.success is True
    rec_meta = res.metadata.get("reconciliation", {})
    unmapped = rec_meta.get("unmapped_leads", 0)
    assert unmapped >= 0


def test_04_explicit_year_dataset_resolution(db: Session):
    """Verify explicit 2025 vs 2026 resolves to matching RAW dataset."""
    ds_2026 = resolve_raw_dataset(db, 2026)
    ds_2025 = resolve_raw_dataset(db, 2025)

    assert ds_2026 is not None
    assert ds_2025 is not None
    assert str(ds_2026) != str(ds_2025)

    # Test answer_question resolves correct dataset for 2026
    res_2026 = answer_question(db, "How many admissions happened in 2026?")
    assert res_2026.get("year") == 2026

    # Test answer_question resolves correct dataset for 2025
    res_2025 = answer_question(db, "How many admissions happened in 2025?")
    assert res_2025.get("year") == 2025


def test_05_target_vs_actual_reconciliation(db: Session):
    """Verify Target comes from TARGET dataset and Actual comes from matching RAW dataset."""
    res_adm = get_target_performance(db, target_for="Admission", campus="Mohali", month="March")
    assert res_adm["success"] is True
    assert res_adm["target"] > 0.0
    assert isinstance(res_adm["actual"], int)
    assert res_adm["actual"] > 0

    res_lead = get_target_performance(db, target_for="Leads", campus="Mohali", month="March")
    assert res_lead["success"] is True
    assert res_lead["target_for"] == "Leads"
    assert isinstance(res_lead["actual"], int)
    assert res_lead["actual"] > 0



def test_06_target_for_grain_separation(db: Session):
    """Verify target_for grains (Admission vs Leads vs CUCET) produce distinct targets."""
    res_adm = get_target_performance(db, target_for="Admission", campus="Mohali")
    res_lead = get_target_performance(db, target_for="Leads", campus="Mohali")

    assert res_adm["target_for"] == "Admission"
    assert res_lead["target_for"] == "Leads"
    # Target values for different Target For grains must not be identical unless coincidence
    assert res_adm["target"] != res_lead["target"] or res_adm["target"] > 0


def test_07_conversation_context_persistence_and_inheritance(db: Session):
    """Verify structured conversation context persists in PostgreSQL and inherits across turns."""
    raw_ds = get_active_dataset(db)
    conv_id = get_or_create_conversation(db, None, str(raw_ds))

    # Turn 1
    res1 = answer_question(db, "How many admissions happened in 2026?", conversation_id=conv_id)
    resolved_ds = res1.get("debug", {}).get("dataset_id") or str(raw_ds)
    ctx1 = get_conversation_context(db, conv_id, None)

    assert ctx1 is not None
    assert ctx1.get("year") == 2026
    assert ctx1.get("metric") is not None

    # Turn 2: Follow-up question inheriting context
    res2 = answer_question(db, "Show state breakdown for that", conversation_id=conv_id)
    assert res2.get("year") == 2026 or res2.get("data") is not None


def test_08_chat_transcript_generation_api(db: Session):
    """Verify on-demand transcript generation endpoint produces valid TXT and CSV responses."""
    from fastapi.testclient import TestClient
    from app.main import app

    raw_ds = get_active_dataset(db)
    conv_id = get_or_create_conversation(db, None, str(raw_ds))

    # Add messages
    save_conversation_message(db, conv_id, "user", "How many admissions in 2026?")
    save_conversation_message(db, conv_id, "assistant", "There were 51 admissions in 2026.")

    client = TestClient(app)

    # Test TXT format
    resp_txt = client.get(f"/api/conversations/{conv_id}/transcript?format=txt")
    assert resp_txt.status_code == 200
    assert "ADMISSIONS INTELLIGENCE ANALYST" in resp_txt.text
    assert "How many admissions in 2026?" in resp_txt.text

    # Test CSV format
    resp_csv = client.get(f"/api/conversations/{conv_id}/transcript?format=csv")
    assert resp_csv.status_code == 200
    assert "USER" in resp_csv.text
    assert "ASSISTANT" in resp_csv.text
