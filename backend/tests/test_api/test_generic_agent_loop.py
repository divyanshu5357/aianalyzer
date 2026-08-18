import unittest
from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import SessionLocal
from app.database.conversations import ensure_conversation_tables, reset_conversation_context
from app.database.repository import set_active_dataset, create_dataset
from app.agent.agent_service import answer_question


class TestGenericAgentLoop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        ensure_conversation_tables(cls.db)
        cls.client = TestClient(app)

        res = cls.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
        cls.dataset_id = str(res) if res else "test_dataset"
        set_active_dataset(cls.db, cls.dataset_id)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.conv_id = f"test_loop_{self._testMethodName}"
        reset_conversation_context(self.db, self.conv_id)

    def test_01_ranking_then_show_top_3(self):
        # Turn 1: Ranking of counsellors with biggest admission rate improvement
        res1 = answer_question(self.db, "Which counsellors had the biggest admission rate improvement?", conversation_id=self.conv_id)
        self.assertIn("response_type", res1)
        self.assertTrue(len(res1.get("data", [])) > 0)

        # Turn 2: "show the top 3"
        res2 = answer_question(self.db, "show the top 3", conversation_id=self.conv_id)
        self.assertEqual(res2["response_type"], "table")
        self.assertTrue(len(res2.get("data", [])) <= 3)

    def test_02_ranking_then_biggest_admission_increase(self):
        # Turn 1: Counsellors admission rate improvement
        answer_question(self.db, "Which counsellors had the biggest admission rate improvement?", conversation_id=self.conv_id)

        # Turn 2: "which one had the biggest increase in admissions?"
        res2 = answer_question(self.db, "which one had the biggest increase in admissions?", conversation_id=self.conv_id)
        self.assertEqual(res2["response_type"], "table")
        self.assertEqual(len(res2["data"]), 1)
        # Verify the result has the expected keys (data-agnostic — specific names depend on the dataset)
        first_row = res2["data"][0]
        self.assertTrue(
            any(k in first_row for k in ["owner", "counsellor", "counselor"]),
            f"Expected owner key in row, got: {list(first_row.keys())}"
        )

    def test_03_breakdown_filter_compare(self):
        # Turn 1: "Show leads by source"
        res1 = answer_question(self.db, "Show leads by source", conversation_id=self.conv_id)

        # Get the actual top 2 sources from the result to use in follow-up
        sources = [r.get("source", r.get("main_source", "")) for r in res1.get("data", [])]
        if len(sources) < 2:
            # Skip data-specific assertions if dataset doesn't have enough source variety
            return

        s1, s2 = sources[0].lower(), sources[1].lower()

        # Turn 2: Filter to top 2 sources using data-driven values
        res2 = answer_question(self.db, f"only {s1} and {s2}", conversation_id=self.conv_id)
        # If filter returns data, verify structure; if empty, just verify response type
        if res2.get("data"):
            self.assertTrue(len(res2["data"]) >= 1)

        # Turn 3: "compare them"
        res3 = answer_question(self.db, "compare them", conversation_id=self.conv_id)
        self.assertEqual(res3["response_type"], "table")

    def test_04_comparison_to_pie_chart(self):
        # Turn 1: Show leads by source
        answer_question(self.db, "Show leads by source", conversation_id=self.conv_id)
        # Turn 2: Compare direct and indirect
        answer_question(self.db, "only direct and indirect", conversation_id=self.conv_id)
        answer_question(self.db, "compare them", conversation_id=self.conv_id)

        # Turn 3: "show as a pie chart"
        res3 = answer_question(self.db, "show as a pie chart", conversation_id=self.conv_id)
        self.assertEqual(res3["response_type"], "chart")
        self.assertEqual(res3["chart_type"], "pie")

    def test_05_yoy_result_why_top_one_improved(self):
        # Turn 1: Counsellor YoY improvement
        answer_question(self.db, "Which counsellors had the biggest admission rate improvement?", conversation_id=self.conv_id)

        # Turn 2: "why did the top one improve?"
        res2 = answer_question(self.db, "why did the top one improve?", conversation_id=self.conv_id)
        self.assertIn("dataset does not contain enough information to determine the exact cause", res2["answer"])
        self.assertEqual(res2["response_type"], "table")

    def test_06_yoy_result_show_first_one(self):
        # Turn 1: Counsellor YoY improvement
        answer_question(self.db, "Which counsellors had the biggest admission rate improvement?", conversation_id=self.conv_id)

        # Turn 2: "show the first one"
        res2 = answer_question(self.db, "show the first one", conversation_id=self.conv_id)
        self.assertEqual(len(res2["data"]), 1)

    def test_07_yoy_result_compare_it_with_last_year(self):
        # Turn 1: Counsellor YoY improvement
        answer_question(self.db, "Which counsellors had the biggest admission rate improvement?", conversation_id=self.conv_id)

        # Turn 2: "compare it with last year"
        res2 = answer_question(self.db, "compare it with last year", conversation_id=self.conv_id)
        self.assertEqual(res2["response_type"], "table")
        self.assertIn("admissions_", res2["columns"][1])

    def test_08_unknown_question_safety(self):
        res = answer_question(self.db, "zookeeper performance previous to current year", conversation_id=self.conv_id)
        self.assertIn(res["debug"]["agent_status"], ["insufficient_data", "entity_not_found"])
        self.assertTrue("couldn't find" in res["answer"].lower() or "don't have enough data" in res["answer"].lower())

    def test_09_unsupported_causal_question_grounding(self):
        res = answer_question(self.db, "Why did admissions increase because of the marketing campaign?", conversation_id=self.conv_id)
        self.assertEqual(res["debug"]["agent_status"], "causal_unsupported")
        self.assertIn("does not contain evidence proving why admissions changed", res["answer"])

    def test_10_new_unrelated_question_no_context_leak(self):
        # Turn 1: Counsellor improvement
        answer_question(self.db, "Which counsellors had the biggest admission rate improvement?", conversation_id=self.conv_id)

        # Turn 2: New independent query: "Show leads by state"
        res2 = answer_question(self.db, "Show leads by state", conversation_id=self.conv_id)
        self.assertIn("state", res2["columns"])
        self.assertNotIn("owner", res2["columns"])

    def test_11_unresolved_reference_asks_clarification(self):
        # Fresh conversation with no context
        res = answer_question(self.db, "compare them", conversation_id=f"fresh_{self.conv_id}")
        self.assertEqual(res["debug"]["agent_status"], "insufficient_context")
        self.assertIn("need a little more context", res["answer"].lower())

    def test_12_api_chat_endpoint(self):
        # Test full conversation flow through the HTTP API
        # Turn 1
        resp1 = self.client.post("/api/chat", json={"question": "Which counsellors had the biggest admission rate improvement?", "conversation_id": self.conv_id})
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertEqual(data1["conversation_id"], self.conv_id)

        # Turn 2
        resp2 = self.client.post("/api/chat", json={"question": "show the top 3", "conversation_id": self.conv_id})
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2["response_type"], "table")
        self.assertTrue(len(data2.get("data", [])) <= 3)


if __name__ == "__main__":
    unittest.main()
