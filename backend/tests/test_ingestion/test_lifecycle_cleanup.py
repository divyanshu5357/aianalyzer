import csv
import os
import unittest
from uuid import uuid4
from sqlalchemy import text

from app.database.connection import SessionLocal
from app.database.repository import (
    create_data_source,
    create_dataset,
    create_quality_report,
    set_active_dataset,
    get_active_dataset_info,
)
from app.ingestion.profiler import profile_file
from app.ingestion.staging_loader import load_to_staging
from app.ingestion.schema_mapper import map_and_store_dataset_schema
from app.ingestion.analytics_normalizer import normalize_dataset
from app.ingestion.cleanup import cleanup_staging_for_dataset, cleanup_benchmark_datasets, get_benchmark_datasets_summary


class TestStagingLifecycleAndCleanup(unittest.TestCase):

    def setUp(self):
        self.db = SessionLocal()
        self.test_csv = "/tmp/test_lifecycle.csv"
        headers = ["Owner", "Cluster", "Lead Type", "Source Cluster", "MSSourcebi", "Campus Name", "State Group", "Program Name (Short)", "CY Leads", "CY CUCET", "CY Admission", "PY Leads", "PY CUCET", "PY Admission"]
        with open(self.test_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for i in range(1, 101):
                w.writerow(["Alice", "North", "Direct", "Digital Cluster", "Google", "Mohali", "Punjab", "B.Tech CSE", 10, 5, 2, 8, 4, 1])

    def tearDown(self):
        self.db.close()
        if os.path.exists(self.test_csv):
            os.remove(self.test_csv)

    def test_end_to_end_lifecycle_and_staging_pruning(self):
        dataset_id = uuid4()
        source_id = create_data_source(self.db, "Real_User_Upload.csv", "file", "Real user upload")
        profile = profile_file(self.test_csv)
        create_dataset(self.db, dataset_id, source_id, "Real_User_Upload", "Real_User_Upload.csv", "csv", profile["rows"], profile["columns"], "profiled")
        create_quality_report(self.db, dataset_id, profile)

        staged_rows = load_to_staging(self.db, dataset_id, self.test_csv)
        self.assertEqual(staged_rows, 100)

        map_and_store_dataset_schema(self.db, dataset_id, profile["column_names"])
        norm_rows = normalize_dataset(self.db, dataset_id)
        self.assertEqual(norm_rows, 100)

        set_active_dataset(self.db, str(dataset_id))
        self.db.commit()

        # Check before staging cleanup
        staging_before = self.db.execute(text("SELECT COUNT(*) FROM staging.records WHERE dataset_id = :d_id"), {"d_id": dataset_id}).scalar()
        analytics_before = self.db.execute(text("SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :d_id"), {"d_id": dataset_id}).scalar()
        self.assertEqual(staging_before, 100)
        self.assertEqual(analytics_before, 100)

        # Execute safe staging cleanup
        cleanup_res = cleanup_staging_for_dataset(self.db, dataset_id)
        self.assertTrue(cleanup_res["success"])
        self.assertEqual(cleanup_res["deleted_staging_rows"], 100)

        # Check after staging cleanup
        staging_after = self.db.execute(text("SELECT COUNT(*) FROM staging.records WHERE dataset_id = :d_id"), {"d_id": dataset_id}).scalar()
        analytics_after = self.db.execute(text("SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :d_id"), {"d_id": dataset_id}).scalar()
        self.assertEqual(staging_after, 0)
        self.assertEqual(analytics_after, 100)

        # Verify active dataset info remains intact
        active_info = get_active_dataset_info(self.db)
        self.assertIsNotNone(active_info)
        self.assertEqual(active_info["id"], str(dataset_id))
        self.assertEqual(active_info["status"], "staging_cleared")

    def test_benchmark_cleanup_protects_active_dataset(self):
        # Create active real dataset
        active_id = uuid4()
        src1 = create_data_source(self.db, "Production_Data.csv", "file", "Production")
        create_dataset(self.db, active_id, src1, "Production_Data", "Production_Data.csv", "csv", 50, 10, "ready")
        set_active_dataset(self.db, str(active_id))

        # Create dummy benchmark dataset
        bench_id = uuid4()
        src2 = create_data_source(self.db, "Bench_Test.csv", "file", "Benchmark")
        create_dataset(self.db, bench_id, src2, "Bench_Test", "benchmark_test.csv", "csv", 20, 10, "profiled")
        self.db.commit()

        summary = get_benchmark_datasets_summary(self.db)
        candidate_ids = [c["id"] for c in summary["candidates"]]
        self.assertIn(str(bench_id), candidate_ids)
        self.assertNotIn(str(active_id), candidate_ids)

        res = cleanup_benchmark_datasets(self.db)
        self.assertGreaterEqual(res["deleted_datasets"], 1)

        # Verify active dataset remains intact in DB
        active_exists = self.db.execute(text("SELECT COUNT(*) FROM system.datasets WHERE id = :d_id"), {"d_id": active_id}).scalar()
        self.assertEqual(active_exists, 1)


if __name__ == "__main__":
    unittest.main()
