from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult


class FunnelTool(BaseAnalyticsTool):
    name = "funnel_tool"
    description = "Computes conversion funnels across lead lifecycle stages."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        query = text(
            """
            SELECT
                COALESCE(SUM(cy_leads), 0) AS total_leads,
                COALESCE(SUM(cy_cucet), 0) AS total_cucet,
                COALESCE(SUM(cy_admission), 0) AS total_admissions
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :ds_id
            """
        )
        row = db.execute(query, {"ds_id": request.dataset_id}).mappings().first()

        leads = int((row and row["total_leads"]) or 0)
        cucet = int((row and row["total_cucet"]) or 0)
        admissions = int((row and row["total_admissions"]) or 0)

        cucet_rate = round((cucet / leads * 100.0), 2) if leads > 0 else 0.0
        adm_rate = round((admissions / leads * 100.0), 2) if leads > 0 else 0.0
        cucet_to_adm_rate = round((admissions / cucet * 100.0), 2) if cucet > 0 else 0.0

        funnel_data = [
            {"stage": "1. Leads", "count": leads, "conversion_rate (%)": 100.0},
            {"stage": "2. CUCET Registered", "count": cucet, "conversion_rate (%)": cucet_rate},
            {"stage": "3. Admissions", "count": admissions, "conversion_rate (%)": adm_rate},
        ]

        return ToolResult(
            success=True,
            operation="funnel",
            columns=["stage", "count", "conversion_rate (%)"],
            data=funnel_data,
            response_type="table",
            year=request.current_year,
            metadata={
                "leads": leads,
                "cucet": cucet,
                "admissions": admissions,
                "lead_to_cucet_rate": cucet_rate,
                "lead_to_admission_rate": adm_rate,
                "cucet_to_admission_rate": cucet_to_adm_rate,
            },
        )
