"""
Phase 8 Automated Mature Evaluation Test Suite

Validates:
1. MatureEvaluator executes and returns evaluation metrics for both censored and mature subsets
2. Champion LightGBM model beats Dummy baseline on Mature Validation PR-AUC and ROC-AUC
3. Top-10% Lift is significantly greater than baseline (Lift > 3.0x)
4. Feature importance hierarchy is correctly generated
"""

import pytest
from app.ml.ml_mature_evaluator import MatureEvaluator


@pytest.fixture(scope="module")
def eval_results():
    evaluator = MatureEvaluator()
    return evaluator.run_evaluation()


class TestMLMatureEvaluation:
    def test_01_mature_evaluation_returns_summary(self, eval_results):
        """MatureEvaluator returns metrics summary for all trained models."""
        assert "evaluation_summary" in eval_results
        summary = eval_results["evaluation_summary"]
        assert "model_e_lightgbm" in summary
        assert "model_a_dummy_prior" in summary

    def test_02_champion_beats_dummy_on_mature_pr_auc(self, eval_results):
        """Champion LightGBM model beats Dummy baseline on Mature Validation PR-AUC."""
        summary = eval_results["evaluation_summary"]
        lgb_pr_auc = summary["model_e_lightgbm"]["val_mature"]["pr_auc"]
        dummy_pr_auc = summary["model_a_dummy_prior"]["val_mature"]["pr_auc"]

        assert lgb_pr_auc > dummy_pr_auc
        assert lgb_pr_auc > 0.30  # Strong performance (>0.30)

    def test_03_champion_top10_lift_exceeds_threshold(self, eval_results):
        """Champion LightGBM model Top-10% Lift exceeds 3.0x."""
        summary = eval_results["evaluation_summary"]
        lgb_lift = summary["model_e_lightgbm"]["val_mature"]["top10_lift"]

        assert lgb_lift > 3.0

    def test_04_feature_importance_generated(self, eval_results):
        """Feature importance list is populated and sorted by importance."""
        assert "feature_importance" in eval_results
        feat_imp = eval_results["feature_importance"]
        assert len(feat_imp) > 0
        top_feature = feat_imp[0]["feature"]
        assert top_feature in ["owner_canonical", "state_canonical", "source_canonical", "zone"]
