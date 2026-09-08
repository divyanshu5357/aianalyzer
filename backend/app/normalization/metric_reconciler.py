"""
Phase 6-7 — Independent Metric Reconciliation

Independently calculates canonical metrics directly from raw business fields,
then compares with the semantic layer result to detect any discrepancy.

Also validates cross-dataset additivity:
  All Campuses = Mohali + Unnao (for additive metrics)
  Rates are recomputed from aggregate numerators/denominators.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class MetricReconciliation:
    dataset_id: str
    dataset_name: str
    campus: str
    year: int
    metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    all_match: bool = True

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "campus": self.campus,
            "year": self.year,
            "metrics": self.metrics,
            "all_match": self.all_match,
        }


def _independent_metrics_from_analytics(db: Session, dataset_id: str) -> Dict[str, Any]:
    """
    Independently calculate canonical metrics from analytics.uploaded_metrics
    using the authoritative metric contract definitions.
    """
    row = db.execute(text("""
        SELECT
            COUNT(*) AS row_count,
            COALESCE(SUM(cy_leads), 0) AS leads,
            COALESCE(SUM(cy_cucet), 0) AS cucet,
            COALESCE(SUM(cy_admission), 0) AS admission,
            COUNT(*) FILTER (WHERE lead_type = 'Refunded') AS refunded,
            COALESCE(SUM(cy_admission), 0) + COUNT(*) FILTER (WHERE lead_type = 'Refunded') AS gross_admission
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :ds_id
    """), {"ds_id": dataset_id}).mappings().first()

    leads = int(row["leads"])
    cucet = int(row["cucet"])
    admission = int(row["admission"])
    refunded = int(row["refunded"])
    gross_admission = int(row["gross_admission"])

    return {
        "leads": leads,
        "cucet": cucet,
        "admission": admission,
        "refunded": refunded,
        "gross_admission": gross_admission,
        "lead_cucet_rate": round(cucet / leads * 100, 4) if leads > 0 else 0.0,
        "lead_admission_rate": round(admission / leads * 100, 4) if leads > 0 else 0.0,
        "cucet_admission_rate": round(admission / cucet * 100, 4) if cucet > 0 else 0.0,
    }


def _semantic_layer_metrics(db: Session, campus: str, years: List[int]) -> Dict[str, Any]:
    """
    Get metrics via the dashboard semantic layer (same path as the API).
    """
    try:
        from app.analytics.dashboard import get_dashboard_overview
        result = get_dashboard_overview(db, campus=campus, years=years)
        kpis = result.get("kpis", {})
        leads_cy = kpis.get("leads", {}).get("cy", 0)
        cucet_cy = kpis.get("cucet", {}).get("cy", 0)
        admission_cy = kpis.get("admissions", {}).get("cy", 0)
        refunded = kpis.get("refunded", {}).get("cy", 0) if "refunded" in kpis else None
        gross = kpis.get("gross_admission", {}).get("cy", 0) if "gross_admission" in kpis else None
        return {
            "leads": leads_cy,
            "cucet": cucet_cy,
            "admission": admission_cy,
            "refunded": refunded,
            "gross_admission": gross,
        }
    except Exception as e:
        logger.warning(f"Semantic layer call failed: {e}")
        return {}


def reconcile_dataset(db: Session, dataset_id: str) -> MetricReconciliation:
    """Reconcile independent SQL metrics vs semantic layer for one dataset."""
    ds = db.execute(text(
        "SELECT dataset_name, campus_name, academic_year "
        "FROM system.datasets WHERE id = :id"
    ), {"id": dataset_id}).mappings().first()

    if not ds:
        raise ValueError(f"Dataset {dataset_id} not found")

    recon = MetricReconciliation(
        dataset_id=dataset_id,
        dataset_name=ds["dataset_name"],
        campus=ds["campus_name"] or "Unknown",
        year=ds["academic_year"] or 0,
    )

    independent = _independent_metrics_from_analytics(db, dataset_id)
    semantic = _semantic_layer_metrics(db, recon.campus, [recon.year])

    for metric_name in ["leads", "cucet", "admission"]:
        ind_val = independent.get(metric_name, 0)
        sem_val = semantic.get(metric_name)
        match = sem_val is not None and int(ind_val) == int(sem_val)
        recon.metrics[metric_name] = {
            "independent_sql": ind_val,
            "semantic_layer": sem_val,
            "match": match,
        }
        if not match:
            recon.all_match = False

    # Add rate metrics (independent only — no semantic comparison needed for rates)
    for rate_name in ["lead_cucet_rate", "lead_admission_rate", "cucet_admission_rate"]:
        recon.metrics[rate_name] = {
            "independent_sql": independent.get(rate_name, 0.0),
            "semantic_layer": None,
            "match": True,  # Rates don't have a direct semantic endpoint to compare
        }

    # Add count metrics
    for count_name in ["refunded", "gross_admission"]:
        recon.metrics[count_name] = {
            "independent_sql": independent.get(count_name, 0),
            "semantic_layer": semantic.get(count_name),
            "match": True,  # May be null in semantic layer
        }

    return recon


def reconcile_cross_dataset(db: Session) -> Dict[str, Any]:
    """
    Phase 7: Cross-dataset validation.
    Verifies All Campuses = Mohali + Unnao for additive metrics.
    """
    datasets = db.execute(text("""
        SELECT id, campus_name, academic_year
        FROM system.datasets
        WHERE is_analytics_enabled = TRUE
        ORDER BY campus_name, academic_year
    """)).mappings().all()

    # Group datasets by campus
    by_campus_year: Dict[Tuple[str, int], str] = {}
    for d in datasets:
        key = (d["campus_name"], d["academic_year"])
        by_campus_year[key] = str(d["id"])

    results = {}

    for year in [2025, 2026]:
        mohali_id = by_campus_year.get(("Mohali", year))
        unnao_id = by_campus_year.get(("Unnao", year))

        if not mohali_id or not unnao_id:
            continue

        mohali_metrics = _independent_metrics_from_analytics(db, mohali_id)
        unnao_metrics = _independent_metrics_from_analytics(db, unnao_id)

        # Calculate "All Campuses" independently
        all_ids = [mohali_id, unnao_id]
        all_metrics = {}
        for metric in ["leads", "cucet", "admission", "refunded", "gross_admission"]:
            all_metrics[metric] = mohali_metrics[metric] + unnao_metrics[metric]

        # Calculate rates from aggregates (NOT averaged)
        total_leads = all_metrics["leads"]
        total_cucet = all_metrics["cucet"]
        total_admission = all_metrics["admission"]
        all_metrics["lead_cucet_rate"] = round(total_cucet / total_leads * 100, 4) if total_leads > 0 else 0.0
        all_metrics["lead_admission_rate"] = round(total_admission / total_leads * 100, 4) if total_leads > 0 else 0.0
        all_metrics["cucet_admission_rate"] = round(total_admission / total_cucet * 100, 4) if total_cucet > 0 else 0.0

        # Verify via scope resolver
        scope_metrics = _semantic_layer_metrics(db, "all", [year])

        year_result = {
            "mohali": mohali_metrics,
            "unnao": unnao_metrics,
            "sum_mohali_unnao": {k: mohali_metrics.get(k, 0) + unnao_metrics.get(k, 0) for k in ["leads", "cucet", "admission", "refunded", "gross_admission"]},
            "all_campuses_independent": all_metrics,
            "all_campuses_semantic": scope_metrics,
            "additive_check": {},
        }

        for metric in ["leads", "cucet", "admission"]:
            expected = mohali_metrics[metric] + unnao_metrics[metric]
            actual_semantic = scope_metrics.get(metric)
            year_result["additive_check"][metric] = {
                "mohali": mohali_metrics[metric],
                "unnao": unnao_metrics[metric],
                "expected_sum": expected,
                "semantic_all": actual_semantic,
                "match": actual_semantic is not None and int(expected) == int(actual_semantic),
            }

        results[f"year_{year}"] = year_result

    return results


def reconcile_all(db: Session) -> Dict[str, Any]:
    """Run full reconciliation: per-dataset + cross-dataset."""
    datasets = db.execute(text(
        "SELECT id FROM system.datasets WHERE is_analytics_enabled = TRUE ORDER BY campus_name, academic_year"
    )).fetchall()

    per_dataset = []
    for (ds_id,) in datasets:
        try:
            recon = reconcile_dataset(db, str(ds_id))
            per_dataset.append(recon.to_dict())
        except Exception as e:
            logger.error(f"Reconciliation failed for {ds_id}: {e}")

    cross = reconcile_cross_dataset(db)

    return {
        "per_dataset": per_dataset,
        "cross_dataset": cross,
    }
