from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database.connection import get_db
from app.database.ai_audit import (
    query_transcripts,
    evaluate_turn,
    promote_to_golden_case,
    export_transcripts,
    ensure_ai_audit_tables,
)

router = APIRouter(
    prefix="/api/audit",
    tags=["Audit & Evaluations"],
)


class TurnEvaluationRequest(BaseModel):
    message_id: str
    status: str  # unreviewed, correct, incorrect, partially_correct
    correct_answer: Optional[str] = None
    correct_intent: Optional[str] = None
    correct_metric: Optional[str] = None
    correct_dimension: Optional[str] = None
    correct_entities: Optional[List[str]] = None
    correct_period_a: Optional[str] = None
    correct_period_b: Optional[str] = None
    correction_notes: Optional[str] = None
    error_category: Optional[str] = None


class PromoteGoldenCaseRequest(BaseModel):
    question: str
    case_code: Optional[str] = None
    expected_intent: Optional[str] = None
    expected_metric: Optional[str] = None
    expected_dimension: Optional[str] = None
    expected_entities: Optional[List[str]] = None
    expected_periods: Optional[List[str]] = None
    expected_result_characteristics: Optional[Dict[str, Any]] = None
    expected_answer_requirements: Optional[str] = None
    conversation_context: Optional[Dict[str, Any]] = None
    source_message_id: Optional[str] = None


@router.get("/transcripts")
def get_audit_transcripts(
    status: Optional[str] = Query(None, description="Filter by status: unreviewed, correct, incorrect, partially_correct"),
    error_category: Optional[str] = Query(None, description="Filter by error category"),
    dataset_id: Optional[str] = Query(None, description="Filter by active dataset ID"),
    period: Optional[str] = Query(None, description="Filter by academic session period label"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Query system conversation turn transcripts with full execution metadata and evaluation status.
    """
    try:
        results = query_transcripts(
            db,
            status=status,
            error_category=error_category,
            dataset_id=dataset_id,
            period=period,
            limit=limit,
            offset=offset,
        )
        return {"count": len(results), "items": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to query audit transcripts: {exc}")


@router.post("/evaluations")
def create_or_update_turn_evaluation(
    request: TurnEvaluationRequest,
    db: Session = Depends(get_db),
):
    """
    Submit or update a human evaluation/correction for a specific conversation turn.
    """
    try:
        res = evaluate_turn(
            db=db,
            message_id=request.message_id,
            status=request.status,
            correct_answer=request.correct_answer,
            correct_intent=request.correct_intent,
            correct_metric=request.correct_metric,
            correct_dimension=request.correct_dimension,
            correct_entities=request.correct_entities,
            correct_period_a=request.correct_period_a,
            correct_period_b=request.correct_period_b,
            correction_notes=request.correction_notes,
            error_category=request.error_category,
        )
        return {"status": "success", "data": res}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save evaluation: {exc}")


@router.post("/golden-cases/promote")
def promote_case(
    request: PromoteGoldenCaseRequest,
    db: Session = Depends(get_db),
):
    """
    Promote a corrected or key failure case into golden_cases for regression testing.
    """
    try:
        res = promote_to_golden_case(
            db=db,
            question=request.question,
            case_code=request.case_code,
            expected_intent=request.expected_intent,
            expected_metric=request.expected_metric,
            expected_dimension=request.expected_dimension,
            expected_entities=request.expected_entities,
            expected_periods=request.expected_periods,
            expected_result_characteristics=request.expected_result_characteristics,
            expected_answer_requirements=request.expected_answer_requirements,
            conversation_context=request.conversation_context,
            source_message_id=request.source_message_id,
        )
        return {"status": "success", "data": res}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to promote golden case: {exc}")


@router.get("/golden-cases")
def get_golden_cases(
    db: Session = Depends(get_db),
):
    """
    List all golden evaluation regression cases.
    """
    ensure_ai_audit_tables(db)
    try:
        rows = db.execute(
            text(
                """
                SELECT
                    id, case_code, question, conversation_context, expected_intent,
                    expected_metric, expected_dimension, expected_entities, expected_periods,
                    expected_result_characteristics, expected_answer_requirements, source_message_id,
                    created_at, updated_at
                FROM ai_audit.golden_cases
                ORDER BY case_code ASC, created_at DESC
                """
            )
        ).mappings().all()

        items = [dict(r) for r in rows]
        return {"count": len(items), "items": items}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch golden cases: {exc}")


@router.get("/export")
def export_audit_data(
    format: str = Query("jsonl", pattern="^(jsonl|csv)$"),
    status: Optional[str] = Query(None),
    error_category: Optional[str] = Query(None),
    dataset_id: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """
    Export audit logs in JSONL or CSV format.
    """
    try:
        exported_content = export_transcripts(
            db=db,
            format_type=format,
            status=status,
            error_category=error_category,
            dataset_id=dataset_id,
            period=period,
            limit=limit,
        )

        media_type = "text/csv" if format.lower() == "csv" else "application/x-ndjson"
        filename = f"ai_audit_transcripts.{format.lower()}"

        return Response(
            content=exported_content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")
