"""
Phase 9.5: 2026 Inquiry Population Isolation & Model Revalidation Module

Retrains LightGBM exclusively on the 2026 CRM Inquiry Stream (academic_year == 2026),
fits Isotonic probability calibration, evaluates on mature 2026 validation data,
and compares performance against the pooled 2025+2026 model baseline.
"""

import os
import logging
from typing import Dict, Any, Tuple, List
import pandas as pd
import numpy as np
import joblib

from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV, FrozenEstimator
from sklearn.metrics import brier_score_loss, average_precision_score, roc_auc_score
from lightgbm import LGBMClassifier

from app.ml.ml_temporal_split import (
    load_temporal_splits,
    PURE_T0_FEATURE_COLUMNS,
    DEFAULT_DATA_DIR,
)
from app.ml.ml_baseline_trainer import DEFAULT_MODEL_DIR, CAT_COLUMNS, NUM_COLUMNS

logger = logging.getLogger(__name__)


class Model2026Revalidator:
    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        model_dir: str = DEFAULT_MODEL_DIR,
        snapshot_date: str = "2026-08-24",
    ):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.snapshot_date = snapshot_date

    def train_and_revalidate_2026_model(self) -> Dict[str, Any]:
        """Re-train LightGBM on 2026-only training data, calibrate, and compare against pooled model."""
        df_train, df_val, df_test = load_temporal_splits(self.data_dir)

        # 1. Strict 2026 Inquiry Stream Isolation
        df_train_2026 = df_train[df_train["academic_year"] == 2026].copy()
        logger.info(
            f"Filtered training set from {len(df_train)} (pooled) to {len(df_train_2026)} (2026-only)."
        )

        # 2. Build Preprocessor for 2026-only data
        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "cat",
                    OneHotEncoder(handle_unknown="ignore", min_frequency=50, sparse_output=True),
                    CAT_COLUMNS,
                ),
                ("num", StandardScaler(), NUM_COLUMNS),
            ]
        )

        X_train_proc = preprocessor.fit_transform(df_train_2026[PURE_T0_FEATURE_COLUMNS])
        y_train_2026 = df_train_2026["cy_admission"].values

        # Save 2026 Preprocessor
        prep_2026_path = os.path.join(self.model_dir, "preprocessor_2026.joblib")
        joblib.dump(preprocessor, prep_2026_path)

        # 3. Fit LightGBM Model on 2026-only data
        lgb_2026 = LGBMClassifier(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=6,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        lgb_2026.fit(X_train_proc, y_train_2026)

        model_2026_path = os.path.join(self.model_dir, "model_2026_lightgbm.joblib")
        joblib.dump(lgb_2026, model_2026_path)

        # 4. Fit Calibrator on 2026 Model
        frozen_lgb_2026 = FrozenEstimator(lgb_2026)
        iso_cal_2026 = CalibratedClassifierCV(estimator=frozen_lgb_2026, method="isotonic")
        iso_cal_2026.fit(X_train_proc, y_train_2026)

        cal_2026_path = os.path.join(self.model_dir, "model_2026_lightgbm_calibrated.joblib")
        joblib.dump(iso_cal_2026, cal_2026_path)

        # 5. Evaluate on Mature 2026 Validation Dataset
        snapshot_dt = pd.to_datetime(self.snapshot_date)
        val_obs = (
            snapshot_dt - pd.to_datetime(df_val["raw_created_on"].str[:19], errors="coerce")
        ).dt.total_seconds() / 86400.0
        val_mature_mask = (val_obs >= 97.86) | (df_val["cy_admission"] == 1)

        df_val_mat = df_val[val_mature_mask].copy()
        X_val_proc_2026 = preprocessor.transform(df_val_mat[PURE_T0_FEATURE_COLUMNS])
        y_val_mat = df_val_mat["cy_admission"].values

        # Predictions from 2026-only model
        p_raw_2026 = lgb_2026.predict_proba(X_val_proc_2026)[:, 1]
        p_iso_2026 = iso_cal_2026.predict_proba(X_val_proc_2026)[:, 1]

        # Evaluate Pooled Champion for Direct Comparison
        prep_pooled = joblib.load(os.path.join(self.model_dir, "preprocessor.joblib"))
        lgb_pooled = joblib.load(os.path.join(self.model_dir, "model_e_lightgbm.joblib"))
        cal_pooled = joblib.load(os.path.join(self.model_dir, "model_e_lightgbm_calibrated.joblib"))

        X_val_proc_pooled = prep_pooled.transform(df_val_mat[PURE_T0_FEATURE_COLUMNS])
        p_iso_pooled = cal_pooled.predict_proba(X_val_proc_pooled)[:, 1]

        # Compute Metrics
        metrics_2026_only = {
            "pr_auc": float(average_precision_score(y_val_mat, p_iso_2026)),
            "roc_auc": float(roc_auc_score(y_val_mat, p_iso_2026)),
            "brier_score": float(brier_score_loss(y_val_mat, p_iso_2026)),
        }

        metrics_pooled = {
            "pr_auc": float(average_precision_score(y_val_mat, p_iso_pooled)),
            "roc_auc": float(roc_auc_score(y_val_mat, p_iso_pooled)),
            "brier_score": float(brier_score_loss(y_val_mat, p_iso_pooled)),
        }

        # 6. Threshold Scan (0.01 to 0.50) for 2026 Model
        threshold_scan = []
        base_rate = y_val_mat.mean()
        total_admissions = int(y_val_mat.sum())

        for t in [0.01, 0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.50]:
            preds = (p_iso_2026 >= t).astype(int)
            tp = int(((preds == 1) & (y_val_mat == 1)).sum())
            fp = int(((preds == 1) & (y_val_mat == 0)).sum())
            fn = int(((preds == 0) & (y_val_mat == 1)).sum())

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            lift = (tp / (tp + fp)) / base_rate if (tp + fp) > 0 else 0.0

            threshold_scan.append(
                {
                    "threshold": t,
                    "leads_selected": int(preds.sum()),
                    "admissions_captured": tp,
                    "pct_admissions_captured": float(tp / total_admissions * 100.0) if total_admissions else 0.0,
                    "precision": float(precision * 100.0),
                    "recall": float(recall * 100.0),
                    "f1_score": float(f1),
                    "operational_lift": float(lift),
                }
            )

        # 7. Top-K Capacity Decile Strategies for 2026 Model
        top_k_strategies = []
        n_val = len(df_val_mat)
        for pct in [5, 10, 15, 20, 25, 30]:
            k = int(n_val * (pct / 100.0))
            idx_top = np.argsort(p_iso_2026)[::-1][:k]

            tp_k = int(y_val_mat[idx_top].sum())
            prec_k = tp_k / k if k > 0 else 0.0
            rec_k = tp_k / total_admissions if total_admissions > 0 else 0.0
            lift_k = prec_k / base_rate if base_rate > 0 else 0.0

            top_k_strategies.append(
                {
                    "top_pct": pct,
                    "lead_volume": k,
                    "admissions_captured": tp_k,
                    "pct_admissions_captured": float(rec_k * 100.0),
                    "precision": float(prec_k * 100.0),
                    "recall": float(rec_k * 100.0),
                    "operational_lift": float(lift_k),
                }
            )

        # 8. Feature Importances
        feature_names = preprocessor.get_feature_names_out()
        importances = lgb_2026.feature_importances_
        fi_list = sorted(
            zip(feature_names, importances), key=lambda x: x[1], reverse=True
        )[:10]
        top_features = [{"feature": f, "importance": int(imp)} for f, imp in fi_list]

        return {
            "train_record_count_2026": len(df_train_2026),
            "mature_validation_count": n_val,
            "metrics_2026_only": metrics_2026_only,
            "metrics_pooled_baseline": metrics_pooled,
            "threshold_scan_2026": threshold_scan,
            "top_k_strategies_2026": top_k_strategies,
            "top_features_2026": top_features,
            "model_2026_path": cal_2026_path,
        }
