import uuid
import pytest
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.database.repository import get_active_dataset

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

class TestPhase11_2H_E2E_QA:
    """End-to-End AI QA Verification Suite across all 9 business QA groups."""

    def test_01_group1_scalar_queries(self, db: Session):
        conv_id = f"test_qa1_{uuid.uuid4().hex[:8]}"

        # 1. 2026 Admissions
        res1 = answer_question(db, "How many admissions happened in 2026?", conversation_id=conv_id)
        assert res1["response_type"] == "text"
        assert "51" in res1["answer"]

        # 2. 2026 Leads
        res2 = answer_question(db, "How many leads happened in 2026?", conversation_id=conv_id)
        assert res2["response_type"] == "text"
        assert "1,000" in res2["answer"] or "1000" in res2["answer"]

        # 3. Total In House Leads
        res3 = answer_question(db, "Show total In House leads", conversation_id=conv_id)
        assert res3["response_type"] == "table"
        assert "In House" in res3["answer"] or (res3.get("data") and res3["data"][0]["category"] == "In House")
        assert any(str(row.get("leads")) == "670" for row in res3.get("data", []))

        # 4. Total Out Sourced Leads
        res4 = answer_question(db, "Show total Out Sourced leads", conversation_id=conv_id)
        assert res4["response_type"] == "table"
        assert any(str(row.get("leads")) == "273" for row in res4.get("data", []))

        # 5. Total Others Leads
        res5 = answer_question(db, "Show total Others leads", conversation_id=conv_id)
        assert res5["response_type"] == "table"
        assert any(str(row.get("leads")) == "55" for row in res5.get("data", []))

        # 6. All Lead Types & Counts
        res6 = answer_question(db, "Show all lead types and counts", conversation_id=conv_id)
        assert res6["response_type"] == "table"
        assert len(res6.get("data", [])) >= 3

    def test_02_group2_lead_type_queries(self, db: Session):
        conv_id = f"test_qa2_{uuid.uuid4().hex[:8]}"

        # 1. In House vs Out Sourced Leads
        res1 = answer_question(db, "Compare In House vs Out Sourced leads", conversation_id=conv_id)
        assert res1["response_type"] == "table"
        cats = [row["category"] for row in res1.get("data", [])]
        assert "In House" in cats and "Out Sourced" in cats

        # 2. In House vs Out Sourced Conversion
        res2 = answer_question(db, "Compare In House vs Out Sourced conversion", conversation_id=conv_id)
        assert res2["response_type"] == "table"
        assert "conversion_rate" in res2.get("columns", []) or "conversion_rate" in str(res2.get("data", []))

        # 3. Which sources are Out Sourced
        res3 = answer_question(db, "Which sources are Out Sourced?", conversation_id=conv_id)
        assert res3["response_type"] == "table"
        assert len(res3.get("data", [])) > 0
        assert res3["data"][0]["lead_type"] == "Out Sourced"

    def test_03_group3_source_queries(self, db: Session):
        conv_id = f"test_qa3_{uuid.uuid4().hex[:8]}"

        # 1. Top 5 Sources by Admissions
        res1 = answer_question(db, "Show top 5 sources by admissions", conversation_id=conv_id)
        assert res1["response_type"] == "table"
        assert len(res1.get("data", [])) == 5

        # 2. Admissions for Google in 2026
        res2 = answer_question(db, "Show admissions for Google in 2026", conversation_id=conv_id)
        assert "17" in res2["answer"] or any(row.get("admissions") == 17 for row in res2.get("data", []))

        # 3. State Breakdown for Google
        res3 = answer_question(db, "Show state breakdown for Google", conversation_id=conv_id)
        assert res3["response_type"] == "table"
        assert "state" in res3.get("columns", [])

        # 4. Compare Google vs Website Admissions
        res4 = answer_question(db, "Compare Google vs Website admissions", conversation_id=conv_id)
        assert res4["response_type"] == "table"
        assert len(res4.get("data", [])) == 2

    def test_04_group4_program_queries(self, db: Session):
        conv_id = f"test_qa4_{uuid.uuid4().hex[:8]}"

        # 1. Program with Most Leads
        res1 = answer_question(db, "Which program generated the most leads?", conversation_id=conv_id)
        assert res1["response_type"] == "table"
        assert len(res1.get("data", [])) > 0

        # 2. University Name by ProgramCode
        res2 = answer_question(db, "What is the university name for CS221?", conversation_id=conv_id)
        assert res2["response_type"] == "text"
        assert "CS221" in res2["answer"] and "Mohali" in res2["answer"]

        # 3. Program Comparison
        res3 = answer_question(db, "Compare CS221 vs CS201 program admissions", conversation_id=conv_id)
        assert res3["response_type"] == "table"
        assert len(res3.get("data", [])) == 2

    def test_05_group5_target_queries(self, db: Session):
        conv_id = f"test_qa5_{uuid.uuid4().hex[:8]}"

        # 1. Lead Target August 2026 (RAW unavailable -> Actual N/A)
        res1 = answer_question(db, "What is the lead target for Mohali in August 2026?", conversation_id=conv_id)
        assert res1["response_type"] == "table"
        assert res1["data"][0]["actual"] == "N/A"
        assert res1["data"][0]["target"] > 0

        # 2. Admission Target August 2026
        res2 = answer_question(db, "What is the admission target for Mohali in August 2026?", conversation_id=conv_id)
        assert res2["response_type"] == "table"
        assert res2["data"][0]["actual"] == "N/A"
        assert res2["data"][0]["target"] > 0

        # 3. March 2026 Actual vs Target
        res3 = answer_question(db, "Compare actual leads vs lead target for Mohali in March 2026", conversation_id=conv_id)
        assert res3["response_type"] == "table"
        assert res3["data"][0]["actual"] == 340

    def test_06_group6_context_preservation(self, db: Session):
        conv_id = f"test_qa6_{uuid.uuid4().hex[:8]}"

        # Turn 1: 2026 Admissions
        res1 = answer_question(db, "How many admissions happened in 2026?", conversation_id=conv_id)
        assert "51" in res1["answer"]

        # Turn 2: Show leads by state (inherits year 2026)
        res2 = answer_question(db, "Show leads by state", conversation_id=conv_id)
        assert res2["response_type"] == "table"
        assert res2.get("year") == 2026

        # Turn 3: Compare their conversion (inherits states & year 2026)
        res3 = answer_question(db, "Compare their conversion", conversation_id=conv_id)
        assert res3["response_type"] == "table"
        assert res3.get("year") == 2026

    def test_07_group8_loop_prevention(self, db: Session):
        conv_id = f"test_qa8_{uuid.uuid4().hex[:8]}"

        # Turn 1: Ambiguous prompt
        answer_question(db, "Compare CS221 vs IBM CSE program admissions", conversation_id=conv_id)
        # Turn 2: Select option CS230
        res2 = answer_question(db, "CS230", conversation_id=conv_id)
        assert res2["response_type"] in ("table", "chart")

        # Turn 3: Repeat prompt -> Must execute without re-prompting
        res3 = answer_question(db, "Compare CS221 vs IBM CSE program admissions", conversation_id=conv_id)
        assert res3["response_type"] in ("table", "chart")

    def test_08_group9_export_transcript(self, db: Session):
        from app.api.conversations import get_conversation_transcript
        conv_id = f"test_qa9_{uuid.uuid4().hex[:8]}"

        answer_question(db, "How many admissions happened in 2026?", conversation_id=conv_id)
        answer_question(db, "Show leads by state", conversation_id=conv_id)

        res_txt = get_conversation_transcript(conv_id, format="txt", db=db)
        res_csv = get_conversation_transcript(conv_id, format="csv", db=db)

        assert "How many admissions happened in 2026?" in res_txt.body.decode()
        assert "Show leads by state" in res_txt.body.decode()
        assert "How many admissions happened in 2026?" in res_csv.body.decode()
