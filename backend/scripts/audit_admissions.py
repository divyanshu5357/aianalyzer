"""
Phase 12.5 / Audit: Admission Aggregation Audit Script

Computes actual PostgreSQL admission counts by admission month (mx_AdmissionDate) for 2025 and 2026.
Rules:
1. mx_AdmissionDate IS NOT NULL (and not empty) is the ONLY source of truth for admissions.
2. Refund status does NOT exclude admissions.
3. Grouped by the year/month of mx_AdmissionDate (parsed as DD/MM/YY, YYYY-MM-DD, etc.), NOT CreatedOn.
4. Counts DISTINCT ProspectID (or unique lead record key) to prevent duplicate row inflation.
5. Excludes disabled/test datasets (only enabled analytics datasets).
6. Compares actual PostgreSQL counts against analytics.dashboard_agg and analytics.uploaded_metrics.
"""

import sys
import json
import logging
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import text
from app.database.connection import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_date_string(dt_str: str) -> datetime | None:
    if not dt_str or not str(dt_str).strip():
        return None
    cleaned = str(dt_str).strip()

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%d/%m/%y %H:%M",
        "%d/%m/%Y %H:%M",
        "%d/%m/%y",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass

    # Try string splitting if date has space or T
    parts = cleaned.split(" ")[0].split("T")[0]
    for fmt in ["%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(parts, fmt)
        except ValueError:
            pass

    return None


def run_audit() -> Dict[str, Any]:
    db = SessionLocal()
    report: Dict[str, Any] = {}

    try:
        # 1. Fetch enabled datasets
        datasets_rows = db.execute(text("""
            SELECT id, dataset_name, original_filename, row_count, academic_year, is_analytics_enabled
            FROM system.datasets
            WHERE is_analytics_enabled = TRUE
            ORDER BY academic_year, dataset_name;
        """)).mappings().all()

        report["enabled_datasets"] = [dict(r) for r in datasets_rows]
        enabled_ds_ids = [str(r["id"]) for r in datasets_rows]

        # 2. Raw staging records audit per dataset
        dataset_stats = []
        monthly_counts: Dict[str, set] = {} # Key: "YYYY-MM", Value: set of ProspectIDs
        
        for ds in datasets_rows:
            ds_id = str(ds["id"])
            ds_name = ds["dataset_name"]

            query = text("""
                SELECT raw_data->>'ProspectID' AS prospect_id,
                       raw_data->>'mx_AdmissionDate' AS mx_admission_date,
                       raw_data->>'CreatedOn' AS created_on,
                       raw_data->>'mx_Refund_Status' AS refund_status
                FROM staging.records
                WHERE dataset_id = :ds_id;
            """)
            records = db.execute(query, {"ds_id": ds_id}).mappings().all()

            total_records = len(records)
            records_with_adm_date = 0
            distinct_prospects_with_adm_date = set()

            for r in records:
                adm_date_raw = r["mx_admission_date"]
                prospect_id = r["prospect_id"] or r.get("id")

                if adm_date_raw and str(adm_date_raw).strip() and str(adm_date_raw).strip().lower() != "null":
                    records_with_adm_date += 1
                    if prospect_id:
                        distinct_prospects_with_adm_date.add(prospect_id)

                    dt = parse_date_string(adm_date_raw)
                    if dt:
                        month_key = dt.strftime("%Y-%m")
                        if month_key not in monthly_counts:
                            monthly_counts[month_key] = set()
                        monthly_counts[month_key].add(prospect_id or f"{ds_id}_{r.get('id')}")

            dataset_stats.append({
                "dataset_id": ds_id,
                "dataset_name": ds_name,
                "academic_year": ds["academic_year"],
                "total_records": total_records,
                "records_with_mx_admission_date": records_with_adm_date,
                "distinct_prospect_admissions": len(distinct_prospects_with_adm_date),
            })

        report["dataset_stats"] = dataset_stats

        # 3. Monthly Breakdown Summary (Distinct ProspectIDs)
        actual_monthly_admissions = {}
        for y_m in sorted(monthly_counts.keys()):
            actual_monthly_admissions[y_m] = len(monthly_counts[y_m])

        report["actual_postgresql_monthly_admissions"] = actual_monthly_admissions

        # Annual sums of distinct admissions
        admissions_2025_actual = sum(cnt for y_m, cnt in actual_monthly_admissions.items() if y_m.startswith("2025"))
        admissions_2026_actual = sum(cnt for y_m, cnt in actual_monthly_admissions.items() if y_m.startswith("2026"))

        report["actual_annual_distinct_admissions"] = {
            "2025": admissions_2025_actual,
            "2026": admissions_2026_actual,
        }

        # 4. Compare with analytics.dashboard_agg
        agg_rows = db.execute(text("""
            SELECT academic_year, SUM(leads_cy) AS leads, SUM(cucet_cy) AS cucet, SUM(admission_cy) AS admissions
            FROM analytics.dashboard_agg
            GROUP BY academic_year;
        """)).mappings().all()

        report["dashboard_agg_totals"] = {str(r["academic_year"]): dict(r) for r in agg_rows}

        # 5. Compare with analytics.uploaded_metrics
        um_rows = db.execute(text("""
            SELECT COALESCE(academic_year, 0) AS year, SUM(cy_leads) AS leads, SUM(cy_cucet) AS cucet, SUM(cy_admission) AS admissions
            FROM analytics.uploaded_metrics
            GROUP BY academic_year;
        """)).mappings().all()

        report["uploaded_metrics_totals"] = {str(r["year"]): dict(r) for r in um_rows}

        return report
    finally:
        db.close()


if __name__ == "__main__":
    res = run_audit()
    print(json.dumps(res, indent=2))
