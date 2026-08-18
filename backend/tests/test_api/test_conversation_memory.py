import unittest
import uuid
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.database.conversations import (
    ensure_conversation_tables,
    get_conversation_context,
)
from app.database.repository import set_active_dataset


class TestConversationalMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        ensure_conversation_tables(cls.db)

        # Get active dataset ID
        res = cls.db.execute(text("SELECT id FROM system.datasets WHERE dataset_name = 'Data - Dump.xlsx' LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
        cls.dataset_id = str(res) if res else "test_dataset"

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        try:
            self.db.rollback()
            res = self.db.execute(text("SELECT id FROM system.datasets WHERE dataset_name = 'Data - Dump.xlsx' LIMIT 1")).scalar()
            if not res:
                res = self.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
            if not res:
                res = self.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
            self.dataset_id = str(res) if res else "test_dataset"
            set_active_dataset(self.db, self.dataset_id)
            self.db.commit()
        except Exception:
            pass

    def tearDown(self):
        try:
            self.db.rollback()
        except Exception:
            pass

    def test_01_pronoun_reason_behind_their_success(self):
        conv_id = f"test_conv_01_{uuid.uuid4()}"
        res1 = answer_question(self.db, "Which courses admission rate increased from previous year?", conversation_id=conv_id)
        self.assertIn("data", res1)

        res2 = answer_question(self.db, "reason behind their success", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        self.assertIn("dataset does not contain enough information to determine the exact cause", res2["answer"])
        self.assertIn("resolved_references", res2.get("debug", {}))

    def test_02_selector_show_only_first_one(self):
        conv_id = f"test_conv_02_{uuid.uuid4()}"
        answer_question(self.db, "Which courses admission rate increased from previous year?", conversation_id=conv_id)

        res2 = answer_question(self.db, "Show only the first one.", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        self.assertLessEqual(len(res2.get("data", [])), 1)

    def test_03_selector_what_about_second_one(self):
        conv_id = f"test_conv_03_{uuid.uuid4()}"
        answer_question(self.db, "Which courses admission rate increased from previous year?", conversation_id=conv_id)

        res2 = answer_question(self.db, "What about the second one?", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        self.assertLessEqual(len(res2.get("data", [])), 1)

    def test_04_yoy_compare_them_with_last_year(self):
        conv_id = f"test_conv_04_{uuid.uuid4()}"
        answer_question(self.db, "Which courses admission rate increased from previous year?", conversation_id=conv_id)

        res2 = answer_question(self.db, "Compare them with last year.", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        self.assertIn("admissions_", res2["columns"][1])

    def test_05_chart_show_them_as_bar_chart(self):
        conv_id = f"test_conv_05_{uuid.uuid4()}"
        answer_question(self.db, "Which courses admission rate increased from previous year?", conversation_id=conv_id)

        res2 = answer_question(self.db, "Show them as a bar chart.", conversation_id=conv_id)
        self.assertEqual(res2.get("response_type"), "chart")
        self.assertEqual(res2.get("chart_type"), "bar")

    def test_06_filter_only_direct_and_indirect(self):
        conv_id = f"test_conv_06_{uuid.uuid4()}"
        answer_question(self.db, "Show leads by source.", conversation_id=conv_id)

        res2 = answer_question(self.db, "Only direct and indirect.", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        sources = [r["source"].lower() for r in res2.get("data", [])]
        for s in sources:
            self.assertIn(s, ["direct", "indirect"])

    def test_07_selector_show_top_3(self):
        conv_id = f"test_conv_07_{uuid.uuid4()}"
        answer_question(self.db, "Show leads by source.", conversation_id=conv_id)

        res2 = answer_question(self.db, "Show the top 3.", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        self.assertLessEqual(len(res2.get("data", [])), 3)

    def test_08_causal_why_did_top_one_improve(self):
        conv_id = f"test_conv_08_{uuid.uuid4()}"
        answer_question(self.db, "Which counsellors improved?", conversation_id=conv_id)

        res2 = answer_question(self.db, "Why did the top one improve?", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        self.assertIn("dataset does not contain enough information to determine the exact cause", res2["answer"])

    def test_09_selector_show_worst_one_as_table(self):
        conv_id = f"test_conv_09_{uuid.uuid4()}"
        answer_question(self.db, "Which courses had the biggest decline?", conversation_id=conv_id)

        res2 = answer_question(self.db, "Show the worst one as a table.", conversation_id=conv_id)
        self.assertTrue(res2.get("debug", {}).get("context_used"))
        self.assertEqual(res2.get("response_type"), "table")

    def test_10_dataset_switch_isolation(self):
        conv_id = f"test_conv_10_{uuid.uuid4()}"
        answer_question(self.db, "Which courses admission rate increased from previous year?", conversation_id=conv_id)

        # Context exists for active dataset
        ctx = get_conversation_context(self.db, conv_id, self.dataset_id)
        self.assertIsNotNone(ctx)

        # Insert a dummy dataset and switch active
        dummy_new_ds = str(uuid.uuid4())
        self.db.execute(
            text(
                """
                INSERT INTO system.datasets (id, dataset_name, original_filename, row_count, column_count, status, is_active)
                VALUES (:id, 'Dummy Isolation DS', 'dummy.csv', 10, 5, 'active', FALSE)
                """
            ),
            {"id": dummy_new_ds},
        )
        self.db.commit()

        set_active_dataset(self.db, dummy_new_ds)

        # Context for conv_id must be cleared/inaccessible for new dataset
        ctx_after = get_conversation_context(self.db, conv_id, dummy_new_ds)
        self.assertIsNone(ctx_after)

        # Restore original active dataset & cleanup dummy
        set_active_dataset(self.db, self.dataset_id)
        self.db.execute(text("DELETE FROM system.datasets WHERE id = :id"), {"id": dummy_new_ds})
        self.db.commit()

    def test_11_fresh_conversation_unresolved_reference(self):
        conv_id = f"test_conv_11_fresh_{uuid.uuid4()}"
        res = answer_question(self.db, "Why did they improve?", conversation_id=conv_id)

        self.assertIn("I need a little more context", res["answer"])
        self.assertEqual(res.get("debug", {}).get("agent_status"), "insufficient_context")


if __name__ == "__main__":
    unittest.main()
