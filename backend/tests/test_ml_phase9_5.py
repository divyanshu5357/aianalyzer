"""
Phase 9.5 Automated Test Suite

Validates:
1. Model2026Revalidator trains LightGBM strictly on 2026 inquiry data
2. 2026-only model PR-AUC >= 0.400 and Brier score < 0.060 on mature validation data
3. Top-10% Operational Lift >= 5.0x
4. Artifacts preprocessor_2026.joblib, model_2026_lightgbm.joblib, and model_2026_lightgbm_calibrated.joblib exist
"""

import os
import pytest

from app.ml.ml_2026_revalidator import Model2026Revalidator
from app.ml.ml_baseline_trainer import DEFAULT_MODEL_DIR


class TestPhase95Revalidation:
    def test_01_2026_model_revalidation_execution(self):
        """Model2026Revalidator retrains LightGBM on 2026-only training data."""
        validator = Model2026Revalidator()
        res = validator.train_and_revalidate_2026_model()

        assert res["train_record_count_2026"] > 800000
        assert res["mature_validation_count"] > 100000

        m2026 = res["metrics_2026_only"]
        assert m2026["pr_auc"] >= 0.400
        assert m2026["roc_auc"] >= 0.860
        assert m2026["brier_score"] < 0.060

    def test_02_comparative_performance_improvement(self):
        """2026-only model matches or beats pooled baseline PR-AUC."""
        validator = Model2026Revalidator()
        res = validator.train_and_revalidate_2026_model()

        pr_2026 = res["metrics_2026_only"]["pr_auc"]
        pr_pooled = res["metrics_pooled_baseline"]["pr_auc"]

        assert pr_2026 >= pr_pooled

    def test_03_top_k_lift_thresholds(self):
        """Top 10% operational strategy achieves >= 5.0x lift."""
        validator = Model2026Revalidator()
        res = validator.train_and_revalidate_2026_model()

        top10_strat = [s for s in res["top_k_strategies_2026"] if s["top_pct"] == 10][0]
        assert top10_strat["operational_lift"] >= 5.0

    def test_04_2026_model_artifacts_exist(self):
        """2026 preprocessor, model, and calibrator joblib artifacts exist."""
        prep_path = os.path.join(DEFAULT_MODEL_DIR, "preprocessor_2026.joblib")
        model_path = os.path.join(DEFAULT_MODEL_DIR, "model_2026_lightgbm.joblib")
        cal_path = os.path.join(DEFAULT_MODEL_DIR, "model_2026_lightgbm_calibrated.joblib")

        assert os.path.exists(prep_path)
        assert os.path.exists(model_path)
        assert os.path.exists(cal_path)
