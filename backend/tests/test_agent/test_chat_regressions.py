import unittest
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from sqlalchemy import text
from app.database.repository import set_active_dataset


class TestChatRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from unittest.mock import patch
        cls.patcher = patch("app.agent.agent_service.plan_question", return_value=None)
        cls.mock_plan = cls.patcher.start()

        cls.db = SessionLocal()
        res = cls.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
        cls.active_dataset_id = str(res) if res else "test_dataset"
        set_active_dataset(cls.db, cls.active_dataset_id)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.db.close()

    def setUp(self):
        self.db.rollback()

    def tearDown(self):
        self.db.rollback()

    # 1. POSITIVE NL INTENT TESTS
    
    def test_question_A_admissions_2026(self):
        """A. How many admissions happened in 2026?"""
        res = answer_question(self.db, "How many admissions happened in 2026?")
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["year"], 2026)
        self.assertIn("admission", res["columns"])
        self.assertEqual(res["data"][0]["admission"], 69776)

    def test_question_B_leads_total(self):
        """B. How many leads are there?"""
        res = answer_question(self.db, "How many leads are there?")
        self.assertIn("leads", res["columns"])
        self.assertEqual(res["data"][0]["leads"], 2600688)

    def test_question_C_leads_by_state(self):
        """C. Show leads by state"""
        res = answer_question(self.db, "Show leads by state")
        self.assertIn("state", res["columns"])
        self.assertIn("leads", res["columns"])
        # Ensure 'None' / NULL state values are filtered out
        for row in res["data"]:
            self.assertIsNotNone(row.get("state"))
            self.assertNotIn(str(row.get("state")).lower().strip(), ["none", "", "null"])

    def test_question_D_admissions_by_program_bar_chart(self):
        """D. Show admissions by program as a bar chart"""
        res = answer_question(self.db, "Show admissions by program as a bar chart")
        self.assertEqual(res["response_type"], "chart")
        self.assertEqual(res["chart_type"], "bar")
        self.assertIn("program_name", res["columns"])
        self.assertIn("admission", res["columns"])
        # Ensure no None programs
        for row in res["data"]:
            self.assertIsNotNone(row.get("program_name"))
            self.assertNotIn(str(row.get("program_name")).lower().strip(), ["none", "", "null"])

    def test_question_E_mohali_vs_chandigarh_pie_chart(self):
        """E. Show Mohali vs Chandigarh admissions as a pie chart"""
        res = answer_question(self.db, "Show Mohali vs Chandigarh admissions as a pie chart")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("MOHALI as a valid campus", res["answer"])
        self.assertIn("CHANDIGARH is not present as a campus", res["answer"])

    def test_question_F_program_performance_detail(self):
        """F. Analyze the performance of program B.COM (H) :(Strategic Finance and Investment Analysis): CM208"""
        res = answer_question(self.db, "Analyze the performance of program B.COM (H) :(Strategic Finance and Investment Analysis): CM208")
        self.assertTrue(res["success"] if "success" in res else True)
        self.assertNotIn("I couldn't find 'Analyze'", res["answer"])
        self.assertIn("B.COM (H) :(Strategic Finance and Investment Analysis): CM208", res["answer"])

    def test_question_G_program_most_admissions(self):
        """G. Which program generated the most admissions?"""
        res = answer_question(self.db, "Which program generated the most admissions?")
        self.assertIn("program_name", res["columns"])
        self.assertIn("admission", res["columns"])
        self.assertNotIn("None", res["answer"])

    def test_question_H_state_most_leads(self):
        """H. Which state generated the most leads?"""
        res = answer_question(self.db, "Which state generated the most leads?")
        self.assertIn("state", res["columns"])
        self.assertIn("leads", res["columns"])
        self.assertNotIn("None", res["answer"])

    def test_question_I_top_10_programs_by_admissions(self):
        """I. Show the top 10 programs by admissions"""
        res = answer_question(self.db, "Show the top 10 programs by admissions")
        self.assertIn("program_name", res["columns"])
        self.assertTrue(len(res["data"]) <= 10)

    def test_question_J_compare_mohali_and_chandigarh(self):
        """J. Compare Mohali and Chandigarh"""
        res = answer_question(self.db, "Compare Mohali and Chandigarh")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("MOHALI as a valid campus", res["answer"])
        self.assertIn("CHANDIGARH is not present as a campus", res["answer"])

    def test_question_K_admissions_for_mohali(self):
        """K. Show admissions for Mohali"""
        res = answer_question(self.db, "Show admissions for Mohali")
        self.assertIn("admission", res["columns"])

    def test_question_L_admissions_2025(self):
        """L. How many admissions happened in 2025?"""
        res = answer_question(self.db, "How many admissions happened in 2025?")
        self.assertEqual(res["year"], 2025)
        self.assertIn("admission", res["columns"])
        self.assertEqual(res["data"][0]["admission"], 3666)

    def test_question_M_leads_by_source(self):
        """M. Show leads by source"""
        res = answer_question(self.db, "Show leads by source")
        self.assertIn("source", res["columns"])

    def test_question_N_admissions_by_campus(self):
        """N. Show admissions by campus"""
        res = answer_question(self.db, "Show admissions by campus")
        self.assertIn("campus_name", res["columns"])

    def test_question_O_counsellor_highest_admission_rate(self):
        """O. Which counsellor had the highest admission rate?"""
        res = answer_question(self.db, "Which counsellor had the highest admission rate?")
        self.assertIn("owner", res["columns"])

    # 2. NEGATIVE TESTS

    def test_negative_students_admitted(self):
        res = answer_question(self.db, "How many students were admitted?")
        self.assertTrue(res.get("success", True))
        self.assertNotIn("couldn't find", res["answer"].lower())

    def test_negative_admissions_happened(self):
        res = answer_question(self.db, "How many admissions happened?")
        self.assertTrue(res.get("success", True))
        self.assertNotIn("couldn't find", res["answer"].lower())

    def test_negative_admission_breakdown(self):
        res = answer_question(self.db, "Show the admission breakdown")
        self.assertTrue(res.get("success", True))
        self.assertNotIn("couldn't find", res["answer"].lower())

    def test_negative_show_performance(self):
        res = answer_question(self.db, "Show performance")
        self.assertTrue(res.get("success", True))
        self.assertNotIn("couldn't find", res["answer"].lower())

    def test_negative_analyze_this(self):
        res = answer_question(self.db, "Analyze this")
        self.assertIn("What would you like me to compare", res["answer"])

    def test_negative_compare_last_year(self):
        res = answer_question(self.db, "Compare last year")
        self.assertIn("What would you like me to compare", res["answer"])

    def test_negative_show_the_trend(self):
        res = answer_question(self.db, "Show the trend")
        self.assertIn("What would you like me to compare", res["answer"])

    def test_negative_programs_improved(self):
        res = answer_question(self.db, "Which programs improved?")
        self.assertTrue(res.get("success", True))
        self.assertNotIn("couldn't find", res["answer"].lower())

    def test_negative_show_top_5_programs(self):
        res = answer_question(self.db, "Show top 5 programs")
        self.assertTrue(res.get("success", True))
        self.assertNotIn("couldn't find", res["answer"].lower())
