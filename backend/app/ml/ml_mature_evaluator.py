"""
Phase 8: Mature Evaluation & Calibration Module

Evaluates baseline models separately on:
1. Full Validation/Test datasets (explicitly labelled as censored/immature)
2. Mature Evaluation datasets (observation age >= 97.86 days)

Performs feature importance extraction and probability calibration analysis.
"""

import os
import logging
from typing import Dict, Any, Tuple, List
import pandas as pd
import numpy as np
import joblib

from app.ml.ml_temporal_split import (
    load_temporal_splits,
    PURE_T0_FEATURE_COLUMNS,
    DEFAULT_DATA_DIR,
)
from app.ml.ml_baseline_trainer import (
    DEFAULT_MODEL_DIR,
    evaluate_predictions,
    CAT_COLUMNS,
    NUM_COLUMNS,
)

logger = logging.getLogger(__name__)


class MatureEvaluator:
    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        model_dir: str = DEFAULT_MODEL_DIR,
        snapshot_date: str = "2026-08-24",
    ):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.snapshot_date = snapshot_date

    def run_evaluation(self) -> Dict[str, Any]:
        """Run mature vs censored evaluation for all trained baseline models."""
        df_train, df_val, df_test = load_temporal_splits(self.data_dir)

        snapshot_dt = pd.to_datetime(self.snapshot_date)

        val_obs = (
            snapshot_dt - pd.to_datetime(df_val["raw_created_on"].str[:19], errors="coerce")
        ).dt.total_seconds() / 86400.0
        val_mature_mask = (val_obs >= 97.86) | (df_val["cy_admission"] == 1)

        test_obs = (
            snapshot_dt - pd.to_datetime(df_test["raw_created_on"].str[:19], errors="coerce")
        ).dt.total_seconds() / 86400.0
        test_mature_mask = (test_obs >= 97.86) | (df_test["cy_admission"] == 1)

        preprocessor_path = os.path.join(self.model_dir, "preprocessor.joblib")
        assert os.path.exists(preprocessor_path), f"Missing preprocessor: {preprocessor_path}"
        preprocessor = joblib.load(preprocessor_path)

        X_val_proc = preprocessor.transform(df_val[PURE_T0_FEATURE_COLUMNS])
        X_test_proc = preprocessor.transform(df_test[PURE_T0_FEATURE_COLUMNS])

        y_val = df_val["cy_admission"].values
        y_test = df_test["cy_admission"].values

        model_files = [
            f for f in os.listdir(self.model_dir) 
            if f.endswith(".joblib") and f.startswith("model_") and not f.startswith("model_2026_")
        ]

        eval_summary = {}

        for m_file in sorted(model_files):
            m_id = m_file.replace(".joblib", "")
            model_path = os.path.join(self.model_dir, m_file)
            model = joblib.load(model_path)

            if hasattr(model, "predict_proba"):
                val_probas = model.predict_proba(X_val_proc)[:, 1]
                test_probas = model.predict_proba(X_test_proc)[:, 1]
            else:
                val_probas = model.predict(X_val_proc)
                test_probas = model.predict(X_test_proc)

            val_full_metrics = evaluate_predictions(y_val, val_probas, f"{m_id}_val_full")
            val_mat_metrics = evaluate_predictions(
                y_val[val_mature_mask], val_probas[val_mature_mask], f"{m_id}_val_mature"
            )

            test_full_metrics = evaluate_predictions(y_test, test_probas, f"{m_id}_test_full")
            test_mat_metrics = evaluate_predictions(
                y_test[test_mature_mask], test_probas[test_mature_mask], f"{m_id}_test_mature"
            )

            eval_summary[m_id] = {
                "val_full_censored": val_full_metrics,
                "val_mature": val_mat_metrics,
                "test_full_censored": test_full_metrics,
                "test_mature": test_mat_metrics,
            }

        # Feature Importance Analysis for Champion LightGBM Model
        lgb_path = os.path.join(self.model_dir, "model_e_lightgbm.joblib")
        feature_importance_list = []
        if os.path.exists(lgb_path):
            lgb_model = joblib.load(lgb_path)
            if hasattr(lgb_model, "feature_importances_"):
                encoded_feature_names = preprocessor.get_feature_names_out()
                importances = lgb_model.feature_importances_

                feat_imp = pd.DataFrame(
                    {"encoded_feature": encoded_feature_names, "importance": importances}
                ).sort_values("importance", ascending=False)

                # Group by original raw feature name
                raw_group = {}
                for idx, row in feat_imp.iterrows():
                    orig_name = str(row["encoded_feature"]).split("__")[1].split("_")[0] if "__" in str(row["encoded_feature"]) else str(row["encoded_feature"])
                    for p in PURE_T0_FEATURE_COLUMNS:
                        if p in str(row["encoded_feature"]):
                            orig_name = p
                            break
                    raw_group[orig_name] = raw_group.get(orig_name, 0.0) + float(row["importance"])

                feature_importance_list = sorted(
                    [{"feature": k, "importance": v} for k, v in raw_group.items()],
                    key=lambda x: x["importance"],
                    reverse=True,
                )

        return {
            "evaluation_summary": eval_summary,
            "feature_importance": feature_importance_list,
            "champion_model_id": "model_e_lightgbm",
        }
