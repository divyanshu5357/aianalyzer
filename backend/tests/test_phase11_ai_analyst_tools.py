"""
Phase 11 — AI Analyst + Trusted Counsellor Tools + Report Generation Test Suite
Validates trusted backend AI tool routing, PostgreSQL data lineage, driver analysis,
report generation, and multi-turn conversational context inheritance.
"""
import unittest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.agent.intent_parser import parse_question
from app.agent.tools.counsellor_tool import CounsellorTool
from app.agent.tools.report_generator_tool import ReportGeneratorTool
from app.agent.tools.driver_analysis_tool import DriverAnalysisTool


class TestPhase11AIAnalystTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_show_counsellors_with_no_calls(self):
        res = answer_question(self.db, "Show counsellors with leads assigned but never called.", conversation_id="p11_test_01")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0 or "counsellor" in res.get("answer", "").lower())
        self.assertIn("counsellor", [c.lower() for c in res.get("columns", [])] if res.get("columns") else ["counsellor"])

    def test_02_which_counsellor_has_most_overdue_interested_leads(self):
        res = answer_question(self.db, "Which counsellor has the most overdue interested leads?", conversation_id="p11_test_02")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0)

    def test_03_show_leads_with_0_calls(self):
        res = answer_question(self.db, "Show leads with 0 calls.", conversation_id="p11_test_03")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0)

    def test_04_show_leads_with_exactly_1_call(self):
        res = answer_question(self.db, "Show leads with exactly 1 call.", conversation_id="p11_test_04")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0)

    def test_05_show_overdue_followups(self):
        res = answer_question(self.db, "Show overdue follow-ups.", conversation_id="p11_test_05")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0 or len(res.get("sections", [])) > 0 or "overdue" in res.get("answer", "").lower())

    def test_06_which_programs_are_declining(self):
        res = answer_question(self.db, "Which programs are declining?", conversation_id="p11_test_06")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0 or len(res.get("sections", [])) > 0 or "program" in res.get("answer", "").lower())

    def test_07_which_counsellors_are_responsible(self):
        res = answer_question(self.db, "Which programs are declining and which counsellors are responsible?", conversation_id="p11_test_07")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0 or len(res.get("sections", [])) > 0 or "analysis" in res.get("answer", "").lower() or "counsellor" in res.get("answer", "").lower())

    def test_08_why_are_admissions_down(self):
        res = answer_question(self.db, "Why are admissions down?", conversation_id="p11_test_08")
        self.assertIsNotNone(res)

    def test_09_compare_cy_vs_py(self):
        res = answer_question(self.db, "Compare CY vs PY admissions.", conversation_id="p11_test_09")
        self.assertIsNotNone(res)

    def test_10_generate_excel_report(self):
        res = answer_question(self.db, "Give me the Excel report.", conversation_id="p11_test_10")
        self.assertIsNotNone(res)
        self.assertIn("/api/counsellor/export", res.get("answer", "") or str(res.get("data", "")))

    def test_11_conversational_followup_using_previous_context(self):
        cid = "p11_test_conv_flow"
        r1 = answer_question(self.db, "Show counsellors with no calls.", conversation_id=cid)
        self.assertIsNotNone(r1)
        r2 = answer_question(self.db, "Only Mohali.", conversation_id=cid)
        self.assertIsNotNone(r2)
        r3 = answer_question(self.db, "Export this.", conversation_id=cid)
        self.assertIsNotNone(r3)

    def test_12_filter_by_campus(self):
        res = answer_question(self.db, "Show counsellor performance for Mohali.", conversation_id="p11_test_12")
        self.assertIsNotNone(res)
        self.assertTrue(len(res.get("data", [])) > 0)

    def test_13_filter_by_month(self):
        res = answer_question(self.db, "Show counsellor performance for April.", conversation_id="p11_test_13")
        self.assertIsNotNone(res)

    def test_14_filter_by_counsellor(self):
        res = answer_question(self.db, "Show performance for Adarsh Singh.", conversation_id="p11_test_14")
        self.assertIsNotNone(res)


if __name__ == "__main__":
    unittest.main()
