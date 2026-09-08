from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.semantic.sql_builder import build_semantic_breakdown_query
from app.semantic.metric_registry import resolve_metric_name
from app.semantic.dimension_registry import resolve_dimension_name


class BreakdownTool(BaseAnalyticsTool):
    name = "breakdown_tool"
    description = "Computes dimensional breakdown across one or more dimensions."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        dims_raw = request.dimensions or ([request.dimension] if request.dimension else ["source"])
        dim_raw = dims_raw[0] if dims_raw else "source"
        dimension = resolve_dimension_name(dim_raw) or dim_raw
        
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
            sql, params, is_ratio = build_semantic_breakdown_query(
                metric_name=metric,
                dimension_name=dimension,
                filters=request.filters,
                dataset_id=request.dataset_id,
                academic_year=yr,
                campus_name=campus,
                limit=request.limit,
                sort_dir=request.sort_direction or "DESC",
            )

            rows = db.execute(text(sql), params).mappings().all()

            data_rows = []
            col_names = [dimension, metric]

            for r in rows:
                row_dict = {dimension: r[dimension]}
                if is_ratio:
                    row_dict[metric] = float(r["metric_val"] or 0.0)
                else:
                    row_dict[metric] = int(r["metric_val"] or 0)
                data_rows.append(row_dict)

            response_type = request.response_type
            if response_type == "text" and len(data_rows) > 1:
                response_type = "table"

            return ToolResult(
                success=True,
                operation="breakdown",
                columns=col_names,
                data=data_rows,
                response_type=response_type,
                chart_type=request.chart_type,
                year=yr,
                metadata={"dimension": dimension, "metric": metric, "result_count": len(data_rows)},
            )

        except Exception as err:
            return ToolResult(
                success=False,
                operation="breakdown",
                error=f"Error executing breakdown query: {err}",
                error_code="query_execution_failure",
            )
