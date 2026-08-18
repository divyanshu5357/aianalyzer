import unittest
from unittest.mock import patch
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from sqlalchemy import text
from app.database.repository import set_active_dataset


class TestAgenticArchitecture(unittest.TestCase):
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

    def test_case_A_ranking_counsellor_highest_admissions(self):
        """Case A: 'Who brought the highest number of admissions?'"""
        res = answer_question(self.db, "Who brought the highest number of admissions?")
        self.assertIn(res["response_type"], ["text", "table"])
        self.assertIn("owner", res["columns"])
        self.assertIn("admission", res["columns"])
        self.assertTrue(len(res["data"]) >= 1)

    def test_case_B_yoy_counsellor_most_improved(self):
        """Case B: 'Which counsellor improved the most from last year?'"""
        res = answer_question(self.db, "Which counsellor improved the most from last year?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("owner", res["columns"])
        self.assertTrue(len(res["data"]) >= 1)

    def test_case_C_yoy_courses_admission_rate_drops(self):
        """Case C: 'Which courses had admission-rate drops?'"""
        res = answer_question(self.db, "Which courses had admission-rate drops?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("program_name", res["columns"])
        self.assertTrue(len(res["data"]) >= 1)

    def test_case_D_top_5_programs_by_admissions(self):
        """Case D: 'Show top 5 programs by admissions.'"""
        res = answer_question(self.db, "Show top 5 programs by admissions.")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("program_name", res["columns"])
        self.assertTrue(1 <= len(res["data"]) <= 5)

    def test_case_E_compare_direct_and_indirect_leads(self):
        """Case E: 'Compare Direct and Website leads.'"""
        res = answer_question(self.db, "Compare Direct and Website leads.")
        self.assertIn(res["response_type"], ["table", "chart"])
        self.assertTrue(len(res["data"]) >= 1)

    def test_case_F_followup_pie_chart(self):
        """Case F: 'Show it as a pie chart.' (Follow-up context)"""
        conv_id = "test_conv_case_f"
        res1 = answer_question(self.db, "Show top 5 programs by admissions.", conversation_id=conv_id)
        self.assertTrue(len(res1["data"]) > 0)

        res2 = answer_question(self.db, "Show it as a pie chart.", conversation_id=conv_id)
        self.assertEqual(res2["response_type"], "chart")
        self.assertEqual(res2["chart_type"], "pie")
        self.assertTrue(len(res2["data"]) > 0)

    def test_case_G_causal_inquiry(self):
        """Case G: 'Why did the top program improve?'"""
        conv_id = "test_conv_case_g"
        res1 = answer_question(self.db, "Show top 5 programs by admissions.", conversation_id=conv_id)
        self.assertTrue(len(res1["data"]) > 0)

        res2 = answer_question(self.db, "Why did the top program improve?", conversation_id=conv_id)
        self.assertIn("describe measurable associations in the dataset", res2["answer"])
        self.assertTrue(len(res2["data"]) >= 1)

    def test_case_H_unsupported_weather_question(self):
        """Case H: 'What is the weather today?'"""
        res = answer_question(self.db, "What is the weather today?")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("don't have enough data in the uploaded dataset", res["answer"].lower())
        self.assertEqual(res["data"], [])

    def test_case_I_unsupported_unrelated_question(self):
        """Case I: 'Tell me something unrelated to the uploaded dataset.'"""
        res = answer_question(self.db, "Tell me something unrelated to the uploaded dataset.")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("don't have enough data in the uploaded dataset", res["answer"].lower())
        self.assertEqual(res["data"], [])

    def test_case_J_ambiguous_question(self):
        """Case J: Intentionally ambiguous analytics question."""
        res = answer_question(self.db, "asdf xyz")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("don't have enough information", res["answer"].lower())
        self.assertEqual(res["data"], [])

    @patch("app.agent.agent_service.plan_question", return_value=None)
    def test_deterministic_fallback_when_gemini_fails(self, mock_plan):
        """Ensure system falls back gracefully to intent parsing when Gemini returns 429 quota error."""
        res = answer_question(self.db, "Show top 5 programs by admissions.")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("program_name", res["columns"])
        self.assertTrue(1 <= len(res["data"]) <= 5)

    def test_hardened_stop_words_no_false_entity(self):
        """Ensure words like 'students' or 'lost' are ignored during candidate entity extraction."""
        res = answer_question(self.db, "How many students were admitted?")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("admission", res["columns"])
        self.assertTrue(len(res["data"]) >= 1)

    def test_hardened_comparison_patterns(self):
        """Ensure various natural language comparison phrasings are correctly routed to ComparisonTool."""
        phrases = [
            "How do Direct and Website compare?",
            "Put Direct and Website side by side.",
            "Compare Direct with Website"
        ]
        for phrase in phrases:
            res = answer_question(self.db, phrase)
            self.assertEqual(res["response_type"], "table")
            self.assertIn("admission", res["columns"])
            self.assertTrue(len(res["data"]) >= 1)

    def test_hardened_ambiguous_no_context(self):
        """Ensure vague queries without conversation context prompt for clarification."""
        res = answer_question(self.db, "What improved?")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("context", res["answer"].lower())

    def test_hardened_unsupported_questions(self):
        """Ensure unrelated domain questions are returned as unsupported early."""
        unsupported = [
            "Who is the CEO of Google?",
            "What is the employee satisfaction score?",
            "What caused this marketing campaign to succeed?"
        ]
        for q in unsupported:
            res = answer_question(self.db, q)
            self.assertEqual(res["response_type"], "text")
            self.assertIn("don't have enough data in the uploaded dataset", res["answer"].lower())

    def test_hardened_yoy_context_followup_chain(self):
        """Ensure a YoY context comparison chain resolved correctly via conversation history."""
        conv_id = "test_yoy_chain_conv"
        # Q1: Establish context
        res1 = answer_question(self.db, "Which courses had admission-rate improvement?", conversation_id=conv_id)
        self.assertEqual(res1["response_type"], "table")
        
        # Q2: Slice first entity
        res2 = answer_question(self.db, "Show the first one", conversation_id=conv_id)
        self.assertIn("result for MPT", res2["answer"])

        # Q3: YoY comparison of first entity
        res3 = answer_question(self.db, "Compare it with last year", conversation_id=conv_id)
        self.assertEqual(res3["response_type"], "table")
        self.assertIn("YoY comparison for MPT", res3["answer"])
        self.assertIn("admission_change", res3["columns"])


if __name__ == "__main__":
    unittest.main()
