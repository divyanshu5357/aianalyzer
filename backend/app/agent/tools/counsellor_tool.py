"""
Counsellor & Call Activity AI Tool
Queries trusted PostgreSQL counsellor metrics for AI chat requests.
"""
from typing import Any
from sqlalchemy.orm import Session

from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.analytics.counsellor_service import (
    get_counsellor_summary,
    get_lead_activity,
)


class CounsellorTool(BaseAnalyticsTool):
    name = "counsellor"
    description = "Queries trusted PostgreSQL counsellor performance, call attempts, and follow-up metrics."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        op = (request.operation or "counsellor_performance").lower()
        filters = request.filters or {}
        campus_val = filters.get("campus_name") or filters.get("campus") or filters.get("unknown_dim")

        # 1. No Call Leads ("never called", "0 calls")
        if op == "no_call_leads" or "never" in request.raw_question.lower() or "no call" in request.raw_question.lower():
            res = get_counsellor_summary(db, campus=campus_val)
            c_list = res.get("counsellors", [])
            # Filter counsellors with 0-call leads
            no_call_counsellors = [c for c in c_list if c.get("calls_0", 0) > 0 or c.get("calls_1", 0) == 0]
            if not no_call_counsellors:
                no_call_counsellors = c_list[:10]

            data = [
                {
                    "counsellor": c["counsellor"],
                    "employee_id": c["employee_id"],
                    "leads_assigned": c["leads_assigned"],
                    "0_call_leads": c["calls_0"],
                    "1_call_leads": c["calls_1"],
                    "total_calls": c["total_calls"],
                }
                for c in no_call_counsellors
            ]
            columns = ["counsellor", "employee_id", "leads_assigned", "0_call_leads", "1_call_leads", "total_calls"]
            top_c = data[0]["counsellor"] if data else "N/A"
            top_0_calls = data[0]["0_call_leads"] if data else 0

            answer = f"Found {len(data)} counsellors with leads assigned. Top counsellor by uncalled/low-call leads is {top_c} with {top_0_calls} leads having 0 calls."
            
            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": answer},
            )

        # 2. Overdue Interested Follow-ups
        elif op == "overdue_interested" or "overdue" in request.raw_question.lower():
            res = get_counsellor_summary(db, campus=campus_val)
            c_list = res.get("counsellors", [])
            overdue_list = sorted(c_list, key=lambda x: x.get("overdue_followups", 0), reverse=True)

            data = [
                {
                    "counsellor": c["counsellor"],
                    "employee_id": c["employee_id"],
                    "overdue_followups": c["overdue_followups"],
                    "interested_leads": c["interested_leads"],
                    "leads_assigned": c["leads_assigned"],
                    "conversion_rate": f"{c['conversion_rate']}%",
                }
                for c in overdue_list[:10]
            ]
            columns = ["counsellor", "employee_id", "overdue_followups", "interested_leads", "leads_assigned", "conversion_rate"]
            top_c = data[0]["counsellor"] if data else "N/A"
            top_cnt = data[0]["overdue_followups"] if data else 0

            answer = f"Counsellor {top_c} has the highest number of overdue follow-ups ({top_cnt} overdue leads). Total {sum(c['overdue_followups'] for c in overdue_list)} overdue follow-up leads identified across counsellors."

            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": answer},
            )

        # 3. Time to First Call
        elif op == "time_to_first_call" or "time" in request.raw_question.lower():
            res = get_counsellor_summary(db, campus=campus_val)
            c_list = res.get("counsellors", [])
            time_list = [c for c in c_list if c.get("avg_time_to_first_call_hours") is not None]
            time_list = sorted(time_list, key=lambda x: x.get("avg_time_to_first_call_hours", 0), reverse=True)

            data = [
                {
                    "counsellor": c["counsellor"],
                    "employee_id": c["employee_id"],
                    "avg_time_to_first_call_hrs": c["avg_time_to_first_call_hours"],
                    "leads_assigned": c["leads_assigned"],
                    "total_calls": c["total_calls"],
                }
                for c in (time_list[:10] if time_list else c_list[:10])
            ]
            columns = ["counsellor", "employee_id", "avg_time_to_first_call_hrs", "leads_assigned", "total_calls"]
            top_c = data[0]["counsellor"] if data else "N/A"
            top_hrs = data[0]["avg_time_to_first_call_hrs"] if data else "N/A"

            answer = f"Counsellor {top_c} has the highest average time to first call ({top_hrs} hours)."

            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": answer},
            )

        # 4. Lowest Average Calls
        elif op == "lowest_avg_calls" or "lowest average call" in request.raw_question.lower() or "lowest call" in request.raw_question.lower():
            from app.analytics.counsellor_service import get_lowest_avg_calls
            ds_id = request.dataset_id
            res = get_lowest_avg_calls(db, dataset_id=ds_id)
            c_list = res.get("counsellors", [])
            data = [
                {
                    "owner": c["owner"],
                    "assigned_leads": c["assigned_leads"],
                    "total_calls": c["total_calls"],
                    "avg_calls_per_lead": c["avg_calls_per_lead"],
                }
                for c in c_list
            ]
            columns = ["owner", "assigned_leads", "total_calls", "avg_calls_per_lead"]
            top_c = data[0]["owner"] if data else "N/A"
            top_avg = data[0]["avg_calls_per_lead"] if data else 0.0

            answer = f"Owner **{top_c}** has the lowest average call attempts per lead ({top_avg} calls/lead)."
            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": answer, "dataset_id": str(ds_id)},
            )

        # 5. Call Attempt Distribution / Specific Call Buckets (e.g. "exactly 1 call")
        elif op == "call_attempts" or "exactly" in request.raw_question.lower() or "call attempt" in request.raw_question.lower():
            bucket = "1" if "1 call" in request.raw_question.lower() or "one call" in request.raw_question.lower() else "all"
            leads_res = get_lead_activity(db, attempt_bucket=bucket, campus=campus_val, page=1, page_size=20)
            l_list = leads_res.get("leads", [])

            data = [
                {
                    "prospect_id": l["prospect_id"],
                    "counsellor": l["owner_name"],
                    "program": l["program_name"],
                    "total_attempts": l["total_call_attempts"],
                    "first_disposition": l.get("first_call_disposition") or "N/A",
                    "followup_status": l.get("followup_status"),
                }
                for l in l_list
            ]
            columns = ["prospect_id", "counsellor", "program", "total_attempts", "first_disposition", "followup_status"]
            cnt = leads_res.get("total_leads", 0)

            answer = f"Found {cnt} total leads matching the call attempt criteria. Showing top {len(data)} lead records."

            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": answer},
            )

        # 5. Default: Counsellor Performance Summary
        else:
            res = get_counsellor_summary(db, campus=campus_val)
            c_list = res.get("counsellors", [])

            data = [
                {
                    "counsellor": c["counsellor"],
                    "employee_id": c["employee_id"],
                    "leads_assigned": c["leads_assigned"],
                    "total_calls": c["total_calls"],
                    "admissions": c["admissions"],
                    "conversion_rate": f"{c['conversion_rate']}%",
                }
                for c in c_list[:15]
            ]
            columns = ["counsellor", "employee_id", "leads_assigned", "total_calls", "admissions", "conversion_rate"]
            kpis = res.get("summary_kpis", {})

            answer = f"Retrieved performance metrics for {kpis.get('total_counsellors', 0)} active counsellors ({kpis.get('total_leads_assigned', 0)} total leads assigned, {kpis.get('total_admissions', 0)} admissions, overall conversion {kpis.get('overall_conversion_rate', 0)}%)."

            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": answer},
            )
