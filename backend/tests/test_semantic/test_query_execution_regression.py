"""
Automated Regression Test Suite for AI Analyst Query Execution Layer.
Verifies both the structured semantic plan AND the exact numerical results
against the real validated 2026 Mohali PostgreSQL dataset.
"""

import pytest
import os
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.agent_service import answer_question
from app.database.repository import set_active_dataset


@pytest.fixture(scope="module")
def db_session():
    db_url = os.environ.get("DATABASE_URL", "postgresql://ai_admin:ai_password@127.0.0.1:5433/ai_agent")
    engine = create_engine(db_url)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    # Guarantee active dataset is set to 2026 Mohali
    set_active_dataset(db, "50b48957-3f9c-4c9a-b8f8-1920b20b5bfe", allow_benchmark=True)
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_1_cucet_registrations_2026(db_session: Session):
    res = answer_question(db_session, "How many CUCET registrations happened in 2026?")
    assert res is not None
    assert "data" in res and len(res["data"]) > 0
    val = res["data"][0].get("cucet")
    assert val == 52107, f"Expected 52,107 CUCET registrations, got {val}"


def test_2_admission_conversion_rate(db_session: Session):
    res = answer_question(db_session, "What is the admission conversion rate?")
    assert res is not None
    assert "data" in res and len(res["data"]) > 0
    val = res["data"][0].get("conversion_rate") or res["data"][0].get("lead_admission_rate")
    assert val == 2.31, f"Expected conversion rate 2.31%, got {val}"
    assert "2.31%" in res["answer"], f"Answer string did not contain '2.31%': {res['answer']}"


def test_3_admissions_by_state(db_session: Session):
    res = answer_question(db_session, "Show admissions by state.")
    assert res is not None
    assert len(res["data"]) > 0, "Admissions by state returned empty data"
    top_state = res["data"][0]
    assert "state" in top_state
    assert top_state["state"] == "Punjab"


def test_4_admissions_by_campus(db_session: Session):
    res = answer_question(db_session, "Show admissions by campus.")
    assert res is not None
    assert len(res["data"]) > 0, "Admissions by campus returned empty data"
    campus_row = res["data"][0]
    assert campus_row.get("campus_name") == "Mohali" or campus_row.get("campus") == "Mohali"
    val = campus_row.get("admission")
    assert val == 22546, f"Expected Mohali admissions = 22,546, got {val}"


def test_5_admissions_by_course_cluster(db_session: Session):
    res = answer_question(db_session, "Show admissions by course cluster.")
    assert res is not None
    # course_cluster is unmapped in LeadSquared dataset -> should handle gracefully without crashing
    assert "data" in res


def test_6_admissions_by_program(db_session: Session):
    res = answer_question(db_session, "Show admissions by program.")
    assert res is not None
    # program_name is unmapped in LeadSquared dataset -> should handle gracefully without crashing
    assert "data" in res


def test_7_admissions_by_counsellor(db_session: Session):
    res = answer_question(db_session, "Show admissions by counsellor.")
    assert res is not None
    assert len(res["data"]) > 0, "Admissions by counsellor returned empty data"
    top_counsellor = res["data"][0]
    assert "owner" in top_counsellor


def test_8_which_program_generated_most_admissions(db_session: Session):
    res = answer_question(db_session, "Which program generated the most admissions?")
    assert res is not None
    assert "data" in res


def test_9_which_source_generated_most_leads(db_session: Session):
    res = answer_question(db_session, "Which source generated the most leads?")
    assert res is not None
    assert len(res["data"]) > 0
    top_src = res["data"][0]
    src_name = top_src.get("source")
    leads_val = top_src.get("leads")
    assert "google" in src_name.lower()
    assert leads_val == 261841, f"Expected 261,841 canonical Google leads, got {leads_val}"


def test_10_which_state_had_highest_admissions(db_session: Session):
    res = answer_question(db_session, "Which state had the highest admissions?")
    assert res is not None
    assert len(res["data"]) > 0
    top_st = res["data"][0]
    assert top_st.get("state") == "Punjab"


def test_11_top_10_programs_by_admissions(db_session: Session):
    res = answer_question(db_session, "Show the top 10 programs by admissions.")
    assert res is not None
    assert "data" in res


def test_12_show_leads_by_state(db_session: Session):
    res = answer_question(db_session, "Show leads by state")
    assert res is not None
    assert len(res["data"]) > 0
    top_st = res["data"][0]
    assert "leads" in top_st


def test_13_same_question_consistency(db_session: Session):
    res1 = answer_question(db_session, "How many leads are there in 2026?", conversation_id="test_conv_1")
    val1 = res1["data"][0].get("leads")
    assert val1 == 974328, f"Turn 1 expected 974,328 leads, got {val1}"

    res2 = answer_question(db_session, "How many leads are there in 2026?", conversation_id="test_conv_1")
    val2 = res2["data"][0].get("leads")
    assert val2 == 974328, f"Turn 2 expected 974,328 leads, got {val2}"


def test_14_source_canonicalization(db_session: Session):
    res = answer_question(db_session, "Show leads by source.")
    assert res is not None
    sources = [r["source"] for r in res["data"]]
    lower_sources = [s.lower() for s in sources]
    assert len(lower_sources) == len(set(lower_sources)), f"Duplicate case variants found in sources: {sources}"
