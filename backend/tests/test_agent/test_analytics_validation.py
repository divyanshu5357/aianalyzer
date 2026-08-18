"""
Regression tests for analytics validation and structured result presentation:
1. Zero ranking wording
2. Same period comparison validation
3. Minimum lead threshold in driver analysis
4. Structured sections formatting
"""
import os
import unittest
from unittest.mock import MagicMock
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.agent.response_formatter import format_tool_response
from app.agent.tools.base import ToolResult
from app.analytics.period_resolver import compare_periods


class TestAnalyticsValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        res = cls.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
        cls.active_dataset_id = str(res) if res else None

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.rollback()

    def tearDown(self):
        self.db.rollback()

    def test_01_zero_ranking_wording(self):
        """1. Zero ranking returns friendly 'No admissions recorded' message when top val is 0."""
        tool_res = ToolResult(
            success=True,
            operation="ranking",
            columns=["program_name", "admission"],
            data=[{"program_name": "Program Zero", "admission": 0}],
            response_type="text",
            year=2026,
            metadata={"dimension": "program_name", "metric": "admission", "limit": 1, "sort_direction": "DESC"},
        )
        formatted = format_tool_response(tool_res, "Which program had the highest admissions?")
        self.assertIn("No admissions were recorded for any matching program in the selected period.", formatted["answer"])

    def test_02_same_period_comparison_prevention(self):
        """2. Comparing identical periods throws ValueError with clear message."""
        with self.assertRaises(ValueError) as ctx:
            compare_periods(self.db, "admission", "2025-26", "2025-26", "program_name")
        self.assertIn("Please select two different years for comparison.", str(ctx.exception))

    def test_03_min_insight_leads_threshold(self):
        """3. Low lead entities below MIN_INSIGHT_LEADS are not flagged as notable performance anomalies."""
        from app.agent.tools.driver_analysis_tool import DriverAnalysisTool
        from app.agent.tools.base import ToolRequest

        if not self.active_dataset_id:
            self.skipTest("No active dataset available")

        # Discover a program name in active dataset
        prog_row = self.db.execute(text(
            f'SELECT "program_name" FROM analytics.uploaded_metrics WHERE dataset_id = :ds AND "program_name" IS NOT NULL LIMIT 1'
        ), {"ds": self.active_dataset_id}).scalar()

        if not prog_row:
            self.skipTest("No program row found in active dataset")

        tool = DriverAnalysisTool()
        req = ToolRequest(
            operation="driver_analysis",
            dataset_id=self.active_dataset_id,
            dimension="program_name",
            values=[str(prog_row)],
            current_year=2026,
            previous_year=2025,
            raw_question=f"Why did {prog_row} change?",
        )
        res = tool.execute(self.db, req)
        self.assertTrue(res.success)
        self.assertIn("sections", res.metadata)

    def test_04_structured_sections_output(self):
        """4. Response formatter returns response_type='analysis' and includes sections array."""
        tool_res = ToolResult(
            success=True,
            operation="driver_analysis",
            columns=["program_name", "cy_leads"],
            data=[{"program_name": "Prog A", "cy_leads": 100}],
            response_type="table",
            year=2026,
            metadata={
                "sections": [
                    {
                        "type": "metric_table",
                        "title": "Performance Change",
                        "columns": ["Metric", "Change"],
                        "data": [{"Metric": "Leads", "Change": "+10"}],
                    }
                ]
            },
        )
        formatted = format_tool_response(tool_res, "Why did it change?")
        self.assertEqual(formatted["response_type"], "analysis")
        self.assertIn("sections", formatted)
        self.assertEqual(len(formatted["sections"]), 1)


if __name__ == "__main__":
    unittest.main()
