import unittest
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from sqlalchemy import text
from app.database.repository import set_active_dataset, get_active_dataset


class TestGenericYoYAnalytics(unittest.TestCase):
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

    def test_courses_admission_rate_dropped(self):
        res = answer_question(self.db, "Which courses admission rate dropped from previous year?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("program_name", res["columns"])
        self.assertIn("rate_change", res["columns"])
        for row in res["data"]:
            self.assertTrue(row["rate_change"] < 0)

    def test_courses_admission_rate_increased(self):
        res = answer_question(self.db, "Which courses admission rate increased from previous year?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("program_name", res["columns"])
        for row in res["data"]:
            self.assertTrue(row["rate_change"] > 0)

    def test_top_5_courses_dropped(self):
        res = answer_question(self.db, "Top 5 courses whose admission rate dropped")
        self.assertEqual(res["response_type"], "table")
        self.assertLessEqual(len(res["data"]), 5)
        for row in res["data"]:
            self.assertTrue(row["rate_change"] < 0)

    def test_top_10_courses_improved(self):
        res = answer_question(self.db, "Top 10 courses whose admission rate improved")
        self.assertEqual(res["response_type"], "table")
        self.assertLessEqual(len(res["data"]), 10)
        for row in res["data"]:
            self.assertTrue(row["rate_change"] > 0)

    def test_biggest_admission_rate_drop(self):
        res = answer_question(self.db, "Which course had the biggest admission-rate drop?")
        self.assertEqual(res["response_type"], "table")
        self.assertLessEqual(len(res["data"]), 1)
        if res["data"]:
            self.assertTrue(res["data"][0]["rate_change"] < 0)

    def test_show_all_programs_decreased(self):
        res = answer_question(self.db, "Show all programs whose admission rate decreased")
        self.assertEqual(res["response_type"], "table")
        for row in res["data"]:
            self.assertTrue(row["rate_change"] < 0)

    def test_counsellors_admission_rate_drops(self):
        res = answer_question(self.db, "Which counsellors had admission-rate drops?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("owner", res["columns"])
        for row in res["data"]:
            self.assertTrue(row["rate_change"] < 0)

    def test_top_5_campuses_improved(self):
        res = answer_question(self.db, "Top 5 campuses with improved admission rate")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("campus_name", res["columns"])
        self.assertLessEqual(len(res["data"]), 5)

    def test_explicit_year_query(self):
        res = answer_question(self.db, "Which courses admission rate dropped from 2025 to 2026?")
        self.assertEqual(res["response_type"], "table")

    def test_chart_version_top_n(self):
        res = answer_question(self.db, "Show top 5 courses whose admission rate dropped as a bar chart")
        self.assertEqual(res["response_type"], "chart")
        self.assertEqual(res["chart_type"], "bar")
        self.assertLessEqual(len(res["data"]), 5)

    def test_no_matching_rows_or_unknown_values(self):
        res = answer_question(self.db, "Which non_existent_dimension had admission-rate drops?")
        self.assertIn("response_type", res)

    def test_existing_comparison_still_works(self):
        res1 = answer_question(self.db, "Show Mohali vs Chandigarh admissions as a pie chart")
        self.assertEqual(res1["response_type"], "chart")
        self.assertEqual(res1["chart_type"], "pie")
        self.assertEqual(len(res1["data"]), 2)

        res2 = answer_question(self.db, "Show Direct vs Indirect leads as a pie chart")
        self.assertEqual(res2["response_type"], "chart")
        self.assertEqual(len(res2["data"]), 2)


if __name__ == "__main__":
    unittest.main()
