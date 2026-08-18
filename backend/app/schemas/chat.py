from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    period_a: str | None = None
    period_b: str | None = None
