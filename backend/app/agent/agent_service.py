import re
import logging
from typing import Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.agent.intent_parser import parse_question, detect_anaphora_references
from app.database.conversations import (
    get_or_create_conversation,
    save_conversation_message,
    get_conversation_context,
    save_conversation_context,
)
from app.agent.gemini_planner import plan_question
from app.agent.router import route_and_execute_plan
from app.agent.response_formatter import format_tool_response
from app.database.repository import get_active_dataset
from app.ingestion.schema_mapper import resolve_canonical_field
from app.agent.tools.utils import resolve_canonical_dim, validate_dataset_value, METRIC_COLUMN_MAP, resolve_flexible_entity, get_distinct_dimension_values

logger = logging.getLogger(__name__)


def get_active_dataset_years(db: Session, dataset_id: Any) -> tuple[int, int]:
    """
    Determine (current_year, previous_year) for the active dataset.

    Priority:
      1. Read period_end_year / period_start_year from system.datasets metadata
         (populated during upload via period detection or user confirmation).
      2. Fall back to scanning staging.records column names/values for a year
         pattern (legacy behaviour, works if staging was not yet cleaned up).
      3. Fall back to (current calendar year, current calendar year - 1).
    """
    if not dataset_id:
        cy = datetime.now().year
        return cy, cy - 1

    # Priority 1: structured period metadata
    try:
        from app.analytics.period_resolver import get_years_from_period_metadata
        years = get_years_from_period_metadata(db, dataset_id)
        if years:
            cy, py = years
            logger.debug("Year context from period metadata: CY=%d PY=%d", cy, py)
            return cy, py
    except Exception as err:
        logger.warning("Period metadata lookup failed: %s", err)

    # Priority 2: scan staging.records (legacy fallback)
    try:
        query_stg = text(
            "SELECT raw_data FROM staging.records WHERE dataset_id = :dataset_id LIMIT 10"
        )
        rows = db.execute(query_stg, {"dataset_id": dataset_id}).mappings().all()
        for r in rows:
            raw = r.get("raw_data") or {}
            for k in raw.keys():
                m = re.search(r"\b(20\d{2})\b", str(k))
                if m:
                    cy = int(m.group(1))
                    return cy, cy - 1
            for k, v in raw.items():
                if isinstance(v, (str, int)):
                    m = re.search(r"\b(20\d{2})\b", str(v))
                    if m:
                        cy = int(m.group(1))
                        return cy, cy - 1
    except Exception as err:
        logger.warning(f"Error inferring dataset year context from staging: {err}")

    # Priority 3: calendar year fallback
    cy = datetime.now().year
    return cy, cy - 1


def _extract_year_context(time_context: Any, current_year: int, previous_year: int) -> int:
    if time_context and str(time_context).isdigit():
        return int(time_context)
    if time_context == "previous_year":
        return previous_year
    return current_year


# find_entity_in_dataset() was removed during the codebase audit.
# Entity resolution is handled by resolve_flexible_entity() in tools/utils.py.


ANALYTICAL_STOP_WORDS = {
    "how", "many", "admissions", "admission", "are", "there", "show", "leads", "lead",
    "by", "source", "sources", "as", "a", "pie", "chart", "bar", "line", "table", "which",
    "courses", "course", "programs", "program", "rate", "dropped", "drop", "decreased",
    "decrease", "from", "previous", "year", "top", "5", "10", "counsellor", "counselor",
    "counsellors", "counselors", "improved", "the", "most", "performance", "current",
    "to", "vs", "versus", "compare", "who", "did", "have", "had", "in", "for", "with",
    "what", "is", "where", "total", "all", "records", "overall", "biggest", "largest",
    "decline", "last", "this", "cycle", "than", "or", "and", "an", "on", "of", "to",
    "their", "they", "them", "it", "that", "those", "these", "same", "first", "second",
    "one", "ones", "reason", "reasons", "success", "why", "about", "only", "direct", "indirect",
    "improvement", "growth", "declined", "conversion", "state", "states", "campus", "campuses", "main", "category", "channel",
    "increased", "increase", "increases", "drops", "decreases", "improving", "declining", "dropping",
    "whose", "were", "has", "been", "graph", "worst", "lowest", "fewest", "owner", "owners",
    "performed", "perform", "performs", "performing", "compared", "comparing", "brought", "generated",
    "highest", "number", "count", "best", "first", "second", "third", "bottom", "ratio",
    "percentage", "change", "gain", "period", "today", "weather", "salary", "salaries", "contract",
    "contracts", "customer", "customers", "president", "france", "stock", "stocks", "price", "prices",
    "unrelated", "something", "data", "dataset", "record", "records", "info", "information",
    "value", "values", "analysis", "analytics", "tell", "give", "list", "get",
    "students", "student", "admitted", "lost", "breakdown", "per", "each", "hierarchy", "ceo", "google", 
    "satisfaction", "employee", "marketing", "campaign", "success", "improvements", "difference", "between", 
    "side", "by", "side", "compare"
}


UNSUPPORTED_KEYWORDS = [
    "weather", "salary", "salaries", "president", "france", "stock", "stocks", "price", "prices",
    "contract", "contracts", "customer", "customers", "revenue", "invoice", "invoices",
    "unrelated", "unrelated to the uploaded dataset", "ceo", "satisfaction score", "employee satisfaction",
    "marketing campaign to succeed", "marketing campaign success"
]

AMBIGUOUS_QUERIES = [
    "analyze this",
    "compare last year",
    "show the trend",
    "show the top 5 improvements",
    "show the top improvements"
]


def has_unrecognized_words(question: str, db: Session, active_dataset: Any) -> bool:
    q_norm = question.lower().strip()
    words = [re.sub(r"\W+", "", w) for w in q_norm.split()]
    for w in words:
        if not w or len(w) <= 3 or w.isdigit():
            continue
        if w in ANALYTICAL_STOP_WORDS:
            continue
        # Analytics domain words (expanded — includes plurals)
        if w in {
            "admission", "admissions", "lead", "leads", "cucet", "rate", "rates",
            "conversion", "conversions", "yoy", "previous", "current", "year", "years",
            "performance", "percentage", "percent", "difference", "change", "growth",
            "breakdown", "ranking", "rankings", "compare", "comparison", "improvement",
            "improvements", "increase", "decrease", "biggest", "highest", "lowest",
            "total", "totals", "count", "average", "trend", "trends", "monthly",
            "quarterly", "annual", "yearly", "metric", "metrics", "analysis", "analyze",
            "insight", "insights", "report", "reports", "summary", "overview",
        }:
            continue
        # Dimension/entity category words (expanded — includes plurals and variants)
        if w in {
            "program", "programs", "course", "courses",
            "counsellor", "counselor", "counsellors", "counselors",
            "owner", "owners", "state", "states",
            "campus", "campuses", "source", "sources", "cluster", "clusters",
            "type", "types", "category", "categories",
        }:
            continue

        # Test if it can be resolved as a flexible entity (actual dimension value)
        res = resolve_flexible_entity(db, active_dataset, w)
        if not res["resolved"] and not res["ambiguous"]:
            return True
    return False


def is_local_intent_confident(intent: dict[str, Any], question: str, db: Session, active_dataset: Any) -> bool:
    q_norm = question.lower().strip()

    # 1. Check if it's explicitly unsupported
    if any(kw in q_norm for kw in UNSUPPORTED_KEYWORDS):
        return True

    # 2. Check if it's explicitly ambiguous
    if q_norm in AMBIGUOUS_QUERIES or any(q_norm == q for q in AMBIGUOUS_QUERIES):
        return True

    # 3. Check if it's a follow-up reference
    ref_info = intent.get("ref_info") or detect_anaphora_references(question)
    if ref_info.get("is_reference"):
        return True

    # Check unrecognized words
    if has_unrecognized_words(question, db, active_dataset):
        return False

    # 4. Check parsed intent type
    intent_type = intent.get("intent_type")
    if not intent_type or intent_type == "unknown":
        return False

    if intent_type in ("metric", "funnel"):
        return True

    if intent_type in ("breakdown", "ranking", "yoy", "source"):
        # Confident if we identified at least one dimension or filter value
        return len(intent.get("dimensions", [])) > 0 or len(intent.get("filters", {})) > 0

    if intent_type == "comparison":
        comp_info = intent.get("comparison_info", {})
        return len(comp_info.get("requested_values", [])) >= 2

    return False


def validate_agent_plan(
    db: Session,
    active_dataset: Any,
    question: str,
    intent: dict[str, Any],
    gemini_plan: dict[str, Any] | None,
    year: int,
    prev_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Validation stage before tool execution.
    Distinguishes unsupported domain questions, ambiguous requests, and missing entities.
    """
    q_norm = question.lower().strip()

    # 1. Reject Unsupported Domain Questions
    is_unsupported = (gemini_plan and gemini_plan.get("is_unsupported")) or any(kw in q_norm for kw in UNSUPPORTED_KEYWORDS)
    if is_unsupported:
        return {
            "question": question,
            "answer": "I don't have enough data in the uploaded dataset to answer that.",
            "response_type": "text",
            "chart_type": None,
            "columns": [],
            "data": [],
            "year": year,
            "debug": {"agent_status": "unsupported", "reason": "unsupported_domain"},
        }

    # If question contains follow-up reference terms, check if we have context
    ref_info = detect_anaphora_references(question)
    has_prev_context = prev_context and (prev_context.get("result_entities") or prev_context.get("data") or prev_context.get("result_set"))
    is_ref_query = ref_info.get("is_reference") or intent.get("intent_type") in ("followup_reference", "followup_operation")

    # If it is a reference and we actually have context, bypass remaining validation
    if is_ref_query and has_prev_context:
        return None

    # 2. Reject Ambiguous / Incomplete Analytics Questions
    is_ambiguous = (gemini_plan and (gemini_plan.get("is_ambiguous") or gemini_plan.get("intent") == "ambiguous"))
    if not is_ambiguous:
        if q_norm in AMBIGUOUS_QUERIES or any(q_norm == q for q in AMBIGUOUS_QUERIES):
            is_ambiguous = True
        elif intent.get("intent_type") == "unknown" and (not gemini_plan or gemini_plan.get("intent") in ("unknown", "ambiguous")):
            is_ambiguous = True

    if is_ambiguous:
        return {
            "question": question,
            "answer": (
                "I don't have enough information. I couldn't confidently interpret that question from the available dataset. "
                "Could you clarify what you want to compare or analyze? "
                "(What would you like me to compare — programs, counsellors, campuses, states, or sources?)"
            ),
            "response_type": "text",
            "chart_type": None,
            "columns": [],
            "data": [],
            "year": year,
            "debug": {"agent_status": "ambiguous", "reason": "insufficient_information"},
        }

    # 3. Dimension-Aware Entity Validation & Resolution Stage
    raw_filters = {}
    if gemini_plan and gemini_plan.get("filters"):
        raw_filters = gemini_plan["filters"]
    else:
        raw_filters = intent.get("filters", {})

    filters_dict = {}
    if isinstance(raw_filters, list):
        for f in raw_filters:
            if isinstance(f, dict) and "dimension" in f and "value" in f:
                filters_dict[f["dimension"]] = f["value"]
            elif hasattr(f, "dimension") and hasattr(f, "value"):
                filters_dict[f.dimension] = f.value
    elif isinstance(raw_filters, dict):
        filters_dict = raw_filters

    resolved_filters = {}
    for f_dim, f_val in filters_dict.items():
        if not f_val:
            continue
        
        # Handle unknown dimensions heuristically
        if f_dim == "unknown_dim":
            res = resolve_flexible_entity(db, active_dataset, str(f_val))
            if res["resolved"]:
                resolved_filters[res["dimension"]] = res["value"]
            elif res["ambiguous"]:
                recs = [{"label": c[1], "question": f"Show admissions for {c[1]}"} for c in res["candidates"][:4]]
                return {
                    "question": question,
                    "answer": f"I found multiple candidates matching '{f_val}'. Which one did you mean?\n\n" + "\n".join([f"- {c[1]} ({c[0].replace('_', ' ')})" for c in res["candidates"]]),
                    "response_type": "text",
                    "chart_type": None,
                    "columns": [],
                    "data": [],
                    "year": year,
                    "recommendations": recs,
                    "debug": {"agent_status": "ambiguous_entity", "candidates": res["candidates"]},
                }
            else:
                noise_vals = ["program", "course", "campus", "state", "owner", "counselor", "counsellor", "source"]
                if str(f_val).lower().strip() in noise_vals:
                    continue
                
                # Unknown entity entirely
                recs = [
                    {"label": "Show top programs", "question": "Show top programs by admissions"},
                    {"label": "Show top campuses", "question": "Show top campuses by admissions"},
                    {"label": "Show top sources", "question": "Show top sources by admissions"}
                ]
                return {
                    "question": question,
                    "answer": f"I couldn't identify the entity '{f_val}' in the dataset. Could you clarify which program, campus, counsellor, state, or source you are referring to?",
                    "response_type": "text",
                    "chart_type": None,
                    "columns": [],
                    "data": [],
                    "year": year,
                    "recommendations": recs,
                    "debug": {"agent_status": "entity_not_found", "reason": f"unknown_entity: {f_val}"},
                }

        res_dim = resolve_canonical_dim(db, active_dataset, f_dim)
        if res_dim["resolved"]:
            col_name = res_dim["original_column"]
            res = resolve_flexible_entity(db, active_dataset, str(f_val))
            if res["resolved"] and res["dimension"] == col_name:
                resolved_filters[col_name] = res["value"]
            elif res["ambiguous"]:
                candidates = [c for c in res["candidates"] if c[0] == col_name]
                if len(candidates) == 1:
                    resolved_filters[col_name] = candidates[0][1]
                elif len(candidates) > 1:
                    recs = [{"label": c[1], "question": f"Show admissions for {c[1]}"} for c in candidates[:4]]
                    return {
                        "question": question,
                        "answer": f"I found multiple candidates matching '{f_val}' for {f_dim.replace('_', ' ')}. Which one did you mean?\n\n" + "\n".join([f"- {c[1]}" for c in candidates]),
                        "response_type": "text",
                        "chart_type": None,
                        "columns": [],
                        "data": [],
                        "year": year,
                        "recommendations": recs,
                        "debug": {"agent_status": "ambiguous_entity", "candidates": candidates},
                    }
                else:
                    return {
                        "question": question,
                        "answer": f"I couldn't find '{f_val}' in the active dataset for {f_dim.replace('_', ' ')}.",
                        "response_type": "text",
                        "chart_type": None,
                        "columns": [],
                        "data": [],
                        "year": year,
                        "debug": {"agent_status": "entity_not_found", "reason": f"entity_not_found: {f_val}"},
                    }
            else:
                ok, matched = validate_dataset_value(db, active_dataset, col_name, str(f_val))
                if ok and matched:
                    resolved_filters[col_name] = matched
                else:
                    noise_vals = ["program", "course", "campus", "state", "owner", "counselor", "counsellor", "source", "by program", "by course", "by campus", "by state", "by owner"]
                    if str(f_val).lower().strip() in noise_vals:
                        continue
                        
                    dim_display = f_dim.replace("_name", "").replace("_", " ")
                    all_vals = get_distinct_dimension_values(db, active_dataset, col_name)
                    all_vals = [v for v in all_vals if v and v.lower() not in ["none", "null", "n/a", "na", "", "grand total", "total"]]
                    
                    choices_str = "\n".join([f"• {v}" for v in all_vals[:5]])
                    recs = [{"label": f"Show admissions for {v}", "question": f"Show admissions for {v}"} for v in all_vals[:3]]
                    if not recs:
                        recs = [{"label": f"Show all {dim_display}s", "question": f"Show all {dim_display}s"}]
                        
                    return {
                        "question": question,
                        "answer": f"I couldn't find '{f_val}' as a valid {dim_display} in the dataset.\n\nAvailable {dim_display} values include:\n{choices_str}",
                        "response_type": "text",
                        "chart_type": None,
                        "columns": [],
                        "data": [],
                        "year": year,
                        "recommendations": recs,
                        "debug": {
                            "agent_status": "entity_not_found",
                            "reason": f"entity_not_found: {f_val}",
                            "requested_value": f_val,
                        },
                    }

    intent["filters"] = resolved_filters
    if gemini_plan:
        gemini_plan["filters"] = resolved_filters

    # Extract planned comparison values and validate
    values = gemini_plan.get("values", []) if gemini_plan else []
    if not values and intent.get("comparison_info"):
        values = intent.get("comparison_info", {}).get("requested_values", [])

    if values:
        # 1. Detect explicit dimension from question wording
        explicit_dim = detect_explicit_dimension(question)
        
        # 2. Resolve all values across the dataset
        resolved_vals = []
        resolved_dims = []
        unresolved_vals = []
        
        for val in values:
            res = resolve_flexible_entity(db, active_dataset, str(val))
            if res["resolved"]:
                resolved_vals.append(res["value"])
                resolved_dims.append(res["dimension"])
            elif res["ambiguous"]:
                # If a value is ambiguous, return choices immediately
                candidates_str = "\n".join([f"- {c[1]} ({c[0].replace('_', ' ')})" for c in res["candidates"]])
                recs = [{"label": c[1], "question": question.replace(val, c[1])} for c in res["candidates"][:4]]
                return {
                    "question": question,
                    "answer": f"I found multiple candidates matching '{val}'. Which one did you mean?\n\n{candidates_str}",
                    "response_type": "text",
                    "chart_type": None,
                    "columns": [],
                    "data": [],
                    "year": year,
                    "recommendations": recs,
                    "debug": {"agent_status": "ambiguous_entity", "candidates": res["candidates"]},
                }
            else:
                unresolved_vals.append(val)

        # 3. Determine the target dimension
        target_dim = explicit_dim
        if not target_dim:
            if resolved_dims:
                # Use the dimension of the first successfully matched value
                target_dim = resolved_dims[0]
            else:
                # If nothing resolved at all, assume program_name as default fallback for error reporting
                target_dim = "program_name"

        # 4. Now, strictly validate all comparison values against the target_dim
        invalid_vals = []
        resolved_vals = []
        for val in values:
            res = resolve_flexible_entity(db, active_dataset, str(val))
            if res["resolved"] and res["dimension"] == target_dim:
                resolved_vals.append(res["value"])
            else:
                invalid_vals.append(val)

        # 5. If there are any invalid values under the target_dim
        if invalid_vals:
            all_vals = get_distinct_dimension_values(db, active_dataset, target_dim)
            all_vals = [v for v in all_vals if v and v.lower() not in ["none", "null", "n/a", "na", "", "grand total", "total"]]
            choices_str = "\n".join([f"• {v}" for v in all_vals[:10]])
            
            valid_suggested = [v for v in values if v not in invalid_vals]
            suggestion_msg = ""
            recs = []
            
            dim_display = target_dim.replace("_name", "").replace("_", " ")
            
            if valid_suggested:
                # Resolve the valid one's canonical name
                res_valid = resolve_flexible_entity(db, active_dataset, str(valid_suggested[0]))
                if res_valid["resolved"]:
                    matched_valid = res_valid["value"]
                    other_alternatives = [v for v in all_vals if v != matched_valid]
                    if other_alternatives:
                        alt = other_alternatives[0]
                        suggestion_msg = f"\n\nWould you like to compare {matched_valid} vs {alt}?"
                        recs = [
                            {"label": f"Compare {matched_valid} vs {alt}", "question": f"Compare {matched_valid} vs {alt} admissions"},
                            {"label": f"Show all {dim_display}s", "question": f"Show all {dim_display}s"},
                            {"label": f"Show admissions by {dim_display}", "question": f"Show admissions by {dim_display}"}
                        ]
            
            if not recs:
                recs = [
                    {"label": f"Show all {dim_display}s", "question": f"Show all {dim_display}s"},
                    {"label": f"Show admissions by {dim_display}", "question": f"Show admissions by {dim_display}"}
                ]

            valid_names_str = ", ".join([str(v).upper() for v in valid_suggested])
            invalid_names_str = ", ".join([str(v).upper() for v in invalid_vals])
            
            if valid_suggested:
                answer = f"I found {valid_names_str} as a valid {dim_display}, but {invalid_names_str} is not present as a {dim_display} in the active dataset.\n\nAvailable {dim_display} values include:\n{choices_str}{suggestion_msg}"
            else:
                answer = f"I couldn't find {invalid_names_str} as valid {dim_display} values in the active dataset.\n\nAvailable {dim_display} values include:\n{choices_str}"

            return {
                "question": question,
                "answer": answer,
                "response_type": "text",
                "chart_type": None,
                "columns": [],
                "data": [],
                "year": year,
                "recommendations": recs,
                "debug": {
                    "agent_status": "entity_not_found",
                    "reason": f"entity_not_found: {invalid_vals}",
                    "target_dimension": target_dim,
                    "invalid_values": invalid_vals,
                },
            }

        # Build interpretation message if names were normalized
        interpretations = []
        for orig, resolved in zip(values, resolved_vals):
            if orig.lower().strip() != resolved.lower().strip():
                interpretations.append(f"'{orig}' as '{resolved}'")
                
        interpretation_msg = ""
        if interpretations:
            interpretation_msg = f"I interpreted {', '.join(interpretations)}. "

        intent["dimensions"] = [target_dim]
        if gemini_plan:
            gemini_plan["dimension"] = target_dim
            gemini_plan["dimensions"] = [target_dim]
            gemini_plan["values"] = resolved_vals
        if "comparison_info" not in intent:
            intent["comparison_info"] = {}
        intent["comparison_info"]["requested_values"] = resolved_vals
        intent["comparison_info"]["interpretation_message"] = interpretation_msg

    return None


def extract_result_entities(data_rows: list[dict[str, Any]], primary_dim: str | None) -> list[str]:
    if not data_rows:
        return []
    entities = []
    for r in data_rows:
        if primary_dim and primary_dim in r and r[primary_dim] is not None:
            val = str(r[primary_dim])
            if val and val not in entities:
                entities.append(val)
        else:
            for k, v in r.items():
                if isinstance(v, str) and k not in ["intent", "response_type"] and v not in entities:
                    entities.append(v)
                    break
    return entities


def detect_explicit_dimension(question: str) -> str | None:
    q = question.lower()
    if "campus" in q or "location" in q:
        return "campus_name"
    if "program" in q or "course" in q or "degree" in q:
        return "program_name"
    if "source" in q or "channel" in q:
        return "source"
    if "state" in q:
        return "state"
    if "owner" in q or "counsellor" in q or "counselor" in q or "agent" in q:
        return "owner"
    if "lead type" in q:
        return "lead_type"
    return None


def is_stopword_phrase(phrase: str) -> bool:
    words = [w.strip() for w in phrase.lower().split() if w.strip()]
    stopwords = {
        "what", "why", "how", "who", "which", "where", "the", "a", "an", "it", "this", "that", "they", "them", "these", 
        "those", "same", "above", "below", "following", "result", "results", "analysis", "driver", "drivers", "cause", 
        "causes", "reason", "reasons", "contribution", "contributions", "increase", "decrease", "decline", "improvement", 
        "growth", "performance", "drove", "did", "do", "does", "is", "was", "are", "were", "of", "in", "for", "to", "with", 
        "about", "behind", "on", "at", "by", "from", "show", "tell", "explain", "analyze", "list", "get", "give", "display",
        "detail", "details", "metric", "metrics", "data", "dataset", "report", "summary", "view", "see", "their", "success",
        "its", "one", "ones", "failure", "failures"
    }
    return all(w in stopwords for w in words)


def extract_entity_from_causal_question(question: str) -> str:
    q = question.strip()
    q = re.sub(r"[?:.!'\"]", "", q)
    words_to_remove = [
        "why did", "why", "what is the reason behind", "what is the reason for", "what is reason behind", 
        "what is reason for", "reason behind", "reason for", "what caused the increase", "what caused the decline", 
        "what caused", "caused", "drove", "driver", "drivers", "contribution", "contribute", "contributing",
        "improve", "improved", "decline", "declined", "increase", "increased", "decrease", "decreased",
        "perform better", "perform worse", "perform", "better", "worse", "program", "course", "campus", "state", "owner"
    ]
    for w in words_to_remove:
        q = re.sub(rf"\b{re.escape(w)}\b", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def resolve_conversation_references(
    db: Session,
    active_dataset: Any,
    question: str,
    intent: dict[str, Any],
    prev_context: dict[str, Any] | None,
    cy_year: int,
    py_year: int,
) -> dict[str, Any] | None:
    """Resolves follow-up questions consuming resolved conversation memory context."""
    q_norm = question.lower().strip()
    ref_info = detect_anaphora_references(question)

    # 1. Causal Questions Without Evidence
    if ("marketing campaign" in q_norm or "because of" in q_norm) and ("why" in q_norm or "reason" in q_norm):
        return {
            "question": question,
            "answer": "I don't have enough information in the uploaded dataset to determine causation. The dataset contains measurable metrics such as leads, admissions, sources, programs, owners, and conversion rates, but it does not contain evidence proving why admissions changed.",
            "response_type": "text",
            "chart_type": None,
            "columns": [],
            "data": [],
            "year": cy_year,
            "debug": {"agent_status": "causal_unsupported", "reason": "dataset_lacks_causal_evidence"},
        }

    # 1.1 Causal/Driver Questions
    is_causal_q = ref_info.get("is_causal") or "reason" in q_norm or "success" in q_norm or "why" in q_norm or intent.get("operation") == "driver_analysis" or intent.get("intent_type") == "driver_analysis"
    if is_causal_q:
        resolved_entity = None
        resolved_dim = None
        
        search_term = extract_entity_from_causal_question(question)
        if search_term and not is_stopword_phrase(search_term):
            res = resolve_flexible_entity(db, str(active_dataset), search_term)
            if res["resolved"]:
                resolved_entity = res["value"]
                resolved_dim = res["dimension"]
            elif res["ambiguous"]:
                return {
                    "question": question,
                    "answer": f"I found multiple candidates matching '{search_term}'. Which one did you mean?\n\n" + "\n".join([f"- {c[1]} ({c[0].replace('_', ' ')})" for c in res["candidates"]]),
                    "response_type": "text",
                    "chart_type": None,
                    "columns": [],
                    "data": [],
                    "year": cy_year,
                    "debug": {"agent_status": "ambiguous_entity", "candidates": res["candidates"]},
                }
            elif not prev_context or not prev_context.get("result_entities"):
                return {
                    "question": question,
                    "answer": f"I couldn't find '{search_term}' in the active dataset.",
                    "response_type": "text",
                    "chart_type": None,
                    "columns": [],
                    "data": [],
                    "year": cy_year,
                    "debug": {"agent_status": "entity_not_found", "reason": f"entity_not_found: {search_term}"},
                }

        # Fallback to context if not resolved
        context_used = False
        if not resolved_entity and prev_context and prev_context.get("result_entities"):
            resolved_entity = prev_context["result_entities"][0]
            resolved_dim = prev_context.get("dimension") or (
                prev_context.get("dimensions")[0] if prev_context.get("dimensions") else "program_name"
            )
            context_used = True

        if resolved_entity:
            limit_val = 5
            limit_match = re.search(r"\b(?:top|first|highest|lowest)\s+(\d+)\b", q_norm)
            if limit_match:
                limit_val = int(limit_match.group(1))

            plan = {
                "intent": "driver_analysis",
                "operation": "driver_analysis",
                "dimension": resolved_dim,
                "values": [resolved_entity],
                "limit": limit_val,
                "metric": "admission",
            }

            intent["intent_type"] = "driver_analysis"
            intent["operation"] = "driver_analysis"
            intent["dimensions"] = [resolved_dim]
            intent["dimension"] = resolved_dim

            tool_result = route_and_execute_plan(
                db=db,
                plan=plan,
                active_dataset=active_dataset,
                current_year=cy_year,
                previous_year=py_year,
                raw_question=question,
            )
            formatted_res = format_tool_response(tool_result, question)
            formatted_res.setdefault("debug", {})["resolved_references"] = {resolved_dim: [resolved_entity]}
            if context_used:
                formatted_res["debug"]["context_used"] = True
            return formatted_res
        
        # If we couldn't resolve it and there is no context
        if not prev_context or not prev_context.get("result_entities"):
            return {
                "question": question,
                "answer": "I need a little more context. I couldn't identify the program, counsellor, campus, or source you are referring to. Please specify which entity you'd like to analyze.",
                "response_type": "text",
                "chart_type": None,
                "columns": [],
                "data": [],
                "year": cy_year,
                "debug": {"agent_status": "insufficient_context", "context_used": False},
            }

    is_ref = ref_info.get("is_reference") or intent.get("intent_type") in ("followup_reference", "followup_operation")
    if not is_ref:
        return None

    if not prev_context or (not prev_context.get("result_entities") and not prev_context.get("data") and not prev_context.get("result_set")):
        return {
            "question": question,
            "answer": "I need a little more context. Which programs or entities are you referring to?",
            "response_type": "text",
            "chart_type": None,
            "columns": [],
            "data": [],
            "year": cy_year,
            "debug": {"agent_status": "insufficient_context", "context_used": False},
        }

    prev_entities = prev_context.get("result_entities", [])
    prev_dim = prev_context.get("dimension") or (
        prev_context.get("dimensions")[0] if prev_context.get("dimensions") else "program_name"
    )
    prev_metric = prev_context.get("metric") or "admission"
    prev_data = prev_context.get("result_set") or prev_context.get("data", [])

    # 2. Source Refinement: "Only direct and indirect"
    if "only direct and indirect" in q_norm or ("direct" in q_norm and "indirect" in q_norm and "only" in q_norm):
        rows = db.execute(
            text(
                """
                SELECT
                    COALESCE(main_source, source) AS source,
                    SUM(cy_leads) AS leads,
                    SUM(cy_admission) AS admission
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds_id
                  AND (LOWER(main_source) IN ('direct', 'indirect') OR LOWER(source) IN ('direct', 'indirect'))
                GROUP BY 1
                ORDER BY 2 DESC;
                """
            ),
            {"ds_id": str(active_dataset)},
        ).mappings().all()

        data_rows = [{"source": r["source"], "leads": int(r["leads"] or 0), "admission": int(r["admission"] or 0)} for r in rows]
        return {
            "question": question,
            "answer": "Here are the lead and admission metrics for direct and indirect sources:",
            "response_type": "table",
            "chart_type": None,
            "columns": ["source", "leads", "admission"],
            "data": data_rows,
            "year": cy_year,
            "debug": {"context_used": True, "resolved_references": {"source": ["direct", "indirect"]}},
        }

    # 3. Format Change on Previous Result: e.g. "show as pie chart"
    if ("pie chart" in q_norm or "bar chart" in q_norm or "line chart" in q_norm or "as a pie" in q_norm or "as a bar" in q_norm) and not any(w in q_norm for w in ["course", "program", "counsellor", "state", "campus"]):
        chart_type = "pie" if "pie" in q_norm else ("line" if "line" in q_norm else "bar")
        if prev_data:
            chart_columns = prev_context.get("result_columns") or list(prev_data[0].keys())
            return {
                "question": question,
                "answer": f"Here is the {chart_type} chart presentation of the previous result set:",
                "response_type": "chart",
                "chart_type": chart_type,
                "columns": chart_columns,
                "data": prev_data,
                "year": cy_year,
                "debug": {"context_used": True, "format_transformed": True},
            }

    # 4. Top-N Slicing: e.g. "show top 3", "show the first one"
    selector = ref_info.get("selector")
    target_entities = list(prev_entities)

    if ("top 3" in q_norm or "top three" in q_norm or "top 5" in q_norm or "top five" in q_norm) and not any(w in q_norm for w in ["course", "courses", "program", "programs"]):
        limit_n = 3 if ("3" in q_norm or "three" in q_norm) else 5
        if prev_data:
            # Return up to limit_n rows; if fewer exist, return all available as a table
            top_n_data = prev_data[:limit_n]
            actual_count = len(top_n_data)
            return {
                "question": question,
                "answer": f"Here are the top {actual_count} results from the previous result set:",
                "response_type": "table",
                "chart_type": None,
                "columns": prev_context.get("result_columns") or list(top_n_data[0].keys()),
                "data": top_n_data,
                "year": cy_year,
                "debug": {"context_used": True, "top_n_sliced": actual_count},
            }
        else:
            target_entities = prev_entities[:limit_n]

    elif selector == "first" or "first one" in q_norm or "1st one" in q_norm:
        target_entities = prev_entities[:1]
    elif selector == "second" or "second one" in q_norm or "2nd one" in q_norm:
        target_entities = prev_entities[1:2] if len(prev_entities) > 1 else prev_entities[:1]
    elif selector == "top_one" or "top one" in q_norm:
        target_entities = prev_entities[:1]
    elif selector == "worst_one" or "worst one" in q_norm or "bottom one" in q_norm:
        target_entities = prev_entities[-1:]

    # 4aa. "Biggest increase/decrease" ranking from previous context
    if any(p in q_norm for p in ["biggest increase", "most increase", "highest increase", "biggest growth", "most improved", "biggest decrease", "most decline"]):
        is_increase = any(p in q_norm for p in ["increase", "growth", "improved"])
        direction = "DESC" if is_increase else "ASC"
        metric_col = "cy_admission - py_admission"
        rows = db.execute(
            text(
                f"""
                SELECT "{prev_dim}",
                       COALESCE(SUM(cy_admission), 0) - COALESCE(SUM(py_admission), 0) AS delta,
                       COALESCE(SUM(cy_admission), 0) AS cy_admission,
                       COALESCE(SUM(py_admission), 0) AS py_admission
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :ds_id
                  AND "{prev_dim}" = ANY(:entities)
                GROUP BY "{prev_dim}"
                ORDER BY delta {direction}
                LIMIT 1
                """
            ),
            {"ds_id": str(active_dataset), "entities": list(prev_entities) if prev_entities else [""]},
        ).mappings().all()
        if rows:
            data_rows = [
                {
                    prev_dim: r[prev_dim],
                    "cy_admission": int(r["cy_admission"]),
                    "py_admission": int(r["py_admission"]),
                    "change": int(r["delta"]),
                }
                for r in rows
            ]
            return {
                "question": question,
                "answer": f"{'The biggest increase' if is_increase else 'The biggest decrease'} in admissions among the previous results:",
                "response_type": "table",
                "chart_type": None,
                "columns": [prev_dim, "cy_admission", "py_admission", "change"],
                "data": data_rows,
                "year": cy_year,
                "debug": {"context_used": True, "ranking_from_context": True},
            }

    # 4a. YoY Comparison on Previous Entity: e.g. "compare it with last year"
    if ref_info.get("is_yoy"):
        itemized_data = []
        for ent in target_entities:
            row = db.execute(
                text(
                    f"""
                    SELECT
                        SUM(cy_leads) AS cy_leads,
                        SUM(cy_admission) AS cy_admission,
                        SUM(py_leads) AS py_leads,
                        SUM(py_admission) AS py_admission
                    FROM analytics.uploaded_metrics
                    WHERE dataset_id = :ds_id
                      AND LOWER("{prev_dim}") = LOWER(:ent)
                    """
                ),
                {"ds_id": str(active_dataset), "ent": ent},
            ).mappings().first()

            cy_adm = int((row and row["cy_admission"]) or 0)
            py_adm = int((row and row["py_admission"]) or 0)
            cy_leads = int((row and row["cy_leads"]) or 0)
            py_leads = int((row and row["py_leads"]) or 0)

            cy_rate = round((cy_adm / cy_leads * 100.0), 2) if cy_leads > 0 else 0.0
            py_rate = round((py_adm / py_leads * 100.0), 2) if py_leads > 0 else 0.0

            adm_diff = cy_adm - py_adm
            rate_diff = round(cy_rate - py_rate, 2)

            itemized_data.append({
                prev_dim: ent,
                f"admissions_{py_year}": py_adm,
                f"admissions_{cy_year}": cy_adm,
                f"leads_{py_year}": py_leads,
                f"leads_{cy_year}": cy_leads,
                "admission_change": adm_diff,
                "conversion_rate_change (%)": rate_diff,
            })

        grounded_answer = (
            f"Here is the YoY comparison for {', '.join(target_entities)} between {py_year} and {cy_year}:"
        )
        return {
            "question": question,
            "answer": grounded_answer,
            "response_type": "table",
            "chart_type": None,
            "columns": [prev_dim, f"admissions_{py_year}", f"admissions_{cy_year}", f"leads_{py_year}", f"leads_{cy_year}", "admission_change", "conversion_rate_change (%)"],
            "data": itemized_data,
            "year": cy_year,
            "debug": {"context_used": True, "resolved_references": {"target_entities": target_entities}},
        }

    # 4b. Contextual Comparison Follow-up: e.g. "compare it with the second one" or "compare them"
    if "compare" in q_norm or "vs" in q_norm or "versus" in q_norm:
        v1 = None
        v2 = None
        # If prev_entities is empty, try to extract entity names from prev_data rows
        entities_to_use = list(prev_entities)
        if not entities_to_use and prev_data:
            key = prev_dim or (list(prev_data[0].keys())[0] if prev_data else None)
            if key:
                entities_to_use = [str(r.get(key, "")) for r in prev_data if r.get(key)]
        if "them" in q_norm and len(entities_to_use) >= 2:
            v1, v2 = entities_to_use[0], entities_to_use[1]
        else:
            if "it" in q_norm or "this" in q_norm or "first" in q_norm or "1st" in q_norm:
                if len(entities_to_use) >= 1:
                    v1 = entities_to_use[0]
            if selector == "second" or "second one" in q_norm or "2nd" in q_norm:
                if len(entities_to_use) >= 2:
                    v2 = entities_to_use[1]
        if not v1 and len(entities_to_use) >= 1:
            v1 = entities_to_use[0]
        if not v2 and len(entities_to_use) >= 2:
            v2 = entities_to_use[1]
        if v1 and v2:
            plan = {
                "intent": "comparison",
                "operation": "comparison",
                "dimension": prev_dim,
                "values": [v1, v2],
                "metric": prev_context.get("metric") or "admission",
                "response_type": "table",
            }
            tool_result = route_and_execute_plan(
                db=db,
                plan=plan,
                active_dataset=active_dataset,
                current_year=cy_year,
                previous_year=py_year,
                raw_question=question,
            )
            formatted_res = format_tool_response(tool_result, question)
            formatted_res.setdefault("debug", {})["context_used"] = True
            return formatted_res



    # 6. Default Entity Result
    sel_rows = []
    for ent in target_entities:
        cy_val = db.execute(
            text(f"""SELECT COALESCE(SUM(cy_admission), 0) FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id AND LOWER("{prev_dim}") = LOWER(:ent)"""),
            {"ds_id": str(active_dataset), "ent": ent},
        ).scalar() or 0
        sel_rows.append({prev_dim: ent, "admission": int(cy_val)})

    return {
        "question": question,
        "answer": f"Here is the result for {', '.join(target_entities)}:",
        "response_type": "table" if len(target_entities) > 1 or "table" in q_norm else "text",
        "chart_type": None,
        "columns": [prev_dim, "admission"],
        "data": sel_rows,
        "year": cy_year,
        "debug": {"context_used": True, "resolved_references": {"selected_entities": target_entities}},
    }


def _log_turn_to_audit(
    db: Session,
    conversation_id: str,
    question: str,
    res: dict[str, Any],
    active_dataset: Any,
    cy_year: int,
    py_year: int,
    intent: dict[str, Any],
    gemini_plan: dict[str, Any] | None = None,
    period_a: str | None = None,
    period_b: str | None = None,
    tool_used: str | None = None,
) -> None:
    try:
        from app.database.ai_audit import record_turn_audit

        ds_id = str(active_dataset) if active_dataset else None
        academic_label = None
        if ds_id:
            try:
                row = db.execute(
                    text("SELECT academic_label FROM system.datasets WHERE id = :id"),
                    {"id": ds_id},
                ).mappings().first()
                if row:
                    academic_label = row.get("academic_label")
            except Exception:
                pass

        det_intent = (gemini_plan and gemini_plan.get("intent")) or intent.get("intent_type") or "unknown"
        op = (gemini_plan and gemini_plan.get("operation")) or intent.get("operation") or det_intent
        metric = (gemini_plan and gemini_plan.get("metric")) or intent.get("metric")
        dim = (gemini_plan and (gemini_plan.get("dimension") or (gemini_plan.get("dimensions")[0] if gemini_plan.get("dimensions") else None))) or intent.get("dimension") or (intent.get("dimensions")[0] if intent.get("dimensions") else None)

        entities = []
        if intent.get("comparison_info") and intent["comparison_info"].get("requested_values"):
            entities = intent["comparison_info"]["requested_values"]
        elif res.get("debug") and res["debug"].get("resolved_references"):
            ref_dict = res["debug"]["resolved_references"]
            for k, v in ref_dict.items():
                if isinstance(v, list):
                    entities.extend([str(x) for x in v])

        err_cat = None
        if res.get("debug"):
            err_cat = res["debug"].get("agent_status") or res["debug"].get("reason")

        record_turn_audit(
            db=db,
            conversation_id=conversation_id,
            user_question=question,
            assistant_answer=res.get("answer", ""),
            dataset_id=ds_id,
            academic_label=academic_label,
            period_a=period_a or str(py_year),
            period_b=period_b or str(cy_year),
            selected_years=[py_year, cy_year],
            response_type=res.get("response_type", "text"),
            detected_intent=det_intent,
            operation=op,
            metric=metric,
            dimension=dim,
            resolved_entities=entities,
            filters=intent.get("filters"),
            tool_used=tool_used or op,
            success=True,
            error_category=err_cat,
            raw_data=res.get("data"),
            columns=res.get("columns"),
        )
    except Exception as e:
        logger.warning(f"Error writing turn audit: {e}")


def answer_question(
    db: Session,
    question: str,
    conversation_id: str | None = None,
    period_a: str | None = None,
    period_b: str | None = None,
) -> dict[str, Any]:
    """
    Agentic Analytics Entrypoint:
    Memory Context -> Gemini/Intent Plan -> Validation -> Followup Resolution -> Generic Router Tool Execution -> Formatter.
    """
    active_dataset = get_active_dataset(db)
    if active_dataset:
        cy_year, py_year = get_active_dataset_years(db, active_dataset)
    else:
        cy_year, py_year = datetime.now().year, datetime.now().year - 1

    conversation_id = get_or_create_conversation(db, conversation_id, active_dataset)
    save_conversation_message(db, conversation_id, "user", question)
    prev_context = get_conversation_context(db, conversation_id, active_dataset)

    if not active_dataset:
        res = {
            "question": question,
            "answer": "Please upload a dataset before asking analytical questions.",
            "response_type": "text",
            "chart_type": None,
            "columns": [],
            "data": [],
            "year": cy_year,
            "conversation_id": conversation_id,
        }
        save_conversation_message(db, conversation_id, "assistant", res["answer"])
        _log_turn_to_audit(db, conversation_id, question, res, active_dataset, cy_year, py_year, {}, None, period_a, period_b)
        return res

    # 1. Planning Stage (Local Parser first, fallback to Gemini if not confident)
    intent = parse_question(question)
    use_gemini = not is_local_intent_confident(intent, question, db, active_dataset)
    gemini_plan = plan_question(question) if use_gemini else None

    # Safety guard: if local parser is not confident AND Gemini is unavailable,
    # return entity_not_found rather than blindly executing an unvalidated query.
    if use_gemini and gemini_plan is None and has_unrecognized_words(question, db, active_dataset):
        safe_res = {
            "question": question,
            "answer": (
                "I couldn't find the entity or metric you're referring to in the active dataset. "
                "Could you clarify which program, campus, counsellor, or source you'd like to analyze?"
            ),
            "response_type": "text",
            "chart_type": None,
            "columns": [],
            "data": [],
            "year": cy_year,
            "conversation_id": conversation_id,
            "debug": {"agent_status": "entity_not_found", "reason": "unrecognized_words_gemini_unavailable"},
        }
        save_conversation_message(db, conversation_id, "assistant", safe_res["answer"])
        _log_turn_to_audit(db, conversation_id, question, safe_res, active_dataset, cy_year, py_year, intent, gemini_plan, period_a, period_b)
        return safe_res

    year = _extract_year_context(intent.get("time_context"), cy_year, py_year)

    q_norm = question.lower().strip()
    
    # Intercept follow-up to driver analysis asking for dimensions
    if prev_context and prev_context.get("intent_type") == "driver_analysis":
        if any(w in q_norm for w in ["source", "owner", "counselor", "counsellor", "campus", "state", "contribute", "contribution", "drove", "driver"]):
            intent["intent_type"] = "followup_reference"
            intent["operation"] = "driver_analysis"
    if gemini_plan and gemini_plan.get("year"):
        year = gemini_plan["year"]

    # Merge Gemini plan findings into intent dict
    if gemini_plan and gemini_plan.get("intent") not in ("unknown", "ambiguous", "unsupported"):
        g_op = gemini_plan.get("operation") or gemini_plan.get("intent")
        intent["intent_type"] = g_op
        if gemini_plan.get("metric"):
            intent["metric"] = gemini_plan["metric"]
        if gemini_plan.get("dimensions"):
            intent["dimensions"] = gemini_plan["dimensions"]
        elif gemini_plan.get("dimension"):
            intent["dimensions"] = [gemini_plan["dimension"]]
        if gemini_plan.get("values"):
            intent["comparison_info"] = {"is_comparison": True, "requested_values": gemini_plan["values"]}
        if gemini_plan.get("response_type"):
            intent["response_type"] = gemini_plan["response_type"]
        if gemini_plan.get("chart_type"):
            intent["chart_type"] = gemini_plan["chart_type"]

    # Hardening: Ambiguous / context-less check
    if intent.get("intent_type") in ("yoy", "ranking", "breakdown", "comparison") and not intent.get("dimensions") and not intent.get("dimension") and not (intent.get("comparison_info") and intent.get("comparison_info", {}).get("requested_values")):
        if not prev_context or (not prev_context.get("dimension") and not prev_context.get("dimensions")):
            intent["intent_type"] = "unknown"
            if gemini_plan:
                gemini_plan["intent"] = "ambiguous"
                gemini_plan["is_ambiguous"] = True

    # 2. Validation Stage
    val_res = validate_agent_plan(
        db=db,
        active_dataset=active_dataset,
        question=question,
        intent=intent,
        gemini_plan=gemini_plan,
        year=year,
        prev_context=prev_context,
    )
    if val_res:
        val_res["conversation_id"] = conversation_id
        save_conversation_message(db, conversation_id, "assistant", val_res["answer"])
        _log_turn_to_audit(db, conversation_id, question, val_res, active_dataset, cy_year, py_year, intent, gemini_plan, period_a, period_b)
        return val_res

    # 3. Follow-up Context Resolution
    ref_res = resolve_conversation_references(
        db=db,
        active_dataset=active_dataset,
        question=question,
        intent=intent,
        prev_context=prev_context,
        cy_year=cy_year,
        py_year=py_year,
    )
    if ref_res:
        ref_res["conversation_id"] = conversation_id
        save_conversation_message(db, conversation_id, "assistant", ref_res["answer"])
        primary_dim = (ref_res.get("columns") and ref_res["columns"][0]) or "program_name"
        res_entities = extract_result_entities(ref_res.get("data", []), primary_dim)
        if res_entities or ref_res.get("data"):
            new_ctx = {
                "dataset_id": str(active_dataset),
                "intent_type": intent.get("intent_type"),
                "dimension": primary_dim,
                "dimensions": intent.get("dimensions", [primary_dim]),
                "metric": intent.get("metric", "admission"),
                "filters": intent.get("filters", {}),
                "current_year": cy_year,
                "previous_year": py_year,
                "response_type": ref_res.get("response_type"),
                "chart_type": ref_res.get("chart_type"),
                "result_entities": res_entities or (prev_context.get("result_entities") if prev_context else []),
                "selected_entities": res_entities[:10],
                "result_set": ref_res.get("data", []),
                "result_columns": ref_res.get("columns", []),
                "data": ref_res.get("data", [])[:10],
            }
            save_conversation_context(db, conversation_id, active_dataset, new_ctx)
        
        if active_dataset:
            from app.agent.tools.recommendation_generator import generate_recommendations
            ref_res["recommendations"] = generate_recommendations(db, str(active_dataset), question, ref_res, prev_context)
            
        _log_turn_to_audit(db, conversation_id, question, ref_res, active_dataset, cy_year, py_year, intent, gemini_plan, period_a, period_b)
        return ref_res

    # 4. Tool Router Execution
    plan_to_route = gemini_plan if (gemini_plan and gemini_plan.get("intent") != "unknown") else intent
    if plan_to_route:
        if "intent" not in plan_to_route and "intent_type" in plan_to_route:
            plan_to_route["intent"] = plan_to_route["intent_type"]
            plan_to_route["operation"] = plan_to_route["intent_type"]
        if "limit" not in plan_to_route and "limit" in intent:
            plan_to_route["limit"] = intent["limit"]
        if "dimension" not in plan_to_route or not plan_to_route["dimension"]:
            dims = plan_to_route.get("dimensions", [])
            if dims:
                plan_to_route["dimension"] = dims[0]
        if "metric" not in plan_to_route or not plan_to_route["metric"]:
            plan_to_route["metric"] = intent.get("metric", "admission")

    tool_result = route_and_execute_plan(
        db=db,
        plan=plan_to_route,
        active_dataset=active_dataset,
        current_year=cy_year,
        previous_year=py_year,
        raw_question=question,
        period_a=period_a,
        period_b=period_b,
    )

    # 5. Formatter Stage
    formatted_res = format_tool_response(tool_result, question)
    
    interp = plan_to_route.get("comparison_info", {}).get("interpretation_message", "") if isinstance(plan_to_route.get("comparison_info"), dict) else ""
    if interp and formatted_res.get("answer"):
        formatted_res["answer"] = interp + formatted_res["answer"]

    formatted_res["conversation_id"] = conversation_id

    save_conversation_message(db, conversation_id, "assistant", formatted_res["answer"])

    # Update Conversation Context for future follow-ups
    primary_dim = (formatted_res.get("columns") and formatted_res["columns"][0]) or "program_name"
    res_entities = extract_result_entities(formatted_res.get("data", []), primary_dim)
    if res_entities or formatted_res.get("data"):
        new_ctx = {
            "dataset_id": str(active_dataset),
            "intent_type": plan_to_route.get("operation") or plan_to_route.get("intent"),
            "dimension": primary_dim,
            "dimensions": plan_to_route.get("dimensions", [primary_dim]),
            "metric": plan_to_route.get("metric", "admission"),
            "filters": plan_to_route.get("filters", {}),
            "current_year": cy_year,
            "previous_year": py_year,
            "response_type": formatted_res.get("response_type"),
            "chart_type": formatted_res.get("chart_type"),
            "result_entities": res_entities,
            "selected_entities": res_entities[:10],
            "result_set": formatted_res.get("data", []),
            "result_columns": formatted_res.get("columns", []),
            "data": formatted_res.get("data", [])[:10],
        }
        save_conversation_context(db, conversation_id, active_dataset, new_ctx)

    if active_dataset:
        from app.agent.tools.recommendation_generator import generate_recommendations
        ctx_to_pass = new_ctx if 'new_ctx' in locals() and new_ctx else prev_context
        formatted_res["recommendations"] = generate_recommendations(db, str(active_dataset), question, formatted_res, ctx_to_pass)

    tool_name = tool_result.get("tool") if isinstance(tool_result, dict) else None
    _log_turn_to_audit(db, conversation_id, question, formatted_res, active_dataset, cy_year, py_year, intent, gemini_plan, period_a, period_b, tool_used=tool_name)

    return formatted_res
