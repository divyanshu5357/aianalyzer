"""
Source Category AI Tool
Calculates Inhouse vs Outsource lead breakdowns, Inhouse top owner performance,
and conversion rate rankings dynamically using organization.source_master (Source_ms dimension).
Strictly 100% data-driven from PostgreSQL without hardcoded source lists.
"""
import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult

logger = logging.getLogger(__name__)


class SourceCategoryTool(BaseAnalyticsTool):
    name = "source_category"
    description = "Analyzes Inhouse vs Outsource leads, admissions, conversion rates, and top owners dynamically using Source_ms dimension."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        ds_id = request.dataset_id
        if not ds_id:
            from app.database.repository import get_active_dataset
            ds_id = get_active_dataset(db)

        if not ds_id:
            return ToolResult(
                success=False,
                tool=self.name,
                operation=request.operation or "source_category",
                data=[],
                columns=[],
                error="No active dataset is available. Please upload/select a dataset.",
                metadata={"summary": "No active dataset is available. Please upload/select a dataset."},
            )

        op = (request.operation or "inhouse_vs_outsource").lower()

        # 1. Top Owners for Inhouse Sources (Lead Type = 'In House' from Source_ms)
        if op == "top_owners_inhouse" or "owner" in request.raw_question.lower():
            sql = text("""
                SELECT
                    r.raw_data->>'OwnerIdName' as owner_name,
                    COUNT(DISTINCT r.raw_data->>'ProspectID') as total_leads,
                    SUM(CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN 1 ELSE 0 END) as total_admissions
                FROM staging.records r
                JOIN organization.source_master sm
                  ON LOWER(TRIM(COALESCE(r.raw_data->>'MSSourcebi', r.raw_data->>'Source', ''))) = LOWER(TRIM(sm.source))
                WHERE r.dataset_id = :ds_id
                  AND LOWER(TRIM(sm.lead_type)) = 'in house'
                  AND NULLIF(TRIM(r.raw_data->>'OwnerIdName'), '') IS NOT NULL
                GROUP BY 1
                ORDER BY total_admissions DESC, total_leads DESC
                LIMIT 10;
            """)
            rows = db.execute(sql, {"ds_id": str(ds_id)}).mappings().all()
            data = []
            for r in rows:
                leads = int(r["total_leads"] or 0)
                adms = int(r["total_admissions"] or 0)
                conv = round((adms / leads * 100.0), 2) if leads > 0 else 0.0
                data.append({
                    "owner": r["owner_name"],
                    "inhouse_leads": leads,
                    "inhouse_admissions": adms,
                    "conversion_rate": f"{conv}%",
                })
            columns = ["owner", "inhouse_leads", "inhouse_admissions", "conversion_rate"]
            top_owner = data[0]["owner"] if data else "N/A"
            top_adms = data[0]["inhouse_admissions"] if data else 0

            summary = (
                f"**Top Inhouse Owners Performance** (Active Dataset: {ds_id}):\n"
                f"Top owner for Inhouse leads (Lead Type: In House) is **{top_owner}** with {top_adms} admissions. "
                f"Showing top {len(data)} owners."
            )
            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": summary, "dataset_id": str(ds_id), "sql_query": str(sql)},
            )

        # 2. Highest Conversion Rate Ranking
        elif op == "highest_conversion_rate" or ("conversion" in request.raw_question.lower() and "owner" in request.raw_question.lower()):
            sql = text("""
                SELECT
                    r.raw_data->>'OwnerIdName' as owner_name,
                    COUNT(DISTINCT r.raw_data->>'ProspectID') as total_leads,
                    SUM(CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN 1 ELSE 0 END) as total_admissions
                FROM staging.records r
                WHERE r.dataset_id = :ds_id
                  AND NULLIF(TRIM(r.raw_data->>'OwnerIdName'), '') IS NOT NULL
                GROUP BY 1
                HAVING COUNT(DISTINCT r.raw_data->>'ProspectID') >= 5
                ORDER BY (SUM(CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN 1.0 ELSE 0.0 END) / COUNT(DISTINCT r.raw_data->>'ProspectID')) DESC
                LIMIT 10;
            """)
            rows = db.execute(sql, {"ds_id": str(ds_id)}).mappings().all()
            data = []
            for r in rows:
                leads = int(r["total_leads"] or 0)
                adms = int(r["total_admissions"] or 0)
                conv = round((adms / leads * 100.0), 2) if leads > 0 else 0.0
                data.append({
                    "owner": r["owner_name"],
                    "total_leads": leads,
                    "admissions": adms,
                    "conversion_rate": f"{conv}%",
                })
            columns = ["owner", "total_leads", "admissions", "conversion_rate"]
            top_owner = data[0]["owner"] if data else "N/A"
            top_conv = data[0]["conversion_rate"] if data else "0%"

            summary = (
                f"**Counsellors Conversion Rate Leaderboard** (Active Dataset: {ds_id}):\n"
                f"Highest conversion rate owner is **{top_owner}** with **{top_conv}** conversion rate."
            )
            return ToolResult(
                success=True,
                tool=self.name,
                operation=op,
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata={"summary": summary, "dataset_id": str(ds_id), "sql_query": str(sql)},
            )

        # 3. Sources by Lead Type Query (e.g. "Which sources are Out Sourced?")
        q_raw = request.raw_question.lower()
        if "which sources" in q_raw or "sources are" in q_raw or "sources for" in q_raw or "sources in" in q_raw:
            target_lt = "Out Sourced" if ("out" in q_raw or "sourced" in q_raw) else "In House"
            sql = text("""
                SELECT DISTINCT source, lead_type
                FROM organization.source_master
                WHERE LOWER(TRIM(lead_type)) = LOWER(TRIM(:lt))
                ORDER BY source ASC;
            """)
            rows = db.execute(sql, {"lt": target_lt}).mappings().all()
            sources_list = [r["source"] for r in rows]
            data = [{"source": s, "lead_type": target_lt} for s in sources_list]
            summary = f"The following **{len(sources_list)}** sources belong to Lead Type **{target_lt}**:\n" + ", ".join([f"`{s}`" for s in sources_list])
            return ToolResult(
                success=True,
                tool=self.name,
                operation="sources_by_lead_type",
                data=data,
                columns=["source", "lead_type"],
                response_type="table",
                metadata={"summary": summary, "dataset_id": str(ds_id), "sql_query": str(sql)},
            )

        # 4. Default: Inhouse vs Outsource Comparison (grouped dynamically by Source_ms.Lead Type)
        else:
            # Dynamic query for In House and Out Sourced categories
            sql = text("""
                SELECT
                    COALESCE(sm.lead_type, 'Unmapped') as lead_category,
                    COUNT(DISTINCT r.raw_data->>'ProspectID') as total_leads,
                    SUM(CASE WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN 1 ELSE 0 END) as total_admissions
                FROM staging.records r
                LEFT JOIN organization.source_master sm
                  ON LOWER(TRIM(COALESCE(r.raw_data->>'MSSourcebi', r.raw_data->>'Source', ''))) = LOWER(TRIM(sm.source))
                WHERE r.dataset_id = :ds_id
                GROUP BY 1
                ORDER BY total_leads DESC;
            """)
            rows = db.execute(sql, {"ds_id": str(ds_id)}).mappings().all()

            data = []
            summary_parts = []
            reconciliation_map = {}
            total_raw_leads = 0

            for r in rows:
                category = r["lead_category"]
                leads = int(r["total_leads"] or 0)
                adms = int(r["total_admissions"] or 0)
                conv = round((adms / leads * 100.0), 2) if leads > 0 else 0.0
                total_raw_leads += leads
                reconciliation_map[category] = leads

                data.append({
                    "category": category,
                    "leads": leads,
                    "admissions": adms,
                    "conversion_rate": f"{conv}%",
                })
                summary_parts.append(f"- **{category}**: {leads:,} leads, {adms:,} admissions ({conv}% conv)")

            columns = ["category", "leads", "admissions", "conversion_rate"]

            # If user asked for a specific single category (e.g., "Show total In House leads" or "Show total Others leads")
            target_cat = None
            if not ("vs" in q_raw or "versus" in q_raw or "compare" in q_raw):
                if "total in house" in q_raw or "show total in house" in q_raw or "total inhouse" in q_raw:
                    target_cat = "In House"
                elif "total out sourced" in q_raw or "show total out sourced" in q_raw or "total outsourced" in q_raw:
                    target_cat = "Out Sourced"
                elif "total others" in q_raw or "others lead" in q_raw or "show total others" in q_raw or "show others" in q_raw:
                    target_cat = "Others"

            if target_cat:
                filtered_data = [d for d in data if d["category"].lower() == target_cat.lower()]
                if filtered_data:
                    cat_item = filtered_data[0]
                    summary = f"There are **{cat_item['leads']:,}** {target_cat} leads ({cat_item['admissions']:,} admissions, {cat_item['conversion_rate']} conversion rate)."
                    return ToolResult(
                        success=True,
                        tool=self.name,
                        operation="lead_category_total",
                        data=filtered_data,
                        columns=columns,
                        chart_type="bar",
                        response_type="table",
                        metadata={"summary": summary, "dataset_id": str(ds_id), "sql_query": str(sql)},
                    )

            summary = (
                f"**Lead Type Categories & Conversion Breakdown** (Source_ms Master Mapping | Dataset: {ds_id}):\n"
                + "\n".join(summary_parts)
            )

            # Dynamic reconciliation metadata (100% computed from database)
            inhouse_cnt = reconciliation_map.get("In House", 0)
            outsource_cnt = reconciliation_map.get("Out Sourced", 0)
            others_cnt = reconciliation_map.get("Others", 0)
            unmapped_cnt = reconciliation_map.get("Unmapped", 0)
            discrepancy_cnt = others_cnt + unmapped_cnt

            reconciled_meta = {
                "summary": summary,
                "dataset_id": str(ds_id),
                "sql_query": str(sql),
                "reconciliation": {
                    "total_raw_leads": total_raw_leads,
                    "inhouse_leads": inhouse_cnt,
                    "outsource_leads": outsource_cnt,
                    "others_leads": others_cnt,
                    "unmapped_leads": unmapped_cnt,
                    "sum_all_categories": sum(reconciliation_map.values()),
                    "discrepancy_leads": discrepancy_cnt,
                }
            }

            return ToolResult(
                success=True,
                tool=self.name,
                operation="inhouse_vs_outsource",
                data=data,
                columns=columns,
                chart_type="bar",
                response_type="table",
                metadata=reconciled_meta,
            )
