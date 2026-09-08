"""
Target Performance AI Tool
Queries actual vs target achievement from the real Target dataset master workbooks (tgt.xlsx) across Source, Program, and State target sheets.
Identifies entities below target across dimensions dynamically without hardcoding.
"""
import re
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.analytics.target_service import (
    get_target_performance,
    get_program_target_breakdown,
    get_state_target_breakdown,
)


class TargetPerformanceTool(BaseAnalyticsTool):
    name = "target_performance"
    description = "Queries target vs actual performance metrics across Source, Program, and State target dimensions."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        q_lower = request.raw_question.lower()
        filters = request.filters or {}
        campus_val = filters.get("campus_name") or ("Mohali" if "mohali" in q_lower else "All")

        # Determine Target For metric (Lead vs Admission vs CUCET)
        target_for = "Admission"
        if "lead" in q_lower:
            target_for = "Leads"
        elif "cucet" in q_lower:
            target_for = "CUCET"

        # Determine month filter
        month_val = None
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december",
                  "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        for m in months:
            if m in q_lower:
                month_val = m
                break

        # Determine explicit year
        year_val = None
        y_match = re.search(r"\b(20\d{2})\b", q_lower)
        if y_match:
            year_val = int(y_match.group(1))

        # 1. Program-wise Target Breakdown
        if "program" in q_lower or "course" in q_lower:
            res = get_program_target_breakdown(
                db,
                target_for=target_for,
                campus=campus_val,
                month=month_val,
                year=year_val,
                raw_dataset_id=request.dataset_id,
            )
            data = res.get("data", [])
            columns = res.get("columns", ["program_code", "target", "target_for"])

            summary = (
                f"**Program-Wise {target_for} Target Breakdown** ({campus_val} - Month: {month_val or 'All'}):\n"
                f"Showing target allocations across programs. Top program target is **{data[0]['program_code']}** ({data[0]['target']:,.2f})."
                if data else f"No program target data found for {campus_val}."
            )
            return ToolResult(
                success=True,
                tool=self.name,
                operation="program_target",
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": summary, "dataset_id": request.dataset_id},
            )

        # 2. State-wise Target Breakdown
        if "state" in q_lower or "region" in q_lower:
            res = get_state_target_breakdown(
                db,
                target_for=target_for,
                campus=campus_val,
                month=month_val,
                year=year_val,
                raw_dataset_id=request.dataset_id,
            )
            data = res.get("data", [])
            columns = res.get("columns", ["state", "target", "target_for"])

            summary = (
                f"**State-Wise {target_for} Target Breakdown** ({campus_val} - Month: {month_val or 'All'}):\n"
                f"Showing target allocations across states. Top state target is **{data[0]['state']}** ({data[0]['target']:,.2f})."
                if data else f"No state target data found for {campus_val}."
            )
            return ToolResult(
                success=True,
                tool=self.name,
                operation="state_target",
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": summary, "dataset_id": request.dataset_id},
            )

        # 3. Overall Target Lookup & Source-wise Target Performance
        res = get_target_performance(
            db,
            target_for=target_for,
            campus=campus_val,
            month=month_val,
            year=year_val,
            raw_dataset_id=request.dataset_id,
        )

        data = [
            {
                "metric": res["target_for"],
                "target": res["target"],
                "actual": res["actual"],
                "variance": res["variance"],
                "achievement_pct": res["achievement_pct"],
                "campus": res["campus"],
                "month": res["month"],
            }
        ]
        columns = ["metric", "target", "actual", "variance", "achievement_pct", "campus", "month"]

        if res.get("actual_available") is False or res.get("actual") == "N/A":
            summary = (
                f"**{res['target_for']} Target Analysis** ({res['campus']} - Month: {res['month']}):\n"
                f"- **Target**: {res['target']:,.2f}\n"
                f"- **Actual**: N/A (Actual data for {res['month']} {year_val or ''} is not available in the uploaded RAW dataset)\n"
                f"- **Variance**: N/A\n"
                f"- **Achievement**: N/A"
            )
        else:
            summary = (
                f"**{res['target_for']} Target Analysis** ({res['campus']} - Month: {res['month']}):\n"
                f"- **Target**: {res['target']:,.2f}\n"
                f"- **Actual**: {res['actual']:,}\n"
                f"- **Variance**: {res['variance']:,.2f}\n"
                f"- **Achievement**: {res['achievement_pct']}"
            )

        return ToolResult(
            success=True,
            tool=self.name,
            operation="target_lookup",
            data=data,
            columns=columns,
            chart_type="bar",
            response_type="table",
            metadata={"summary": summary, "dataset_id": request.dataset_id},
        )
