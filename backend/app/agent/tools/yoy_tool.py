from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.utils import resolve_canonical_dim, validate_dataset_value
from app.analytics.period_resolver import compare_periods

class YoYTool(BaseAnalyticsTool):
    name = "yoy_tool"
    description = "Computes Year-over-Year metric and conversion rate changes across entities."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        dim_col = request.dimension or (request.dimensions[0] if request.dimensions else "program_name")
        direction = request.direction or "decrease"
        limit = request.limit or 50
        metric = request.metric or "admission"

        if request.period_a and request.period_b:
            try:
                res = compare_periods(db, metric, request.period_a, request.period_b, dim_col, limit=limit)
                
                # Filter by direction
                processed = res["data"]
                
                if request.filters and dim_col in request.filters:
                    f_val = str(request.filters[dim_col]).lower()
                    processed = [x for x in processed if f_val in str(x["name"]).lower()]
                    
                if direction == "decrease":
                    filtered = [x for x in processed if x.get("rate_change_percentage_points", x.get("absolute_change", 0)) < 0]
                    if not filtered:
                        filtered = [x for x in processed if x.get("absolute_change", 0) < 0]
                    if not filtered:
                        filtered = list(processed)
                    filtered.sort(key=lambda x: (x.get("rate_change_percentage_points", 0), x.get("absolute_change", 0)))
                else:
                    filtered = [x for x in processed if x.get("rate_change_percentage_points", x.get("absolute_change", 0)) > 0]
                    if not filtered:
                        filtered = [x for x in processed if x.get("absolute_change", 0) > 0]
                    if not filtered:
                        filtered = list(processed)
                    filtered.sort(key=lambda x: (x.get("rate_change_percentage_points", 0), x.get("absolute_change", 0)), reverse=True)

                if limit and limit > 0:
                    filtered = filtered[:limit]

                # Map back to ToolResult format for natural language
                final_data = []
                for x in filtered:
                    row = {
                        dim_col: x["name"],
                        "previous_year_leads": 0,
                        "current_year_leads": 0,
                        "previous_year_admissions": x["period_b_value"],
                        "current_year_admissions": x["period_a_value"],
                        "previous_year_admission_rate": x.get("period_b_rate", 0),
                        "current_year_admission_rate": x.get("period_a_rate", 0),
                        "admission_change": x["absolute_change"],
                        "rate_change": x.get("rate_change_percentage_points", 0),
                    }
                    if metric == "leads":
                        row["previous_year_leads"] = x["period_b_value"]
                        row["current_year_leads"] = x["period_a_value"]
                        
                    final_data.append(row)

                return ToolResult(
                    success=True,
                    operation="yoy",
                    columns=[dim_col, "previous_year_leads", "current_year_leads", "previous_year_admissions", "current_year_admissions", "previous_year_admission_rate", "current_year_admission_rate", "admission_change", "rate_change"],
                    data=final_data,
                    response_type="table",
                )
            except Exception as e:
                return ToolResult(success=False, operation="yoy", error=str(e), error_code="compare_error")
                
        res_dim = resolve_canonical_dim(db, request.dataset_id, dim_col)
        if not res_dim["resolved"]:
            return ToolResult(
                success=False,
                operation="yoy",
                error=res_dim.get("error", f"Dimension '{dim_col}' not found."),
                error_code="dimension_not_found",
            )
        orig_col = res_dim["original_column"]

        query = text(
            f"""
            SELECT
                "{orig_col}" AS entity_val,
                COALESCE(SUM(py_leads), 0) AS py_leads,
                COALESCE(SUM(cy_leads), 0) AS cy_leads,
                COALESCE(SUM(py_admission), 0) AS py_admission,
                COALESCE(SUM(cy_admission), 0) AS cy_admission
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :ds_id AND "{orig_col}" IS NOT NULL AND TRIM("{orig_col}") != ''
            GROUP BY "{orig_col}"
            """
        )
        rows = db.execute(query, {"ds_id": request.dataset_id}).mappings().all()

        if not rows:
            return ToolResult(
                success=False,
                operation="yoy",
                error=f"No {dim_col} records found in active dataset.",
                error_code="no_data",
            )

        processed = []
        for r in rows:
            ent_name = str(r["entity_val"]).strip()
            py_l = float(r["py_leads"] or 0)
            cy_l = float(r["cy_leads"] or 0)
            py_a = float(r["py_admission"] or 0)
            cy_a = float(r["cy_admission"] or 0)

            py_rate = round((py_a / py_l * 100.0), 2) if py_l > 0 else 0.0
            cy_rate = round((cy_a / cy_l * 100.0), 2) if cy_l > 0 else 0.0
            rate_change = round(cy_rate - py_rate, 2)
            adm_change = int(cy_a - py_a)

            processed.append({
                dim_col: ent_name,
                "previous_year_leads": int(py_l),
                "current_year_leads": int(cy_l),
                "previous_year_admissions": int(py_a),
                "current_year_admissions": int(cy_a),
                "previous_year_admission_rate": py_rate,
                "current_year_admission_rate": cy_rate,
                "admission_change": adm_change,
                "rate_change": rate_change,
            })

        if request.filters and dim_col in request.filters:
            f_val = str(request.filters[dim_col]).lower()
            matched = [x for x in processed if f_val in str(x[dim_col]).lower()]
            if matched:
                processed = matched

        if direction == "decrease":
            filtered = [x for x in processed if x["rate_change"] < 0]
            if not filtered:
                filtered = [x for x in processed if x["admission_change"] < 0]
            if not filtered:
                filtered = list(processed)
            filtered.sort(key=lambda x: (x["rate_change"], x["admission_change"]))
        else:
            filtered = [x for x in processed if x["rate_change"] > 0]
            if not filtered:
                filtered = [x for x in processed if x["admission_change"] > 0]
            if not filtered:
                filtered = list(processed)
            filtered.sort(key=lambda x: (x["rate_change"], x["admission_change"]), reverse=True)

        if limit and limit > 0:
            filtered = filtered[:limit]

        columns = [
            dim_col,
            "previous_year_leads",
            "current_year_leads",
            "previous_year_admissions",
            "current_year_admissions",
            "previous_year_admission_rate",
            "current_year_admission_rate",
            "admission_change",
            "rate_change",
        ]

        return ToolResult(
            success=True,
            operation="yoy",
            columns=columns,
            data=filtered,
            response_type=request.response_type or "table",
            chart_type=request.chart_type,
            year=request.year or request.current_year,
            metadata={
                "dimension": dim_col,
                "direction": direction,
                "limit": limit,
                "total_matched": len(filtered),
            },
        )
