import csv
import os
import resource
import time
import unittest
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from app.database.connection import SessionLocal, engine
from app.database.repository import create_data_source, create_dataset, set_active_dataset, get_active_dataset_info
from app.ingestion.profiler import profile_file
from app.ingestion.staging_loader import load_to_staging
from app.ingestion.schema_mapper import map_and_store_dataset_schema
from app.ingestion.analytics_normalizer import normalize_dataset


def get_peak_memory_mb() -> float:
    """Get peak memory usage of process in MB."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # On macOS, ru_maxrss is in bytes; on Linux, in kilobytes.
    import platform
    if platform.system() == "Darwin":
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024


def generate_test_csv(file_path: str, row_count: int) -> str:
    """Generate a realistic test CSV file with the given row count."""
    headers = [
        "Owner", "Cluster", "Lead Type", "Source Cluster", "MSSourcebi",
        "Campus Name", "State Group", "Program Name (Short)",
        "CY Leads", "CY CUCET", "CY Admission",
        "PY Leads", "PY CUCET", "PY Admission"
    ]

    owners = ["Alice", "Bob", "Charlie", "David", "Eva"]
    clusters = ["North", "South", "East", "West", "Central"]
    lead_types = ["Direct", "Partner", "Digital", "Referral"]
    sources = ["Google", "Facebook", "Direct Web", "Email", "Events"]
    campuses = ["Mohali", "Chandigarh", "Delhi", "Mumbai", "Bangalore"]
    states = ["Punjab", "Haryana", "Delhi", "Maharashtra", "Karnataka"]
    programs = ["B.Tech CSE", "MBA", "BBA", "B.Sc Biotech", "M.Tech"]

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for i in range(1, row_count + 1):
            writer.writerow([
                owners[i % len(owners)],
                clusters[i % len(clusters)],
                lead_types[i % len(lead_types)],
                "Digital Cluster",
                sources[i % len(sources)],
                campuses[i % len(campuses)],
                states[i % len(states)],
                programs[i % len(programs)],
                10 + (i % 50),
                5 + (i % 20),
                2 + (i % 10),
                8 + (i % 40),
                4 + (i % 15),
                1 + (i % 8)
            ])
    return file_path


def run_benchmark(row_count: int):
    file_path = f"/tmp/benchmark_{row_count}.csv"
    print(f"\n==================================================")
    print(f"  BENCHMARK FOR {row_count:,} ROWS")
    print(f"==================================================")
    print(f"Generating test CSV file ({row_count:,} rows)...")
    gen_start = time.time()
    generate_test_csv(file_path, row_count)
    gen_time = time.time() - gen_start
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"Generated {file_path} ({file_size_mb:.2f} MB) in {gen_time:.2f} s")

    db = SessionLocal()
    try:
        mem_before = get_peak_memory_mb()
        start_total = time.time()

        # 1. Profile
        prof_start = time.time()
        profile = profile_file(file_path)
        prof_time = time.time() - prof_start

        # 2. Setup Dataset metadata
        dataset_id = uuid4()
        source_id = create_data_source(db, f"Bench_{row_count}", "file", "Benchmark data")
        create_dataset(db, dataset_id, source_id, f"Bench_{row_count}", f"benchmark_{row_count}.csv", "csv", profile["rows"], profile["columns"], "profiled")

        # 3. Stage data
        stage_start = time.time()
        staged_rows = load_to_staging(db, dataset_id, file_path)
        stage_time = time.time() - stage_start

        # 4. Schema mapping
        map_start = time.time()
        map_and_store_dataset_schema(db, dataset_id, profile["column_names"])
        map_time = time.time() - map_start

        # 5. Normalize metrics
        norm_start = time.time()
        normalized_rows = normalize_dataset(db, dataset_id)
        norm_time = time.time() - norm_start

        # 6. Commit transaction & set active dataset
        set_active_dataset(db, str(dataset_id))
        db.commit()

        total_time = time.time() - start_total
        mem_after = get_peak_memory_mb()

        # 7. Check database sizes
        staging_size_res = db.execute(text("SELECT pg_total_relation_size('staging.records')")).scalar()
        analytics_size_res = db.execute(text("SELECT pg_total_relation_size('analytics.uploaded_metrics')")).scalar()
        staging_size_mb = (staging_size_res or 0) / (1024 * 1024)
        analytics_size_mb = (analytics_size_res or 0) / (1024 * 1024)

        # 8. Analytical query latency
        query_start = time.time()
        query_res = db.execute(text("""
            SELECT campus_name, SUM(cy_admission) as total_adm, SUM(cy_leads) as total_leads
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :d_id
            GROUP BY campus_name
            ORDER BY total_adm DESC
        """), {"d_id": dataset_id}).fetchall()
        query_latency_ms = (time.time() - query_start) * 1000

        # 9. Correctness checks
        staging_cnt = db.execute(text("SELECT COUNT(*) FROM staging.records WHERE dataset_id = :d_id"), {"d_id": dataset_id}).scalar()
        analytics_cnt = db.execute(text("SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :d_id"), {"d_id": dataset_id}).scalar()
        duplicates_cnt = db.execute(text("""
            SELECT COUNT(*) - COUNT(DISTINCT (dataset_id, row_number))
            FROM analytics.uploaded_metrics WHERE dataset_id = :d_id
        """), {"d_id": dataset_id}).scalar()

        # 10. Verify Active Dataset
        active_info = get_active_dataset_info(db)
        active_matches = active_info and active_info.get("id") == str(dataset_id)

        print(f"\n--- BENCHMARK RESULTS ({row_count:,} rows) ---")
        print(f"Staging Ingestion Time : {stage_time:.2f} sec")
        print(f"Normalization Time     : {norm_time:.2f} sec")
        print(f"Total Ingestion Time   : {total_time:.2f} sec")
        print(f"Peak Process Memory    : {mem_after:.2f} MB (Delta: {mem_after - mem_before:.2f} MB)")
        print(f"Staging DB Storage     : {staging_size_mb:.2f} MB")
        print(f"Analytics DB Storage   : {analytics_size_mb:.2f} MB")
        print(f"Analytical Query Latency: {query_latency_ms:.2f} ms")
        print(f"Staging Row Count      : {staging_cnt}")
        print(f"Normalized Row Count   : {analytics_cnt}")
        print(f"Duplicates Count       : {duplicates_cnt}")
        print(f"Active Dataset Intact  : {active_matches}")
        print(f"Query Results Count    : {len(query_res)}")

        assert staging_cnt == row_count, f"Staging count mismatch: {staging_cnt} vs {row_count}"
        assert analytics_cnt == row_count, f"Analytics count mismatch: {analytics_cnt} vs {row_count}"
        assert duplicates_cnt == 0, f"Duplicates found: {duplicates_cnt}"
        assert active_matches, "Active dataset context mismatch"

        return {
            "rows": row_count,
            "stage_time": stage_time,
            "norm_time": norm_time,
            "total_time": total_time,
            "peak_memory_mb": mem_after,
            "staging_storage_mb": staging_size_mb,
            "analytics_storage_mb": analytics_size_mb,
            "query_latency_ms": query_latency_ms,
        }

    finally:
        db.close()
        if os.path.exists(file_path):
            os.remove(file_path)


class TestIngestionScalability(unittest.TestCase):

    def test_100k_rows(self):
        res = run_benchmark(100_000)
        self.assertEqual(res["rows"], 100_000)

    def test_1m_rows(self):
        res = run_benchmark(1_000_000)
        self.assertEqual(res["rows"], 1_000_000)

    def test_5m_rows(self):
        res = run_benchmark(5_000_000)
        self.assertEqual(res["rows"], 5_000_000)


if __name__ == "__main__":
    unittest.main()

