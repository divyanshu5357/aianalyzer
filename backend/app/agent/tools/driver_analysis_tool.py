import logging
import math
import os
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.agent.tools.utils import resolve_canonical_dim, validate_dataset_value

logger = logging.getLogger(__name__)

MIN_INSIGHT_LEADS = int(os.getenv("MIN_INSIGHT_LEADS", "10"))


class DriverAnalysisTool(BaseAnalyticsTool):
    name = "driver_analysis_tool"
    description = "Performs a contribution and driver analysis for an entity whose performance changed."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        entity_dim = request.dimension or "program_name"
        limit_n = request.limit or 5

        if not request.values:
            # Try to see if there is a filter on entity_dim
            val = request.filters.get(entity_dim)
            if val:
                request.values = [str(val)]
            else:
                return ToolResult(
                    success=False,
                    operation="driver_analysis",
                    error="No entity specified for driver analysis. Please specify which program, campus, counsellor or source you are analyzing.",
                    error_code="missing_entity",
                )

        entity = request.values[0]

        # 1. Resolve canonical dimension for entity
        res_dim = resolve_canonical_dim(db, request.dataset_id, entity_dim)
        if not res_dim["resolved"]:
            return ToolResult(
                success=False,
                operation="driver_analysis",
                error=f"Could not resolve dimension '{entity_dim}' in the active dataset.",
                error_code="invalid_dimension",
            )
        db_entity_col = res_dim["original_column"]

        # Validate entity value
        ok, matched_entity = validate_dataset_value(db, request.dataset_id, db_entity_col, entity)
        if not ok or not matched_entity:
            return ToolResult(
                success=False,
                operation="driver_analysis",
                error=f"Entity '{entity}' was not found in the active dataset for '{entity_dim}'.",
                error_code="entity_not_found",
            )

        # 2. Query overall totals for the target entity
        totals_sql = text(
            f"""
            SELECT
                COALESCE(SUM(cy_leads), 0) AS cy_leads,
                COALESCE(SUM(py_leads), 0) AS py_leads,
                COALESCE(SUM(cy_admission), 0) AS cy_admission,
                COALESCE(SUM(py_admission), 0) AS py_admission,
                COALESCE(SUM(cy_cucet), 0) AS cy_cucet,
                COALESCE(SUM(py_cucet), 0) AS py_cucet
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :ds_id AND "{db_entity_col}" = :entity_val
            """
        )
        try:
            totals_row = db.execute(totals_sql, {"ds_id": request.dataset_id, "entity_val": matched_entity}).mappings().first()
        except Exception as e:
            db.rollback()
            return ToolResult(
                success=False,
                operation="driver_analysis",
                error=f"Failed to query performance totals: {str(e)}",
                error_code="database_error",
            )

        if not totals_row or (totals_row["cy_leads"] == 0 and totals_row["py_leads"] == 0 and totals_row["cy_admission"] == 0 and totals_row["py_admission"] == 0):
            return ToolResult(
                success=False,
                operation="driver_analysis",
                error=f"No metric data found for '{matched_entity}' in the active dataset.",
                error_code="no_data",
            )

        cy_leads = int(totals_row["cy_leads"] or 0)
        py_leads = int(totals_row["py_leads"] or 0)
        cy_admission = int(totals_row["cy_admission"] or 0)
        py_admission = int(totals_row["py_admission"] or 0)

        cy_conv = round((cy_admission / cy_leads * 100), 2) if cy_leads > 0 else 0.0
        py_conv = round((py_admission / py_leads * 100), 2) if py_leads > 0 else 0.0

        leads_change = cy_leads - py_leads
        leads_growth = round((leads_change / py_leads * 100), 2) if py_leads > 0 else 0.0

        admission_change = cy_admission - py_admission
        admission_growth = round((admission_change / py_admission * 100), 2) if py_admission > 0 else 0.0

        conv_change = round(cy_conv - py_conv, 2)

        # 3. Group by other dimensions
        cols_to_group = ["source", "main_source", "owner", "campus_name", "state"]
        cols_to_group = [c for c in cols_to_group if c != db_entity_col]

        group_data = {}
        for grp_col in cols_to_group:
            grp_sql = text(
                f"""
                SELECT
                    COALESCE("{grp_col}", 'UNKNOWN') AS category,
                    COALESCE(SUM(cy_leads), 0) AS cy_leads,
                    COALESCE(SUM(py_leads), 0) AS py_leads,
                    COALESCE(SUM(cy_admission), 0) AS cy_admission,
                    COALESCE(SUM(py_admission), 0) AS py_admission,
                    COALESCE(SUM(cy_cucet), 0) AS cy_cucet,
                    COALESCE(SUM(py_cucet), 0) AS py_cucet
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds_id AND "{db_entity_col}" = :entity_val
                GROUP BY "{grp_col}"
                """
            )
            try:
                rows = db.execute(grp_sql, {"ds_id": request.dataset_id, "entity_val": matched_entity}).mappings().all()
                group_data[grp_col] = []
                for r in rows:
                    c_cy_l = int(r["cy_leads"] or 0)
                    c_py_l = int(r["py_leads"] or 0)
                    c_cy_a = int(r["cy_admission"] or 0)
                    c_py_a = int(r["py_admission"] or 0)

                    c_cy_conv = round((c_cy_a / c_cy_l * 100), 2) if c_cy_l > 0 else 0.0
                    c_py_conv = round((c_py_a / c_py_l * 100), 2) if c_py_l > 0 else 0.0

                    c_l_chg = c_cy_l - c_py_l
                    c_l_growth = round((c_l_chg / c_py_l * 100), 2) if c_py_l > 0 else 0.0

                    c_a_chg = c_cy_a - c_py_a
                    c_a_growth = round((c_a_chg / c_py_a * 100), 2) if c_py_a > 0 else 0.0

                    c_conv_chg = round(c_cy_conv - c_py_conv, 2)

                    # Mix/Share analysis
                    c_cy_share = round((c_cy_a / cy_admission * 100), 2) if cy_admission > 0 else 0.0
                    c_py_share = round((c_py_a / py_admission * 100), 2) if py_admission > 0 else 0.0
                    c_share_chg = round(c_cy_share - c_py_share, 2)

                    group_data[grp_col].append({
                        "category": r["category"],
                        "cy_leads": c_cy_l,
                        "py_leads": c_py_l,
                        "leads_change": c_l_chg,
                        "leads_growth": c_l_growth,
                        "cy_admission": c_cy_a,
                        "py_admission": c_py_a,
                        "admission_change": c_a_chg,
                        "admission_growth": c_a_growth,
                        "cy_conv": c_cy_conv,
                        "py_conv": c_py_conv,
                        "conv_change": c_conv_chg,
                        "cy_share": c_cy_share,
                        "py_share": c_py_share,
                        "share_change": c_share_chg,
                    })
            except Exception as e:
                db.rollback()
                logger.warning(f"Error grouping driver by column '{grp_col}': {e}")

        # 4. Synthesize Driver Report
        text_parts = []
        is_improvement = admission_change >= 0

        # Performance Change Table
        text_parts.append("### Performance change\n")
        text_parts.append("| Metric | Previous Year | Current Year | Change |")
        text_parts.append("|---|---:|---:|---:|")
        text_parts.append(f"| Leads | {py_leads:,} | {cy_leads:,} | {'+' if leads_change >= 0 else ''}{leads_change:,} ({'+' if leads_growth >= 0 else ''}{leads_growth:.2f}%) |")
        text_parts.append(f"| Admissions | {py_admission:,} | {cy_admission:,} | {'+' if admission_change >= 0 else ''}{admission_change:,} ({'+' if admission_growth >= 0 else ''}{admission_growth:.2f}%) |")
        text_parts.append(f"| Admission rate | {py_conv:.2f}% | {cy_conv:.2f}% | {'+' if conv_change >= 0 else ''}{conv_change:.2f} pp |")
        text_parts.append("")

        # 5. Anomaly checks & Driver summaries
        observations = []
        driver_items = []

        # Lead Volume Driver
        driver_items.append({
            "driver": "Lead volume change",
            "prev": f"{py_leads:,} leads",
            "curr": f"{cy_leads:,} leads",
            "change": f"{'+' if leads_change >= 0 else ''}{leads_change:,} ({'+' if leads_growth >= 0 else ''}{leads_growth:.2f}%)",
            "abs_chg": abs(leads_change),
        })

        # Conversion efficiency
        driver_items.append({
            "driver": "Conversion efficiency",
            "prev": f"{py_conv:.2f}% rate",
            "curr": f"{cy_conv:.2f}% rate",
            "change": f"{'+' if conv_change >= 0 else ''}{conv_change:.2f} pp",
            "abs_chg": abs(conv_change) * 1000, # scale up to rank on equal footing
        })

        # Process each group column to get top contributor & Mix change
        for col, data in group_data.items():
            if not data:
                continue
            
            # Sort by absolute admissions change
            sorted_by_change = sorted(data, key=lambda x: abs(x["admission_change"]), reverse=True)
            top_category = sorted_by_change[0]
            cat_name = top_category["category"]
            cat_chg = top_category["admission_change"]
            cat_cy = top_category["cy_admission"]
            cat_py = top_category["py_admission"]
            cat_cy_l = top_category["cy_leads"]

            col_label = col.replace("_", " ").title()
            sample_tag = " (Low sample size)" if cat_cy_l < MIN_INSIGHT_LEADS else ""
            driver_items.append({
                "driver": f"Top {col_label} ({cat_name}){sample_tag}",
                "prev": f"{cat_py:,} adm",
                "curr": f"{cat_cy:,} adm",
                "change": f"{'+' if cat_chg >= 0 else ''}{cat_chg:,} adm",
                "abs_chg": abs(cat_chg),
            })

            # Check for anomalies — enforce MIN_INSIGHT_LEADS threshold
            for item in data:
                i_name = item["category"]
                # 1. Unusually strong lead growth but conversion rate declined
                if item["cy_leads"] >= MIN_INSIGHT_LEADS and item["leads_change"] > 0 and item["leads_growth"] >= 50.0 and item["conv_change"] <= -5.0:
                    observations.append(
                        f"**Notable Anomaly**: {col_label} '{i_name}' showed unusually strong lead growth (+{item['leads_growth']:.1f}%) "
                        f"but conversion rate declined by {abs(item['conv_change']):.2f} percentage points."
                    )
                # 2. Low lead volume but exceptionally high conversion rate (must meet MIN_INSIGHT_LEADS)
                if item["cy_leads"] >= MIN_INSIGHT_LEADS and item["cy_leads"] < (cy_leads * 0.05) and item["cy_conv"] > (cy_conv * 1.5):
                    observations.append(
                        f"**Notable Performance**: {col_label} '{i_name}' has relatively low lead volume ({item['cy_leads']:,}) "
                        f"but unusually high conversion efficiency ({item['cy_conv']:.2f}% vs overall {cy_conv:.2f}%)."
                    )

        # Sort driver items by absolute impact
        driver_items.sort(key=lambda x: x["abs_chg"], reverse=True)

        text_parts.append("### Strongest associated drivers\n")
        text_parts.append("| Driver | Previous | Current | Change |")
        text_parts.append("|---|---:|---:|---:|")
        for d in driver_items[:5]:
            text_parts.append(f"| {d['driver']} | {d['prev']} | {d['curr']} | {d['change']} |")
        text_parts.append("")

        sections = []
        sections.append({
            "type": "metric_table",
            "title": "Performance Change",
            "columns": ["Metric", "Previous Year", "Current Year", "Change"],
            "data": [
                {
                    "Metric": "Leads",
                    "Previous Year": f"{py_leads:,}",
                    "Current Year": f"{cy_leads:,}",
                    "Change": f"{'+' if leads_change >= 0 else ''}{leads_change:,} ({'+' if leads_growth >= 0 else ''}{leads_growth:.2f}%)",
                },
                {
                    "Metric": "Admissions",
                    "Previous Year": f"{py_admission:,}",
                    "Current Year": f"{cy_admission:,}",
                    "Change": f"{'+' if admission_change >= 0 else ''}{admission_change:,} ({'+' if admission_growth >= 0 else ''}{admission_growth:.2f}%)",
                },
                {
                    "Metric": "Admission Rate",
                    "Previous Year": f"{py_conv:.2f}%",
                    "Current Year": f"{cy_conv:.2f}%",
                    "Change": f"{'+' if conv_change >= 0 else ''}{conv_change:.2f} pp",
                },
            ],
        })

        sections.append({
            "type": "driver_table",
            "title": "Strongest Associated Drivers",
            "columns": ["Driver", "Previous", "Current", "Change"],
            "data": [
                {
                    "Driver": d["driver"],
                    "Previous": d["prev"],
                    "Current": d["curr"],
                    "Change": d["change"],
                }
                for d in driver_items[:5]
            ],
        })

        # 6. Detailed Dimension Breakdowns for TOP N contributions
        # Group by main_source or source
        src_col = "source" if "source" in group_data else ("main_source" if "main_source" in group_data else None)
        if src_col and group_data[src_col]:
            src_data = group_data[src_col]
            # Admissions growth contributors
            growth_contribs = sorted([s for s in src_data if s["admission_change"] != 0], key=lambda x: x["admission_change"], reverse=True)
            
            if growth_contribs:
                top_growers = growth_contribs[:limit_n]
                dir_label = "GROWTH" if is_improvement else "DECLINE"
                text_parts.append(f"### Top {len(top_growers)} Admission {dir_label} Sources\n")
                text_parts.append("| Source | PY Admissions | CY Admissions | Change | CY Share | Share Change |")
                text_parts.append("|---|---:|---:|---:|---:|---:|")
                for s in top_growers:
                    text_parts.append(
                        f"| {s['category']} | {s['py_admission']:,} | {s['cy_admission']:,} | "
                        f"{'+' if s['admission_change'] >= 0 else ''}{s['admission_change']:,} | "
                        f"{s['cy_share']:.2f}% | {'+' if s['share_change'] >= 0 else ''}{s['share_change']:.2f} pp |"
                    )
                text_parts.append("")

                sections.append({
                    "type": "metric_table",
                    "title": f"Top {len(top_growers)} Admission {dir_label} Sources",
                    "columns": ["Source", "PY Admissions", "CY Admissions", "Change", "CY Share", "Share Change"],
                    "data": [
                        {
                            "Source": s["category"],
                            "PY Admissions": f"{s['py_admission']:,}",
                            "CY Admissions": f"{s['cy_admission']:,}",
                            "Change": f"{'+' if s['admission_change'] >= 0 else ''}{s['admission_change']:,}",
                            "CY Share": f"{s['cy_share']:.2f}%",
                            "Share Change": f"{'+' if s['share_change'] >= 0 else ''}{s['share_change']:.2f} pp",
                        }
                        for s in top_growers
                    ],
                })

                # Add share mix observations
                for s in top_growers[:2]:
                    if abs(s["share_change"]) >= 1.0:
                        direction = "larger" if s["share_change"] >= 0 else "smaller"
                        observations.append(
                            f"**Share Mix Shift**: Source '{s['category']}' became a {direction} contributor to {matched_entity} admissions, "
                            f"shifting its admission share from {s['py_share']:.2f}% to {s['cy_share']:.2f}% "
                            f"({'+' if s['share_change'] >= 0 else ''}{s['share_change']:.2f} pp)."
                        )

        # Campus Contributions
        if "campus_name" in group_data and group_data["campus_name"]:
            top_campuses = sorted(group_data["campus_name"], key=lambda x: abs(x["admission_change"]), reverse=True)[:3]
            if top_campuses:
                text_parts.append("### Geographical Contribution (Campus Name)\n")
                text_parts.append("| Location | PY Admissions | CY Admissions | Change | CY Share |")
                text_parts.append("|---|---:|---:|---:|---:|")
                for g in top_campuses:
                    text_parts.append(f"| {g['category']} | {g['py_admission']:,} | {g['cy_admission']:,} | {'+' if g['admission_change'] >= 0 else ''}{g['admission_change']:,} | {g['cy_share']:.2f}% |")
                text_parts.append("")

                sections.append({
                    "type": "metric_table",
                    "title": "Geographical Contribution (Campus Name)",
                    "columns": ["Location", "PY Admissions", "CY Admissions", "Change", "CY Share"],
                    "data": [
                        {
                            "Location": g["category"],
                            "PY Admissions": f"{g['py_admission']:,}",
                            "CY Admissions": f"{g['cy_admission']:,}",
                            "Change": f"{'+' if g['admission_change'] >= 0 else ''}{g['admission_change']:,}",
                            "CY Share": f"{g['cy_share']:.2f}%",
                        }
                        for g in top_campuses
                    ],
                })

        # State Contributions
        if "state" in group_data and group_data["state"]:
            top_states = sorted(group_data["state"], key=lambda x: abs(x["admission_change"]), reverse=True)[:3]
            if top_states:
                text_parts.append("### Geographical Contribution (State)\n")
                text_parts.append("| Location | PY Admissions | CY Admissions | Change | CY Share |")
                text_parts.append("|---|---:|---:|---:|---:|")
                for g in top_states:
                    text_parts.append(f"| {g['category']} | {g['py_admission']:,} | {g['cy_admission']:,} | {'+' if g['admission_change'] >= 0 else ''}{g['admission_change']:,} | {g['cy_share']:.2f}% |")
                text_parts.append("")

                sections.append({
                    "type": "metric_table",
                    "title": "Geographical Contribution (State)",
                    "columns": ["Location", "PY Admissions", "CY Admissions", "Change", "CY Share"],
                    "data": [
                        {
                            "Location": g["category"],
                            "PY Admissions": f"{g['py_admission']:,}",
                            "CY Admissions": f"{g['cy_admission']:,}",
                            "Change": f"{'+' if g['admission_change'] >= 0 else ''}{g['admission_change']:,}",
                            "CY Share": f"{g['cy_share']:.2f}%",
                        }
                        for g in top_states
                    ],
                })

        # Counsellor / Owner Contributions
        owner_col = "owner"
        if owner_col in group_data and group_data[owner_col]:
            owner_data = group_data[owner_col]
            top_owners = sorted(owner_data, key=lambda x: abs(x["admission_change"]), reverse=True)[:3]
            if top_owners:
                text_parts.append("### Counsellor/Owner Contribution\n")
                text_parts.append("| Owner | PY Admissions | CY Admissions | Change | CY Conversion |")
                text_parts.append("|---|---:|---:|---:|---:|")
                for o in top_owners:
                    text_parts.append(f"| {o['category']} | {o['py_admission']:,} | {o['cy_admission']:,} | {'+' if o['admission_change'] >= 0 else ''}{o['admission_change']:,} | {o['cy_conv']:.2f}% |")
                text_parts.append("")

                sections.append({
                    "type": "metric_table",
                    "title": "Counsellor/Owner Contribution",
                    "columns": ["Owner", "PY Admissions", "CY Admissions", "Change", "CY Conversion"],
                    "data": [
                        {
                            "Owner": o["category"],
                            "PY Admissions": f"{o['py_admission']:,}",
                            "CY Admissions": f"{o['cy_admission']:,}",
                            "Change": f"{'+' if o['admission_change'] >= 0 else ''}{o['admission_change']:,}",
                            "CY Conversion": f"{o['cy_conv']:.2f}%",
                        }
                        for o in top_owners
                    ],
                })

        # 7. Core key observations list
        text_parts.append("### Key observations\n")
        
        # Lead volume bullet
        lead_dir = "increased" if leads_change >= 0 else "declined"
        observations.append(
            f"Overall lead volume {lead_dir} by {abs(leads_change):,} "
            f"({'+' if leads_growth >= 0 else ''}{leads_growth:.2f}% growth) between PY and CY."
        )

        # Conversion bullet
        conv_dir = "improved" if conv_change >= 0 else "declined"
        observations.append(
            f"Overall conversion efficiency {conv_dir} by {abs(conv_change):.2f} percentage points "
            f"(moving from {py_conv:.2f}% to {cy_conv:.2f}%)."
        )

        # Add all to observations list
        for obs in observations:
            text_parts.append(f"- {obs}")
        text_parts.append("")

        sections.append({
            "type": "observation_list",
            "title": "Key Observations",
            "items": observations,
        })

        # Causal warning footer
        causal_footer = (
            "The dataset does not contain enough information to determine the exact cause. "
            "These findings describe measurable associations in the dataset; "
            "they do not prove that any particular source, counsellor, or campaign caused the change."
        )
        text_parts.append(causal_footer)

        sections.append({
            "type": "text_block",
            "content": causal_footer,
        })

        markdown_answer = "\n".join(text_parts)

        # Return structured ToolResult
        return ToolResult(
            success=True,
            operation="driver_analysis",
            columns=[entity_dim, "py_leads", "cy_leads", "py_admission", "cy_admission", "conversion_rate_change"],
            data=[{
                entity_dim: matched_entity,
                "py_leads": py_leads,
                "cy_leads": cy_leads,
                "py_admission": py_admission,
                "cy_admission": cy_admission,
                "conversion_rate_change": conv_change,
            }],
            response_type="table",
            chart_type=None,
            year=request.current_year,
            metadata={
                "entity": matched_entity,
                "dimension": entity_dim,
                "markdown_answer": markdown_answer,
                "sections": sections,
            },
        )

