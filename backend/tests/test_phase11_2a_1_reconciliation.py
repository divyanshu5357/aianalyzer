"""
Phase 11.2A.1 — Dashboard KPI vs Monthly Graph Reconciliation Test Suite
Enforces strict equality between KPI card totals and monthly trend chart sums for CY and PY admissions.
"""
import unittest
from app.database.connection import SessionLocal
from app.analytics.dashboard import get_dashboard_overview, get_monthly_trend
from app.api.dashboard import get_unified_metrics_contract


class TestPhase11_2A_1_Reconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_cy_and_py_kpi_equals_monthly_sum(self):
        """Verify SUM(monthly CY) == CY KPI AND SUM(monthly PY) == PY KPI."""
        overview = get_dashboard_overview(self.db)
        kpis = overview.get("kpis", {})
        cy_kpi = kpis.get("admissions", {}).get("cy", 0)
        py_kpi = kpis.get("admissions", {}).get("py", 0)

        trend = get_monthly_trend(self.db, metric="admissions")
        cy_monthly_sum = sum(r.get("cy") or 0 for r in trend if r.get("cy") is not None)
        py_monthly_sum = sum(r.get("py") or 0 for r in trend if r.get("py") is not None)

        self.assertEqual(cy_kpi, cy_monthly_sum, f"CY KPI ({cy_kpi}) does not match CY Monthly Sum ({cy_monthly_sum})")
        self.assertEqual(py_kpi, py_monthly_sum, f"PY KPI ({py_kpi}) does not match PY Monthly Sum ({py_monthly_sum})")

    def test_02_unified_metrics_contract_reconciliation_flag(self):
        """Verify GET /api/dashboard/metrics contract returns reconciliation.passed == True."""
        contract = get_unified_metrics_contract(campus=None, years=None, state=None, source=None, program=None, db=self.db)
        rec = contract.get("reconciliation", {})
        self.assertTrue(rec.get("passed"), f"Reconciliation failed in unified metrics contract: {rec}")
        self.assertEqual(contract["cy"]["admissions"], rec["cy_monthly_sum"])
        self.assertEqual(contract["py"]["admissions"], rec["py_monthly_sum"])

    def test_03_campus_filtered_reconciliation(self):
        """Verify reconciliation under specific campus filter (Mohali)."""
        contract = get_unified_metrics_contract(campus="Mohali", years=None, state=None, source=None, program=None, db=self.db)
        rec = contract.get("reconciliation", {})
        self.assertTrue(rec.get("passed"), f"Mohali campus reconciliation failed: {rec}")


if __name__ == "__main__":
    unittest.main()
