import os
import json
import csv
import uuid
import unittest
import tempfile
from app.database.connection import SessionLocal
from app.database.ai_audit import (
    ensure_ai_audit_tables,
    record_turn_audit,
    evaluate_turn,
)
from app.tools.export_ai_audit import export_audit_records


class TestExportAIAuditCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        cls.conv_id = f"conv_cli_test_{uuid.uuid4().hex[:8]}"
        try:
            ensure_ai_audit_tables(db)
            
            # Seed test turns
            msg1 = record_turn_audit(
                db=db,
                conversation_id=cls.conv_id,
                user_question="Compare B.E. CSE vs MBA",
                assistant_answer="Here is the comparison table",
                dataset_id="ds_cli_test_1",
                academic_label="2025-26",
                period_a="2025",
                period_b="2026",
                selected_years=[2025, 2026],
                response_type="table",
                detected_intent="comparison",
                operation="comparison",
                metric="admission",
                dimension="program_name",
                resolved_entities=["B.E. CSE", "MBA"],
                tool_used="ComparisonTool",
                success=True,
            )

            msg2 = record_turn_audit(
                db=db,
                conversation_id=cls.conv_id,
                user_question="Why did MBA decline?",
                assistant_answer="Unable to parse cause",
                dataset_id="ds_cli_test_1",
                academic_label="2025-26",
                period_a="2025",
                period_b="2026",
                selected_years=[2025, 2026],
                response_type="text",
                detected_intent="driver_analysis",
                operation="driver_analysis",
                error_category="context_error",
                success=False,
            )

            evaluate_turn(
                db=db,
                message_id=msg2,
                status="incorrect",
                correction_notes="Failed context lookup",
                error_category="context_error",
            )
        finally:
            db.close()

    def test_export_jsonl(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            summary = export_audit_records(
                format_type="jsonl",
                output_path=tmp_path,
                conversation_id=self.conv_id,
            )

            self.assertGreaterEqual(summary["conversations"], 1)
            self.assertEqual(summary["messages"], 2)
            self.assertEqual(summary["evaluated_turns"], 1)
            self.assertEqual(summary["output_path"], os.path.abspath(tmp_path))

            # Read JSONL file
            with open(tmp_path, "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]

            self.assertEqual(len(lines), 2)
            req_fields = [
                "conversation_id", "message_id", "role", "question", "assistant_answer",
                "created_at", "dataset_id", "session_period", "year_a", "year_b",
                "intent", "metric", "dimension", "resolved_entities", "filters",
                "tool_used", "success", "error_category", "evaluation_status",
                "correct_answer", "correction_notes"
            ]
            for field in req_fields:
                self.assertIn(field, lines[0])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_export_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            summary = export_audit_records(
                format_type="csv",
                output_path=tmp_path,
                conversation_id=self.conv_id,
            )

            self.assertEqual(summary["messages"], 2)

            # Read CSV file
            with open(tmp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            self.assertEqual(len(rows), 2)
            self.assertIn("conversation_id", reader.fieldnames)
            self.assertIn("evaluation_status", reader.fieldnames)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_export_filter_by_status_and_error_category(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            summary = export_audit_records(
                format_type="jsonl",
                output_path=tmp_path,
                conversation_id=self.conv_id,
                status="incorrect",
                error_category="context_error",
            )

            self.assertEqual(summary["messages"], 1)
            self.assertEqual(summary["evaluated_turns"], 1)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
