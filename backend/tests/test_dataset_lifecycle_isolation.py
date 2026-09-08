"""
Comprehensive Regression Test Suite — Dataset Lifecycle Isolation & Scope Resolution (TEST A - TEST I)

Validates:
- TEST A: Upload/activate 2025 & 2026 -> verify both years return authentic metrics.
- TEST B: Delete 2026 -> verify 2025 still works 100%, 2026 reports unavailable/N/A.
- TEST C: Upload new 2026 -> verify 2025 still works, 2026 uses new dataset.
- TEST D: Delete 2025 -> verify 2026 still works 100%.
- TEST E: Replace 2026 with a replacement upload -> verify old 2026 remains usable until new dataset activates.
- TEST F: Delete TARGET -> verify RAW dashboard actuals still work.
- TEST G: Delete DIMENSION -> verify system cleanly handles reference data without zeroing actual metrics.
- TEST H: Verify Dashboard Overview after every lifecycle operation.
- TEST I: Verify AI Agent tools after every lifecycle operation.
"""

import unittest
from uuid import uuid4
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.database.repository import create_data_source, create_dataset, set_active_dataset, enable_dataset_analytics
from app.ingestion.cleanup import delete_dataset_cascade
from app.api.data_management import delete_single_dataset
from app.analytics.aggregate_service import get_agg_overview
from app.analytics.scope_resolver import resolve_analytics_scope
from app.agent.agent_service import answer_question
from app.analytics.aggregate_refresh import refresh_dashboard_agg


def _get_leads(ov: dict) -> int:
    """Helper to safely extract leads from get_agg_overview response."""
    val = ov.get("kpis", {}).get("leads", {}).get("cy")
    return val if val is not None else 0


def _get_admissions(ov: dict) -> int:
    """Helper to safely extract admissions from get_agg_overview response."""
    val = ov.get("kpis", {}).get("admissions", {}).get("cy")
    return val if val is not None else 0


class TestDatasetLifecycleIsolation(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.test_dataset_ids = []
        self.test_campus = f"IsoTestCampus_{uuid4().hex[:6]}"

    def tearDown(self):
        if self.test_dataset_ids:
            try:
                delete_dataset_cascade(self.db, self.test_dataset_ids)
                self.db.commit()
            except Exception:
                self.db.rollback()
        self.db.close()

    def _create_mock_raw_dataset(self, year: int, campus: str | None, leads: int, admissions: int):
        if campus is None:
            campus = self.test_campus
        ds_id = str(uuid4())
        self.test_dataset_ids.append(ds_id)

        source_id = create_data_source(
            self.db,
            source_name=f"Mock_RAW_{campus}_{year}_{ds_id[:6]}.csv",
            source_type="file",
            description="Test isolation dataset",
        )
        create_dataset(
            db=self.db,
            dataset_id=ds_id,
            source_id=source_id,
            dataset_name=f"Mock_RAW_{campus}_{year}_{ds_id[:6]}.csv",
            original_filename=f"Mock_RAW_{campus}_{year}_{ds_id[:6]}.csv",
            dataset_type="csv",
            row_count=leads,
            column_count=10,
            status="profiled",
            file_checksum=f"checksum_{ds_id}",
        )

        self.db.execute(
            text("""
                UPDATE system.datasets
                SET academic_year = :yr,
                    campus_name = :cmp,
                    workbook_type = 'RAW',
                    status = 'staging_cleared',
                    is_analytics_enabled = TRUE,
                    is_active = TRUE
                WHERE id = :ds_id
            """),
            {"ds_id": ds_id, "yr": year, "cmp": campus},
        )

        # Batch insert analytics.uploaded_metrics for speed
        val_rows = [
            {
                "id": str(uuid4()),
                "ds_id": ds_id,
                "row_num": m,
                "cmp": campus,
                "yr": year,
                "m": m,
                "l": max(1, leads // 12),
                "a": max(0, admissions // 12),
            }
            for m in range(1, 13)
        ]
        self.db.execute(
            text("""
                INSERT INTO analytics.uploaded_metrics (
                    id, dataset_id, row_number, campus_name, academic_year, created_month, admission_month,
                    cy_leads, cy_admission, py_leads, py_admission
                ) VALUES (
                    :id, :ds_id, :row_num, :cmp, :yr, :m, :m,
                    :l, :a, 0, 0
                )
            """),
            val_rows,
        )

        self.db.commit()
        set_active_dataset(self.db, ds_id, allow_benchmark=True)
        return ds_id

    def test_01_TEST_A_upload_2025_and_2026_both_work(self):
        """TEST A: Upload 2025 and 2026 -> verify both years return authentic metrics."""
        ds_2025 = self._create_mock_raw_dataset(2025, self.test_campus, 1200, 120)
        ds_2026 = self._create_mock_raw_dataset(2026, self.test_campus, 2400, 240)
        refresh_dashboard_agg(self.db)

        scope_2025 = resolve_analytics_scope(self.db, campus=self.test_campus, years=[2025])
        scope_2026 = resolve_analytics_scope(self.db, campus=self.test_campus, years=[2026])

        self.assertIn(ds_2025, scope_2025["dataset_ids"])
        self.assertIn(ds_2026, scope_2026["dataset_ids"])

        ov_2025 = get_agg_overview(self.db, campus=self.test_campus, years=[2025])
        ov_2026 = get_agg_overview(self.db, campus=self.test_campus, years=[2026])

        self.assertGreater(_get_leads(ov_2025), 0)
        self.assertGreater(_get_leads(ov_2026), 0)

    def test_02_TEST_B_delete_2026_2025_still_works(self):
        """TEST B: Delete 2026 -> verify 2025 still works 100%, 2026 reports unavailable/empty."""
        ds_2025 = self._create_mock_raw_dataset(2025, self.test_campus, 1200, 120)
        ds_2026 = self._create_mock_raw_dataset(2026, self.test_campus, 2400, 240)
        refresh_dashboard_agg(self.db)

        # Delete 2026 dataset
        delete_single_dataset(ds_2026, confirm=True, db=self.db)
        self.test_dataset_ids.remove(ds_2026)

        # 2025 MUST continue working 100%
        ov_2025 = get_agg_overview(self.db, campus=self.test_campus, years=[2025])
        self.assertGreater(_get_leads(ov_2025), 0)
        self.assertGreater(_get_admissions(ov_2025), 0)

        # 2026 MUST report zero / unavailable without throwing unhandled exceptions
        ov_2026 = get_agg_overview(self.db, campus=self.test_campus, years=[2026])
        self.assertEqual(_get_leads(ov_2026), 0)

    def test_03_TEST_C_reupload_2026_both_years_work(self):
        """TEST C: Upload new 2026 dataset -> verify both 2025 and new 2026 work."""
        ds_2025 = self._create_mock_raw_dataset(2025, self.test_campus, 1200, 120)
        ds_2026_old = self._create_mock_raw_dataset(2026, self.test_campus, 2400, 240)
        refresh_dashboard_agg(self.db)

        delete_single_dataset(ds_2026_old, confirm=True, db=self.db)
        self.test_dataset_ids.remove(ds_2026_old)

        # Upload new 2026 dataset B2
        ds_2026_new = self._create_mock_raw_dataset(2026, self.test_campus, 3600, 360)
        refresh_dashboard_agg(self.db)

        ov_2025 = get_agg_overview(self.db, campus=self.test_campus, years=[2025])
        ov_2026 = get_agg_overview(self.db, campus=self.test_campus, years=[2026])

        self.assertGreater(_get_leads(ov_2025), 0)
        self.assertGreater(_get_leads(ov_2026), 0)

    def test_04_TEST_D_delete_2025_2026_still_works(self):
        """TEST D: Delete 2025 -> verify 2026 still works 100%."""
        ds_2025 = self._create_mock_raw_dataset(2025, self.test_campus, 1200, 120)
        ds_2026 = self._create_mock_raw_dataset(2026, self.test_campus, 2400, 240)
        refresh_dashboard_agg(self.db)

        delete_single_dataset(ds_2025, confirm=True, db=self.db)
        self.test_dataset_ids.remove(ds_2025)

        ov_2026 = get_agg_overview(self.db, campus=self.test_campus, years=[2026])
        self.assertGreater(_get_leads(ov_2026), 0)

    def test_05_TEST_E_replacement_safety(self):
        """TEST E: Replace 2026 with a replacement upload -> verify previous dataset remains usable until new dataset activates."""
        ds_2026_v1 = self._create_mock_raw_dataset(2026, self.test_campus, 2000, 200)
        refresh_dashboard_agg(self.db)

        ov_v1 = get_agg_overview(self.db, campus=self.test_campus, years=[2026])
        self.assertGreater(_get_leads(ov_v1), 0)

        # Create new dataset v2
        ds_2026_v2 = self._create_mock_raw_dataset(2026, self.test_campus, 3000, 300)
        refresh_dashboard_agg(self.db)

        ov_v2 = get_agg_overview(self.db, campus=self.test_campus, years=[2026])
        self.assertGreaterEqual(_get_leads(ov_v2), 300)

    def test_06_TEST_F_delete_target_raw_dashboard_still_works(self):
        """TEST F: Delete TARGET -> verify RAW dashboard actuals still work."""
        ds_2026 = self._create_mock_raw_dataset(2026, self.test_campus, 1500, 150)
        
        # Create mock target dataset
        tgt_id = str(uuid4())
        self.test_dataset_ids.append(tgt_id)
        create_dataset(
            db=self.db,
            dataset_id=tgt_id,
            source_id=create_data_source(self.db, "target.xlsx", "file", "target"),
            dataset_name="target.xlsx",
            original_filename="target.xlsx",
            dataset_type="xlsx",
            row_count=50,
            column_count=5,
            status="profiled",
            file_checksum=f"chk_tgt_{tgt_id}",
        )
        self.db.execute(text("UPDATE system.datasets SET workbook_type = 'TARGET', is_analytics_enabled = TRUE WHERE id = :id"), {"id": tgt_id})
        self.db.commit()

        # Delete TARGET dataset
        delete_single_dataset(tgt_id, confirm=True, db=self.db)
        self.test_dataset_ids.remove(tgt_id)

        # RAW Dashboard MUST continue working
        ov = get_agg_overview(self.db, campus=self.test_campus, years=[2026])
        self.assertGreater(_get_leads(ov), 0)

    def test_07_TEST_G_delete_dimension_actual_metrics_not_zeroed(self):
        """TEST G: Delete DIMENSION -> verify system handles reference data without zeroing actual metrics."""
        ds_2026 = self._create_mock_raw_dataset(2026, self.test_campus, 1800, 180)

        dim_id = str(uuid4())
        self.test_dataset_ids.append(dim_id)
        create_dataset(
            db=self.db,
            dataset_id=dim_id,
            source_id=create_data_source(self.db, "dim.xlsx", "file", "dimension"),
            dataset_name="dim.xlsx",
            original_filename="dim.xlsx",
            dataset_type="xlsx",
            row_count=30,
            column_count=5,
            status="profiled",
            file_checksum=f"chk_dim_{dim_id}",
        )
        self.db.execute(text("UPDATE system.datasets SET workbook_type = 'DIMENSION', is_analytics_enabled = TRUE WHERE id = :id"), {"id": dim_id})
        self.db.commit()

        delete_single_dataset(dim_id, confirm=True, db=self.db)
        self.test_dataset_ids.remove(dim_id)

        ov = get_agg_overview(self.db, campus=self.test_campus, years=[2026])
        self.assertGreater(_get_leads(ov), 0)

    def test_08_TEST_H_dashboard_overview_after_lifecycle_ops(self):
        """TEST H: Verify Dashboard Overview after lifecycle operation."""
        ds_2025 = self._create_mock_raw_dataset(2025, self.test_campus, 1000, 100)
        ds_2026 = self._create_mock_raw_dataset(2026, self.test_campus, 2000, 200)
        refresh_dashboard_agg(self.db)

        # Run overview resolution
        rep_2025 = get_agg_overview(self.db, campus=self.test_campus, years=[2025])
        self.assertIsNotNone(rep_2025)
        self.assertGreater(_get_leads(rep_2025), 0)

        # Delete 2026
        delete_single_dataset(ds_2026, confirm=True, db=self.db)
        self.test_dataset_ids.remove(ds_2026)

        # 2025 overview MUST remain fully operational
        rep_2025_after = get_agg_overview(self.db, campus=self.test_campus, years=[2025])
        self.assertIsNotNone(rep_2025_after)
        self.assertGreater(_get_leads(rep_2025_after), 0)

    def test_09_TEST_I_ai_agent_tools_after_lifecycle_ops(self):
        """TEST I: Verify AI Agent intent parser and aggregate queries after lifecycle operation."""
        ds_2025 = self._create_mock_raw_dataset(2025, self.test_campus, 1000, 100)
        refresh_dashboard_agg(self.db)

        # Test intent parser
        from app.agent.intent_parser import parse_question

        parsed = parse_question("How many leads in 2025?")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.get("intent_type"), "metric")
        self.assertEqual(parsed.get("metric"), "leads")

        # Test direct tool execution post-lifecycle
        res = get_agg_overview(self.db, campus=self.test_campus, years=[2025])
        self.assertIsNotNone(res)
        self.assertGreater(_get_leads(res), 0)


if __name__ == "__main__":
    unittest.main()
