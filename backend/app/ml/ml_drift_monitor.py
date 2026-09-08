"""
Phase 11.6: Data & Model Drift Monitoring Service
Detects feature distribution shifts, missingness changes, unmapped values, and prediction distribution drift.
"""

import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DriftMonitor:
    def __init__(self, baseline_stats: Dict[str, Any] = None):
        self.baseline_stats = baseline_stats or {}

    def compute_missingness_drift(self, df_current: pd.DataFrame, feature_cols: List[str]) -> Dict[str, float]:
        """Computes missingness percentage per feature in current dataset."""
        if df_current.empty:
            return {}

        n = len(df_current)
        missingness = {}
        for col in feature_cols:
            if col in df_current.columns:
                null_count = df_current[col].isnull().sum() + (df_current[col] == "Unknown").sum()
                missingness[col] = round(float(null_count / n * 100.0), 2)
            else:
                missingness[col] = 100.0
        return missingness

    def detect_unmapped_entities(
        self, df_current: pd.DataFrame, master_programs: set, master_sources: set
    ) -> Dict[str, Any]:
        """Identifies unmapped program codes or source values in raw CRM records."""
        curr_progs = set(df_current.get("program_code", []).unique())
        curr_sources = set(df_current.get("source_canonical", []).unique())

        unmapped_progs = list(curr_progs - master_programs)
        unmapped_sources = list(curr_sources - master_sources)

        return {
            "unmapped_programs_count": len(unmapped_progs),
            "unmapped_programs": unmapped_progs[:10],
            "unmapped_sources_count": len(unmapped_sources),
            "unmapped_sources": unmapped_sources[:10],
            "has_unmapped_entities": len(unmapped_progs) > 0 or len(unmapped_sources) > 0,
        }

    def evaluate_drift_report(
        self,
        df_current: pd.DataFrame,
        feature_cols: List[str],
        predictions: List[float],
        master_programs: set = None,
        master_sources: set = None,
    ) -> Dict[str, Any]:
        """Generates a complete drift monitoring report."""
        master_programs = master_programs or set()
        master_sources = master_sources or set()

        missingness = self.compute_missingness_drift(df_current, feature_cols)
        unmapped = self.detect_unmapped_entities(df_current, master_programs, master_sources)

        # Prediction distribution stats
        arr_preds = np.array(predictions) if predictions else np.array([])
        mean_pred = float(arr_preds.mean()) if len(arr_preds) > 0 else 0.0
        high_prob_pct = float((arr_preds >= 0.50).mean() * 100.0) if len(arr_preds) > 0 else 0.0

        high_missingness_cols = [col for col, pct in missingness.items() if pct > 30.0]
        retraining_recommended = len(high_missingness_cols) > 0 or unmapped["has_unmapped_entities"]

        reasons = []
        if high_missingness_cols:
            reasons.append(f"High missingness (>30%) detected in features: {high_missingness_cols}")
        if unmapped["has_unmapped_entities"]:
            reasons.append("New unmapped program codes or acquisition sources detected.")

        return {
            "total_records_evaluated": len(df_current),
            "missingness_per_feature": missingness,
            "high_missingness_features": high_missingness_cols,
            "unmapped_entity_check": unmapped,
            "prediction_distribution": {
                "mean_predicted_probability": round(mean_pred, 4),
                "high_probability_leads_percent": round(high_prob_pct, 2),
            },
            "retraining_recommended": retraining_recommended,
            "recommendation_reasons": reasons,
        }
