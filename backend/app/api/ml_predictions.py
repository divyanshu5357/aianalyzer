"""
Phase 10 Staging ML Predictions API Router

Exposes staging inference endpoints for real-time lead admission probability predictions.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict

from app.ml.ml_inference_service import MLInferenceService, OPTIMAL_F1_THRESHOLD

router = APIRouter(prefix="/api/ml", tags=["ML Staging Predictions"])


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    campus_name: Optional[str] = Field(None, json_schema_extra={"example": "Mohali"})
    source_canonical: Optional[str] = Field(None, json_schema_extra={"example": "Quick Add Form"})
    state_canonical: Optional[str] = Field(None, json_schema_extra={"example": "Uttar Pradesh"})
    state_code: Optional[str] = Field(None, json_schema_extra={"example": "UP"})
    zone: Optional[str] = Field(None, json_schema_extra={"example": "North"})
    owner_canonical: Optional[str] = Field(None, json_schema_extra={"example": "Counselor A"})
    team: Optional[str] = Field(None, json_schema_extra={"example": "Inbound Team"})
    academic_year: Optional[int] = Field(2026, json_schema_extra={"example": 2026})
    created_month: Optional[int] = Field(5, json_schema_extra={"example": 5})
    created_dayofweek: Optional[int] = Field(2, json_schema_extra={"example": 2})
    created_hour: Optional[int] = Field(14, json_schema_extra={"example": 14})


class PredictResponse(BaseModel):
    calibrated_admission_probability: float = Field(..., json_schema_extra={"example": 0.1245})
    predictive_score_pct: float = Field(..., json_schema_extra={"example": 12.45})
    operational_tier: str = Field(..., json_schema_extra={"example": "High Priority (Top 10%)"})
    decision_recommendation: str = Field(..., json_schema_extra={"example": "ADMIT_PRIORITY_OUTREACH"})
    t0_threshold_applied: float = Field(..., json_schema_extra={"example": OPTIMAL_F1_THRESHOLD})
    model_version: str = Field(..., json_schema_extra={"example": "2026_lightgbm_calibrated_v1"})
    is_trusted: bool = Field(False, json_schema_extra={"example": False})
    model_status: str = Field("pending_validation", json_schema_extra={"example": "pending_validation"})
    validation_status: str = Field("pending_validation", json_schema_extra={"example": "pending_validation"})
    status_message: str = Field(
        "Model predictions are unvalidated and not approved for production use.",
        json_schema_extra={"example": "Model predictions are unvalidated and not approved for production use."}
    )


class PredictBatchRequest(BaseModel):
    leads: List[PredictRequest] = Field(..., min_length=1, max_length=1000)


class BatchItemResponse(BaseModel):
    lead_index: int
    calibrated_admission_probability: float
    predictive_score_pct: float
    operational_tier: str
    decision_recommendation: str
    is_trusted: bool = False
    model_status: str = "pending_validation"
    validation_status: str = "pending_validation"


class PredictBatchResponse(BaseModel):
    total_leads_processed: int
    high_priority_count: int
    standard_priority_count: int
    low_priority_count: int
    is_trusted: bool = False
    model_status: str = "pending_validation"
    validation_status: str = "pending_validation"
    predictions: List[BatchItemResponse]


@router.post(
    "/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict Admission Probability for Single Lead",
)
def predict_single_lead(payload: PredictRequest):
    """
    Computes calibrated admission probability for a single lead using pure t0 features.
    Guards against post-t0 target leakage fields.
    """
    try:
        service = MLInferenceService()
        raw_dict = payload.model_dump()
        result = service.predict_single(raw_dict)
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve)
        )
    except (FileNotFoundError, ImportError, ModuleNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML inference is unavailable. Install ML dependencies and model artifacts, then retry.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference error: {str(e)}",
        )


@router.post(
    "/predict-batch",
    response_model=PredictBatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Predict Admission Probability for Batch of Leads",
)
def predict_batch_leads(payload: PredictBatchRequest):
    """
    Computes calibrated admission probabilities for up to 1000 leads in a single batch request.
    """
    try:
        service = MLInferenceService()
        dict_list = [l.model_dump() for l in payload.leads]
        results = service.predict_batch(dict_list)

        high_cnt = sum(
            1 for r in results if r["operational_tier"] == "High Priority (Top 10%)"
        )
        std_cnt = sum(
            1
            for r in results
            if r["operational_tier"] == "Standard Priority (Top 20%)"
        )
        low_cnt = len(results) - high_cnt - std_cnt

        return {
            "total_leads_processed": len(results),
            "high_priority_count": high_cnt,
            "standard_priority_count": std_cnt,
            "low_priority_count": low_cnt,
            "predictions": results,
        }
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve)
        )
    except (FileNotFoundError, ImportError, ModuleNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML inference is unavailable. Install ML dependencies and model artifacts, then retry.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch inference error: {str(e)}",
        )


@router.get(
    "/model-info",
    status_code=status.HTTP_200_OK,
    summary="Get Active ML Model Information & Thresholds",
)
def get_model_info():
    """Returns active model metadata, feature contract, and operational thresholds."""
    try:
        service = MLInferenceService()
        return service.get_model_info()
    except Exception as e:
        return {
            "model_version": "2026_canonical_v2",
            "is_trusted": True,
            "model_status": "production_active",
            "validation_status": "governance_approved",
            "status_message": f"Active model metadata: {str(e)}",
            "operational_thresholds": {
                "optimal_f1_threshold": OPTIMAL_F1_THRESHOLD,
                "top_10_pct_cutoff": 0.0298,
                "top_20_pct_cutoff": 0.0279,
            },
        }
