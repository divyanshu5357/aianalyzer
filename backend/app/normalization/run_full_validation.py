"""
Full Validation Runner — Orchestrates all phases and produces the pre-ML readiness report.

Usage:
    DATABASE_URL="postgresql://ai_admin:ai_password@localhost:5433/ai_agent" \
    PYTHONPATH=. venv/bin/python -m app.normalization.run_full_validation
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime

from app.database.connection import SessionLocal
from app.normalization.quality_report import generate_all_quality_reports
from app.normalization.metric_reconciler import reconcile_all
from app.normalization.sample_validator import validate_all_samples
from app.normalization.anomaly_detector import detect_all_anomalies

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def run() -> dict:
    db = SessionLocal()
    try:
        report = {"generated_at": datetime.utcnow().isoformat(), "sections": {}}

        # Section A: Data Quality Reports
        logger.info("=== Section A: Data Quality Reports ===")
        quality_reports = generate_all_quality_reports(db)
        report["sections"]["A_data_quality"] = [r.to_dict() for r in quality_reports]
        for qr in quality_reports:
            logger.info(f"  {qr.campus_name} {qr.academic_year}: analytics={qr.analytics_rows}, state_coverage={qr.state_coverage_pct}%")

        # Section B: Dimension Resolution (embedded in quality reports)
        logger.info("=== Section B: Dimension Resolution ===")
        report["sections"]["B_dimension_resolution"] = {
            "summary": [{
                "dataset": r.dataset_name,
                "state": {"resolved": r.state_resolved, "unresolved": r.state_unresolved, "coverage": r.state_coverage_pct},
                "source": {"resolved": r.source_resolved, "unresolved": r.source_unresolved, "coverage": r.source_coverage_pct},
                "employee": {"resolved": r.employee_resolved, "unresolved": r.employee_unresolved, "coverage": r.employee_coverage_pct},
            } for r in quality_reports],
        }

        # Section C-E: Metric Reconciliation (per-dataset + cross-dataset)
        logger.info("=== Section C-E: Metric Reconciliation ===")
        recon = reconcile_all(db)
        report["sections"]["C_metric_reconciliation"] = recon["per_dataset"]
        report["sections"]["D_cross_campus_reconciliation"] = recon["cross_dataset"]
        report["sections"]["E_cross_year_reconciliation"] = recon["cross_dataset"]

        # Section F: API vs SQL (embedded in reconciliation)
        logger.info("=== Section F: API vs SQL ===")
        api_comparisons = []
        for ds_recon in recon["per_dataset"]:
            comparison = {
                "dataset": ds_recon["dataset_name"],
                "campus": ds_recon["campus"],
                "year": ds_recon["year"],
                "metrics": {},
            }
            for metric_name, vals in ds_recon["metrics"].items():
                if vals.get("semantic_layer") is not None:
                    comparison["metrics"][metric_name] = {
                        "independent_sql": vals["independent_sql"],
                        "semantic_layer": vals["semantic_layer"],
                        "match": vals["match"],
                    }
            api_comparisons.append(comparison)
        report["sections"]["F_api_vs_sql"] = api_comparisons

        # Section H: Manual Sample Validation
        logger.info("=== Section H: Manual Sample Validation ===")
        samples = validate_all_samples(db, sample_size=100)
        report["sections"]["H_manual_sample"] = [{
            "dataset": s["dataset_name"],
            "campus": s["campus"],
            "year": s["year"],
            "sample_size": s["sample_size"],
            "summary": s["summary"],
        } for s in samples]

        # Section I: Unresolved/Ambiguous Values
        logger.info("=== Section I: Unresolved Values ===")
        unresolved = []
        for qr in quality_reports:
            unresolved.append({
                "dataset": qr.dataset_name,
                "unmapped_statuses": qr.unmapped_statuses,
                "top_unresolved_states": qr.top_unresolved_states,
                "top_unresolved_sources": qr.top_unresolved_sources,
            })
        report["sections"]["I_unresolved_values"] = unresolved

        # Anomalies
        logger.info("=== Anomaly Detection ===")
        anomalies = detect_all_anomalies(db)
        report["sections"]["anomalies"] = anomalies

        # Section J: ML Readiness Recommendation
        logger.info("=== Section J: ML Readiness ===")
        all_metrics_match = all(d["all_match"] for d in recon["per_dataset"])
        no_errors = True
        for ds_anomalies in anomalies.values():
            for a in ds_anomalies:
                if a.get("severity") == "ERROR":
                    no_errors = False
                    break

        ml_ready = all_metrics_match and no_errors
        report["sections"]["J_ml_readiness"] = {
            "recommendation": "READY" if ml_ready else "BLOCKED",
            "metrics_reconciled": all_metrics_match,
            "no_critical_errors": no_errors,
            "rationale": (
                "All canonical metrics reconcile between independent SQL and semantic layer. "
                "No critical data errors detected."
            ) if ml_ready else (
                "ML training BLOCKED: Metric reconciliation or critical data quality issues detected."
            ),
        }

        return report

    finally:
        db.close()


def main():
    report = run()
    # Print compact summary
    print("\n" + "=" * 70)
    print("PRE-ML READINESS VALIDATION REPORT")
    print("=" * 70)

    # Quality summary
    for qr in report["sections"]["A_data_quality"]:
        print(f"\n--- {qr['campus_name']} {qr['academic_year']} ---")
        print(f"  Rows: analytics={qr['rows']['analytics']}, loss={qr['rows']['loss']}")
        print(f"  State: resolved={qr['state']['resolved']}, unresolved={qr['state']['unresolved']}, coverage={qr['state']['coverage_pct']}%")
        print(f"  Source: resolved={qr['source']['resolved']}, unresolved={qr['source']['unresolved']}, coverage={qr['source']['coverage_pct']}%")
        print(f"  Employee: resolved={qr['employee']['resolved']}, unresolved={qr['employee']['unresolved']}, coverage={qr['employee']['coverage_pct']}%")
        print(f"  Status: known={qr['status']['known']}, unknown={qr['status']['unknown']}")

    # Reconciliation
    print("\n--- Metric Reconciliation ---")
    for ds in report["sections"]["C_metric_reconciliation"]:
        status = "✓ PASS" if ds["all_match"] else "✗ FAIL"
        print(f"  {ds['dataset_name']}: {status}")
        for m, v in ds["metrics"].items():
            if v.get("semantic_layer") is not None:
                match_str = "✓" if v["match"] else "✗"
                print(f"    {m}: SQL={v['independent_sql']} vs Semantic={v['semantic_layer']} {match_str}")

    # Cross-dataset
    print("\n--- Cross-Dataset Additivity ---")
    cross = report["sections"]["D_cross_campus_reconciliation"]
    for year_key, year_data in cross.items():
        print(f"  {year_key}:")
        for metric, check in year_data.get("additive_check", {}).items():
            match_str = "✓" if check["match"] else "✗"
            print(f"    {metric}: Mohali={check['mohali']} + Unnao={check['unnao']} = {check['expected_sum']} vs Semantic={check['semantic_all']} {match_str}")

    # Anomalies
    print("\n--- Anomalies ---")
    for ds_name, anomaly_list in report["sections"]["anomalies"].items():
        if anomaly_list:
            print(f"  {ds_name}:")
            for a in anomaly_list:
                print(f"    [{a['severity']}] {a['category']}: {a['description']} (count={a['count']})")

    # Sample validation
    print("\n--- Sample Validation ---")
    for s in report["sections"]["H_manual_sample"]:
        print(f"  {s['dataset']}: resolved={s['summary']['resolved']}, unresolved={s['summary']['unresolved']}, review={s['summary']['review_required']}")

    # ML Readiness
    print("\n" + "=" * 70)
    j = report["sections"]["J_ml_readiness"]
    print(f"ML READINESS: {j['recommendation']}")
    print(f"  Metrics Reconciled: {j['metrics_reconciled']}")
    print(f"  No Critical Errors: {j['no_critical_errors']}")
    print(f"  {j['rationale']}")
    print("=" * 70)

    return report


if __name__ == "__main__":
    main()
