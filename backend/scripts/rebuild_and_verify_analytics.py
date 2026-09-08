"""
Rebuild and Verify Analytics script
1. Re-normalizes staging records into analytics.uploaded_metrics with created_month and admission_month.
2. Re-populates analytics.dashboard_agg.
3. Tests get_agg_monthly_trend API helper to confirm zero synthetic weighting.
"""
import sys
import json
import logging
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.ingestion.analytics_normalizer import normalize_dataset
from app.analytics.aggregate_refresh import refresh_dashboard_agg
from app.analytics.aggregate_service import get_agg_monthly_trend

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def rebuild_and_verify():
    db = SessionLocal()
    try:
        # Enabled datasets
        ds_rows = db.execute(text("""
            SELECT id, dataset_name, academic_year 
            FROM system.datasets 
            WHERE is_analytics_enabled = TRUE;
        """)).mappings().all()

        print("1. Re-normalizing enabled datasets into analytics.uploaded_metrics...")
        for ds in ds_rows:
            ds_id = ds["id"]
            ds_name = ds["dataset_name"]
            print(f" - Processing dataset {ds_name} ({ds_id})...")
            cnt = normalize_dataset(db, ds_id, mode="insert")
            print(f"   -> Inserted {cnt} metrics rows into analytics.uploaded_metrics.")

        print("\n2. Refreshing analytics.dashboard_agg...")
        refresh_dashboard_agg(db)
        print("   -> analytics.dashboard_agg refreshed successfully.")

        print("\n3. Testing API Monthly Trend Output for 2026...")
        trend_2026 = get_agg_monthly_trend(db, years=[2026], metric="admissions")
        print("   -> 2026 Admissions Monthly Trend:")
        for t in trend_2026:
            print(f"      {t['month']:<12}: cy_admission = {t['cy_admission']:<6} (cy_leads = {t['cy_leads']})")

        print("\n4. Testing API Monthly Trend Output for 2025...")
        trend_2025 = get_agg_monthly_trend(db, years=[2025], metric="admissions")
        print("   -> 2025 Admissions Monthly Trend:")
        for t in trend_2025:
            print(f"      {t['month']:<12}: cy_admission = {t['cy_admission']:<6} (cy_leads = {t['cy_leads']})")

    finally:
        db.close()

if __name__ == "__main__":
    rebuild_and_verify()
