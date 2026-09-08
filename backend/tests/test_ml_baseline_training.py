"""
Phase 8 Automated Baseline Model Training Test Suite

Validates:
1. Model training pipeline executes without error across all required baseline models (Models A, B, C, D, E)
2. Model artifacts and preprocessor are persisted in backend/app/ml/models/
3. Model predictions comply with probability range [0.0, 1.0]
4. Feature schema and zero-leakage compliance
"""

import os
import pytest
import numpy as np
import joblib

from app.ml.ml_baseline_trainer import BaselineTrainer, DEFAULT_MODEL_DIR
from app.ml.ml_temporal_split import load_temporal_splits, PURE_T0_FEATURE_COLUMNS
from app.ml.ml_feature_pipeline import FORBIDDEN_LEAKAGE_FIELDS


@pytest.fixture(scope="module")
def train_models():
    trainer = BaselineTrainer(model_dir=DEFAULT_MODEL_DIR)
    results = trainer.train_all_baselines()
    return results


class TestMLBaselineTraining:
    def test_01_preprocessor_artifact_exists(self, train_models):
        """Preprocessor joblib artifact exists in model_dir."""
        preprocessor_path = os.path.join(DEFAULT_MODEL_DIR, "preprocessor.joblib")
        assert os.path.exists(preprocessor_path)
        assert os.path.getsize(preprocessor_path) > 0

    def test_02_all_baseline_models_persisted(self, train_models):
        """All 5 required baseline model artifacts exist."""
        expected_models = [
            "model_a_dummy_prior.joblib",
            "model_b_dummy_stratified.joblib",
            "model_c_logistic_regression.joblib",
            "model_d_random_forest.joblib",
            "model_e_lightgbm.joblib",
        ]
        for m_file in expected_models:
            path = os.path.join(DEFAULT_MODEL_DIR, m_file)
            assert os.path.exists(path), f"Missing model artifact: {path}"
            assert os.path.getsize(path) > 0

    def test_03_champion_lightgbm_predicts_valid_probabilities(self, train_models):
        """Champion LightGBM model outputs valid probability predictions in [0, 1]."""
        lgb_path = os.path.join(DEFAULT_MODEL_DIR, "model_e_lightgbm.joblib")
        prep_path = os.path.join(DEFAULT_MODEL_DIR, "preprocessor.joblib")

        model = joblib.load(lgb_path)
        prep = joblib.load(prep_path)

        df_train, df_val, _ = load_temporal_splits()
        X_val = prep.transform(df_val[PURE_T0_FEATURE_COLUMNS].head(100))
        probas = model.predict_proba(X_val)[:, 1]

        assert len(probas) == 100
        assert np.all(probas >= 0.0)
        assert np.all(probas <= 1.0)

    def test_04_zero_leakage_fields_in_training_schema(self):
        """No forbidden leakage fields exist in model input schema."""
        for col in PURE_T0_FEATURE_COLUMNS:
            assert col.lower() not in FORBIDDEN_LEAKAGE_FIELDS
