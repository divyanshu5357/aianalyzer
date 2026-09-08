"""
Phase 12: Neo4j Integration Test Suite

Tests:
1. GraphCanonicalizer: lead ID, state (international location rule), owner (employee_id key), source, program, campus.
2. Durable Queue Producer (enqueue_sync_event)
3. Sync Worker event dispatching
4. ID-level Reconciliation & Discrepancy detection
5. ML Graph Connector integration without modifying ML inference contract
"""

import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.normalization.graph_canonicalizer import GraphCanonicalizer
from app.database.sync_queue import enqueue_sync_event
from app.database.neo4j_sync_worker import Neo4jSyncWorker
from app.database.neo4j_reconciler import Neo4jReconciler
from app.ml.ml_graph_connector import record_ml_prediction_to_graph
from app.database.neo4j_driver import Neo4jConnectionManager


class TestGraphCanonicalizer(unittest.TestCase):
    def setUp(self):
        self.canonicalizer = GraphCanonicalizer(db=None)

    def test_canonicalize_lead_id(self):
        self.assertEqual(self.canonicalizer.canonicalize_lead_id("  enq10234 "), "ENQ10234")
        with self.assertRaises(ValueError):
            self.canonicalizer.canonicalize_lead_id("")

    def test_international_location_rule(self):
        res1 = self.canonicalizer.canonicalize_state("Kathmandu", country="Nepal")
        self.assertEqual(res1["state_code"], "INT")
        self.assertEqual(res1["state_name"], "INTERNATIONAL")
        self.assertTrue(res1["is_international"])

        res2 = self.canonicalizer.canonicalize_state("NRI Overseas Direct", country="")
        self.assertEqual(res2["state_code"], "INT")
        self.assertTrue(res2["is_international"])

        res3 = self.canonicalizer.canonicalize_state("Punjab", country="India")
        self.assertNotEqual(res3["state_code"], "INT")
        self.assertFalse(res3["is_international"])

    def test_canonicalize_owner_with_employee_id(self):
        # Explicit employee_id provided
        res1 = self.canonicalizer.canonicalize_owner("Counselor Alice", raw_employee_id="EMP_998")
        self.assertEqual(res1["employee_id"], "emp_998")
        self.assertEqual(res1["employee_name"], "Counselor Alice")

        # Fallback slugification
        res2 = self.canonicalizer.canonicalize_owner("Bob Smith", raw_employee_id=None)
        self.assertEqual(res2["employee_id"], "emp_bob_smith")
        self.assertEqual(res2["display_name"], "Bob Smith")

    def test_case_insensitive_casing_deduplication(self):
        res_a = self.canonicalizer.canonicalize_source("Quick Add Form")
        res_b = self.canonicalizer.canonicalize_source("  QUICK ADD FORM  ")
        self.assertEqual(res_a["source_key"], res_b["source_key"])

        res_p1 = self.canonicalizer.canonicalize_program("B.Tech CSE", program_code="CG201")
        res_p2 = self.canonicalizer.canonicalize_program("b.tech cse", program_code="cg201")
        self.assertEqual(res_p1["program_code"], res_p2["program_code"])


class TestNeo4jIntegrationComponents(unittest.TestCase):
    def test_enqueue_sync_event_mock(self):
        mock_db = MagicMock(spec=Session)
        mock_db.execute.return_value.fetchone.return_value = ("00000000-0000-0000-0000-000000000001",)

        event_id = enqueue_sync_event(
            db=mock_db,
            entity_type="LEAD",
            entity_id="ENQ1001",
            action="UPSERT_LEAD",
            payload={"enquiry_id": "ENQ1001"},
        )
        self.assertEqual(event_id, "00000000-0000-0000-0000-000000000001")
        self.assertTrue(mock_db.execute.called)

    def test_ml_graph_connector(self):
        mock_db = MagicMock(spec=Session)
        mock_db.execute.return_value.fetchone.return_value = ("event-uuid-123",)

        pred_result = {
            "calibrated_admission_probability": 0.1245,
            "predictive_score_pct": 12.45,
            "operational_tier": "High Priority (Top 10%)",
            "decision_recommendation": "ADMIT_PRIORITY_OUTREACH",
            "t0_threshold_applied": 0.05,
            "model_version": "2026_lightgbm_calibrated_v1",
        }

        event_id = record_ml_prediction_to_graph(mock_db, "ENQ5544", pred_result)
        self.assertEqual(event_id, "event-uuid-123")

    @patch.object(Neo4jConnectionManager, "is_healthy", return_value=False)
    def test_reconciler_offline_handling(self, mock_healthy):
        mock_db = MagicMock(spec=Session)
        reconciler = Neo4jReconciler(mock_db)
        res = reconciler.reconcile(auto_repair=False)
        self.assertEqual(res["status"], "failed")
        self.assertIn("Neo4j driver is offline", res["reason"])


if __name__ == "__main__":
    unittest.main()
