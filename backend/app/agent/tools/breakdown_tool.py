from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.utils import get_metric_column, get_missing_filter_clauses, resolve_canonical_dim, validate_dataset_value


class BreakdownTool(BaseAnalyticsTool):
    name = "breakdown_tool"
    description = "Computes dimensional breakdown across one or more dimensions."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        dims_raw = request.dimensions or ([request.dimension] if request.dimension else ["main_source"])
        metric = request.metric or "admission"
        db_metric_col = get_metric_column(metric, request.year, request.current_year, request.previous_year)

        resolved_dims = []
        for d_raw in dims_raw:
            res_dim = resolve_canonical_dim(db, request.dataset_id, d_raw)
            if not res_dim["resolved"]:
                return ToolResult(
                    success=False,
                    operation="breakdown",
                    error=res_dim.get("error", f"Dimension '{d_raw}' not found."),
                    error_code="dimension_not_found",
                )
            resolved_dims.append((d_raw, res_dim["original_column"]))

        where_clauses = ["dataset_id = :ds_id"]
        
        # Apply missing filter clauses for the breakdown columns
        missing_clauses = get_missing_filter_clauses(request.raw_question, [col for _, col in resolved_dims])
        where_clauses.extend(missing_clauses)
        
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
                        operation="breakdown",
                        error=f"Value '{f_val}' was not found in the active dataset for '{f_dim}'.",
                        error_code="entity_not_found",
                    )

        select_cols = [f'"{col}" AS "{d_raw}"' for d_raw, col in resolved_dims]
        group_cols = [f'"{col}"' for _, col in resolved_dims]

        where_sql = " WHERE " + " AND ".join(where_clauses)
        sql = f"""
        SELECT
            {', '.join(select_cols)},
            COALESCE(SUM({db_metric_col}), 0) AS metric_val
        FROM analytics.uploaded_metrics
        {where_sql}
        GROUP BY {', '.join(group_cols)}
        ORDER BY metric_val DESC
        """

        rows = db.execute(text(sql), params).mappings().all()

        data_rows = []
        col_names = [d[0] for d in resolved_dims] + [metric]

        for r in rows:
            row_dict = {d[0]: r[d[0]] for d in resolved_dims}
            row_dict[metric] = int(r["metric_val"] or 0)
            data_rows.append(row_dict)

        if request.limit and request.limit > 0:
            data_rows = data_rows[:request.limit]

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
            year=request.year or request.current_year,
            metadata={"dimensions": [d[0] for d in resolved_dims], "metric": metric},
        )
