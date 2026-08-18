import logging
from typing import Any
from sqlalchemy.orm import Session

from app.agent.tools.base import ToolRequest, ToolResult
from app.agent.tools.metric_tool import MetricTool
from app.agent.tools.breakdown_tool import BreakdownTool
from app.agent.tools.ranking_tool import RankingTool
from app.agent.tools.comparison_tool import ComparisonTool
from app.agent.tools.yoy_tool import YoYTool
from app.agent.tools.funnel_tool import FunnelTool
from app.agent.tools.filter_tool import FilterTool
from app.agent.tools.driver_analysis_tool import DriverAnalysisTool

logger = logging.getLogger(__name__)


def route_and_execute_plan(
    db: Session,
    plan: dict[str, Any],
    active_dataset: str,
    current_year: int = 2026,
    previous_year: int = 2025,
    raw_question: str = "",
    period_a: str | None = None,
    period_b: str | None = None,
) -> ToolResult:
    """
    Generic Tool Router:
    plan -> validate -> select tool -> execute -> structured result (ToolResult)
    """
    intent = plan.get("intent") or "metric"
    operation = plan.get("operation") or intent

    metric = plan.get("metric") or "admission"
    dimension = plan.get("dimension")
    dimensions = plan.get("dimensions") or ([dimension] if dimension else [])
    
    raw_filters = plan.get("filters", {})
    filters_dict = {}
    if isinstance(raw_filters, list):
        for f in raw_filters:
            if isinstance(f, dict) and "dimension" in f and "value" in f:
                filters_dict[f["dimension"]] = f["value"]
            elif hasattr(f, "dimension") and hasattr(f, "value"):
                filters_dict[f.dimension] = f.value
    elif isinstance(raw_filters, dict):
        filters_dict = raw_filters

    values = plan.get("values") or (plan.get("comparison_info", {}).get("requested_values") if isinstance(plan.get("comparison_info"), dict) else []) or []
    sort_dir = plan.get("sort") or "desc"
    limit = plan.get("limit")
    direction = plan.get("direction")
    response_type = plan.get("response_type") or "text"
    chart_type = plan.get("chart_type")

    plan_year = plan.get("year")
    if not plan_year:
        tc = plan.get("time_context")
        if tc:
            if str(tc).isdigit():
                plan_year = int(tc)
            elif tc == "previous_year":
                plan_year = previous_year
            elif tc == "current_year":
                plan_year = current_year

    tool_req = ToolRequest(
        dataset_id=str(active_dataset),
        operation=operation,
        metric=metric,
        dimension=dimension,
        dimensions=dimensions,
        filters=filters_dict,
        values=values,
        sort_direction=sort_dir,
        limit=limit,
        current_year=current_year,
        previous_year=previous_year,
        year=plan_year,
        response_type=response_type,
        chart_type=chart_type,
        direction=direction,
        raw_question=raw_question,
        period_a=period_a,
        period_b=period_b,
    )

    # 1. Routing to Appropriate Tool
    if operation in ("ranking",) or intent == "ranking":
        tool = RankingTool()
    elif operation in ("comparison",) or intent == "comparison":
        tool = ComparisonTool()
    elif operation in ("yoy", "yoy_change") or intent == "yoy_change":
        tool = YoYTool()
    elif operation in ("funnel",) or intent == "funnel":
        tool = FunnelTool()
    elif operation in ("breakdown",) or intent == "breakdown" or len(dimensions) > 1:
        tool = BreakdownTool()
    elif operation in ("filter",):
        tool = FilterTool()
    elif operation in ("driver_analysis",) or intent == "driver_analysis":
        tool = DriverAnalysisTool()
    else:
        # Default to breakdown if dimension specified, otherwise metric
        if dimensions or dimension:
            tool = BreakdownTool()
        else:
            tool = MetricTool()

    logger.info(f"Routing question '{raw_question}' to {tool.name} (operation: {operation})")
    return tool.execute(db, tool_req)
