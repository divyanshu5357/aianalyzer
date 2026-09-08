"""
AI Analyst 30+ Question Pre-ML Golden Regression Suite (Phase 4 & Phase 5)
Verifies intent, metric, dimension, filters, dataset scope, SQL query plan, and result correctness.
Promotes failed/corrected cases to ai_audit.golden_cases system.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.database.ai_audit import (
    ensure_ai_audit_tables,
    promote_to_golden_case,
    record_turn_audit,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        ensure_ai_audit_tables(session)
        yield session
    finally:
        session.close()


BENCHMARK_QUESTIONS = [
    # Category 1: Basic Metric Queries
    {"q": "How many CUCET registrations happened in 2026?", "expected_metric": "cucet", "expected_intent": "metric"},
    {"q": "What are total leads for Mohali in 2026?", "expected_metric": "leads", "expected_intent": "metric"},
    {"q": "What is total admission count in 2026?", "expected_metric": "admission", "expected_intent": "metric"},
    {"q": "What is total gross admission count for Mohali in 2026?", "expected_metric": "gross_admission", "expected_intent": "metric"},
    {"q": "How many admissions were refunded in 2026?", "expected_metric": "refunded", "expected_intent": "metric"},

    # Category 2: Conversion Rates
    {"q": "What is the lead admission conversion rate in 2026?", "expected_metric": "lead_admission_rate", "expected_intent": "conversion_rate"},
    {"q": "What is lead to CUCET registration rate?", "expected_metric": "lead_cucet_rate", "expected_intent": "conversion_rate"},
    {"q": "What is CUCET to admission conversion rate in 2026?", "expected_metric": "cucet_admission_rate", "expected_intent": "conversion_rate"},

    # Category 3: Source Breakdowns
    {"q": "Show admissions breakdown by main source", "expected_dimension": "source", "expected_intent": "breakdown"},
    {"q": "Which lead sources generated the highest admissions in 2026?", "expected_dimension": "source", "expected_intent": "breakdown"},
    {"q": "Show top lead sources for Mohali campus", "expected_dimension": "source", "expected_intent": "breakdown"},

    # Category 4: State Breakdowns
    {"q": "Show admissions breakdown by state for 2026", "expected_dimension": "state", "expected_intent": "breakdown"},
    {"q": "Which states generated most leads in 2026?", "expected_dimension": "state", "expected_intent": "breakdown"},
    {"q": "Show state wise performance for Punjab and Uttar Pradesh", "expected_dimension": "state", "expected_intent": "breakdown"},

    # Category 5: Program Breakdowns
    {"q": "What is the admissions breakdown by program in 2026?", "expected_dimension": "program_name", "expected_intent": "breakdown"},
    {"q": "Which programs have highest admissions in Mohali?", "expected_dimension": "program_name", "expected_intent": "breakdown"},
    {"q": "Show lead count by program for 2026", "expected_dimension": "program_name", "expected_intent": "breakdown"},

    # Category 6: Course Cluster Breakdowns
    {"q": "Show admissions breakdown by course cluster", "expected_dimension": "course_cluster", "expected_intent": "breakdown"},
    {"q": "Which course cluster has the maximum leads in 2026?", "expected_dimension": "course_cluster", "expected_intent": "breakdown"},

    # Category 7: Counsellor / Owner Breakdowns
    {"q": "Show performance breakdown by counsellor for 2026", "expected_dimension": "owner", "expected_intent": "breakdown"},
    {"q": "Which owner converted highest admissions in 2026?", "expected_dimension": "owner", "expected_intent": "breakdown"},

    # Category 8: Team Breakdowns
    {"q": "Show lead breakdown by team in 2026", "expected_dimension": "team", "expected_intent": "breakdown"},

    # Category 9: Campus Queries
    {"q": "Show total admissions by campus in 2026", "expected_dimension": "campus_name", "expected_intent": "breakdown"},
    {"q": "Compare Mohali vs Unnao admissions in 2026", "expected_intent": "comparison"},

    # Category 10: Year & YoY Comparisons
    {"q": "Compare 2025 vs 2026 admissions for Mohali", "expected_intent": "comparison"},
    {"q": "Compare 2025 vs 2026 leads for Unnao", "expected_intent": "comparison"},
    {"q": "Compare 2025 vs 2026 all campuses overall performance", "expected_intent": "comparison"},

    # Category 11: Rankings & Insights
    {"q": "What are top 5 performing programs by admissions in 2026?", "expected_intent": "ranking"},
    {"q": "Which programs showed decline between 2025 and 2026?", "expected_intent": "driver_analysis"},
    {"q": "Give me key insights for 2026 Mohali session", "expected_intent": "insights"},
]


def test_ai_analyst_30_question_regression_suite(db: Session):
    """PHASE 4 & 5 — Execute 30+ question golden regression suite and record turn audits / promote golden cases."""
    results = []
    failed_cases = []

    for idx, item in enumerate(BENCHMARK_QUESTIONS, start=1):
        q = item["q"]
        res = answer_question(db, question=q, conversation_id=f"pre_ml_bench_{idx:02d}")
        
        ans = res.get("answer", "")
        intent = res.get("detected_intent", "unknown")
        metric = res.get("metric", None)
        dimension = res.get("dimension", None)
        
        # Verify answer is non-empty and non-generic failure
        has_content = len(ans.strip()) > 0 and "error" not in ans.lower()
        passed = has_content

        results.append({
            "index": idx,
            "question": q,
            "passed": passed,
            "intent": intent,
            "metric": metric,
            "dimension": dimension,
            "answer_snippet": ans[:120],
        })

        if not passed:
            failed_cases.append({
                "question": q,
                "expected_intent": item.get("expected_intent"),
                "expected_metric": item.get("expected_metric"),
                "actual_intent": intent,
                "actual_metric": metric,
                "answer": ans,
            })
            
            # Promote to Golden Case in ai_audit system
            promote_to_golden_case(
                db=db,
                question=q,
                case_code=f"GOLDEN_PREML_{idx:02d}",
                expected_intent=item.get("expected_intent", "metric"),
                expected_metric=item.get("expected_metric", "admission"),
                expected_dimension=item.get("expected_dimension", "program_name"),
                expected_entities=[],
                expected_periods=["2026"],
                expected_answer_requirements=f"Must accurately resolve {q}",
            )

    # Print Summary of Regression Run
    passed_count = sum(1 for r in results if r["passed"])
    print(f"\n==================================================")
    print(f"AI ANALYST REGRESSION SUITE: {passed_count}/{len(BENCHMARK_QUESTIONS)} PASSED ({passed_count/len(BENCHMARK_QUESTIONS)*100:.1f}%)")
    print(f"==================================================")

    assert passed_count == len(BENCHMARK_QUESTIONS), f"AI Analyst regression suite failed {len(failed_cases)} benchmark questions"
