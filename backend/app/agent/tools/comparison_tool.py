from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.utils import get_metric_column, resolve_canonical_dim, validate_dataset_value


class ComparisonTool(BaseAnalyticsTool):
    name = "comparison_tool"
    description = "Compares metrics between specific entities or categories."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        metric = request.metric or "admission"
        db_metric_col = get_metric_column(metric, request.year, request.current_year, request.previous_year)
        requested_vals = request.values or []

        if not requested_vals:
            return ToolResult(
                success=False,
                operation="comparison",
                error="No comparison values specified.",
                error_code="missing_comparison_values",
            )

        explicit_dim = request.dimension or (request.dimensions[0] if request.dimensions else None)
        cols_to_check = ["main_source", "source", "campus_name", "program_name", "state", "owner", "lead_type", "cluster"]
        if explicit_dim and explicit_dim in cols_to_check:
            cols_to_check = [explicit_dim] + [c for c in cols_to_check if c != explicit_dim]

        # 1. Try to resolve all comparison values under the same column first (preferred)
        best_dim = None
        resolved_mapping = {}

        for col in cols_to_check:
            mapping = {}
            for req in requested_vals:
                valid, matched = validate_dataset_value(db, request.dataset_id, col, req)
                if valid and matched:
                    mapping[req] = matched
            if len(mapping) == len(requested_vals):
                best_dim = col
                resolved_mapping = mapping
                break

        # 2. If same-column check failed, fallback to cross-column resolution
        if not best_dim:
            cross_mapping = {}
            for req in requested_vals:
                for col in cols_to_check:
                    valid, matched = validate_dataset_value(db, request.dataset_id, col, req)
                    if valid and matched:
                        cross_mapping[req] = (col, matched)
                        break
            if len(cross_mapping) == len(requested_vals):
                best_dim = list(cross_mapping.values())[0][0]
                resolved_mapping = cross_mapping
            else:
                missing = [r for r in requested_vals if r not in cross_mapping]
                missing_str = missing[0] if missing else "requested value"
                return ToolResult(
                    success=False,
                    operation="comparison",
                    error=f"Value '{missing_str}' was not found in the active dataset.",
                    error_code="entity_not_found",
                )

        # 3. Construct unified SELECT query
        queries = []
        params = {"ds_id": request.dataset_id}
        
        is_cross_column = isinstance(list(resolved_mapping.values())[0], tuple)
        if is_cross_column:
            stored_vals = [db_val for col, db_val in resolved_mapping.values()]
        else:
            stored_vals = list(resolved_mapping.values())
        
        for idx, req_val in enumerate(requested_vals):
            if is_cross_column:
                col, db_val = resolved_mapping[req_val]
            else:
                col = best_dim
                db_val = resolved_mapping[req_val]
                
            param_key = f"val_{idx}"
            queries.append(
                f"""
                SELECT 
                    :display_val_{idx} AS dim_val,
                    COALESCE(SUM({db_metric_col}), 0) AS metric_val
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds_id AND "{col}" = :{param_key}
                """
            )
            params[f"display_val_{idx}"] = req_val
            params[param_key] = db_val
            
        # Build reverse map of matched db value -> original user display casing
        reverse_map = {}
        for req_val, mapped in resolved_mapping.items():
            if isinstance(mapped, tuple):
                col, db_val = mapped
            else:
                db_val = mapped
            reverse_map[db_val] = req_val

        sql = " UNION ALL ".join(queries)
        rows = db.execute(text(sql), params).mappings().all()

        data_rows = []
        for r in rows:
            db_val = r["dim_val"]
            display_val = reverse_map.get(db_val, db_val)
            data_rows.append({best_dim: display_val, metric: int(r["metric_val"] or 0)})

        response_type = request.response_type
        if response_type == "text" and len(data_rows) > 1:
            response_type = "chart" if request.chart_type else "table"

        return ToolResult(
            success=True,
            operation="comparison",
            columns=[best_dim, metric],
            data=data_rows,
            response_type=response_type,
            chart_type=request.chart_type or ("pie" if response_type == "chart" else None),
            year=request.year or request.current_year,
            metadata={
                "dimension": best_dim,
                "metric": metric,
                "requested_values": requested_vals,
                "resolved_values": stored_vals,
            },
        )
