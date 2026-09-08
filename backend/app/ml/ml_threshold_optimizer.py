"""
Phase 9: Threshold Optimization & Operational Strategy Module

Performs comprehensive decision threshold scanning (0.01 to 0.50) and Top-K decile evaluation
on the Mature Validation Dataset (observation_age >= 97.86 days).
"""

import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np

from app.ml.ml_temporal_split import load_temporal_splits, PURE_T0_FEATURE_COLUMNS, DEFAULT_DATA_DIR
from app.ml.ml_baseline_trainer import DEFAULT_MODEL_DIR
import joblib

logger = logging.getLogger(__name__)

THRESHOLD_GRID = [0.01, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
TOP_K_GRID = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


class ThresholdOptimizer:
    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        model_dir: str = DEFAULT_MODEL_DIR,
        snapshot_date: str = "2026-08-24",
    ):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.snapshot_date = snapshot_date

    def run_threshold_optimization(self) -> Dict[str, Any]:
        """Evaluate probability thresholds and Top-K strategies on mature validation dataset."""
        df_train, df_val, df_test = load_temporal_splits(self.data_dir)

        snapshot_dt = pd.to_datetime(self.snapshot_date)
        val_obs = (
            snapshot_dt - pd.to_datetime(df_val["raw_created_on"].str[:19], errors="coerce")
        ).dt.total_seconds() / 86400.0
        val_mature_mask = (val_obs >= 97.86) | (df_val["cy_admission"] == 1)

        df_val_mat = df_val[val_mature_mask].copy()

        prep_path = f"{self.model_dir}/preprocessor.joblib"
        model_path = f"{self.model_dir}/model_e_lightgbm.joblib"

        prep = joblib.load(prep_path)
        model = joblib.load(model_path)

        X_val_proc = prep.transform(df_val_mat[PURE_T0_FEATURE_COLUMNS])
        y_val_mat = df_val_mat["cy_admission"].values
        probas = model.predict_proba(X_val_proc)[:, 1]

        total_leads = len(y_val_mat)
        total_admissions = int(y_val_mat.sum())
        base_rate = float(y_val_mat.mean())

        # 1. Threshold Scan Results
        threshold_results = []
        best_f1 = -1.0
        optimal_threshold = 0.05

        for t in THRESHOLD_GRID:
            preds = (probas >= t).astype(int)
            selected = int(preds.sum())
            captured = int(y_val_mat[preds == 1].sum())

            prec = float(captured / selected) if selected > 0 else 0.0
            rec = float(captured / total_admissions) if total_admissions > 0 else 0.0
            f1 = float((2 * prec * rec) / (prec + rec)) if (prec + rec) > 0 else 0.0
            pred_pos_rate = float((selected / total_leads) * 100)
            pct_captured = float((captured / total_admissions) * 100)
            lift = float(prec / base_rate) if base_rate > 0 else 1.0

            if f1 > best_f1:
                best_f1 = f1
                optimal_threshold = t

            threshold_results.append(
                {
                    "threshold": t,
                    "leads_selected": selected,
                    "predicted_positive_rate_pct": pred_pos_rate,
                    "admissions_captured": captured,
                    "pct_admissions_captured": pct_captured,
                    "precision": prec,
                    "recall": rec,
                    "f1_score": f1,
                    "lift": lift,
                }
            )

        # 2. Operational Top-K Results
        top_k_results = []
        for k in TOP_K_GRID:
            n_top = max(1, int(total_leads * k))
            top_idx = np.argsort(probas)[::-1][:n_top]
            top_captured = int(y_val_mat[top_idx].sum())

            top_prec = float(top_captured / n_top)
            top_rec = float(top_captured / total_admissions)
            top_lift = float(top_prec / base_rate) if base_rate > 0 else 1.0
            cutoff_prob = float(probas[top_idx[-1]])

            top_k_results.append(
                {
                    "top_k_pct": float(k * 100),
                    "lead_count": n_top,
                    "cutoff_probability": cutoff_prob,
                    "admissions_captured": top_captured,
                    "pct_admissions_captured": float(top_rec * 100),
                    "precision": top_prec,
                    "recall": top_rec,
                    "lift": top_lift,
                }
            )

        return {
            "total_mature_leads": total_leads,
            "total_mature_admissions": total_admissions,
            "base_admission_rate": base_rate,
            "optimal_f1_threshold": optimal_threshold,
            "best_f1_score": best_f1,
            "threshold_scan": threshold_results,
            "top_k_strategies": top_k_results,
        }
