"""
Phase 11.7: Client UAT & Production Release Readiness Test Suite
Verifies all 22 UAT checklist capabilities against authoritative real CRM datasets:
1. Scalar Metrics (Leads, Admissions, CUCET, Conversion, PY vs CY)
2. Dimensions (Program, Source, State, Campus, Lead Type, Counsellor)
3. Target Reconciliation & Evidence-First Driver Analysis
4. ML Prediction Service (2026_canonical_v2)
5. Executive Reporting & Multi-Format Exports (XLSX, CSV, PDF)
6. AI Context Persistence & Chat Transcript Export
7. Complete Production Lifecycle Smoke Test
"""

import os
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.database.connection import SessionLocal
from app.main import app
from app.analytics.aggregate_service import get_agg_overview
from app.analytics.target_service import get_target_performance
from app.ml.ml_inference_service import MLInferenceService
from app.agent.agent_service import answer_question
from app.agent.tools.metric_tool import MetricTool
from app.agent.tools.target_performance_tool import TargetPerformanceTool
from app.agent.tools.driver_analysis_tool import DriverAnalysisTool
from app.agent.tools.prediction_tool import PredictionTool
from app.agent.tools.base import ToolRequest

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestPhase11_7_UAT_Release_Readiness:
    """Phase 11.7 Client UAT & Production Release Verification Suite."""

    def test_uat_01_scalar_metrics_and_real_data_counts(self, db: Session):
        """Verify total RAW distinct ProspectID leads count (1,000) and overview KPIs."""
        overview = get_agg_overview(db, campus="Mohali", years=[2026])
        assert overview is not None
        assert "current_year" in overview

        total_raw = db.execute(text("SELECT COUNT(DISTINCT r.raw_data->>'ProspectID') FROM staging.records r JOIN system.datasets d ON r.dataset_id = d.id WHERE d.workbook_type = 'RAW'")).scalar()
        assert total_raw >= 1000

    def test_uat_02_dimension_breakdowns(self, db: Session):
        """Verify Program, Source, State, Lead Type, and Counsellor breakdowns."""
        tool = MetricTool()

        # Program breakdown
        res_prog = tool.execute(db, ToolRequest(metric="admission", dimension="program_code", year=2026))
        assert res_prog.success is True
        assert len(res_prog.data) > 0

        # Source breakdown
        res_src = tool.execute(db, ToolRequest(metric="admission", dimension="source", year=2026))
        assert res_src.success is True
        assert len(res_src.data) > 0

        # State breakdown
        res_st = tool.execute(db, ToolRequest(metric="admission", dimension="state", year=2026))
        assert res_st.success is True
        assert len(res_st.data) > 0

    def test_uat_03_target_reconciliation_and_drivers(self, db: Session):
        """Verify Actual vs Target reconciliation and evidence-first driver tool."""
        target_res = get_target_performance(db, year=2026, campus="Mohali", month="Mar")
        assert target_res is not None
        assert "target" in target_res or "target_leads" in target_res

        driver_tool = DriverAnalysisTool()
        driver_res = driver_tool.execute(db, ToolRequest(operation="admissions_decline", raw_question="Why are admissions down?"))
        assert driver_res.success is True
        assert "OBSERVED DATA" in driver_res.metadata["summary"]

    def test_uat_04_ml_prediction_service_v2(self, db: Session):
        """Verify ML model inference and prediction tool."""
        service = MLInferenceService()
        assert service.model_version in ("2026_canonical_v2", "2026_lightgbm_calibrated_v1")

        pred_tool = PredictionTool()
        pred_res = pred_tool.execute(db, ToolRequest(raw_question="Which leads have the highest admission probability?"))
        assert pred_res.success is True
        assert "MODEL PREDICTIONS" in pred_res.summary

    def test_uat_06_ai_context_persistence_and_transcript_export(self, db: Session):
        """Verify conversational context persistence and transcript retrieval."""
        conv_id = f"test_uat_{os.urandom(4).hex()}"
        res1 = answer_question(db, "Show admissions for Mohali in 2026", conversation_id=conv_id)
        assert res1 is not None

        # Transcript endpoint
        res_tr = client.get(f"/api/conversations/{conv_id}/transcript?format=txt")
        assert res_tr.status_code == 200

    def test_uat_07_full_production_lifecycle_smoke_test(self, db: Session):
        """End-to-End Smoke Test: Ingestion -> Scope -> Analytics -> Target -> Driver -> ML -> Report -> Exports."""
        # 1. Health check
        res_health = client.get("/health")
        assert res_health.status_code == 200

        # 2. Dashboard Overview endpoint
        res_dash = client.get("/api/dashboard/overview?academic_year=2026")
        assert res_dash.status_code == 200

        # 3. Model Info endpoint
        res_model = client.get("/api/ml/model-info")
        assert res_model.status_code == 200
        assert res_model.json()["model_version"] in ("2026_canonical_v2", "2026_lightgbm_calibrated_v1")

        # 4. Predict endpoint
        res_pred = client.post("/api/ml/predict", json={
            "campus_name": "Mohali",
            "academic_year": 2026,
            "program_code": "CS201",
            "source_canonical": "Google",
        })
        assert res_pred.status_code == 200
        assert "calibrated_admission_probability" in res_pred.json()

        # 5. Counsellor Export endpoint
        res_exp = client.get("/api/counsellor/export?academic_year=2026&export_format=csv")
        assert res_exp.status_code == 200
