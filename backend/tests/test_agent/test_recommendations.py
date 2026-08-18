import unittest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.database.repository import set_active_dataset

class TestRecommendationsAndEntityResolution(unittest.TestCase):
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

    def test_01_chandigarh_invalid_comparison(self):
        """1. Chandigarh is not a valid campus and must trigger clarification"""
        res = answer_question(self.db, "Show Mohali vs Chandigarh admissions as a pie chart")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("MOHALI as a valid campus", res["answer"])
        self.assertIn("CHANDIGARH is not present as a campus", res["answer"])
        # Should return dynamic recommendations
        self.assertTrue(len(res.get("recommendations", [])) >= 1)

    def test_02_happened_not_entity(self):
        """2. 'happened' or year 2026 must not be treated as entity filters"""
        res = answer_question(self.db, "How many admissions happened in 2026?")
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["year"], 2026)
        self.assertIn("admission", res["columns"])

    def test_03_leads_by_state(self):
        """3. Show leads by state (no fake NULL/None entity)"""
        res = answer_question(self.db, "Show leads by state")
        self.assertEqual(res["response_type"], "table")
        for row in res["data"]:
            state_val = str(row.get("state")).lower().strip()
            self.assertNotIn(state_val, ["none", "null", ""])

    def test_04_admissions_by_program_no_none(self):
        """4. Show admissions by program (no 'None' program row)"""
        res = answer_question(self.db, "Show admissions by program")
        for row in res["data"]:
            prog_val = str(row.get("program_name")).lower().strip()
            self.assertNotIn(prog_val, ["none", "null", ""])

    def test_05_compare_be_cse_vs_bcom(self):
        """5. Resolve natural-language variants against canonical programs"""
        res = answer_question(self.db, "Compare B.E CSE vs Bcom")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("I found multiple candidates matching", res["answer"])

    def test_06_ambiguous_bcom_clarification(self):
        """6. Ambiguous query shows multiple candidates and dynamic chips"""
        res = answer_question(self.db, "Show admissions for B.COM")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("I found multiple candidates matching", res["answer"])
        recs = res.get("recommendations", [])
        self.assertTrue(len(recs) >= 1)
        for r in recs:
            self.assertIn("Show admissions for", r["question"])

    def test_07_recommendations_after_every_answer(self):
        """7. Recommendations are generated after every answer"""
        res = answer_question(self.db, "Which program had the highest admissions?")
        self.assertTrue(len(res.get("recommendations", [])) >= 2)

    def test_08_why_did_it_improve_context(self):
        """8. Contextual follow-up works"""
        conv_id = "test_conv_rec_8"
        answer_question(self.db, "Which program had the highest admissions?", conversation_id=conv_id)
        res = answer_question(self.db, "Why did it improve?", conversation_id=conv_id)
        self.assertEqual(res["response_type"], "table")
        self.assertIn("B.E. CSE : CS201", res["answer"])

    def test_09_compare_it_with_second_one(self):
        """9. Contextual follow-up 'compare it with the second one' works"""
        conv_id = "test_conv_rec_9"
        answer_question(self.db, "Show admissions by program", conversation_id=conv_id)
        res = answer_question(self.db, "Compare it with the second one", conversation_id=conv_id)
        self.assertEqual(res["response_type"], "table")
        self.assertIn("B.E. CSE : CS201", res["answer"])
