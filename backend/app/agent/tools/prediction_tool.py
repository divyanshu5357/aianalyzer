"""
Phase 11.5: AI Agent Prediction Tool
Provides admission probability predictions, high-priority lead identification,
and predictive cohort statistics powered by the versioned ML Inference Service.
100% database & model-driven. LLM never calculates probabilities or invents metrics.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
import pandas as pd

from app.agent.tools.base import BaseAnalyticsTool, ToolRequest, ToolResult
from app.ml.ml_canonical_feature_pipeline import CanonicalMLFeaturePipeline
from app.ml.ml_inference_service import MLInferenceService

logger = logging.getLogger(__name__)


class PredictionTool(BaseAnalyticsTool):
    """Tool for querying admission probability predictions and lead priority scores."""

    def __init__(self):
        self.name = "prediction_analysis"
        self.description = "Predicts lead admission probabilities and identifies high-priority leads needing counselor attention."

    def execute(self, db: Session, request: ToolRequest) -> ToolResult:
        pipeline = CanonicalMLFeaturePipeline(db)
        df_features = pipeline.extract_features(limit=500)

        if df_features.empty:
            return ToolResult(
                success=False,
                operation=request.operation,
                data=[],
                response_type="text",
                metadata={"summary": "No active raw lead records available for ML prediction."},
                error="No active raw lead records available for ML prediction.",
                error_code="EMPTY_DATASET",
            )

        # Run model inference on raw leads
        service = MLInferenceService()
        records_dict = df_features.to_dict(orient="records")
        preds = service.predict_batch(records_dict)

        # Merge prediction metadata into DataFrame
        df_features["probability"] = [p["calibrated_admission_probability"] for p in preds]
        df_features["score_pct"] = [p["predictive_score_pct"] for p in preds]
        df_features["tier"] = [p["operational_tier"] for p in preds]
        df_features["recommendation"] = [p["decision_recommendation"] for p in preds]

        total_leads = len(df_features)
        high_priority = df_features[df_features["tier"] == "High Priority (Top 10%)"]
        std_priority = df_features[df_features["tier"] == "Standard Priority (Top 20%)"]
        high_pct = round((len(high_priority) / total_leads * 100.0), 1) if total_leads > 0 else 0.0

        # Program aggregated predicted admissions
        prog_preds = (
            df_features.groupby("program_code")
            .agg(
                total_leads=("id", "count"),
                avg_prob=("probability", "mean"),
                predicted_admissions=("probability", "sum"),
            )
            .reset_index()
        )
        prog_preds["avg_prob_pct"] = (prog_preds["avg_prob"] * 100.0).round(2)
        prog_preds["predicted_admissions"] = prog_preds["predicted_admissions"].round(1)
        prog_preds = prog_preds.sort_values(by="predicted_admissions", ascending=False)

        q_lower = (request.raw_question or "").lower()

        if "counselor" in q_lower or "attention" in q_lower or "immediate" in q_lower:
            # Top leads needing immediate attention
            top_leads = (
                df_features.sort_values(by="probability", ascending=False)
                .head(10)[["id", "program_code", "source_canonical", "owner_canonical", "score_pct", "tier", "recommendation"]]
                .to_dict(orient="records")
            )
            summary_text = (
                f"### 📊 OBSERVED ACTUALS\n"
                f"Identified **{total_leads:,} active leads** across current dataset.\n\n"
                f"### 🔮 MODEL PREDICTIONS ({service.model_version})\n"
                f"Found **{len(high_priority)} high-priority leads** ({high_pct}% of cohort) with top predicted conversion probability.\n\n"
                f"### 💡 ACTIONABLE COUNSELOR GUIDANCE\n"
                f"Top 10 leads requiring immediate priority outreach have been listed below."
            )
            return ToolResult(
                success=True,
                operation=request.operation,
                columns=["id", "program_code", "source_canonical", "owner_canonical", "score_pct", "tier", "recommendation"],
                data=top_leads,
                response_type="table",
                metadata={
                    "summary": summary_text,
                    "model_version": service.model_version,
                    "total_leads": total_leads,
                    "high_priority_count": len(high_priority),
                    "high_priority_pct": high_pct,
                },
            )
        elif "program" in q_lower or "highest predicted" in q_lower:
            top_progs = prog_preds.head(10).to_dict(orient="records")
            top_prog_name = prog_preds.iloc[0]["program_code"] if not prog_preds.empty else "N/A"
            top_prog_adm = prog_preds.iloc[0]["predicted_admissions"] if not prog_preds.empty else 0
            top_prog_prob = prog_preds.iloc[0]["avg_prob_pct"] if not prog_preds.empty else 0

            summary_text = (
                f"### 📊 OBSERVED ACTUALS\n"
                f"Evaluated predictions across **{len(prog_preds)} academic programs**.\n\n"
                f"### 🔮 MODEL PREDICTIONS ({service.model_version})\n"
                f"Top predicted admissions program: **{top_prog_name}** "
                f"({top_prog_adm} expected admissions, Avg Prob: {top_prog_prob}%).\n\n"
                f"### 💡 ACTIONABLE COUNSELOR GUIDANCE\n"
                f"Focus marketing and counselor capacity on top predicted conversion programs."
            )
            return ToolResult(
                success=True,
                operation=request.operation,
                columns=["program_code", "total_leads", "avg_prob_pct", "predicted_admissions"],
                data=top_progs,
                response_type="table",
                metadata={
                    "summary": summary_text,
                    "model_version": service.model_version,
                    "top_program": top_prog_name,
                },
            )
        else:
            # Default cohort prediction summary
            top_leads = (
                df_features.sort_values(by="probability", ascending=False)
                .head(10)[["id", "program_code", "source_canonical", "owner_canonical", "score_pct", "tier"]]
                .to_dict(orient="records")
            )
            summary_text = (
                f"### 📊 OBSERVED ACTUALS\n"
                f"Total evaluated leads: **{total_leads:,}**.\n\n"
                f"### 🔮 MODEL PREDICTIONS ({service.model_version})\n"
                f"High-priority leads (Top 10% cutoff): **{len(high_priority)}** ({high_pct}% of total).\n"
                f"Standard-priority leads: **{len(std_priority)}**.\n\n"
                f"### 💡 ACTIONABLE COUNSELOR GUIDANCE\n"
                f"Target high-priority leads first to maximize conversion yield."
            )
            return ToolResult(
                success=True,
                operation=request.operation,
                columns=["id", "program_code", "source_canonical", "owner_canonical", "score_pct", "tier"],
                data=top_leads,
                response_type="table",
                metadata={
                    "summary": summary_text,
                    "model_version": service.model_version,
                    "total_leads": total_leads,
                    "high_priority_pct": high_pct,
                },
            )
