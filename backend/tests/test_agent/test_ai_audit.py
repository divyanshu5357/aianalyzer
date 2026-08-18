import os
import unittest
import json
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.database.ai_audit import (
    ensure_ai_audit_tables,
    record_turn_audit,
    evaluate_turn,
    promote_to_golden_case,
    seed_initial_golden_cases,
    query_transcripts,
    export_transcripts,
    VALID_EVAL_STATUSES,
    VALID_ERROR_CATEGORIES,
)
from app.agent.agent_service import answer_question


class TestAIAuditStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        try:
            ensure_ai_audit_tables(db)
            seed_initial_golden_cases(db)
        finally:
            db.close()

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_schema_and_initial_golden_cases(self):
        """Verify ai_audit tables exist and initial 4 golden cases are seeded."""
        rows = self.db.execute(
            text("SELECT case_code, question FROM ai_audit.golden_cases ORDER BY case_code ASC")
        ).mappings().all()
        
        codes = [r["case_code"] for r in rows]
        self.assertIn("CASE_1", codes)
        self.assertIn("CASE_2", codes)
        self.assertIn("CASE_3", codes)
        self.assertIn("CASE_4", codes)

    def test_record_turn_audit_and_data_minimization(self):
        """Verify recording turn audit, metadata, and data minimization summary."""
        conv_id = "conv_test_audit_001"
        large_mock_data = [{"id": i, "program": f"Program_{i}", "admissions": i * 10} for i in range(100)]
        
        msg_id = record_turn_audit(
            db=self.db,
            conversation_id=conv_id,
            user_question="Show admissions breakdown for top programs",
            assistant_answer="Here is the breakdown of top programs by admissions:",
            dataset_id="ds_test_123",
            academic_label="2025-26",
            period_a="2025",
            period_b="2026",
            selected_years=[2025, 2026],
            response_type="table",
            detected_intent="breakdown",
            operation="breakdown",
            metric="admission",
            dimension="program_name",
            resolved_entities=["Program_1", "Program_2"],
            filters={"campus_name": "Main Campus"},
            tool_used="BreakdownTool",
            success=True,
            raw_data=large_mock_data,
            columns=["program", "admissions"],
        )

        # Query the turn back
        transcripts = query_transcripts(self.db, dataset_id="ds_test_123")
        found = [t for t in transcripts if t["message_id"] == msg_id]
        self.assertEqual(len(found), 1)

        record = found[0]
        self.assertEqual(record["user_question"], "Show admissions breakdown for top programs")
        self.assertEqual(record["detected_intent"], "breakdown")
        self.assertEqual(record["metric"], "admission")
        self.assertEqual(record["dimension"], "program_name")
        self.assertEqual(record["eval_status"], "unreviewed")
        self.assertEqual(record["result_row_count"], 100)

        # Data Minimization Check: sample_rows must be at most 10, not 100
        summary = record["result_summary"]
        self.assertIn("sample_rows", summary)
        self.assertLessEqual(len(summary["sample_rows"]), 10)

    def test_evaluate_turn_and_promote_golden_case(self):
        """Verify human evaluation lifecycle: marking incorrect, updating correction notes, and promoting to golden case."""
        conv_id = "conv_test_audit_002"
        msg_id = record_turn_audit(
            db=self.db,
            conversation_id=conv_id,
            user_question="Compare B.E. CSE vs MBA",
            assistant_answer="Invalid response",
            dataset_id="ds_test_456",
            detected_intent="unknown",
            error_category="intent_error",
        )

        # Evaluate turn as incorrect with notes
        eval_res = evaluate_turn(
            db=self.db,
            message_id=msg_id,
            status="incorrect",
            correct_answer="B.E. CSE has 150 admissions vs MBA with 80 admissions.",
            correct_intent="comparison",
            correct_metric="admission",
            correct_dimension="program_name",
            correct_entities=["B.E. CSE", "MBA"],
            correction_notes="Agent misclassified entity comparison as unknown intent",
            error_category="intent_error",
        )

        self.assertEqual(eval_res["status"], "incorrect")
        self.assertEqual(eval_res["error_category"], "intent_error")

        # Promote to Golden Case
        gc_res = promote_to_golden_case(
            db=self.db,
            question="Compare B.E. CSE vs MBA admissions",
            case_code="GOLDEN_TEST_COMPARE",
            expected_intent="comparison",
            expected_metric="admission",
            expected_dimension="program_name",
            expected_entities=["B.E. CSE", "MBA"],
            expected_periods=["2025-26"],
            expected_answer_requirements="Must return comparison table of admissions for B.E. CSE vs MBA.",
            source_message_id=msg_id,
        )

        self.assertEqual(gc_res["case_code"], "GOLDEN_TEST_COMPARE")

        # Verify golden case stored in DB
        row = self.db.execute(
            text("SELECT case_code, expected_intent FROM ai_audit.golden_cases WHERE case_code = 'GOLDEN_TEST_COMPARE'")
        ).mappings().first()
        self.assertIsNotNone(row)
        self.assertEqual(row["expected_intent"], "comparison")

    def test_export_transcripts_jsonl_and_csv(self):
        """Verify export capability to JSONL and CSV format."""
        conv_id = "conv_test_audit_export"
        record_turn_audit(
            db=self.db,
            conversation_id=conv_id,
            user_question="Total admissions in CY?",
            assistant_answer="Total admissions in CY is 500.",
            dataset_id="ds_export_999",
            response_type="text",
            detected_intent="metric",
        )

        # Export JSONL
        jsonl_str = export_transcripts(self.db, format_type="jsonl", dataset_id="ds_export_999")
        self.assertTrue(len(jsonl_str) > 0)
        json_obj = json.loads(jsonl_str.split("\n")[0])
        self.assertEqual(json_obj["user_question"], "Total admissions in CY?")

        # Export CSV
        csv_str = export_transcripts(self.db, format_type="csv", dataset_id="ds_export_999")
        self.assertTrue(len(csv_str) > 0)
        self.assertIn("message_id", csv_str)
        self.assertIn("Total admissions in CY?", csv_str)

    def test_chat_integration_records_audit_turn(self):
        """Verify asking a chat question via answer_question creates an audit record seamlessly."""
        res = answer_question(self.db, question="Show total admissions", conversation_id="conv_chat_audit_integration")
        self.assertIn("answer", res)
        
        # Verify turn was audited
        transcripts = query_transcripts(self.db, limit=10)
        user_questions = [t["user_question"] for t in transcripts]
        self.assertIn("Show total admissions", user_questions)


if __name__ == "__main__":
    unittest.main()
