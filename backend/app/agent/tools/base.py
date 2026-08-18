from abc import ABC, abstractmethod
from typing import Any, Literal
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


class ToolRequest(BaseModel):
    dataset_id: str
    operation: str
    metric: str = "admission"
    dimension: str | None = None
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    values: list[str] = Field(default_factory=list)
    sort_direction: Literal["asc", "desc"] | None = "desc"
    limit: int | None = None
    current_year: int = 2026
    previous_year: int = 2025
    year: int | None = None
    response_type: Literal["text", "table", "chart"] = "text"
    chart_type: Literal["bar", "pie", "line"] | None = None
    direction: Literal["increase", "decrease"] | None = None
    raw_question: str = ""
    period_a: str | None = None
    period_b: str | None = None


class ToolResult(BaseModel):
    success: bool
    operation: str
    columns: list[str] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)
    response_type: str = "text"
    chart_type: str | None = None
    year: int = 2026
    error: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseAnalyticsTool(ABC):
    name: str
    description: str

    @abstractmethod
    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        """Execute analytical calculation using parameterized SQL."""
        pass
