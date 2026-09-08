"""
Phase 11.2C — Semantic Query Routing, Entity Resolution & Conversation Context Tests
"""
import pytest
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question, get_active_dataset
from app.semantic.entity_resolver import resolve_entity_dimension


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_entity_resolution_dimensions(db: Session):
    active_ds = get_active_dataset(db)
    
    # 1. Inhouse / Outsource -> Lead Type
    res_in = resolve_entity_dimension(db, active_ds, "inhouse")
    assert res_in["resolved"] is True
    assert res_in["dimension"] == "lead_type"
    assert res_in["value"] == "In House"

    res_out = resolve_entity_dimension(db, active_ds, "outsource")
    assert res_out["resolved"] is True
    assert res_out["dimension"] == "lead_type"
    assert res_out["value"] == "Out Sourced"

    # 2. Google -> Source
    res_goog = resolve_entity_dimension(db, active_ds, "Google")
    assert res_goog["resolved"] is True
    assert res_goog["dimension"] == "source"
    assert res_goog["value"] == "Google"

    # 3. Punjab -> State
    res_pb = resolve_entity_dimension(db, active_ds, "Punjab")
    assert res_pb["resolved"] is True
    assert res_pb["dimension"] == "state"
    assert res_pb["value"] == "Punjab"


def test_conversation_a_inhouse_vs_outsource(db: Session):
    cid = "test_conv_a_phase11_2c"
    res1 = answer_question(db, "Compare inhouse vs outsource leads", conversation_id=cid)
    assert res1.get("answer") is not None
    assert "In House" in res1.get("answer") or "Inhouse" in res1.get("answer")

    res2 = answer_question(db, "Compare inhouse vs outsource leads and conversion", conversation_id=cid)
    assert res2.get("answer") is not None
    assert "In House" in res2.get("answer") or "Inhouse" in res2.get("answer")


def test_conversation_b_google_breakdowns(db: Session):
    cid = "test_conv_b_phase11_2c"
    res1 = answer_question(db, "Show all sources", conversation_id=cid)
    assert res1.get("answer") is not None

    res2 = answer_question(db, "Show top sources for Google", conversation_id=cid)
    assert "already a Source" in res2.get("answer")

    res3 = answer_question(db, "Show state breakdown for Google", conversation_id=cid)
    assert res3.get("debug", {}).get("intent") == "state_breakdown_program"
    assert res3.get("data") is not None
    assert len(res3.get("data")) > 0
    assert "Punjab" in [row.get("state") for row in res3["data"]]


def test_conversation_c_top_owners_inhouse(db: Session):
    cid = "test_conv_c_phase11_2c"
    res = answer_question(db, "Top owners Inhouse", conversation_id=cid)
    assert res.get("answer") is not None
    assert "Inhouse" in res.get("answer") or "In House" in res.get("answer")


def test_conversation_d_year_inheritance(db: Session):
    cid = "test_conv_d_phase11_2c"
    res1 = answer_question(db, "How many admissions happened in 2026?", conversation_id=cid)
    ds_id_2026 = res1.get("debug", {}).get("dataset_id")
    assert ds_id_2026 is not None

    res2 = answer_question(db, "Show leads by state", conversation_id=cid)
    ds_id_d2 = res2.get("debug", {}).get("dataset_id")
    assert ds_id_d2 == ds_id_2026
    assert "2026" in res2.get("answer")
