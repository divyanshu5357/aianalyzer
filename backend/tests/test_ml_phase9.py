"""
Phase 9 Automated Test Suite

Validates:
1. ThresholdOptimizer runs threshold scan (0.01 to 0.50) and Top-K operational strategies on mature validation data
2. ProbabilityCalibrator fits Isotonic calibration and reduces Brier score below 0.060
3. FeatureAvailabilityAuditor verifies 100% t0 compliance across all model input features
4. CohortStabilityAnalyzer executes cohort breakdown across academic years and campuses
5. Calibrated model joblib artifact exists in backend/app/ml/models/
"""

import os
import pytest

from app.database.connection import SessionLocal
from app.ml.ml_threshold_optimizer import ThresholdOptimizer
from app.ml.ml_probability_calibrator import ProbabilityCalibrator
from app.ml.ml_feature_availability import FeatureAvailabilityAuditor
from app.ml.ml_cohort_stability import CohortStabilityAnalyzer
from app.ml.ml_baseline_trainer import DEFAULT_MODEL_DIR


class TestPhase9Modules:
    def test_01_feature_availability_audit(self):
        """FeatureAvailabilityAuditor confirms t0 compliance for model features."""
        db = SessionLocal()
        try:
            auditor = FeatureAvailabilityAuditor(db)
            res = auditor.audit_t0_feature_availability(sample_limit=1000)
            assert res["total_audited_records"] > 0
            assert res["all_features_t0_compliant"] is True
        finally:
            db.close()

    def test_02_cohort_stability_analysis(self):
        """CohortStabilityAnalyzer returns academic year and campus breakdown."""
        analyzer = CohortStabilityAnalyzer()
        res = analyzer.run_cohort_stability_analysis()

        assert "academic_year_breakdown" in res
        assert "campus_breakdown" in res
        assert 2025 in res["academic_year_breakdown"]
        assert 2026 in res["academic_year_breakdown"]

    def test_03_threshold_optimizer_execution(self):
        """ThresholdOptimizer scans thresholds (0.01 to 0.50) and Top-K decile strategies."""
        optimizer = ThresholdOptimizer()
        res = optimizer.run_threshold_optimization()

        assert res["total_mature_leads"] > 0
        assert len(res["threshold_scan"]) >= 10
        assert len(res["top_k_strategies"]) >= 5

        # Maximum F1 threshold check
        assert res["optimal_f1_threshold"] in [0.05, 0.08, 0.10]
        assert res["best_f1_score"] > 0.40

    def test_04_probability_calibrator_execution(self):
        """ProbabilityCalibrator reduces Brier score loss to < 0.060."""
        calibrator = ProbabilityCalibrator()
        res = calibrator.train_and_evaluate_calibrators()

        iso_brier = res["isotonic_calibrated"]["brier_score"]
        assert iso_brier < 0.060
        assert res["isotonic_calibrated"]["pr_auc"] > 0.39

    def test_05_calibrated_model_artifact_exists(self):
        """Calibrated model joblib artifact exists in model_dir."""
        cal_path = os.path.join(DEFAULT_MODEL_DIR, "model_e_lightgbm_calibrated.joblib")
        assert os.path.exists(cal_path)
        assert os.path.getsize(cal_path) > 0
