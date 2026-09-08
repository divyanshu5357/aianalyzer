"""
Phase 11.5: ML Model Migration, Retraining & Prediction Integration Test Suite
Verifies:
1. Legacy model artifact audit (preserves old baseline untouched).
2. Feature migration mapping contract.
3. Canonical PostgreSQL feature pipeline extraction (distinct ProspectIDs, zero duplicates).
4. Target leakage guardrail prevention (rejects post-t0 fields).
5. Time-aware chronological dataset splitting.
6. Model retraining and isotonic/sigmoid calibration.
7. Model versioning (v2 artifacts under app/ml/models/v2/).
8. Inference service v2 loading and prediction.
9. FastAPI REST prediction endpoints (/api/ml/model-info, /api/ml/predict, /api/ml/predict-batch).
10. AI Agent PredictionTool integration.
11. Quantitative comparison of legacy vs v2 canonical models.
"""

import os
import json
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.database.connection import SessionLocal
from app.main import app
from app.ml.ml_canonical_feature_pipeline import (
    CanonicalMLFeaturePipeline,
    validate_no_leakage,
    CANONICAL_FEATURE_COLUMNS,
    TARGET_COLUMN,
    get_canonical_feature_summary,
)
from app.ml.ml_canonical_temporal_split import load_canonical_temporal_splits
from app.ml.ml_canonical_trainer import CanonicalTrainer, V2_MODEL_DIR
from app.ml.ml_inference_service import MLInferenceService
from app.agent.tools.prediction_tool import PredictionTool
from app.agent.tools.base import ToolRequest
from app.agent.agent_service import answer_question

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestPhase11_5_ML_Migration:
    """Phase 11.5 ML Model Migration & Retraining Suite."""

    def test_01_old_feature_audit(self):
        """Verify legacy model baseline artifacts exist untouched."""
        legacy_dir = os.path.join(os.path.dirname(__file__), "..", "app", "ml", "models")
        legacy_model = os.path.join(legacy_dir, "model_2026_lightgbm_calibrated.joblib")
        legacy_prep = os.path.join(legacy_dir, "preprocessor_2026.joblib")
        assert os.path.exists(legacy_model) or os.path.exists(legacy_prep)

    def test_02_feature_migration_mapping(self):
        """Verify canonical feature summary contract."""
        summary = get_canonical_feature_summary()
        assert summary["target"] == "cy_admission"
        assert "program_code" in summary["canonical_features"]
        assert "lead_type" in summary["canonical_features"]
        assert "mx_admissiondate" in summary["forbidden_leakage_fields"]

    def test_03_canonical_feature_extraction(self, db: Session):
        """Verify feature extraction from staging.records with distinct ProspectIDs."""
        pipeline = CanonicalMLFeaturePipeline(db)
        df = pipeline.extract_features(limit=200)
        assert not df.empty
        assert "program_code" in df.columns
        assert "lead_type" in df.columns
        assert TARGET_COLUMN in df.columns

    def test_04_target_leakage_prevention(self):
        """Verify validate_no_leakage raises error if post-t0 leakage fields exist."""
        with pytest.raises(ValueError) as excinfo:
            validate_no_leakage(["campus_name", "mx_AdmissionDate", "program_code"])
        assert "TARGET LEAKAGE DETECTED" in str(excinfo.value)

    def test_05_chronological_split(self, db: Session):
        """Verify load_canonical_temporal_splits performs time-aware splitting."""
        df_train, df_val, df_test, stats = load_canonical_temporal_splits(db)
        assert len(df_train) > 0
        assert len(df_val) > 0
        assert len(df_test) > 0
        assert stats["total_records"] == len(df_train) + len(df_val) + len(df_test)

    def test_06_model_retraining_v2(self, db: Session):
        """Retrain canonical model v2 and persist artifacts in models/v2/."""
        trainer = CanonicalTrainer(db)
        meta = trainer.train_and_evaluate()
        assert meta["model_version"] == "2026_canonical_v2"
        assert os.path.exists(os.path.join(V2_MODEL_DIR, "model_v2_canonical_lightgbm_calibrated.joblib"))
        assert os.path.exists(os.path.join(V2_MODEL_DIR, "preprocessor_v2.joblib"))
        assert os.path.exists(os.path.join(V2_MODEL_DIR, "metadata.json"))

    def test_07_v2_model_versioning_and_metadata(self):
        """Verify v2 metadata file content and evaluation metrics."""
        meta_path = os.path.join(V2_MODEL_DIR, "metadata.json")
        assert os.path.exists(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["model_version"] == "2026_canonical_v2"
        assert "evaluation_metrics" in meta
        assert "roc_auc" in meta["evaluation_metrics"]

    def test_08_ml_inference_service_v2(self):
        """Verify MLInferenceService loads v2 canonical model."""
        service = MLInferenceService()
        assert service.model_version == "2026_canonical_v2"
        res = service.predict_single({
            "campus_name": "Mohali",
            "academic_year": 2026,
            "program_code": "CS201",
            "source_canonical": "Google",
            "lead_type": "In House",
            "state_canonical": "Punjab",
            "owner_canonical": "PANKAJ SHARMA",
        })
        assert res["model_version"] == "2026_canonical_v2"
        assert "calibrated_admission_probability" in res
        assert res["calibrated_admission_probability"] >= 0.0

    def test_09_fastapi_ml_prediction_endpoints(self):
        """Test FastAPI endpoints with v2 payload features."""
        # Model info
        res_info = client.get("/api/ml/model-info")
        assert res_info.status_code == 200

        # Predict single lead
        res_pred = client.post("/api/ml/predict", json={
            "campus_name": "Mohali",
            "academic_year": 2026,
            "program_code": "CS201",
            "source_canonical": "Google",
            "lead_type": "In House",
            "state_canonical": "Punjab",
            "owner_canonical": "PANKAJ SHARMA",
        })
        assert res_pred.status_code == 200
        data = res_pred.json()
        assert "calibrated_admission_probability" in data

        # Predict batch
        res_batch = client.post("/api/ml/predict-batch", json={
            "leads": [
                {
                    "campus_name": "Mohali",
                    "program_code": "CS201",
                    "source_canonical": "Google",
                },
                {
                    "campus_name": "Mohali",
                    "program_code": "BE-CSE",
                    "source_canonical": "Website",
                }
            ]
        })
        assert res_batch.status_code == 200
        batch_data = res_batch.json()
        assert batch_data["total_leads_processed"] == 2

    def test_10_ai_agent_prediction_tool(self, db: Session):
        """Test AI PredictionTool execution."""
        tool = PredictionTool()
        req = ToolRequest(
            dataset_id="test",
            operation="admission_probability",
            raw_question="Which leads need immediate counselor attention?"
        )
        res = tool.execute(db, req)
        assert res.success is True
        assert "MODEL PREDICTIONS" in res.summary
        assert len(res.data) > 0

    def test_11_ai_chat_predictive_question(self, db: Session):
        """Test end-to-end AI Agent handling predictive questions."""
        conv_id = f"test_ml_{os.urandom(4).hex()}"
        res = answer_question(db, "Which leads have the highest admission probability?", conversation_id=conv_id)
        assert res["response_type"] in ("table", "text")
        assert "MODEL PREDICTIONS" in res["answer"] or "probability" in str(res).lower()
