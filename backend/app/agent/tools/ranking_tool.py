from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.semantic.sql_builder import build_semantic_breakdown_query
from app.semantic.metric_registry import resolve_metric_name
from app.semantic.dimension_registry import resolve_dimension_name


class RankingTool(BaseAnalyticsTool):
    name = "ranking_tool"
    description = "Ranks top N or bottom N entities by a metric."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        dim_raw = request.dimension or (request.dimensions[0] if request.dimensions else "program_name")
        dimension = resolve_dimension_name(dim_raw) or dim_raw
        
        metric_raw = request.metric or "admission"
        metric = resolve_metric_name(metric_raw) or metric_raw

        limit = request.limit or 1
        sort_dir = request.sort_direction or "DESC"
        if request.direction == "lowest":
            sort_dir = "ASC"

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
                limit=limit,
                sort_dir=sort_dir,
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
                operation="ranking",
                columns=col_names,
                data=data_rows,
                response_type=response_type,
                chart_type=request.chart_type,
                year=yr,
                metadata={"dimension": dimension, "metric": metric, "limit": limit, "result_count": len(data_rows)},
            )

        except Exception as err:
            return ToolResult(
                success=False,
                operation="ranking",
                error=f"Error executing ranking query: {err}",
                error_code="query_execution_failure",
            )
