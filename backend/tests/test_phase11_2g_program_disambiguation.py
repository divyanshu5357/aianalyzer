"""
Phase 11.2G Program Disambiguation & Program Comparison Automated Test Suite
Verifies:
1. Exact two-program comparison resolves and executes without clarification loop.
2. Long program name vs short program name resolves both programs to ProgramCode.
3. Selecting candidate from clarification option resolves program_b_code and executes immediately.
4. Repeated same question after selection reuses stored ProgramCodes without re-prompting.
5. Follow-up "compare their leads" reuses stored comparison context for leads metric.
6. Follow-up "compare their conversion" reuses stored comparison context for conversion metric.
7. Ambiguous single program asks once, then resolves and executes after selection.
100% database-driven assertions.
"""
import uuid
import pytest
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.database.conversations import get_conversation_context


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_01_exact_two_program_comparison(db: Session):
    """Verify exact two-program comparison executes immediately without asking for clarification."""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    res = answer_question(
        db,
        "Compare CS221 vs CS201 admissions",
        conversation_id=conv_id
    )
    assert res["response_type"] in ("table", "chart")
    assert len(res["data"]) == 2
    assert any(row.get("admission") is not None for row in res["data"])
    assert "multiple candidates" not in res["answer"].lower()

    ctx = get_conversation_context(db, conv_id, None)
    assert ctx is not None
    assert ctx.get("program_a_code") == "CS221"
    assert ctx.get("program_b_code") == "CS201"


def test_02_long_program_name_vs_short_name(db: Session):
    """Verify long IBM AI program name vs short name B.E CSE resolves both to canonical ProgramCodes."""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    long_q = "Compare Bachelor of Engineering (Computer Science Engineering) with Specialization in AI and Machine Learning in association with IBM vs B.E CSE admissions"
    res = answer_question(db, long_q, conversation_id=conv_id)
    assert res["response_type"] in ("table", "chart")
    assert len(res["data"]) == 2
    assert "multiple candidates" not in res["answer"].lower()

    ctx = get_conversation_context(db, conv_id, None)
    assert ctx is not None
    assert ctx.get("program_a_code") == "CS221"
    assert ctx.get("program_b_code") == "CS201"


def test_03_selecting_candidate_from_clarification(db: Session):
    """Verify ambiguous program asks once, and candidate selection in next turn executes query immediately."""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    # Turn 1: Ambiguous comparison prompt
    res1 = answer_question(db, "Compare CS221 vs IBM CSE program admissions", conversation_id=conv_id)
    assert "multiple" in res1["answer"].lower() or "candidates" in res1["answer"].lower()
    assert res1.get("recommendations") is not None

    ctx1 = get_conversation_context(db, conv_id, None)
    assert ctx1.get("pending_target") == "program_b"
    assert ctx1.get("program_a_code") == "CS221"

    # Turn 2: User selects candidate CS230
    res2 = answer_question(db, "CS230", conversation_id=conv_id)
    assert res2["response_type"] in ("table", "chart")
    assert len(res2["data"]) == 2
    assert "multiple candidates" not in res2["answer"].lower()

    ctx2 = get_conversation_context(db, conv_id, None)
    assert ctx2.get("program_a_code") == "CS221"
    assert ctx2.get("program_b_code") == "CS230"


def test_04_repeated_same_question_after_selection(db: Session):
    """Verify repeating the original prompt after selection reuses stored ProgramCodes without re-prompting."""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    # Turn 1: Ambiguous prompt
    answer_question(db, "Compare CS221 vs IBM CSE program admissions", conversation_id=conv_id)
    # Turn 2: Select candidate CS230
    answer_question(db, "CS230", conversation_id=conv_id)
    
    # Turn 3: Repeat original prompt
    res3 = answer_question(db, "Compare CS221 vs IBM CSE program admissions", conversation_id=conv_id)
    assert res3["response_type"] in ("table", "chart")
    assert len(res3["data"]) == 2
    assert "multiple candidates" not in res3["answer"].lower()



def test_05_followup_compare_their_leads(db: Session):
    """Verify follow-up 'compare their leads' reuses stored comparison context."""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    # Turn 1: Initial comparison
    answer_question(db, "Compare CS221 vs CS201 admissions", conversation_id=conv_id)
    
    # Turn 2: Follow-up for leads
    res2 = answer_question(db, "compare their leads", conversation_id=conv_id)
    assert res2["response_type"] in ("table", "chart")
    assert len(res2["data"]) == 2
    assert any("leads" in row for row in res2["data"])


def test_06_followup_compare_their_conversion(db: Session):
    """Verify follow-up 'compare their conversion' calculates conversion rates for stored programs."""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    # Turn 1: Initial comparison
    answer_question(db, "Compare CS221 vs CS201 admissions", conversation_id=conv_id)

    # Turn 2: Follow-up for conversion
    res2 = answer_question(db, "compare their conversion", conversation_id=conv_id)
    assert res2["response_type"] == "table"
    assert len(res2["data"]) == 2
    assert any("conversion_rate (%)" in row for row in res2["data"])


def test_07_ambiguous_single_program_resolution(db: Session):
    """Verify ambiguous single program asks once, then resolves and executes after selection."""
    conv_id = f"test_conv_{uuid.uuid4().hex[:8]}"
    # Turn 1: Ambiguous single program
    res1 = answer_question(db, "Show admissions for IBM B.E program", conversation_id=conv_id)
    assert "multiple" in res1["answer"].lower() or "candidates" in res1["answer"].lower()

    # Turn 2: Select candidate CS230
    res2 = answer_question(db, "CS230", conversation_id=conv_id)
    assert "total" in res2["answer"].lower() or len(res2.get("data", [])) > 0
    assert "multiple candidates" not in res2["answer"].lower()


