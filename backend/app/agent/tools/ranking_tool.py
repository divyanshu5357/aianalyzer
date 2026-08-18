from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.utils import get_metric_column, get_missing_filter_clauses, resolve_canonical_dim, validate_dataset_value


class RankingTool(BaseAnalyticsTool):
    name = "ranking_tool"
    description = "Ranks entities (top N or bottom N) by a specified metric."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        dim_raw = request.dimension or (request.dimensions[0] if request.dimensions else "owner")
        metric = request.metric or "admission"
        db_metric_col = get_metric_column(metric, request.year, request.current_year, request.previous_year)
        sort_dir = "DESC" if (request.sort_direction or "desc").lower() == "desc" else "ASC"
        limit = request.limit or 1

        res_dim = resolve_canonical_dim(db, request.dataset_id, dim_raw)
        if not res_dim["resolved"]:
            return ToolResult(
                success=False,
                operation="ranking",
                error=res_dim.get("error", f"Dimension '{dim_raw}' not found."),
                error_code="dimension_not_found",
            )
        orig_col = res_dim["original_column"]

        where_clauses = ["dataset_id = :ds_id"]
        
        # Apply missing filter clauses for the ranking column
        missing_clauses = get_missing_filter_clauses(request.raw_question, [orig_col])
        where_clauses.extend(missing_clauses)
        
        params = {"ds_id": request.dataset_id, "limit": limit}

        for f_dim, f_val in request.filters.items():
            res_f = resolve_canonical_dim(db, request.dataset_id, f_dim)
            if res_f["resolved"]:
                f_col = res_f["original_column"]
                valid, matched_val = validate_dataset_value(db, request.dataset_id, f_col, str(f_val))
                if valid:
                    param_key = f"filter_{f_col}"
                    where_clauses.append(f'"{f_col}" = :{param_key}')
                    params[param_key] = matched_val
                else:
                    return ToolResult(
                        success=False,
                        operation="ranking",
                        error=f"Value '{f_val}' was not found in the active dataset for '{f_dim}'.",
                        error_code="entity_not_found",
                    )

        where_sql = " WHERE " + " AND ".join(where_clauses)
        sql = f"""
        SELECT
            "{orig_col}" AS entity_name,
            COALESCE(SUM({db_metric_col}), 0) AS metric_val
        FROM analytics.uploaded_metrics
        {where_sql}
        GROUP BY "{orig_col}"
        ORDER BY metric_val {sort_dir}
        LIMIT :limit
        """

        rows = db.execute(text(sql), params).mappings().all()

        data_rows = []
        for r in rows:
            data_rows.append({dim_raw: r["entity_name"], metric: int(r["metric_val"] or 0)})

        response_type = request.response_type
        if response_type == "text" and limit > 1:
            response_type = "table"

        return ToolResult(
            success=True,
            operation="ranking",
            columns=[dim_raw, metric],
            data=data_rows,
            response_type=response_type,
            chart_type=request.chart_type,
            year=request.year or request.current_year,
            metadata={"dimension": dim_raw, "metric": metric, "limit": limit, "sort_direction": sort_dir},
        )
