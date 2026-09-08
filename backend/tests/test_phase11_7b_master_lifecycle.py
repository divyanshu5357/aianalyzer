

import unittest
import time
from uuid import uuid4
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.database.repository import (
    set_active_dataset,
    enable_dataset_analytics,
    resolve_target_dataset,
    resolve_raw_dataset,
)
from app.analytics.aggregate_service import get_agg_overview, get_agg_monthly_trend
from app.analytics.target_service import get_target_performance
from app.api.dashboard import _normalize_metric


class TestPhase11_7B_MasterLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    # -------------------------------------------------------------------------
    # PART 3 — TARGET MASTER: STRICTLY ONE ACTIVE MASTER FILE
    # -------------------------------------------------------------------------
    def test_01_target_master_activation_supersedes_existing(self):
        """Activating a new Target master must deactivate any existing Target master."""
        dummy_old_id = str(uuid4())
        dummy_new_id = str(uuid4())

        # Insert two dummy target datasets
        self.db.execute(text("""
            INSERT INTO system.datasets (id, dataset_name, original_filename, workbook_type, is_active, is_analytics_enabled, status)
            VALUES (:old_id, 'tgt_old.xlsx', 'tgt_old.xlsx', 'TARGET', TRUE, TRUE, 'normalized'),
                   (:new_id, 'tgt_new.xlsx', 'tgt_new.xlsx', 'TARGET', FALSE, FALSE, 'normalized')
        """), {"old_id": dummy_old_id, "new_id": dummy_new_id})
        self.db.commit()

        try:
            # Activate the new target dataset
            set_active_dataset(self.db, dummy_new_id)

            old_state = self.db.execute(
                text("SELECT is_active, is_analytics_enabled FROM system.datasets WHERE id = :id"),
                {"id": dummy_old_id}
            ).mappings().first()
            new_state = self.db.execute(
                text("SELECT is_active, is_analytics_enabled FROM system.datasets WHERE id = :id"),
                {"id": dummy_new_id}
            ).mappings().first()

            self.assertFalse(old_state["is_active"], "Old target master must be deactivated")
            self.assertFalse(old_state["is_analytics_enabled"], "Old target master must have analytics disabled")
            self.assertTrue(new_state["is_active"], "New target master must be active")
            self.assertTrue(new_state["is_analytics_enabled"], "New target master must have analytics enabled")
        finally:
            # Clean up dummy records and restore original active target
            self.db.execute(text("DELETE FROM system.datasets WHERE id IN (:old_id, :new_id)"),
                            {"old_id": dummy_old_id, "new_id": dummy_new_id})
            self.db.execute(text("""
                UPDATE system.datasets SET is_active = TRUE, is_analytics_enabled = TRUE
                WHERE id = '0a991108-876e-42b2-8978-5e5ea2049a14'
            """))
            self.db.commit()

    def test_02_dimension_master_activation_supersedes_existing(self):
        """Activating a new Dimension master must deactivate any existing Dimension master."""
        dummy_old_id = str(uuid4())
        dummy_new_id = str(uuid4())

        self.db.execute(text("""
            INSERT INTO system.datasets (id, dataset_name, original_filename, workbook_type, is_active, is_analytics_enabled, status)
            VALUES (:old_id, 'dim_old.xlsx', 'dim_old.xlsx', 'DIMENSION', TRUE, TRUE, 'normalized'),
                   (:new_id, 'dim_new.xlsx', 'dim_new.xlsx', 'DIMENSION', FALSE, FALSE, 'normalized')
        """), {"old_id": dummy_old_id, "new_id": dummy_new_id})
        self.db.commit()

        try:
            set_active_dataset(self.db, dummy_new_id)

            old_state = self.db.execute(
                text("SELECT is_active, is_analytics_enabled FROM system.datasets WHERE id = :id"),
                {"id": dummy_old_id}
            ).mappings().first()
            new_state = self.db.execute(
                text("SELECT is_active, is_analytics_enabled FROM system.datasets WHERE id = :id"),
                {"id": dummy_new_id}
            ).mappings().first()

            self.assertFalse(old_state["is_active"], "Old dimension master must be deactivated")
            self.assertFalse(old_state["is_analytics_enabled"], "Old dimension master must have analytics disabled")
            self.assertTrue(new_state["is_active"], "New dimension master must be active")
            self.assertTrue(new_state["is_analytics_enabled"], "New dimension master must have analytics enabled")
        finally:
            self.db.execute(text("DELETE FROM system.datasets WHERE id IN (:old_id, :new_id)"),
                            {"old_id": dummy_old_id, "new_id": dummy_new_id})
            self.db.execute(text("""
                UPDATE system.datasets SET is_active = TRUE, is_analytics_enabled = TRUE
                WHERE id = '3cdf4cd5-83e0-4e05-b574-d94065b3859d'
            """))
            self.db.commit()

    # -------------------------------------------------------------------------
    # PART 4 — RAW DATASETS: MULTI-DATASET COEXISTENCE BY SCOPE
    # -------------------------------------------------------------------------
    def test_03_raw_multi_dataset_coexistence(self):
        """RAW datasets for 2025 and 2026 must coexist as simultaneously active and analytics-enabled."""
        rows = self.db.execute(text("""
            SELECT academic_year, campus_name, is_active, is_analytics_enabled
            FROM system.datasets
            WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'RAW'
              AND id IN ('66a38ff7-fa21-4b77-be4b-59995e239d6a', 'd1c37e76-8d48-4277-b696-a14abf6e1f3b')
        """)).mappings().all()

        self.assertEqual(len(rows), 2, "Both 2025 and 2026 RAW datasets must exist")
        years = {r["academic_year"] for r in rows}
        self.assertIn(2025, years)
        self.assertIn(2026, years)
        for r in rows:
            self.assertTrue(r["is_active"], f"Dataset for year {r['academic_year']} must be active")
            self.assertTrue(r["is_analytics_enabled"], f"Dataset for year {r['academic_year']} must be analytics enabled")

    def test_04_raw_replacement_matching_scope(self):
        """Activating a RAW dataset for (2026, 'Mohali') must only deactivate other (2026, 'Mohali') datasets, preserving 2025."""
        dummy_2026_id = str(uuid4())

        self.db.execute(text("""
            INSERT INTO system.datasets (id, dataset_name, original_filename, workbook_type, academic_year, campus_name, is_active, is_analytics_enabled, status)
            VALUES (:id, 'mohali_2026_v2.csv', 'mohali_2026_v2.csv', 'RAW', 2026, 'Mohali', FALSE, FALSE, 'normalized')
        """), {"id": dummy_2026_id})
        self.db.commit()

        try:
            set_active_dataset(self.db, dummy_2026_id)

            # 2025 Mohali must remain untouched
            state_2025 = self.db.execute(
                text("SELECT is_active, is_analytics_enabled FROM system.datasets WHERE id = '66a38ff7-fa21-4b77-be4b-59995e239d6a'")
            ).mappings().first()
            self.assertTrue(state_2025["is_active"], "2025 Mohali must remain active")
            self.assertTrue(state_2025["is_analytics_enabled"], "2025 Mohali must remain analytics enabled")
        finally:
            self.db.execute(text("DELETE FROM system.datasets WHERE id = :id"), {"id": dummy_2026_id})
            # Restore 2026 Mohali
            self.db.execute(text("""
                UPDATE system.datasets SET is_active = TRUE, is_analytics_enabled = TRUE
                WHERE id = 'd1c37e76-8d48-4277-b696-a14abf6e1f3b'
            """))
            self.db.commit()

    def test_05_target_master_single_active_constraint(self):
        """Verify repository resolve_target_dataset returns strictly one active master."""
        target_id = resolve_target_dataset(self.db)
        self.assertIsNotNone(target_id, "Active target dataset must exist")

        active_targets = self.db.execute(text("""
            SELECT id FROM system.datasets
            WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'TARGET' AND is_active = TRUE
        """)).fetchall()
        self.assertEqual(len(active_targets), 1, "Strictly ONE target master must be active")

    def test_06_dimension_master_single_active_constraint(self):
        """Verify strictly one Dimension master is active."""
        active_dims = self.db.execute(text("""
            SELECT id FROM system.datasets
            WHERE UPPER(COALESCE(workbook_type, 'RAW')) = 'DIMENSION' AND is_active = TRUE
        """)).fetchall()
        self.assertEqual(len(active_dims), 1, "Strictly ONE dimension master must be active")

    # -------------------------------------------------------------------------
    # PART 1 — FIX 2025 PY SHOWING ZERO & SCOPE RESOLUTION
    # -------------------------------------------------------------------------
    def test_07_py_2025_resolution_when_2026_selected(self):
        """When 2026 is selected, CY = 2026 actuals and PY = 2025 actuals (both non-zero)."""
        overview = get_agg_overview(self.db, campus="Mohali", years=[2026, 2025])
        kpis = overview.get("kpis", {})

        self.assertEqual(overview.get("current_year"), 2026)
        self.assertEqual(overview.get("previous_year"), 2025)

        # Leads
        leads = kpis.get("leads", {})
        self.assertGreater(leads.get("cy", 0), 900000, "CY leads must be ~982k")
        self.assertGreater(leads.get("py", 0), 900000, "PY leads must be ~940k, NEVER zero")
        self.assertGreater(leads.get("change", 0), 0, "Lead change must be positive")
        self.assertIsNotNone(leads.get("growth_pct"), "Growth percentage must be computed")

        # Admissions
        adm = kpis.get("admissions", {})
        self.assertGreater(adm.get("cy", 0), 30000, "CY admissions must be ~31k")
        self.assertGreater(adm.get("py", 0), 25000, "PY admissions must be ~29k, NEVER zero")
        self.assertGreater(adm.get("change", 0), 0, "Admissions change must be positive")

        # Conversion Rate
        conv = kpis.get("conversion_rate", {})
        self.assertGreater(conv.get("cy", 0), 2.5)
        self.assertGreater(conv.get("py", 0), 2.5)

    def test_08_py_missing_returns_none(self):
        """When querying a year where PY has no dataset (e.g. year 2025 where PY is 2024), PY metrics must be None, not 0."""
        overview = get_agg_overview(self.db, campus="Mohali", years=[2025, 2024])
        kpis = overview.get("kpis", {})

        leads = kpis.get("leads", {})
        self.assertGreater(leads.get("cy", 0), 900000, "CY leads must be ~940k")
        self.assertIsNone(leads.get("py"), "PY leads must be None when no PY dataset exists")
        self.assertIsNone(leads.get("change"), "Change must be None when no PY dataset exists")
        self.assertIsNone(leads.get("growth_pct"), "Growth % must be None when no PY dataset exists")

        adm = kpis.get("admissions", {})
        self.assertGreater(adm.get("cy", 0), 25000)
        self.assertIsNone(adm.get("py"), "PY admissions must be None when no PY dataset exists")

    # -------------------------------------------------------------------------
    # PART 5 — TARGET VS CURRENT-YEAR LOGIC (NO SYNTHETIC DATA)
    # -------------------------------------------------------------------------
    def test_09_target_missing_returns_none(self):
        """When no target dataset exists, get_target_performance must return N/A / None, not 0."""
        # Temporarily deactivate target dataset
        self.db.execute(text("""
            UPDATE system.datasets SET is_active = FALSE, is_analytics_enabled = FALSE
            WHERE id = '0a991108-876e-42b2-8978-5e5ea2049a14'
        """))
        self.db.commit()

        try:
            res = get_target_performance(self.db, target_for="Admission", campus="Mohali", year=2026)
            self.assertEqual(res["target"], "N/A", "Target must be 'N/A' when no target dataset exists")
            self.assertEqual(res["variance"], "N/A", "Variance must be 'N/A' when target is missing")
            self.assertEqual(res["achievement_pct"], "N/A", "Achievement % must be 'N/A' when target is missing")
        finally:
            self.db.execute(text("""
                UPDATE system.datasets SET is_active = TRUE, is_analytics_enabled = TRUE
                WHERE id = '0a991108-876e-42b2-8978-5e5ea2049a14'
            """))
            self.db.commit()

    def test_10_no_synthetic_target_multipliers(self):
        """get_agg_monthly_trend must never apply synthetic multipliers (e.g. 1.15*) when Target is missing."""
        # Deactivate target
        self.db.execute(text("""
            UPDATE system.datasets SET is_active = FALSE, is_analytics_enabled = FALSE
            WHERE id = '0a991108-876e-42b2-8978-5e5ea2049a14'
        """))
        self.db.commit()

        try:
            trend = get_agg_monthly_trend(self.db, campus="Mohali", years=[2026, 2025], metric="admissions")
            trends_list = trend if isinstance(trend, list) else trend.get("trend", [])
            for t in trends_list:
                self.assertIsNone(t.get("target"), "Target in monthly trend must be None when no target exists, never synthetic")
        finally:
            self.db.execute(text("""
                UPDATE system.datasets SET is_active = TRUE, is_analytics_enabled = TRUE
                WHERE id = '0a991108-876e-42b2-8978-5e5ea2049a14'
            """))
            self.db.commit()

    def test_11_target_compares_only_cy_actual(self):
        """Target performance must strictly compare target against CY actual, never PY actual."""
        res_cy = get_target_performance(self.db, target_for="Leads", campus="Mohali", month="March", year=2026)
        res_py = get_target_performance(self.db, target_for="Leads", campus="Mohali", month="March", year=2025)

        # Actuals for 2026 and 2025 must be distinct
        self.assertNotEqual(res_cy["actual"], "N/A")
        self.assertNotEqual(res_py["actual"], "N/A")
        self.assertNotEqual(res_cy["actual"], res_py["actual"], "CY actual and PY actual must differ")
        # Target for March Mohali Leads
        self.assertEqual(res_cy["target"], 107578.58)

    def test_12_target_never_used_as_py_actual(self):
        """Target values must never masquerade as PY actual numbers in overview or reports."""
        overview = get_agg_overview(self.db, campus="Mohali", years=[2026, 2025])
        py_leads = overview["kpis"]["leads"]["py"]
        py_adm = overview["kpis"]["admissions"]["py"]

        # Real 2025 actuals are ~940k leads and ~29k admissions, NOT target numbers (which are 66k/29k etc.)
        self.assertEqual(py_leads, 940981, "PY leads must be authentic 2025 actuals")
        self.assertEqual(py_adm, 29024, "PY admissions must be authentic 2025 actuals")

    # -------------------------------------------------------------------------
    # PART 6 — TARGET ROW DATE/MONTH LOGIC
    # -------------------------------------------------------------------------
    def test_13_target_row_level_matching(self):
        """Target queries must match at row-level by Date, Month, Campus, and Target For."""
        # Query August Mohali Leads target
        res_aug = get_target_performance(self.db, target_for="Leads", campus="Mohali", month="August")
        self.assertEqual(res_aug["target"], 66715.31)

        # Query March Mohali Leads target
        res_mar = get_target_performance(self.db, target_for="Leads", campus="Mohali", month="March")
        self.assertEqual(res_mar["target"], 107578.58)

        # Query Annual Mohali Admissions target
        res_ann = get_target_performance(self.db, target_for="Admission", campus="Mohali", month=None)
        self.assertEqual(res_ann["target"], 29300.0)

    def test_14_separate_target_for(self):
        """Target For = 'Admission', 'Leads', 'CUCET' must return separate allocations."""
        res_adm = get_target_performance(self.db, target_for="Admission", campus="Mohali", month="March")
        res_lead = get_target_performance(self.db, target_for="Leads", campus="Mohali", month="March")
        res_cucet = get_target_performance(self.db, target_for="CUCET", campus="Mohali", month="March")

        self.assertEqual(res_adm["target"], 2320.0)
        self.assertEqual(res_lead["target"], 107578.58)
        self.assertEqual(res_cucet["target"], 7536.25)

    # -------------------------------------------------------------------------
    # PART 2 — INVESTIGATE & ELIMINATE ALL 404 / 422 / 500 ERRORS
    # -------------------------------------------------------------------------
    def test_15_dashboard_metrics_no_500(self):
        """Verify dashboard metrics calculation works without logger 500 error."""
        from app.analytics.aggregate_service import get_agg_overview
        res = get_agg_overview(self.db, campus="Mohali", years=[2026, 2025])
        self.assertIn("kpis", res)
        self.assertIn("leads", res["kpis"])

    def test_16_top_performers_admissions_regex_no_422(self):
        """_normalize_metric must accept 'admissions' and 'leads' without raising ValueError or 422."""
        self.assertEqual(_normalize_metric("admissions"), "admission")
        self.assertEqual(_normalize_metric("admission"), "admission")
        self.assertEqual(_normalize_metric("leads"), "leads")
        self.assertEqual(_normalize_metric("lead"), "leads")
        self.assertEqual(_normalize_metric("conversion_rate"), "conversion_rate")

    # -------------------------------------------------------------------------
    # PART 10 — PERFORMANCE & OPTIMIZATION VERIFICATION
    # -------------------------------------------------------------------------
    def test_20_scoped_aggregate_performance(self):
        """Scoped overview and monthly trend queries must complete under 500ms."""
        # Warmup query cache
        get_agg_overview(self.db, campus="Mohali", years=[2026, 2025])
        t0 = time.time()
        get_agg_overview(self.db, campus="Mohali", years=[2026, 2025])
        dur_overview = time.time() - t0

        get_agg_monthly_trend(self.db, campus="Mohali", years=[2026, 2025], metric="admissions")
        t1 = time.time()
        get_agg_monthly_trend(self.db, campus="Mohali", years=[2026, 2025], metric="admissions")
        dur_trend = time.time() - t1

        self.assertLess(dur_overview, 0.500, f"Overview query took {dur_overview:.3f}s (expected < 0.500s)")
        self.assertLess(dur_trend, 0.500, f"Monthly trend query took {dur_trend:.3f}s (expected < 0.500s)")


if __name__ == "__main__":
    unittest.main()
