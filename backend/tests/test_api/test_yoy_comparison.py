import unittest
from uuid import uuid4
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from sqlalchemy import text
from app.database.repository import set_active_dataset, get_active_dataset


class TestYoYAndComparisonAnalytics(unittest.TestCase):
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

    def test_pie_chart_comparison_mohali_vs_chandigarh(self):
        res = answer_question(self.db, "Show Mohali vs Chandigarh admissions as a pie chart")
        self.assertEqual(res["response_type"], "chart")
        self.assertEqual(res["chart_type"], "pie")
        self.assertIn("campus_name", res["columns"])
        self.assertIn("admission", res["columns"])
        self.assertTrue(len(res["data"]) >= 1)
        # Verify that total dataset sum is NOT returned as a single slice
        self.assertNotEqual(len(res["data"]), 1)

    def test_pie_chart_comparison_direct_vs_indirect(self):
        res = answer_question(self.db, "Show Direct vs Indirect admissions as a pie chart")
        self.assertEqual(res["response_type"], "chart")
        self.assertEqual(res["chart_type"], "pie")
        self.assertIn("main_source", res["columns"])
        self.assertEqual(len(res["data"]), 2)

    def test_counsellor_yoy_improvement(self):
        res = answer_question(self.db, "Which counsellor performance increased from previous year?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("owner", res["columns"])
        self.assertIn("admission_change", res["columns"])
        self.assertIn("rate_change", res["columns"])
        self.assertTrue(len(res["data"]) > 0)
        # Check sorting order: top improved counsellor has highest positive admission_change
        top = res["data"][0]
        self.assertTrue(top["admission_change"] >= res["data"][-1]["admission_change"])

    def test_counsellor_yoy_decline(self):
        res = answer_question(self.db, "Which counsellor performed worst compared with previous year?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("owner", res["columns"])
        self.assertTrue(len(res["data"]) > 0)
        # Check sorting order: worst performer has lowest/negative admission_change
        worst = res["data"][0]
        self.assertTrue(worst["admission_change"] <= res["data"][-1]["admission_change"])

    def test_non_existent_values_comparison(self):
        res = answer_question(self.db, "Show UnknownCampusX vs UnknownCampusY admissions as a pie chart")
        self.assertTrue("couldn't find" in res["answer"].lower() or "not found" in res["answer"].lower())

        self.assertEqual(res["data"], [])



if __name__ == "__main__":
    unittest.main()
