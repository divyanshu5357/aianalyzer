import json
import logging
from typing import Any, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from app.config.settings import settings

logger = logging.getLogger(__name__)


class DimensionFilter(BaseModel):
    dimension: str
    value: str


class GeminiPlan(BaseModel):
    intent: Literal[
        "metric",
        "breakdown",
        "comparison",
        "ranking",
        "yoy_change",
        "funnel",
        "followup_operation",
        "causal_inquiry",
        "ambiguous",
        "unsupported",
        "unknown",
    ]
    operation: (
        Literal[
            "metric",
            "breakdown",
            "comparison",
            "ranking",
            "yoy",
            "funnel",
            "filter",
            "followup",
            "causal",
            "ambiguous",
            "unsupported",
            "unknown",
        ]
        | None
    ) = None
    metric: (
        Literal[
            "leads",
            "cucet",
            "admission",
            "lead_cucet_rate",
            "lead_admission_rate",
            "cucet_admission_rate",
            "conversion_rate",
        ]
        | None
    ) = None
    dimension: (
        Literal[
            "main_source",
            "source",
            "sub_source",
            "cluster",
            "lead_type",
            "campus_name",
            "state",
            "program_name",
            "owner",
        ]
        | None
    ) = None
    dimensions: list[str] = Field(default_factory=list)
    filters: list[DimensionFilter] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    sort: Literal["asc", "desc"] | None = None
    direction: Literal["increase", "decrease"] | None = None
    limit: int | None = None
    year: int | None = None
    response_type: Literal["text", "table", "chart"] = "text"
    chart_type: Literal["bar", "pie", "line"] | None = None
    reference_to_previous_result: bool = False
    operation_on_previous_result: (
        Literal["top_n", "bottom_n", "select_entity", "compare", "format_change", "filter", "recalculate", "sort"]
        | None
    ) = None
    causal_request: bool = False
    is_ambiguous: bool = False
    is_unsupported: bool = False


SYSTEM_INSTRUCTION = """
You are an AI Analytics Intent Planner.
Analyze natural language questions about organization metrics and produce a structured JSON plan for tool execution.

STRICT CLASSIFICATION RULES:

1. UNSUPPORTED QUESTIONS:
- If the question asks for information outside the metrics dataset domain (e.g. weather, president of a country, employee salary/satisfaction, stock prices, contracts, invoices, external politics, general trivia):
  Set intent="unsupported", operation="unsupported", is_unsupported=true.

2. AMBIGUOUS / INSUFFICIENT QUESTIONS:
- If the question is an incomplete, garbled, or vague analytics request without specifying what to compare, rank, or measure (e.g., "asdf xyz", "analyze something", "tell me performance", "show data"):
  Set intent="ambiguous", operation="ambiguous", is_ambiguous=true.

3. CAUSAL INQUIRIES:
- If the question asks "why", "reason for", "because of", "what caused", or asks for causal proof of an increase/decrease:
  Set intent="causal_inquiry", operation="causal", causal_request=true.

4. RANKING QUERIES:
- Questions asking for top/bottom/highest/lowest/most/least (e.g. "who brought the most admissions?", "top 5 programs by admissions", "counsellor with highest admissions"):
  Set intent="ranking", operation="ranking", sort="desc" or "asc", limit accordingly.

5. COMPARISON QUERIES:
- Questions comparing specific named entities or categories (e.g. "Mohali vs Chandigarh", "compare Direct and Indirect"):
  Set intent="comparison", operation="comparison", values=["val1", "val2"].

6. YOY / RATE CHANGE QUERIES:
- Questions asking about YoY changes, improvements, drops, declines (e.g. "which courses lost conversion", "which counsellor improved most"):
  Set intent="yoy_change", operation="yoy", direction="increase" or "decrease".

7. BREAKDOWN & METRIC QUERIES:
- Questions asking for dimensional breakdowns (e.g. "leads by source"): set intent="breakdown", operation="breakdown".
- Questions asking for overall metric totals (e.g. "how many admissions"): set intent="metric", operation="metric".

NATURAL LANGUAGE GUIDELINES:
- "main source", "category", "lead type" -> "main_source"
- "channel", "source cluster", "source" -> "source"
- "program", "course" -> "program_name"
- "campus", "location" -> "campus_name"
- "owner", "counselor", "counsellor" -> "owner"
- "state" -> "state"

Return JSON matching the schema ONLY.
"""


def _fallback_plan() -> dict[str, Any]:
    """Return safe unknown intent when Gemini planning fails or key is unconfigured."""
    return GeminiPlan(
        intent="unknown",
        operation="unknown",
        metric=None,
        dimension=None,
        values=[],
        year=None,
        response_type="text",
        chart_type=None,
    ).model_dump()


import time
import httpx
from google.genai import errors

_gemini_cooldown_until = 0.0


def plan_question(question: str) -> dict[str, Any] | None:
    """
    Plan a natural-language question using Gemini LLM.
    Returns structured JSON dict. Does not crash on failure.
    """
    global _gemini_cooldown_until

    if not settings.gemini_enabled:
        return None

    if not settings.gemini_api_key:
        logger.warning("Gemini API key is not configured.")
        return None

    now = time.time()
    if now < _gemini_cooldown_until:
        logger.info("Gemini planner unavailable; using local planner.")
        return None

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiPlan,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        max_retries = 2
        response = None

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=settings.gemini_model,
                    contents=question,
                    config=config,
                )
                break
            except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Gemini call timed out, retrying once... (Attempt {attempt+1})")
                    continue
                else:
                    logger.error(f"Gemini call timed out after retry: {e}. Falling back to local planner.")
                    return None
            except httpx.RequestError as e:
                logger.error(f"Gemini network request error: {e}. Falling back to local planner.")
                return None

        if not response or not response.text:
            logger.warning("Gemini returned empty response text.")
            return None

        parsed = json.loads(response.text)
        plan = GeminiPlan(**parsed)
        return plan.model_dump()

    except errors.APIError as e:
        if e.code == 429:
            _gemini_cooldown_until = time.time() + settings.gemini_cooldown_seconds
            logger.warning(
                f"Gemini planner disabled temporarily: 429 RESOURCE_EXHAUSTED cooldown={settings.gemini_cooldown_seconds}s"
            )
        elif e.code == 503:
            # Transient overload — back off for 5 minutes
            _gemini_cooldown_until = time.time() + 300
            logger.warning(
                "Gemini planner unavailable: 503 UNAVAILABLE (high demand). "
                "Falling back to local planner for 5 minutes."
            )
        elif e.code in (400, 403):
            _gemini_cooldown_until = time.time() + 86400  # 1 day
            logger.warning(
                f"Gemini planner disabled: API key or model error (code {e.code}). Disabling Gemini."
            )
        else:
            logger.error(f"Gemini planner server error: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini planner encountered an error: {type(e).__name__} - {e}")
        return None


