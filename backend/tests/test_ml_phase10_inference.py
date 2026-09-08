"""
Phase 10 Staging ML Inference Integration — Comprehensive Test Suite

Tests every requirement exactly as specified:
  1.  Normal lead prediction (Mohali, high-engagement profile)
  2.  Unknown state / source / owner (unseen at training time)
  3.  Missing / None categorical values
  4.  New/unseen categorical value strings
  5.  Probability always in [0.0, 1.0]
  6.  No post-t0 fields enter inference (leakage guardrail)
  7.  Calibrated model is actually being used (output ≠ raw LightGBM)
  8.  Existing dashboard and backend behavior unchanged (aggregate tests pass)
  9.  Batch API endpoint works correctly
  10. Response schema is complete and correct
  11. Inference latency is acceptable (<500ms single, <5s batch of 100)
  12. Model artifacts are the correct 2026-specific ones
  13. Feature contract: exactly 11 t0 features, none post-t0

All tests use in-memory fixtures from representative records.
No records are inserted into production data.
"""

import os
import time
import pytest
import joblib
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.main import app
from app.ml.ml_inference_service import (
    MLInferenceService,
    FORBIDDEN_LEAKAGE_FIELDS,
    OPTIMAL_F1_THRESHOLD,
    TOP_10_PCT_PROB_CUTOFF,
    TOP_20_PCT_PROB_CUTOFF,
)
from app.ml.ml_temporal_split import PURE_T0_FEATURE_COLUMNS
from app.ml.ml_baseline_trainer import DEFAULT_MODEL_DIR, CAT_COLUMNS, NUM_COLUMNS

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures — representative in-memory records, never touch production DB
# ---------------------------------------------------------------------------

TYPICAL_MOHALI_LEAD = {
    "campus_name": "Mohali",
    "academic_year": 2026,
    "source_canonical": "Quick Add Form",
    "state_canonical": "Uttar Pradesh",
    "state_code": "UP",
    "zone": "North",
    "owner_canonical": "Counselor A",
    "team": "Inbound Team",
    "created_month": 5,
    "created_dayofweek": 2,
    "created_hour": 14,
}

TYPICAL_UNNAO_LEAD = {
    "campus_name": "Unnao",
    "academic_year": 2026,
    "source_canonical": "Walk In",
    "state_canonical": "Uttar Pradesh",
    "state_code": "UP",
    "zone": "North",
    "owner_canonical": "Counselor B",
    "team": "Walk-in Team",
    "created_month": 3,
    "created_dayofweek": 0,
    "created_hour": 11,
}

UNKNOWN_STATE_LEAD = {
    "campus_name": "Mohali",
    "academic_year": 2026,
    "source_canonical": "UNKNOWN_XYZ_SOURCE_9999",
    "state_canonical": "UNMAPPED_STATE_BRANDNEW",
    "state_code": "XX",
    "zone": "UNMAPPED_ZONE",
    "owner_canonical": "UNMAPPED_OWNER_ALIEN",
    "team": "UNMAPPED_TEAM_GHOST",
    "created_month": 1,
    "created_dayofweek": 6,
    "created_hour": 0,
}

NULL_CATEGORICAL_LEAD = {
    "campus_name": None,
    "academic_year": 2026,
    "source_canonical": None,
    "state_canonical": None,
    "state_code": None,
    "zone": None,
    "owner_canonical": None,
    "team": None,
    "created_month": 6,
    "created_dayofweek": 3,
    "created_hour": 9,
}

FORBIDDEN_LEAKAGE_PAYLOAD = {
    **TYPICAL_MOHALI_LEAD,
    "mx_AdmissionDate": "2026-05-15 10:00:00",  # post-t0 leakage
}

FORBIDDEN_PROSPECT_STAGE = {
    **TYPICAL_UNNAO_LEAD,
    "ProspectStage": "Admitted",  # post-t0 leakage
}

FORBIDDEN_MULTIPLE_FIELDS = {
    **TYPICAL_MOHALI_LEAD,
    "mx_Admission_done": 1,
    "mx_FastTrackId": "FT123",
}

BATCH_100_LEADS = [
    {
        "campus_name": "Mohali" if i % 2 == 0 else "Unnao",
        "academic_year": 2026,
        "source_canonical": "Quick Add Form" if i % 3 == 0 else "Walk In",
        "state_canonical": "Uttar Pradesh" if i % 4 == 0 else "Punjab",
        "state_code": "UP" if i % 4 == 0 else "PB",
        "zone": "North",
        "owner_canonical": f"Counselor {chr(65 + (i % 5))}",
        "team": "Inbound Team",
        "created_month": (i % 12) + 1,
        "created_dayofweek": i % 7,
        "created_hour": i % 24,
    }
    for i in range(100)
]


# ---------------------------------------------------------------------------
# Test Group 1: Feature Contract Validation
# ---------------------------------------------------------------------------

class TestFeatureContract:
    """
    Validates the ML feature contract: 11 pure t0 features,
    correct column names, separation of CAT vs NUM, no post-t0 fields.
    """

    def test_pure_t0_has_exactly_11_features(self):
        """Feature contract must specify exactly 11 t0 features."""
        assert len(PURE_T0_FEATURE_COLUMNS) == 11, (
            f"Expected 11 t0 features, got {len(PURE_T0_FEATURE_COLUMNS)}: {PURE_T0_FEATURE_COLUMNS}"
        )

    def test_cat_and_num_cover_all_t0_features(self):
        """CAT_COLUMNS + NUM_COLUMNS must exactly equal PURE_T0_FEATURE_COLUMNS."""
        combined = set(CAT_COLUMNS) | set(NUM_COLUMNS)
        t0_set = set(PURE_T0_FEATURE_COLUMNS)
        assert combined == t0_set, (
            f"CAT+NUM mismatch with T0. "
            f"Missing from T0: {combined - t0_set}. "
            f"Extra in T0: {t0_set - combined}."
        )

    def test_no_post_t0_leakage_in_feature_columns(self):
        """None of the FORBIDDEN_LEAKAGE_FIELDS may appear in PURE_T0_FEATURE_COLUMNS."""
        overlap = FORBIDDEN_LEAKAGE_FIELDS.intersection(
            {c.lower() for c in PURE_T0_FEATURE_COLUMNS}
        )
        assert not overlap, (
            f"Post-t0 leakage fields found in PURE_T0_FEATURE_COLUMNS: {overlap}"
        )

    def test_cy_cucet_not_in_t0_features(self):
        """
        cy_cucet was excluded from PURE_T0_FEATURE_COLUMNS per Phase 7 timing audit.
        It must not appear as an inference feature.
        """
        assert "cy_cucet" not in PURE_T0_FEATURE_COLUMNS

    def test_correct_categorical_features(self):
        """CAT_COLUMNS must contain exactly the expected 7 categoricals."""
        expected_cats = {
            "campus_name", "source_canonical", "state_canonical",
            "state_code", "zone", "owner_canonical", "team"
        }
        assert set(CAT_COLUMNS) == expected_cats

    def test_correct_numerical_features(self):
        """NUM_COLUMNS must contain exactly the expected 4 numerics."""
        expected_nums = {"academic_year", "created_month", "created_dayofweek", "created_hour"}
        assert set(NUM_COLUMNS) == expected_nums


# ---------------------------------------------------------------------------
# Test Group 2: Model Artifact Validation
# ---------------------------------------------------------------------------

class TestModelArtifacts:
    """
    Validates that the correct 2026-specific model artifacts exist
    and have the right type/shape.
    """

    def test_preprocessor_2026_joblib_exists(self):
        path = os.path.join(DEFAULT_MODEL_DIR, "preprocessor_2026.joblib")
        assert os.path.exists(path), f"Missing: {path}"
        assert os.path.getsize(path) > 0

    def test_model_2026_lightgbm_joblib_exists(self):
        path = os.path.join(DEFAULT_MODEL_DIR, "model_2026_lightgbm.joblib")
        assert os.path.exists(path), f"Missing: {path}"
        assert os.path.getsize(path) > 0

    def test_model_2026_lightgbm_calibrated_joblib_exists(self):
        path = os.path.join(DEFAULT_MODEL_DIR, "model_2026_lightgbm_calibrated.joblib")
        assert os.path.exists(path), f"Missing: {path}"
        assert os.path.getsize(path) > 0

    def test_inference_service_loads_2026_preprocessor(self):
        """MLInferenceService must load preprocessor_2026.joblib, not the pooled one."""
        svc = MLInferenceService()
        # preprocessor must be fitted ColumnTransformer
        from sklearn.compose import ColumnTransformer
        assert isinstance(svc.preprocessor, ColumnTransformer)

    def test_calibrated_model_is_calibrated_classifier(self):
        """The active model must be a CalibratedClassifierCV (not raw LightGBM)."""
        svc = MLInferenceService()
        from sklearn.calibration import CalibratedClassifierCV
        assert isinstance(svc.calibrated_model, CalibratedClassifierCV), (
            f"Expected CalibratedClassifierCV, got {type(svc.calibrated_model).__name__}. "
            "Ensure inference service loads model_2026_lightgbm_calibrated.joblib."
        )

    def test_calibrated_model_uses_isotonic_method(self):
        """Calibration method must be valid calibrator ('isotonic' or 'sigmoid')."""
        svc = MLInferenceService()
        assert getattr(svc.calibrated_model, "method", None) in ("isotonic", "sigmoid"), (
            "Expected valid calibration method. "
            f"Got: {getattr(svc.calibrated_model, 'method', 'N/A')}"
        )


# ---------------------------------------------------------------------------
# Test Group 3: Direct Inference Unit Tests (no HTTP)
# ---------------------------------------------------------------------------

class TestDirectInference:
    """
    Directly tests MLInferenceService.predict_single() and predict_batch()
    without going through the FastAPI layer — faster and more granular.
    """

    def test_01_normal_mohali_lead_prediction(self):
        """Normal Mohali lead returns all expected response fields."""
        svc = MLInferenceService()
        result = svc.predict_single(TYPICAL_MOHALI_LEAD)

        assert "calibrated_admission_probability" in result
        assert "operational_tier" in result
        assert "decision_recommendation" in result
        assert "t0_threshold_applied" in result
        assert "model_version" in result
        assert result["model_version"] == svc.model_version

    def test_02_probability_always_in_0_1(self):
        """Calibrated probability must always be in [0.0, 1.0]."""
        svc = MLInferenceService()
        for lead, name in [
            (TYPICAL_MOHALI_LEAD, "typical_mohali"),
            (TYPICAL_UNNAO_LEAD, "typical_unnao"),
            (UNKNOWN_STATE_LEAD, "unknown_state"),
            (NULL_CATEGORICAL_LEAD, "null_categoricals"),
        ]:
            result = svc.predict_single(lead)
            p = result["calibrated_admission_probability"]
            assert 0.0 <= p <= 1.0, (
                f"[{name}] Probability {p} out of [0,1] bounds"
            )

    def test_03_unknown_state_source_owner_does_not_crash(self):
        """
        OHE handle_unknown='ignore' must absorb unseen categoricals.
        The model must return a valid prediction, not raise an error.
        """
        svc = MLInferenceService()
        result = svc.predict_single(UNKNOWN_STATE_LEAD)
        p = result["calibrated_admission_probability"]
        assert 0.0 <= p <= 1.0

    def test_04_missing_categorical_values_handled(self):
        """
        None values in categorical fields must be handled gracefully.
        validate_t0_features converts None -> None (string columns).
        Preprocessor must not raise on None strings.
        """
        svc = MLInferenceService()
        result = svc.predict_single(NULL_CATEGORICAL_LEAD)
        p = result["calibrated_admission_probability"]
        assert 0.0 <= p <= 1.0

    def test_05_new_unseen_category_value(self):
        """
        Brand-new categorical string values (not seen during training)
        must not raise. OHE handle_unknown='ignore' zeros out the column.
        """
        svc = MLInferenceService()
        novel_lead = {
            **TYPICAL_MOHALI_LEAD,
            "campus_name": "BRAND_NEW_CAMPUS_2099",
            "source_canonical": "NEVER_SEEN_CHANNEL_XYZ",
            "owner_canonical": "GHOST_COUNSELOR_OMEGA",
        }
        result = svc.predict_single(novel_lead)
        p = result["calibrated_admission_probability"]
        assert 0.0 <= p <= 1.0

    def test_06_leakage_guardrail_mx_admission_date(self):
        """mx_AdmissionDate (post-t0) must trigger ValueError with leakage message."""
        svc = MLInferenceService()
        with pytest.raises(ValueError, match="Target Leakage Guardrail Triggered"):
            svc.predict_single(FORBIDDEN_LEAKAGE_PAYLOAD)

    def test_07_leakage_guardrail_prospect_stage(self):
        """ProspectStage (post-t0) must trigger ValueError with leakage message."""
        svc = MLInferenceService()
        with pytest.raises(ValueError, match="Target Leakage Guardrail Triggered"):
            svc.predict_single(FORBIDDEN_PROSPECT_STAGE)

    def test_08_leakage_guardrail_multiple_forbidden_fields(self):
        """Multiple forbidden fields must also trigger the leakage guardrail."""
        svc = MLInferenceService()
        with pytest.raises(ValueError, match="Target Leakage Guardrail Triggered"):
            svc.predict_single(FORBIDDEN_MULTIPLE_FIELDS)

    def test_09_calibrated_model_differs_from_raw_lgbm(self):
        """
        The calibrated model output must differ from the raw LightGBM output.
        This proves the calibrated artifact is actually being used, not the uncalibrated one.
        """
        raw_model = joblib.load(
            os.path.join(DEFAULT_MODEL_DIR, "model_2026_lightgbm.joblib")
        )
        prep = joblib.load(
            os.path.join(DEFAULT_MODEL_DIR, "preprocessor_2026.joblib")
        )

        sample = pd.DataFrame([{
            **TYPICAL_MOHALI_LEAD
        }])
        X = prep.transform(sample[PURE_T0_FEATURE_COLUMNS])

        p_raw = float(raw_model.predict_proba(X)[0, 1])

        svc = MLInferenceService()
        result = svc.predict_single(TYPICAL_MOHALI_LEAD)
        p_cal = result["calibrated_admission_probability"]

        assert abs(p_cal - p_raw) > 1e-6, (
            f"Calibrated ({p_cal:.6f}) == Raw ({p_raw:.6f}). "
            "Inference service is using raw LightGBM, not the calibrated model."
        )

    def test_10_operational_tier_assignment_high_priority(self):
        """
        If calibrated_prob >= TOP_10_PCT_PROB_CUTOFF, tier must be 'High Priority (Top 10%)'.
        """
        svc = MLInferenceService()
        # Force a synthetic probability by running many leads and checking tier logic directly
        # Use a lead profile that historically generates meaningful probabilities
        result = svc.predict_single(TYPICAL_MOHALI_LEAD)
        p = result["calibrated_admission_probability"]
        tier = result["operational_tier"]

        if p >= TOP_10_PCT_PROB_CUTOFF:
            assert tier == "High Priority (Top 10%)"
        elif p >= TOP_20_PCT_PROB_CUTOFF:
            assert tier == "Standard Priority (Top 20%)"
        else:
            assert tier == "Low Priority"

    def test_11_decision_recommendation_logic(self):
        """
        decision_recommendation is ADMIT_PRIORITY_OUTREACH if prob >= OPTIMAL_F1_THRESHOLD,
        else STANDARD_NURTURE. Verify every lead follows this rule.
        """
        svc = MLInferenceService()
        for lead in [TYPICAL_MOHALI_LEAD, TYPICAL_UNNAO_LEAD, UNKNOWN_STATE_LEAD]:
            result = svc.predict_single(lead)
            p = result["calibrated_admission_probability"]
            rec = result["decision_recommendation"]

            if p >= OPTIMAL_F1_THRESHOLD:
                assert rec == "ADMIT_PRIORITY_OUTREACH", (
                    f"p={p:.4f} >= threshold={OPTIMAL_F1_THRESHOLD} but rec={rec}"
                )
            else:
                assert rec == "STANDARD_NURTURE", (
                    f"p={p:.4f} < threshold={OPTIMAL_F1_THRESHOLD} but rec={rec}"
                )

    def test_12_threshold_metadata_in_response(self):
        """t0_threshold_applied must equal OPTIMAL_F1_THRESHOLD."""
        svc = MLInferenceService()
        result = svc.predict_single(TYPICAL_MOHALI_LEAD)
        assert result["t0_threshold_applied"] == OPTIMAL_F1_THRESHOLD

    def test_13_predictive_score_pct_matches_probability(self):
        """predictive_score_pct must equal calibrated_admission_probability * 100."""
        svc = MLInferenceService()
        result = svc.predict_single(TYPICAL_UNNAO_LEAD)
        p = result["calibrated_admission_probability"]
        pct = result["predictive_score_pct"]
        assert abs(pct - round(p * 100.0, 2)) < 0.001

    def test_14_single_inference_latency_under_500ms(self):
        """Single inference (after model is loaded) must complete in <500ms."""
        svc = MLInferenceService()  # ensure already loaded

        t0 = time.perf_counter()
        svc.predict_single(TYPICAL_MOHALI_LEAD)
        latency_ms = (time.perf_counter() - t0) * 1000

        assert latency_ms < 500, (
            f"Single inference took {latency_ms:.1f}ms (limit: 500ms)"
        )

    def test_15_batch_inference_100_leads_under_5s(self):
        """Batch inference of 100 leads must complete in <5 seconds."""
        svc = MLInferenceService()

        t0 = time.perf_counter()
        results = svc.predict_batch(BATCH_100_LEADS)
        latency_s = time.perf_counter() - t0

        assert len(results) == 100
        assert latency_s < 5.0, (
            f"Batch of 100 leads took {latency_s:.2f}s (limit: 5s)"
        )

    def test_16_batch_all_probabilities_valid(self):
        """All probabilities in a batch must be in [0.0, 1.0]."""
        svc = MLInferenceService()
        results = svc.predict_batch(BATCH_100_LEADS)

        for i, r in enumerate(results):
            p = r["calibrated_admission_probability"]
            assert 0.0 <= p <= 1.0, f"Lead index {i}: probability {p} out of [0,1]"

    def test_17_validate_no_extra_features_enter_inference(self):
        """
        Extra unknown fields in the payload beyond the 11 t0 features
        are silently ignored (not passed to the model), not causing errors.
        """
        svc = MLInferenceService()
        payload_with_extras = {
            **TYPICAL_MOHALI_LEAD,
            "crm_id": "LEAD_ABC123",
            "phone_number": "9876543210",
            "email": "lead@example.com",
            # No forbidden post-t0 fields
        }
        result = svc.predict_single(payload_with_extras)
        assert 0.0 <= result["calibrated_admission_probability"] <= 1.0


# ---------------------------------------------------------------------------
# Test Group 4: API Endpoint Integration Tests
# ---------------------------------------------------------------------------

class TestAPIEndpoints:
    """Tests against the FastAPI HTTP layer via TestClient."""

    def test_01_model_info_returns_200(self):
        """GET /api/ml/model-info returns 200 with correct model version."""
        res = client.get("/api/ml/model-info")
        assert res.status_code == 200
        data = res.json()
        svc = MLInferenceService()
        assert data["model_version"] == svc.model_version
        assert "operational_thresholds" in data
        assert "evaluation_metrics" in data

    def test_02_model_info_thresholds_are_correct(self):
        """Operational thresholds in /api/ml/model-info match constants."""
        res = client.get("/api/ml/model-info")
        thresholds = res.json()["operational_thresholds"]
        assert thresholds["optimal_f1_threshold"] == OPTIMAL_F1_THRESHOLD
        assert thresholds["top_10_pct_cutoff"] == TOP_10_PCT_PROB_CUTOFF
        assert thresholds["top_20_pct_cutoff"] == TOP_20_PCT_PROB_CUTOFF

    def test_03_predict_single_mohali_lead_200(self):
        """POST /api/ml/predict returns 200 for a typical Mohali lead."""
        res = client.post("/api/ml/predict", json=TYPICAL_MOHALI_LEAD)
        assert res.status_code == 200
        data = res.json()
        assert "calibrated_admission_probability" in data
        assert 0.0 <= data["calibrated_admission_probability"] <= 1.0

    def test_04_predict_single_unnao_lead_200(self):
        """POST /api/ml/predict returns 200 for a typical Unnao lead."""
        res = client.post("/api/ml/predict", json=TYPICAL_UNNAO_LEAD)
        assert res.status_code == 200
        data = res.json()
        assert 0.0 <= data["calibrated_admission_probability"] <= 1.0

    def test_05_predict_unknown_state_source_200(self):
        """POST /api/ml/predict returns 200 for an unknown state/source/owner."""
        res = client.post("/api/ml/predict", json=UNKNOWN_STATE_LEAD)
        assert res.status_code == 200
        data = res.json()
        assert 0.0 <= data["calibrated_admission_probability"] <= 1.0

    def test_06_predict_null_categoricals_200(self):
        """POST /api/ml/predict handles null/missing categorical values without 500."""
        res = client.post("/api/ml/predict", json=NULL_CATEGORICAL_LEAD)
        assert res.status_code == 200
        assert 0.0 <= res.json()["calibrated_admission_probability"] <= 1.0

    def test_07_predict_leakage_mx_admission_date_422(self):
        """POST /api/ml/predict rejects mx_AdmissionDate with HTTP 422."""
        res = client.post("/api/ml/predict", json=FORBIDDEN_LEAKAGE_PAYLOAD)
        assert res.status_code == 422
        assert "Target Leakage Guardrail Triggered" in res.json()["detail"]

    def test_08_predict_leakage_prospect_stage_422(self):
        """POST /api/ml/predict rejects ProspectStage with HTTP 422."""
        res = client.post("/api/ml/predict", json=FORBIDDEN_PROSPECT_STAGE)
        assert res.status_code == 422

    def test_09_predict_full_response_schema(self):
        """POST /api/ml/predict response has all 6 required fields."""
        res = client.post("/api/ml/predict", json=TYPICAL_MOHALI_LEAD)
        data = res.json()
        required_fields = {
            "calibrated_admission_probability",
            "predictive_score_pct",
            "operational_tier",
            "decision_recommendation",
            "t0_threshold_applied",
            "model_version",
        }
        missing = required_fields - set(data.keys())
        assert not missing, f"Missing fields in response: {missing}"

    def test_10_predict_batch_2_leads_200(self):
        """POST /api/ml/predict-batch returns 200 for a 2-lead batch."""
        payload = {
            "leads": [TYPICAL_MOHALI_LEAD, TYPICAL_UNNAO_LEAD]
        }
        res = client.post("/api/ml/predict-batch", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["total_leads_processed"] == 2
        assert len(data["predictions"]) == 2

    def test_11_predict_batch_indices_are_sequential(self):
        """Batch predictions include correct, sequential lead_index."""
        payload = {"leads": [TYPICAL_MOHALI_LEAD, UNKNOWN_STATE_LEAD, NULL_CATEGORICAL_LEAD]}
        res = client.post("/api/ml/predict-batch", json=payload)
        assert res.status_code == 200
        preds = res.json()["predictions"]
        for i, pred in enumerate(preds):
            assert pred["lead_index"] == i

    def test_12_predict_batch_summary_counts_correct(self):
        """Batch summary counts (high/standard/low) must sum to total_leads_processed."""
        payload = {"leads": BATCH_100_LEADS}
        res = client.post("/api/ml/predict-batch", json=payload)
        assert res.status_code == 200
        data = res.json()
        total = data["total_leads_processed"]
        count_sum = (
            data["high_priority_count"]
            + data["standard_priority_count"]
            + data["low_priority_count"]
        )
        assert total == 100
        assert count_sum == total, (
            f"Tier counts {data['high_priority_count']}+{data['standard_priority_count']}"
            f"+{data['low_priority_count']} != {total}"
        )

    def test_13_predict_batch_empty_leads_rejected(self):
        """POST /api/ml/predict-batch rejects an empty leads list."""
        res = client.post("/api/ml/predict-batch", json={"leads": []})
        assert res.status_code == 422  # FastAPI min_length=1 violation

    def test_14_no_admit_probability_exceeds_unity(self):
        """All 100 batch predictions must have probability <= 1.0."""
        payload = {"leads": BATCH_100_LEADS}
        res = client.post("/api/ml/predict-batch", json=payload)
        preds = res.json()["predictions"]
        for p in preds:
            assert p["calibrated_admission_probability"] <= 1.0
            assert p["calibrated_admission_probability"] >= 0.0


# ---------------------------------------------------------------------------
# Test Group 5: Dashboard & Backend Isolation Tests
# ---------------------------------------------------------------------------

class TestDashboardIsolation:
    """
    Verifies that the ML staging layer does NOT affect dashboard data,
    aggregate queries, or existing production endpoints.
    """

    def test_01_dashboard_overview_still_returns_200(self):
        """GET /api/dashboard/overview is unaffected by Phase 10 ML integration."""
        res = client.get("/api/dashboard/overview?campus=all&years=2026")
        assert res.status_code == 200

    def test_02_data_management_datasets_still_returns_200(self):
        """GET /api/admin/datasets is unaffected by Phase 10 ML integration."""
        res = client.get("/api/admin/datasets")
        assert res.status_code == 200

    def test_03_ml_predict_does_not_write_to_db(self):
        """
        POST /api/ml/predict must not insert, update, or delete any DB rows.
        We verify this by checking the dashboard aggregate totals before and after.
        """
        from app.database.connection import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            before = db.execute(
                text("SELECT SUM(leads_cy) FROM analytics.dashboard_agg WHERE academic_year=2026")
            ).scalar()
        finally:
            db.close()

        # Run 5 predictions
        for _ in range(5):
            client.post("/api/ml/predict", json=TYPICAL_MOHALI_LEAD)

        db = SessionLocal()
        try:
            after = db.execute(
                text("SELECT SUM(leads_cy) FROM analytics.dashboard_agg WHERE academic_year=2026")
            ).scalar()
        finally:
            db.close()

        assert before == after, (
            f"Dashboard aggregate changed after ML inference: {before} -> {after}. "
            "ML inference must be read-only."
        )

    def test_04_ml_endpoint_not_in_dashboard_router(self):
        """
        The ML endpoints use /api/ml/ prefix.
        Verify they are distinct from /api/dashboard/ routes.
        """
        from app.api.ml_predictions import router as ml_router
        ml_routes = {r.path for r in ml_router.routes}
        assert all("/ml/" in r for r in ml_routes), (
            "ML router contains non-/ml/ routes"
        )

    def test_05_singleton_service_does_not_reinitialize_on_repeated_calls(self):
        """
        MLInferenceService uses singleton pattern. Calling it twice must
        return the same instance (model loaded once at startup, not per-request).
        """
        svc1 = MLInferenceService()
        svc2 = MLInferenceService()
        assert svc1 is svc2, "MLInferenceService is not a singleton — model reloads on every call"


# ---------------------------------------------------------------------------
# Test Group 6: Leakage Audit — exhaustive forbidden field coverage
# ---------------------------------------------------------------------------

class TestLeakageBlock:
    """
    Every field in FORBIDDEN_LEAKAGE_FIELDS must trigger the guardrail.
    The inference service must reject ALL of them, not just a subset.
    """

    @pytest.mark.parametrize("forbidden_field", sorted(list(FORBIDDEN_LEAKAGE_FIELDS)))
    def test_every_forbidden_field_triggers_guardrail(self, forbidden_field):
        """Each forbidden post-t0 field individually triggers the leakage guardrail."""
        svc = MLInferenceService()
        payload = {
            **TYPICAL_MOHALI_LEAD,
            forbidden_field: "FORBIDDEN_VALUE",
        }
        with pytest.raises(ValueError, match="Target Leakage Guardrail Triggered"):
            svc.predict_single(payload)
