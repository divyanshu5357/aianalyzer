"""
Phase 11.2B-Target — Power BI Target Engine Reconciliation Test Suite
Validates target calculation, date range filtering, target grain, and Target For separation.
"""
import unittest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.target_service import get_target_performance


class TestPhase11_2BTargetPowerBIReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.tgt_ds = "0a991108-876e-42b2-8978-5e5ea2049a14"
        cls.raw_2026 = "47aa37e1-9949-4a01-a3e4-b33b7df93b1c"

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_target_for_separation(self):
        """Verify Admission, Leads, and CUCET targets are kept strictly separate."""
        res_adm = get_target_performance(self.db, target_for="Admission", campus="Mohali")
        res_leads = get_target_performance(self.db, target_for="Leads", campus="Mohali")
        res_cucet = get_target_performance(self.db, target_for="CUCET", campus="Mohali")

        self.assertEqual(res_adm["target_for"], "Admission")
        self.assertEqual(res_leads["target_for"], "Leads")
        self.assertEqual(res_cucet["target_for"], "CUCET")

        self.assertEqual(res_adm["target"], 29300.0)
        self.assertEqual(res_leads["target"], 967383.54)
        self.assertEqual(res_cucet["target"], 55500.0)

    def test_02_daily_target_weight_summation(self):
        """Verify that daily decimal allocation weights (e.g. 0.037037) sum to exact integer targets across days."""
        val = self.db.execute(text("""
            SELECT SUM((raw_data->>'Final Target')::numeric)
            FROM staging.records
            WHERE dataset_id = :ds
              AND raw_data->>'Campus' = 'Mohali'
              AND raw_data->>'Source' = 'BROCHURE'
              AND raw_data->>'Month' = 'Dec'
              AND raw_data->>'Target For' = 'Admission'
        """), {"ds": self.tgt_ds}).scalar()

        # 27 days * 0.037037037037037 = 1.0
        self.assertAlmostEqual(float(val), 1.0, places=2)

    def test_03_date_range_filtered_target(self):
        """Verify target service handles explicit date range filtering (e.g. 2025-10-07 to 2026-07-28)."""
        res = get_target_performance(
            self.db,
            target_for="Leads",
            campus="Mohali",
            start_date="2025-10-07",
            end_date="2026-07-28"
        )
        self.assertEqual(res["target"], 869412.84)


if __name__ == "__main__":
    unittest.main()
