"""
Phase 8: Baseline ML Model Training Module

Trains baseline machine learning models on the Phase 7 temporal dataset:
- Model A: Dummy Majority Baseline
- Model B: Dummy Stratified Baseline
- Model C: Logistic Regression (Unweighted & Weighted)
- Model D: Random Forest Baseline
- Model E: LightGBM Gradient Boosting (Champion Baseline)

Persists trained model artifacts and preprocessing pipelines to backend/app/ml/models/.
"""

import os
import logging
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np
import joblib

from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from lightgbm import LGBMClassifier
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
    brier_score_loss,
    confusion_matrix,
)

from app.ml.ml_temporal_split import (
    load_temporal_splits,
    PURE_T0_FEATURE_COLUMNS,
    DEFAULT_DATA_DIR,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

CAT_COLUMNS = [
    "campus_name",
    "source_canonical",
    "state_canonical",
    "state_code",
    "zone",
    "owner_canonical",
    "team",
]
NUM_COLUMNS = ["academic_year", "created_month", "created_dayofweek", "created_hour"]


def evaluate_predictions(
    y_true: np.ndarray, probas: np.ndarray, name: str
) -> Dict[str, Any]:
    """Compute comprehensive evaluation metrics for a model's prediction probabilities."""
    preds = (probas >= 0.5).astype(int)

    has_multiclass = len(np.unique(y_true)) > 1

    pr_auc = float(average_precision_score(y_true, probas)) if has_multiclass else 0.0
    roc_auc = float(roc_auc_score(y_true, probas)) if has_multiclass else 0.5
    prec = float(precision_score(y_true, preds, zero_division=0))
    rec = float(recall_score(y_true, preds, zero_division=0))
    f1 = float(f1_score(y_true, preds, zero_division=0))
    brier = float(brier_score_loss(y_true, probas))

    cm = confusion_matrix(y_true, preds).tolist() if has_multiclass else [[0, 0], [0, 0]]

    # Precision@Top-10% and Lift
    top10_n = max(1, int(len(probas) * 0.10))
    top10_idx = np.argsort(probas)[::-1][:top10_n]
    top10_prec = float(y_true[top10_idx].mean())
    base_rate = float(y_true.mean())
    lift10 = float(top10_prec / base_rate) if base_rate > 0 else 1.0

    return {
        "model_name": name,
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "brier_score": brier,
        "confusion_matrix": cm,
        "top10_precision": top10_prec,
        "top10_lift": lift10,
        "base_rate": base_rate,
    }


class BaselineTrainer:
    def __init__(self, data_dir: str = DEFAULT_DATA_DIR, model_dir: str = DEFAULT_MODEL_DIR):
        self.data_dir = data_dir
        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)

    def train_all_baselines(self) -> Dict[str, Any]:
        """Train baseline models and return quantitative evaluation results."""
        df_train, df_val, df_test = load_temporal_splits(self.data_dir)

        X_train = df_train[PURE_T0_FEATURE_COLUMNS]
        y_train = df_train["cy_admission"].values

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

        logger.info("Fitting feature preprocessor...")
        X_train_proc = preprocessor.fit_transform(X_train)

        # Save preprocessor artifact
        preprocessor_path = os.path.join(self.model_dir, "preprocessor.joblib")
        joblib.dump(preprocessor, preprocessor_path)

        models = {
            "model_a_dummy_prior": DummyClassifier(strategy="prior"),
            "model_b_dummy_stratified": DummyClassifier(strategy="stratified", random_state=42),
            "model_c_logistic_regression": LogisticRegression(max_iter=300, random_state=42, solver="lbfgs"),
            "model_c_logistic_weighted": LogisticRegression(
                max_iter=300, class_weight="balanced", random_state=42, solver="lbfgs"
            ),
            "model_d_random_forest": RandomForestClassifier(
                n_estimators=50, max_depth=10, random_state=42, n_jobs=-1
            ),
            "model_e_lightgbm": LGBMClassifier(
                n_estimators=100, max_depth=6, learning_rate=0.1, random_state=42, n_jobs=-1, verbose=-1
            ),
            "model_e_lightgbm_weighted": LGBMClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            ),
        }

        results = {}

        for m_id, model in models.items():
            logger.info(f"Training baseline model: {m_id}")
            model.fit(X_train_proc, y_train)

            # Persist model artifact
            model_path = os.path.join(self.model_dir, f"{m_id}.joblib")
            joblib.dump(model, model_path)

            results[m_id] = {
                "model_id": m_id,
                "model_obj": model,
                "model_path": model_path,
            }

        return results
