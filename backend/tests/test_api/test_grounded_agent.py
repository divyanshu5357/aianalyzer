import unittest
from unittest.mock import patch
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from sqlalchemy import text
from app.database.repository import set_active_dataset, get_active_dataset


class TestGroundedAgenticAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        res = cls.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
        cls.active_dataset_id = str(res) if res else "test_dataset"
        set_active_dataset(cls.db, cls.active_dataset_id)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.rollback()

    def tearDown(self):
        self.db.rollback()

    def test_1_valid_metric_query(self):
        res = answer_question(self.db, "How many admissions are there?")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("admission", res["answer"].lower())
        self.assertTrue(len(res["answer"]) > 0)

    def test_2_valid_breakdown_table(self):
        res = answer_question(self.db, "Show leads by source")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("source", res["columns"])
        self.assertIn("leads", res["columns"])
        self.assertTrue(len(res["data"]) > 0)

    def test_3_pie_chart_comparison(self):
        res = answer_question(self.db, "Show Mohali vs Chandigarh admissions as a pie chart")
        self.assertEqual(res["response_type"], "chart")
        self.assertEqual(res["chart_type"], "pie")
        self.assertIn("campus_name", res["columns"])
        self.assertIn("admission", res["columns"])
        self.assertTrue(len(res["data"]) >= 1)
        self.assertNotEqual(len(res["data"]), 1)

    def test_4_yoy_rate_drop(self):
        res = answer_question(self.db, "Which courses admission rate dropped from previous year?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("program_name", res["columns"])
        self.assertTrue(len(res["data"]) > 0)

    def test_5_top_5_yoy_drop(self):
        res = answer_question(self.db, "Top 5 courses whose admission rate dropped")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("program_name", res["columns"])
        self.assertTrue(1 <= len(res["data"]) <= 5)

    def test_6_counsellor_yoy_improvement(self):
        res = answer_question(self.db, "Which counsellor improved the most?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("owner", res["columns"])
        self.assertTrue(len(res["data"]) > 0)

    def test_7_aliza_yoy_performance(self):
        res = answer_question(self.db, "aliza performance previous to current year")
        if "couldn't find" in res["answer"].lower():
            self.assertEqual(res["debug"]["agent_status"], "entity_not_found")
        else:
            self.assertEqual(res["response_type"], "table")
            self.assertIn("owner", res["columns"])

    def test_8_unknown_owner_entity_not_found(self):
        res = answer_question(self.db, "Atlantis counsellor performance")
        self.assertIn("couldn't find 'atlantis'", res["answer"].lower())
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["data"], [])
        self.assertEqual(res["debug"]["agent_status"], "entity_not_found")

    def test_9_unsupported_business_concept(self):
        res = answer_question(self.db, "Which customers renewed their contracts?")
        self.assertIn("don't have enough data", res["answer"].lower())
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["data"], [])
        self.assertEqual(res["debug"]["agent_status"], "unsupported")

    def test_10_unrelated_general_question(self):
        res = answer_question(self.db, "Who is the president of France?")
        self.assertIn("don't have enough data", res["answer"].lower())
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["data"], [])
        self.assertEqual(res["debug"]["agent_status"], "unsupported")

    def test_11_malformed_ambiguous_question(self):
        res = answer_question(self.db, "asdf xyz abc")
        self.assertIn("don't have enough information", res["answer"].lower())
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["data"], [])
        self.assertEqual(res["debug"]["agent_status"], "ambiguous")

    @patch("app.agent.agent_service.plan_question", return_value=None)
    def test_12_gemini_429_deterministic_fallback_known_question(self, mock_plan):
        res = answer_question(self.db, "Show leads by source")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("source", res["columns"])

    @patch("app.agent.agent_service.plan_question", return_value=None)
    def test_13_gemini_429_deterministic_fallback_unknown_question(self, mock_plan):
        res = answer_question(self.db, "asdf xyz abc")
        self.assertIn("don't have enough information", res["answer"].lower())
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["data"], [])


if __name__ == "__main__":
    unittest.main()
