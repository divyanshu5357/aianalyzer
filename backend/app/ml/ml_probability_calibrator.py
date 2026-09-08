"""
Phase 9: Probability Calibration Module

Fits and compares probability calibration strategies (Raw LightGBM, Sigmoid/Platt Scaling, Isotonic Regression).
Persists calibrated model artifacts to backend/app/ml/models/model_e_lightgbm_calibrated.joblib.
"""

import os
import logging
from typing import Dict, Any, Tuple, List
import pandas as pd
import numpy as np
import joblib

from sklearn.calibration import CalibratedClassifierCV, FrozenEstimator
from sklearn.metrics import brier_score_loss, average_precision_score, roc_auc_score

from app.ml.ml_temporal_split import load_temporal_splits, PURE_T0_FEATURE_COLUMNS, DEFAULT_DATA_DIR
from app.ml.ml_baseline_trainer import DEFAULT_MODEL_DIR

logger = logging.getLogger(__name__)


class ProbabilityCalibrator:
    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        model_dir: str = DEFAULT_MODEL_DIR,
        snapshot_date: str = "2026-08-24",
    ):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.snapshot_date = snapshot_date

    def train_and_evaluate_calibrators(self) -> Dict[str, Any]:
        """Fit Sigmoid and Isotonic calibrators and return comparative evaluation metrics."""
        df_train, df_val, df_test = load_temporal_splits(self.data_dir)

        prep_path = os.path.join(self.model_dir, "preprocessor.joblib")
        lgb_path = os.path.join(self.model_dir, "model_e_lightgbm.joblib")

        prep = joblib.load(prep_path)
        lgb_model = joblib.load(lgb_path)

        X_train_proc = prep.transform(df_train[PURE_T0_FEATURE_COLUMNS])
        y_train = df_train["cy_admission"].values

        snapshot_dt = pd.to_datetime(self.snapshot_date)
        val_obs = (
            snapshot_dt - pd.to_datetime(df_val["raw_created_on"].str[:19], errors="coerce")
        ).dt.total_seconds() / 86400.0
        val_mature_mask = (val_obs >= 97.86) | (df_val["cy_admission"] == 1)

        df_val_mat = df_val[val_mature_mask].copy()
        X_val_proc = prep.transform(df_val_mat[PURE_T0_FEATURE_COLUMNS])
        y_val_mat = df_val_mat["cy_admission"].values

        # 1. Fit Calibrators using FrozenEstimator (scikit-learn >=1.6 compliant)
        frozen_lgb = FrozenEstimator(lgb_model)

        logger.info("Fitting Sigmoid calibrator...")
        sigmoid_cal = CalibratedClassifierCV(estimator=frozen_lgb, method="sigmoid")
        sigmoid_cal.fit(X_train_proc, y_train)

        logger.info("Fitting Isotonic calibrator...")
        isotonic_cal = CalibratedClassifierCV(estimator=frozen_lgb, method="isotonic")
        isotonic_cal.fit(X_train_proc, y_train)

        # 2. Persist Champion Isotonic Calibrator
        cal_path = os.path.join(self.model_dir, "model_e_lightgbm_calibrated.joblib")
        joblib.dump(isotonic_cal, cal_path)

        # 3. Predict & Compute Metrics
        p_raw = lgb_model.predict_proba(X_val_proc)[:, 1]
        p_sig = sigmoid_cal.predict_proba(X_val_proc)[:, 1]
        p_iso = isotonic_cal.predict_proba(X_val_proc)[:, 1]

        def get_cal_metrics(probas: np.ndarray, name: str) -> Dict[str, float]:
            return {
                "name": name,
                "brier_score": float(brier_score_loss(y_val_mat, probas)),
                "pr_auc": float(average_precision_score(y_val_mat, probas)),
                "roc_auc": float(roc_auc_score(y_val_mat, probas)),
                "mean_predicted_prob": float(probas.mean()),
                "observed_admission_rate": float(y_val_mat.mean()),
            }

        # 4. Decile Reliability Bucket Analysis (Isotonic)
        decile_buckets = []
        df_buckets = pd.DataFrame({"p_iso": p_iso, "y": y_val_mat})
        df_buckets["decile"] = pd.qcut(df_buckets["p_iso"], q=10, duplicates="drop")

        for d_cat, group in df_buckets.groupby("decile", observed=True):
            decile_buckets.append(
                {
                    "prob_min": float(group["p_iso"].min()),
                    "prob_max": float(group["p_iso"].max()),
                    "mean_predicted_prob": float(group["p_iso"].mean()),
                    "observed_admission_rate": float(group["y"].mean()),
                    "sample_count": len(group),
                }
            )

        return {
            "raw_lightgbm": get_cal_metrics(p_raw, "Raw LightGBM"),
            "sigmoid_calibrated": get_cal_metrics(p_sig, "Sigmoid Calibrated"),
            "isotonic_calibrated": get_cal_metrics(p_iso, "Isotonic Calibrated"),
            "selected_calibrator": "Isotonic Regression",
            "calibrated_model_path": cal_path,
            "decile_reliability_buckets": decile_buckets,
        }
