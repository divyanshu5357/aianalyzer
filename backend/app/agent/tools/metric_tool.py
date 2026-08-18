from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.utils import get_metric_column, resolve_canonical_dim, validate_dataset_value


class MetricTool(BaseAnalyticsTool):
    name = "metric_tool"
    description = "Computes total single or aggregated metric values (admissions, leads, cucet)."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        metric = request.metric or "admission"
        db_metric_col = get_metric_column(metric, request.year, request.current_year, request.previous_year)

        where_clauses = ["dataset_id = :ds_id"]
        params = {"ds_id": request.dataset_id}

        for f_dim, f_val in request.filters.items():
            res_dim = resolve_canonical_dim(db, request.dataset_id, f_dim)
            if res_dim["resolved"]:
                orig_col = res_dim["original_column"]
                valid, matched_val = validate_dataset_value(db, request.dataset_id, orig_col, str(f_val))
                if valid:
                    param_key = f"filter_{orig_col}"
                    where_clauses.append(f'"{orig_col}" = :{param_key}')
                    params[param_key] = matched_val
                else:
                    return ToolResult(
                        success=False,
                        operation="metric",
                        error=f"Value '{f_val}' was not found in the active dataset for '{f_dim}'.",
                        error_code="entity_not_found",
                    )

        where_sql = " WHERE " + " AND ".join(where_clauses)
        query = text(
            f"""
            SELECT COALESCE(SUM({db_metric_col}), 0) AS total_val
            FROM analytics.uploaded_metrics
            {where_sql}
            """
        )
        try:
            val = int(db.execute(query, params).scalar() or 0)
        except Exception:
            val = 0

        return ToolResult(
            success=True,
            operation="metric",
            columns=[metric],
            data=[{metric: val}],
            response_type=request.response_type,
            year=request.year or request.current_year,
            metadata={"metric": metric, "total_value": val},
        )
