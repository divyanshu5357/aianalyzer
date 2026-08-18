import re
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.agent.tools.utils import get_distinct_dimension_values

def get_top_entities(db: Session, dataset_id: str, dimension: str, limit: int = 2) -> list[str]:
    try:
        sql = text(f"""
            SELECT "{dimension}", SUM(cy_admission) as total
            FROM analytics.uploaded_metrics
            WHERE dataset_id = :ds_id AND "{dimension}" IS NOT NULL 
              AND TRIM(LOWER("{dimension}")) NOT IN ('', 'none', 'null', 'grand total', 'total', 'unknown', '-')
            GROUP BY "{dimension}"
            ORDER BY total DESC
            LIMIT :limit
        """)
        rows = db.execute(sql, {"ds_id": dataset_id, "limit": limit}).mappings().all()
        return [r[dimension] for r in rows]
    except Exception:
        db.rollback()
        return []

def generate_recommendations(
    db: Session,
    active_dataset: str,
    last_question: str,
    last_response: dict[str, Any],
    prev_context: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """
    Generate 2-4 context-aware dynamic follow-up questions.
    """
    # 1. If response already contains explicit recommendations (e.g. from validation stage)
    if last_response.get("recommendations"):
        return last_response["recommendations"]

    recs = []
    q_norm = last_question.lower()

    # Retrieve debugging metadata
    debug_meta = last_response.get("debug", {})
    if not isinstance(debug_meta, dict):
        debug_meta = {}
    meta = debug_meta.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}

    operation = debug_meta.get("operation") or meta.get("operation") or last_response.get("response_type")
    dimension = meta.get("dimension") or last_response.get("columns")[0] if (last_response.get("columns") and len(last_response["columns"]) > 0) else None

    # Helper to clean dimension names
    def clean_dim(d: str) -> str:
        if "program" in d: return "program"
        if "campus" in d: return "campus"
        if "state" in d: return "state"
        if "owner" in d: return "counsellor"
        return "source"

    # Extract target entity from response if any
    target_entity = None
    target_dim = None

    if last_response.get("data") and isinstance(last_response["data"], list) and len(last_response["data"]) > 0:
        row = last_response["data"][0]
        # Try to identify dimension value in row
        for col in ["program_name", "campus_name", "state", "owner", "source", "main_source"]:
            if col in row and row[col]:
                target_entity = str(row[col])
                target_dim = col
                break
                
    if not target_entity and prev_context and prev_context.get("filters"):
        # Fallback to the filters used in the query to find the target entity
        for col, val in prev_context["filters"].items():
            if col in ["program_name", "campus_name", "state", "owner", "source", "main_source"] and val:
                target_entity = str(val)
                target_dim = col
                break

    # 2. Check if comparison question
    is_comparison = "vs" in q_norm or "compare" in q_norm or operation == "comparison"
    if is_comparison:
        requested_vals = meta.get("requested_values")
        if not requested_vals and last_response.get("data") and isinstance(last_response["data"], list):
            # Extract names from result data
            dim_key = dimension or (last_response["columns"][0] if last_response.get("columns") else None)
            if dim_key:
                requested_vals = [r[dim_key] for r in last_response["data"] if dim_key in r]
        
        if requested_vals and len(requested_vals) >= 2:
            v1, v2 = requested_vals[0], requested_vals[1]
            recs = [
                {"label": f"Compare their conversion rates", "question": f"Compare {v1} vs {v2} conversion rates"},
                {"label": f"Compare their leads", "question": f"Compare {v1} vs {v2} leads"},
                {"label": f"Show PY vs CY comparison", "question": f"Show PY vs CY admissions for {v1} and {v2}"},
            ]
            if target_dim:
                recs.append({"label": f"Show top sources for {v1}", "question": f"Show top sources for {v1}"})
            return recs[:4]

    # 3. Check if chart response
    is_chart = last_response.get("response_type") == "chart" or last_response.get("chart_type") is not None
    if is_chart and dimension:
        d_clean = clean_dim(dimension)
        # Find top 2 to suggest comparison
        top_entities = get_top_entities(db, active_dataset, dimension, limit=2)
        
        recs = [
            {"label": f"Show top 5 {d_clean}s", "question": f"Show the top 5 {d_clean}s by admissions"},
            {"label": f"Show admission conversion by {d_clean}", "question": f"Show admission conversion rate by {d_clean}"},
        ]
        if len(top_entities) >= 2:
            recs.append({"label": f"Compare {top_entities[0]} vs {top_entities[1]}", "question": f"Compare {top_entities[0]} vs {top_entities[1]} admissions"})
        
        return recs[:4]

    # 4. If we have a single target entity resolved (e.g. from detail, YoY, or ranking query)
    if target_entity and target_dim:
        d_clean = clean_dim(target_dim)
        top_entities = get_top_entities(db, active_dataset, target_dim, limit=2)
        other_entity = top_entities[1] if (len(top_entities) > 1 and top_entities[0].lower().strip() == target_entity.lower().strip()) else (top_entities[0] if top_entities else None)
        
        recs = [
            {"label": f"Show why {target_entity} improved", "question": f"Why did {target_entity} improve?"},
            {"label": f"Show top sources for {target_entity}", "question": f"Show top sources for {target_entity}"},
            {"label": f"Show state breakdown for {target_entity}", "question": f"Show state breakdown for {target_entity}"},
        ]
        if other_entity and other_entity.lower().strip() != target_entity.lower().strip():
            recs.append({"label": f"Compare with {other_entity}", "question": f"Compare {target_entity} vs {other_entity} admissions"})
        else:
            recs.append({"label": f"Show top 5 {d_clean}s", "question": f"Show the top 5 {d_clean}s by admissions"})
            
        return recs[:4]

    # 5. Fallback recommendations using active dataset values
    # Discover a valid program and campus to suggest comparisons
    progs = get_top_entities(db, active_dataset, "program_name", limit=2)
    campuses = get_top_entities(db, active_dataset, "campus_name", limit=2)

    if progs and len(progs) >= 2:
        recs.append({"label": f"Compare {progs[0]} vs {progs[1]}", "question": f"Compare {progs[0]} vs {progs[1]} admissions"})
    if campuses and len(campuses) >= 2:
        recs.append({"label": f"Compare {campuses[0]} vs {campuses[1]}", "question": f"Compare {campuses[0]} vs {campuses[1]} admissions"})
        
    recs.extend([
        {"label": "Show leads by state", "question": "Show leads by state"},
        {"label": "Which program generated the most leads?", "question": "Which program generated the most leads?"},
    ])
    
    return recs[:4]
