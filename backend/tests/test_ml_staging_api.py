"""
Phase 10 Automated Staging ML API Test Suite

Validates:
1. GET /api/ml/model-info returns 200 with model metadata and operational thresholds.
2. POST /api/ml/predict computes calibrated prediction for single lead.
3. POST /api/ml/predict rejects forbidden post-t0 leakage fields with 422 HTTP error.
4. POST /api/ml/predict-batch computes calibrated predictions for batch payload.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestMLStagingAPI:
    def test_01_get_model_info(self):
        """GET /api/ml/model-info returns active model metadata."""
        res = client.get("/api/ml/model-info")
        assert res.status_code == 200
        data = res.json()
        assert data["model_version"] == "2026_lightgbm_calibrated_v1"
        assert "operational_thresholds" in data
        assert data["evaluation_metrics"]["pr_auc"] == 0.4149

    def test_02_predict_single_lead_success(self):
        """POST /api/ml/predict returns calibrated probability and tier for valid lead."""
        payload = {
            "campus_name": "Mohali",
            "source_canonical": "Quick Add Form",
            "state_canonical": "Uttar Pradesh",
            "state_code": "UP",
            "zone": "North",
            "owner_canonical": "Counselor A",
            "team": "Inbound Team",
            "academic_year": 2026,
            "created_month": 5,
            "created_dayofweek": 2,
            "created_hour": 14,
        }
        res = client.post("/api/ml/predict", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "calibrated_admission_probability" in data
        assert 0.0 <= data["calibrated_admission_probability"] <= 1.0
        assert data["operational_tier"] in [
            "High Priority (Top 10%)",
            "Standard Priority (Top 20%)",
            "Low Priority",
        ]
        assert data["decision_recommendation"] in [
            "ADMIT_PRIORITY_OUTREACH",
            "STANDARD_NURTURE",
        ]

    def test_03_predict_leakage_guardrail_rejection(self):
        """POST /api/ml/predict rejects post-t0 leakage fields with 422 status code."""
        payload = {
            "campus_name": "Mohali",
            "source_canonical": "Direct",
            "mx_AdmissionDate": "2026-05-15 10:00:00",  # FORBIDDEN POST-T0 LEAKAGE
        }
        res = client.post("/api/ml/predict", json=payload)
        assert res.status_code == 422
        assert "Target Leakage Guardrail Triggered" in res.json()["detail"]

    def test_04_predict_batch_leads_success(self):
        """POST /api/ml/predict-batch returns batch prediction array and summary."""
        payload = {
            "leads": [
                {
                    "campus_name": "Mohali",
                    "source_canonical": "Quick Add Form",
                    "state_canonical": "Uttar Pradesh",
                    "academic_year": 2026,
                },
                {
                    "campus_name": "Unnao",
                    "source_canonical": "Other",
                    "state_canonical": "Bihar",
                    "academic_year": 2026,
                },
            ]
        }
        res = client.post("/api/ml/predict-batch", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["total_leads_processed"] == 2
        assert len(data["predictions"]) == 2
        assert data["predictions"][0]["lead_index"] == 0
        assert data["predictions"][1]["lead_index"] == 1
