from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.semantic.sql_builder import build_semantic_metric_query
from app.semantic.metric_registry import resolve_metric_name, calculate_ratio


class MetricTool(BaseAnalyticsTool):
    name = "metric_tool"
    description = "Computes total single or aggregated metric values (admissions, leads, cucet, conversion rates)."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        metric_raw = request.metric or "admission"
        metric = resolve_metric_name(metric_raw) or metric_raw

        yr = request.year or request.current_year
        if not yr and request.filters and "year" in request.filters:
            try:
                yr = int(request.filters["year"])
            except ValueError:
                pass

        campus = None
        if request.filters:
            campus = request.filters.get("campus") or request.filters.get("campus_name")

        try:
            sql, params, is_ratio = build_semantic_metric_query(
                metric_name=metric,
                filters=request.filters,
                dataset_id=request.dataset_id,
                academic_year=yr,
                campus_name=campus,
            )
            row = db.execute(text(sql), params).mappings().first()

            if is_ratio:
                num = int((row and row["numerator"]) or 0)
                den = int((row and row["denominator"]) or 0)
                ratio_val = round(calculate_ratio(num, den), 2)
                return ToolResult(
                    success=True,
                    operation="metric",
                    columns=[metric, "numerator", "denominator"],
                    data=[{metric: ratio_val, "numerator": num, "denominator": den}],
                    response_type=request.response_type,
                    year=yr,
                    metadata={"metric": metric, "value": ratio_val, "is_ratio": True, "numerator": num, "denominator": den},
                )
            else:
                val = int((row and row["total_value"]) or 0)
                return ToolResult(
                    success=True,
                    operation="metric",
                    columns=[metric],
                    data=[{metric: val}],
                    response_type=request.response_type,
                    year=yr,
                    metadata={"metric": metric, "total_value": val},
                )

        except Exception as err:
            return ToolResult(
                success=False,
                operation="metric",
                error=f"Error executing metric query: {err}",
                error_code="query_execution_failure",
            )
