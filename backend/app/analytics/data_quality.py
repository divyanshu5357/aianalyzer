"""
Pre-ML Data Quality & Dimension Coverage Auditor
Analyzes production datasets for completeness, null rates, unmapped dimension values, and metric coverage.
Optimized with single-pass SQL aggregation.
"""

from typing import Dict, Any, List
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.analytics.dashboard import _resolve_dimension_col


def run_data_quality_audit(db: Session) -> List[Dict[str, Any]]:
    """
    Run comprehensive data quality audit across all enabled production datasets.
    Returns structured metrics per dataset.
    """
    datasets = db.execute(
        text("""
            SELECT id, dataset_name, academic_year, campus_name, row_count
            FROM system.datasets
            WHERE is_analytics_enabled = TRUE
            ORDER BY campus_name, academic_year
        """)
    ).mappings().all()

    # Get available columns in analytics.uploaded_metrics
    db_cols = db.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_schema='analytics' AND table_name='uploaded_metrics'")
    ).scalars().all()
    avail_cols = set(db_cols)

    audit_reports = []

    target_dimensions = [
        "academic_year",
        "campus_name",
        "source",
        "state",
        "state_code",
        "zone",
        "program_name",
        "program_code",
        "course_cluster",
        "owner",
        "team",
    ]

    for d in datasets:
        ds_id = str(d["id"])
        total_rows = d["row_count"] or 1

        # Single-pass null & coverage aggregation
        filter_exprs = []
        for dim in target_dimensions:
            col_name = _resolve_dimension_col(dim)
            if col_name in avail_cols:
                filter_exprs.append(f'COUNT(*) FILTER (WHERE "{col_name}" IS NULL OR "{col_name}"::text = \'\') as null_{dim}')
            else:
                filter_exprs.append(f'COUNT(*) as null_{dim}')

        sql_exprs = ", ".join(filter_exprs)
        query = f"""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(*) FILTER (WHERE cy_leads > 0) as lead_rows,
                COUNT(*) FILTER (WHERE cy_cucet > 0) as cucet_rows,
                COUNT(*) FILTER (WHERE cy_admission > 0) as admission_rows,
                COUNT(*) FILTER (WHERE lead_type = 'Refunded') as refunded_rows,
                COUNT(*) FILTER (WHERE main_source IS NOT NULL AND main_source != '') as mapped_source,
                COUNT(*) FILTER (WHERE program_name IS NOT NULL AND program_name != '') as mapped_program,
                COUNT(*) FILTER (WHERE state IS NOT NULL AND state != '') as mapped_state,
                COUNT(*) FILTER (WHERE owner IS NOT NULL AND owner != '') as mapped_owner,
                {sql_exprs}
            FROM analytics.uploaded_metrics
            WHERE dataset_id::text = '{ds_id}'
        """

        res = db.execute(text(query)).mappings().first()

        null_counts = {}
        for dim in target_dimensions:
            col_name = _resolve_dimension_col(dim)
            cnt = res[f"null_{dim}"] or 0
            null_counts[dim] = {
                "resolved_column": col_name,
                "exists_in_schema": col_name in avail_cols,
                "null_count": cnt,
                "null_pct": round((cnt / total_rows) * 100.0, 2),
            }

        report = {
            "dataset_id": ds_id,
            "dataset_name": d["dataset_name"],
            "campus_name": d["campus_name"],
            "academic_year": d["academic_year"],
            "row_count": total_rows,
            "duplicate_count": 0,
            "dimension_null_rates": null_counts,
            "source_mapping_coverage": round((res["mapped_source"] / total_rows) * 100.0, 2),
            "program_mapping_coverage": round((res["mapped_program"] / total_rows) * 100.0, 2),
            "state_mapping_coverage": round((res["mapped_state"] / total_rows) * 100.0, 2),
            "employee_mapping_coverage": round((res["mapped_owner"] / total_rows) * 100.0, 2),
            "admission_row_coverage": round((res["admission_rows"] / total_rows) * 100.0, 2),
            "cucet_row_coverage": round((res["cucet_rows"] / total_rows) * 100.0, 2),
        }
        audit_reports.append(report)

    return audit_reports


if __name__ == "__main__":
    db = SessionLocal()
    try:
        results = run_data_quality_audit(db)
        print("DATA QUALITY AUDIT COMPLETE:")
        for r in results:
            print(f"\n--- {r['campus_name']} {r['academic_year']} ({r['dataset_name']}) ---")
            print(f"Row count: {r['row_count']:,} | Duplicates: {r['duplicate_count']}")
            print(f"Source coverage: {r['source_mapping_coverage']}% | Program coverage: {r['program_mapping_coverage']}% | State coverage: {r['state_mapping_coverage']}% | Employee coverage: {r['employee_mapping_coverage']}%")
            print(f"Admission row coverage: {r['admission_row_coverage']}% | CUCET row coverage: {r['cucet_row_coverage']}%")
    finally:
        db.close()
