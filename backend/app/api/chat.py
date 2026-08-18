from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.agent.agent_service import answer_question
from app.schemas.chat import ChatRequest

router = APIRouter(
    prefix="/api/chat",
    tags=["Chat"],
)


@router.post("")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Answer a natural-language analytics question.
    """

    try:
        result = answer_question(
            db,
            request.question,
            conversation_id=request.conversation_id,
            period_a=request.period_a,
            period_b=request.period_b,
        )


        return result

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {exc}",
        )
