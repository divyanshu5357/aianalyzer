"""
Report Generator AI Tool
Generates downloadable Excel/CSV report streams for AI chat requests.
"""
from typing import Any
from sqlalchemy.orm import Session

from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult


class ReportGeneratorTool(BaseAnalyticsTool):
    name = "report_generator"
    description = "Generates downloadable Excel/CSV reports for counsellor performance and lead activity."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        q_lower = request.raw_question.lower()
        fmt = "xlsx" if "excel" in q_lower or "xlsx" in q_lower else "csv"
        
        filters = request.filters or {}
        year = filters.get("academic_year") or request.year
        campus = filters.get("campus_name") or request.filters.get("campus")

        query_parts = [f"export_format={fmt}", "report_type=counsellor_performance"]
        if year and year != "all":
            query_parts.append(f"academic_year={year}")
        if campus and campus != "all":
            query_parts.append(f"campus={campus}")

        download_url = f"/api/counsellor/export?{'&'.join(query_parts)}"

        summary_text = (
            f"Generated official **{fmt.upper()} Report** based on your active filters.\n\n"
            f"Click to download: [{fmt.upper()} Counsellor Report]({download_url})"
        )

        data = [
            {
                "report_format": fmt.upper(),
                "report_type": "Counsellor Performance & Activity",
                "status": "Ready for Download",
                "download_url": download_url,
            }
        ]
        columns = ["report_format", "report_type", "status", "download_url"]

        return ToolResult(
            success=True,
            tool=self.name,
            operation="generate_report",
            data=data,
            columns=columns,
            chart_type=None,
            response_type="text",
            metadata={"summary": summary_text},
        )
