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

class TestPhase11_3_AI_Insights:
    """Phase 11.3 AI Insights & Performance Driver Analysis Test Suite."""

    def test_01_admissions_decline_analysis(self, db: Session):
        conv_id = f"test_ins1_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "Why are admissions down?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert "Admissions dropped" in res["answer"] or "Admissions" in str(res.get("data", []))
        assert "CS221" in res["answer"] or "CS221" in str(res.get("data", []))

    def test_02_program_decline_analysis(self, db: Session):
        conv_id = f"test_ins2_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "Which programs are declining?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert len(res.get("data", [])) > 0
        assert res["data"][0]["program_name"] == "CS221"
        assert res["data"][0]["variance"] == -12

    def test_03_source_decline_analysis(self, db: Session):
        conv_id = f"test_ins3_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "Which sources caused the decline?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert len(res.get("data", [])) > 0
        assert res["data"][0]["source"] == "Website"
        assert res["data"][0]["variance"] == -8

    def test_04_counsellor_underperformance(self, db: Session):
        conv_id = f"test_ins4_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "Which counsellors are underperforming?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert len(res.get("data", [])) > 0
        assert "counsellor_name" in res["data"][0] or "owner" in str(res["data"][0])

    def test_05_target_shortfall_analysis(self, db: Session):
        conv_id = f"test_ins5_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "Why are we below target?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert res["data"][0]["actual"] == 340
        assert res["data"][0]["shortfall"] < 0

    def test_06_improvement_analysis(self, db: Session):
        conv_id = f"test_ins6_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "What improved this month?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert len(res.get("data", [])) > 0
        assert "Google" in str(res.get("data", [])) or "Google" in res["answer"]

    def test_07_management_focus_summary(self, db: Session):
        conv_id = f"test_ins7_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "Where should management focus?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert len(res.get("data", [])) >= 3
        assert "EXECUTIVE MANAGEMENT FOCUS" in res["answer"] or "Program Recovery" in str(res["data"])

    def test_08_missing_period_handling(self, db: Session):
        conv_id = f"test_ins8_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "What is the lead target for Mohali in August 2026?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert res["data"][0]["actual"] == "N/A"
        assert "not available" in res["answer"]

    def test_09_year_resolution_explicit(self, db: Session):
        conv_id = f"test_ins9_{uuid.uuid4().hex[:8]}"
        res = answer_question(db, "Which programs were declining in 2025?", conversation_id=conv_id)
        assert res["response_type"] == "table"
        assert "2025" in res["answer"] or "2024" in res["answer"]
