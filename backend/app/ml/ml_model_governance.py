"""
Phase 11.6: ML Model Governance & Promotion Service
Enforces quality thresholds, candidate validation, and comparison against active production model before promotion.
"""

import os
import json
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Configurable governance quality thresholds
DEFAULT_GOVERNANCE_THRESHOLDS = {
    "min_roc_auc": 0.75,
    "min_pr_auc": 0.40,
    "max_brier_score": 0.15,
    "min_top10_lift": 1.50,
}


class ModelGovernance:
    def __init__(self, thresholds: Dict[str, float] = None):
        self.thresholds = thresholds or DEFAULT_GOVERNANCE_THRESHOLDS

    def validate_candidate_quality(self, candidate_metrics: Dict[str, Any]) -> Tuple[bool, list[str]]:
        """Validate if candidate model meets absolute quality thresholds."""
        reasons = []

        roc_auc = candidate_metrics.get("roc_auc", 0.0)
        if roc_auc < self.thresholds["min_roc_auc"]:
            reasons.append(f"ROC-AUC {roc_auc:.4f} < min threshold {self.thresholds['min_roc_auc']}")

        pr_auc = candidate_metrics.get("pr_auc", 0.0)
        if pr_auc < self.thresholds["min_pr_auc"]:
            reasons.append(f"PR-AUC {pr_auc:.4f} < min threshold {self.thresholds['min_pr_auc']}")

        brier = candidate_metrics.get("brier_score", 1.0)
        if brier > self.thresholds["max_brier_score"]:
            reasons.append(f"Brier score {brier:.4f} > max threshold {self.thresholds['max_brier_score']}")

        lift = candidate_metrics.get("top10_lift", 0.0)
        if lift < self.thresholds["min_top10_lift"]:
            reasons.append(f"Top 10% lift {lift:.2f}x < min threshold {self.thresholds['min_top10_lift']}x")

        passed = len(reasons) == 0
        return passed, reasons

    def compare_and_evaluate_promotion(
        self, candidate_metrics: Dict[str, Any], production_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compares candidate model against production baseline and determines promotion."""
        valid, quality_reasons = self.validate_candidate_quality(candidate_metrics)
        if not valid:
            return {
                "promoted": False,
                "decision": "REJECTED_QUALITY_THESHOLD_FAILED",
                "reasons": quality_reasons,
                "candidate_metrics": candidate_metrics,
                "production_metrics": production_metrics,
            }

        cand_auc = candidate_metrics.get("roc_auc", 0.0)
        prod_auc = production_metrics.get("roc_auc", 0.0)

        cand_brier = candidate_metrics.get("brier_score", 1.0)
        prod_brier = production_metrics.get("brier_score", 1.0)

        improvements = []
        regressions = []

        if cand_auc >= prod_auc - 0.01:
            improvements.append(f"ROC-AUC ({cand_auc:.4f} vs {prod_auc:.4f}) meets/exceeds baseline")
        else:
            regressions.append(f"ROC-AUC ({cand_auc:.4f} vs {prod_auc:.4f}) dropped significantly")

        if cand_brier <= prod_brier + 0.01:
            improvements.append(f"Brier score ({cand_brier:.4f} vs {prod_brier:.4f}) meets/exceeds baseline")
        else:
            regressions.append(f"Brier score ({cand_brier:.4f} vs {prod_brier:.4f}) degraded")

        promoted = len(regressions) == 0
        decision = "PROMOTED_TO_PRODUCTION" if promoted else "REJECTED_BASELINE_REGRESSION"

        return {
            "promoted": promoted,
            "decision": decision,
            "improvements": improvements,
            "regressions": regressions,
            "candidate_metrics": candidate_metrics,
            "production_metrics": production_metrics,
        }
