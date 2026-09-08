"""
Phase 11.5: Canonical ML Model Retraining & Calibration Module
Retrains machine learning baseline models using the PostgreSQL canonical feature pipeline.
Persists version v2 model artifacts and metadata to backend/app/ml/models/v2/.
"""

import os
import json
import logging
from typing import Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np
import joblib

from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
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
from sqlalchemy.orm import Session

from app.ml.ml_canonical_feature_pipeline import (
    CANONICAL_FEATURE_COLUMNS,
    TARGET_COLUMN,
)
from app.ml.ml_canonical_temporal_split import load_canonical_temporal_splits

logger = logging.getLogger(__name__)

V2_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "v2")

CAT_COLUMNS_V2 = [
    "campus_name",
    "program_code",
    "source_canonical",
    "lead_type",
    "state_canonical",
    "state_code",
    "zone",
    "owner_canonical",
    "team",
]
NUM_COLUMNS_V2 = ["academic_year", "created_month", "created_dayofweek", "created_hour", "cy_cucet"]


def evaluate_predictions_v2(y_true: np.ndarray, probas: np.ndarray, model_name: str) -> Dict[str, Any]:
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

    top10_n = max(1, int(len(probas) * 0.10))
    top10_idx = np.argsort(probas)[::-1][:top10_n]
    top10_prec = float(y_true[top10_idx].mean())
    base_rate = float(y_true.mean())
    lift10 = float(top10_prec / base_rate) if base_rate > 0 else 1.0

    return {
        "model_name": model_name,
        "pr_auc": round(pr_auc, 4),
        "roc_auc": round(roc_auc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "brier_score": round(brier, 4),
        "confusion_matrix": cm,
        "top10_precision": round(top10_prec, 4),
        "top10_lift": round(lift10, 2),
        "base_rate": round(base_rate, 4),
    }


class CanonicalTrainer:
    def __init__(self, db: Session, model_dir: Optional[str] = None, version_tag: str = "v3"):
        self.db = db
        self.version_tag = version_tag
        if model_dir:
            self.model_dir = model_dir
        else:
            self.model_dir = os.path.join(os.path.dirname(__file__), "models", version_tag)
        os.makedirs(self.model_dir, exist_ok=True)

    def train_and_evaluate(self) -> Dict[str, Any]:
        """Train canonical ML models, calibrate LightGBM, persist versioned artifacts, and return metadata."""
        df_train, df_val, df_test, split_stats = load_canonical_temporal_splits(self.db)

        X_train = df_train[CANONICAL_FEATURE_COLUMNS]
        y_train = df_train[TARGET_COLUMN].values

        X_val = df_val[CANONICAL_FEATURE_COLUMNS]
        y_val = df_val[TARGET_COLUMN].values

        X_test = df_test[CANONICAL_FEATURE_COLUMNS]
        y_test = df_test[TARGET_COLUMN].values

        preprocessor = ColumnTransformer(
            transformers=[
                (
                    "cat",
                    OneHotEncoder(handle_unknown="ignore", min_frequency=1, sparse_output=False),
                    CAT_COLUMNS_V2,
                ),
                ("num", StandardScaler(), NUM_COLUMNS_V2),
            ]
        )

        logger.info(f"Fitting canonical feature preprocessor for {self.version_tag}...")
        X_train_proc = preprocessor.fit_transform(X_train)
        X_val_proc = preprocessor.transform(X_val)
        X_test_proc = preprocessor.transform(X_test)

        prep_filename = f"preprocessor_{self.version_tag}.joblib"
        prep_path = os.path.join(self.model_dir, prep_filename)
        joblib.dump(preprocessor, prep_path)

        # Train Base Champion Model (LightGBM)
        base_lgbm = LGBMClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.05,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )
        base_lgbm.fit(X_train_proc, y_train)

        # Train Calibrated Model
        calibrated_model = CalibratedClassifierCV(
            estimator=base_lgbm,
            method="sigmoid",
            cv="prefit",
        )
        calibrated_model.fit(X_val_proc, y_val)

        model_filename = f"model_{self.version_tag}_canonical_lightgbm_calibrated.joblib"
        model_path = os.path.join(self.model_dir, model_filename)
        joblib.dump(calibrated_model, model_path)

        # Evaluate on Test Set
        test_probas = calibrated_model.predict_proba(X_test_proc)[:, 1]
        model_version_name = f"2026_canonical_{self.version_tag}"
        metrics = evaluate_predictions_v2(y_test, test_probas, model_version_name)

        from datetime import datetime
        metadata = {
            "model_version": model_version_name,
            "algorithm": "Calibrated LightGBM Classifier (Sigmoid)",
            "target_variable": TARGET_COLUMN,
            "training_timestamp": datetime.utcnow().isoformat() + "Z",
            "feature_columns": CANONICAL_FEATURE_COLUMNS,
            "categorical_columns": CAT_COLUMNS_V2,
            "numeric_columns": NUM_COLUMNS_V2,
            "split_statistics": split_stats,
            "evaluation_metrics": metrics,
            "artifacts": {
                "model": model_filename,
                "preprocessor": prep_filename,
            },
        }

        meta_path = os.path.join(self.model_dir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata
