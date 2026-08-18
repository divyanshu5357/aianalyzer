import json
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Cooldown so we don't hammer Gemini on every upload when it's overloaded
_schema_gemini_cooldown_until: float = 0.0
_SCHEMA_COOLDOWN_SECONDS = 300  # 5 minutes after any 429/503

# Canonical concept definitions
CANONICAL_CONCEPTS = {
    "leads": ["cy_leads", "leads", "lead", "enquiries", "enquiry", "total_leads", "total_enquiries"],
    "cucet": ["cy_cucet", "cucet", "registrations", "registration", "applications", "application"],
    "admission": ["cy_admission", "admission", "admissions", "enrolled", "enrollment", "total_admissions"],
    "py_leads": ["py_leads", "py_lead", "previous_year_leads", "past_leads"],
    "py_cucet": ["py_cucet", "previous_year_cucet", "past_cucet"],
    "py_admission": ["py_admission", "previous_year_admissions", "past_admissions"],
    "source": ["mssourcebi", "source", "marketing_channel", "channel", "leaf_source", "sub_source"],
    "main_source": ["source_cluster", "main_source", "source_category", "category", "channel_group"],
    "program_name": ["program_name", "program_name_(short)", "program", "course", "specialization", "degree"],
    "campus_name": ["campus_name", "campus", "location", "branch", "center"],
    "state": ["state_group", "state", "region"],
    "owner": ["owner", "counselor", "agent", "representative"],
    "lead_type": ["lead_type", "channel_type", "type"],
}

# Rule-based exact mapping definitions with high confidence
EXACT_RULES = {
    "cy leads": ("leads", 0.99),
    "cy cucet": ("cucet", 0.99),
    "cy admission": ("admission", 0.99),
    "py leads": ("py_leads", 0.99),
    "py cucet": ("py_cucet", 0.99),
    "py admission": ("py_admission", 0.99),
    "mssourcebi": ("source", 0.98),
    "source cluster": ("main_source", 0.98),
    "program name (short)": ("program_name", 0.98),
    "program name": ("program_name", 0.98),
    "campus name": ("campus_name", 0.98),
    "state group": ("state", 0.98),
    "owner": ("owner", 0.98),
    "lead type": ("lead_type", 0.98),
    "enquiries": ("leads", 0.96),
    "enrolled": ("admission", 0.96),
    "course": ("program_name", 0.95),
    "marketing channel": ("source", 0.94),
    "location": ("campus_name", 0.94),
}


def _fuzzy_rule_match(col_name: str) -> Optional[tuple[str, float]]:
    """Extended fuzzy matching for columns not caught by EXACT_RULES."""
    clean = col_name.strip().lower().replace("-", " ").replace("_", " ")

    fuzzy_map = [
        (["lead", "enquir", "inquiry", "prospect"], "leads", 0.85),
        (["cucet", "registr", "applicat"], "cucet", 0.85),
        (["admiss", "enroll", "enrolled", "joining"], "admission", 0.85),
        (["py lead", "prev lead", "last year lead", "previous lead"], "py_leads", 0.85),
        (["py cucet", "prev cucet", "last year cucet"], "py_cucet", 0.85),
        (["py admiss", "prev admiss", "last year admiss", "previous admiss"], "py_admission", 0.85),
        (["source", "channel", "medium", "origin"], "source", 0.80),
        (["cluster", "main source", "source group", "source cat"], "main_source", 0.80),
        (["program", "course", "degree", "special", "branch of study"], "program_name", 0.80),
        (["campus", "location", "center", "branch", "college"], "campus_name", 0.80),
        (["state", "region", "province", "geography"], "state", 0.80),
        (["owner", "counsel", "agent", "bdm", "executive", "representative"], "owner", 0.80),
        (["lead type", "type", "category"], "lead_type", 0.75),
    ]

    for keywords, concept, conf in fuzzy_map:
        if any(kw in clean for kw in keywords):
            return (concept, conf)

    return None


def _rule_match(col_name: str) -> Optional[tuple[str, float]]:
    """Exact and partial rule-based match against EXACT_RULES dictionary."""
    clean = col_name.strip().lower()
    if clean in EXACT_RULES:
        return EXACT_RULES[clean]

    for key, (concept, conf) in EXACT_RULES.items():
        if key in clean or clean in key:
            return (concept, round(conf - 0.05, 2))

    return None



def infer_schema_with_gemini(
    columns: List[str],
    sample_rows: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Use Gemini API to infer semantic canonical fields for unrecognized columns.
    Only column names, types, and small sample values are sent.
    Returns [] if Gemini is unavailable or in cooldown — caller falls back to fuzzy rules.
    """
    global _schema_gemini_cooldown_until

    if not settings.gemini_api_key:
        return []

    # Skip Gemini call if we're in cooldown from a previous 429/503
    if time.time() < _schema_gemini_cooldown_until:
        logger.info("Gemini schema mapping skipped: in cooldown after previous error.")
        return []

    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)

        prompt = f"""
You are a database schema analyzer.
Given a list of column names and sample data, map each column to one of these canonical fields if appropriate:
- leads
- cucet
- admission
- py_leads
- py_cucet
- py_admission
- source
- main_source
- program_name
- campus_name
- state
- owner
- lead_type

Columns: {columns}
Sample Rows: {sample_rows[:3] if sample_rows else 'None'}

Return ONLY a valid JSON array of objects with keys:
"original_column": string,
"canonical_field": string or null,
"confidence": float between 0.0 and 1.0,
"is_ambiguous": boolean,
"reasoning": string

Do not include markdown code block formatting. Return pure JSON.
"""

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )

        text_content = response.text.strip()
        if text_content.startswith("```json"):
            text_content = text_content[7:]
        if text_content.endswith("```"):
            text_content = text_content[:-3]
        text_content = text_content.strip()

        parsed = json.loads(text_content)
        if isinstance(parsed, list):
            return parsed

    except Exception as err:
        err_str = str(err)
        # Apply cooldown for quota/availability errors so we stop retrying immediately
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            _schema_gemini_cooldown_until = time.time() + _SCHEMA_COOLDOWN_SECONDS
            logger.warning(
                f"Gemini schema mapping quota exceeded (429). "
                f"Falling back to rule-based mapping for {_SCHEMA_COOLDOWN_SECONDS}s."
            )
        elif "503" in err_str or "UNAVAILABLE" in err_str:
            _schema_gemini_cooldown_until = time.time() + _SCHEMA_COOLDOWN_SECONDS
            logger.warning(
                f"Gemini schema mapping unavailable (503). "
                f"Falling back to rule-based mapping for {_SCHEMA_COOLDOWN_SECONDS}s. "
                "Upload will still complete successfully."
            )
        else:
            logger.warning(f"Gemini schema mapping error (non-critical): {err}. Using rule-based fallback.")

    return []


def map_and_store_dataset_schema(
    db: Session,
    dataset_id: Any,
    columns: List[str],
    sample_rows: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Inspect columns, infer canonical concepts using rules + Gemini, and persist to system.column_mappings.
    """
    mapped_results = []
    unresolved_cols = []

    # Step 1: Apply rule matching
    for col in columns:
        rule_res = _rule_match(col)
        if rule_res:
            concept, conf = rule_res
            mapped_results.append({
                "original_column": col,
                "canonical_field": concept,
                "confidence": conf,
                "is_ambiguous": False,
                "reasoning": f"Matched via rule strategy for {col}"
            })
        else:
            unresolved_cols.append(col)

    # Step 2: Fuzzy fallback for unresolved columns, then Gemini for truly unknown ones
    fuzzy_resolved = []
    still_unresolved = []
    for col in unresolved_cols:
        fuzzy_res = _fuzzy_rule_match(col)
        if fuzzy_res:
            concept, conf = fuzzy_res
            mapped_results.append({
                "original_column": col,
                "canonical_field": concept,
                "confidence": conf,
                "is_ambiguous": False,
                "reasoning": f"Matched via fuzzy keyword strategy for '{col}'"
            })
            fuzzy_resolved.append(col)
        else:
            still_unresolved.append(col)

    # Step 3: Use Gemini only for columns that neither exact nor fuzzy rules resolved
    if still_unresolved:
        gemini_mappings = infer_schema_with_gemini(still_unresolved, sample_rows)
        gemini_dict = {m.get("original_column"): m for m in gemini_mappings if isinstance(m, dict)}

        for col in still_unresolved:
            if col in gemini_dict:
                g_m = gemini_dict[col]
                mapped_results.append({
                    "original_column": col,
                    "canonical_field": g_m.get("canonical_field"),
                    "confidence": float(g_m.get("confidence", 0.7)),
                    "is_ambiguous": bool(g_m.get("is_ambiguous", False)),
                    "reasoning": g_m.get("reasoning", "Inferred by Gemini AI")
                })
            else:
                mapped_results.append({
                    "original_column": col,
                    "canonical_field": None,
                    "confidence": 0.0,
                    "is_ambiguous": True,
                    "reasoning": "Unmapped/Unknown column — no rule, fuzzy, or Gemini match found"
                })

    # Step 3: Database persistence
    insert_query = text(
        """
        INSERT INTO system.column_mappings (
            dataset_id,
            original_column,
            canonical_field,
            confidence,
            is_ambiguous,
            reasoning
        )
        VALUES (
            :dataset_id,
            :original_column,
            :canonical_field,
            :confidence,
            :is_ambiguous,
            :reasoning
        )
        ON CONFLICT (dataset_id, original_column)
        DO UPDATE SET
            canonical_field = EXCLUDED.canonical_field,
            confidence = EXCLUDED.confidence,
            is_ambiguous = EXCLUDED.is_ambiguous,
            reasoning = EXCLUDED.reasoning
        """
    )

    for item in mapped_results:
        db.execute(
            insert_query,
            {
                "dataset_id": dataset_id,
                "original_column": item["original_column"],
                "canonical_field": item["canonical_field"],
                "confidence": item["confidence"],
                "is_ambiguous": item["is_ambiguous"],
                "reasoning": item["reasoning"],
            }
        )

    db.commit()
    return mapped_results


def get_dataset_column_mapping(db: Session, dataset_id: Any) -> Dict[str, Any]:
    """
    Retrieve stored column mappings for a given dataset.
    Returns dict mapping original_column -> metadata, and canonical_field -> original_column.
    """
    rows = db.execute(
        text(
            """
            SELECT original_column, canonical_field, confidence, is_ambiguous, reasoning
            FROM system.column_mappings
            WHERE dataset_id = :dataset_id
            """
        ),
        {"dataset_id": dataset_id}
    ).mappings().all()

    by_original = {}
    by_canonical = {}

    for r in rows:
        col_info = {
            "original_column": r["original_column"],
            "canonical_field": r["canonical_field"],
            "confidence": float(r["confidence"]),
            "is_ambiguous": r["is_ambiguous"],
            "reasoning": r["reasoning"],
        }
        by_original[r["original_column"]] = col_info
        if r["canonical_field"]:
            by_canonical[r["canonical_field"]] = r["original_column"]

    return {
        "by_original": by_original,
        "by_canonical": by_canonical,
    }


def resolve_canonical_field(db: Session, dataset_id: Any, canonical_field: str) -> Dict[str, Any]:
    """
    Resolve a canonical business field for the specified dataset.
    Checks system.column_mappings for an active mapping.
    """
    row = db.execute(
        text(
            """
            SELECT original_column, confidence, is_ambiguous, reasoning
            FROM system.column_mappings
            WHERE dataset_id = :dataset_id AND canonical_field = :canonical_field
            ORDER BY confidence DESC
            LIMIT 1
            """
        ),
        {"dataset_id": dataset_id, "canonical_field": canonical_field}
    ).mappings().first()

    if not row:
        return {
            "resolved": False,
            "original_column": None,
            "error": f"The uploaded dataset does not contain column for '{canonical_field}'.",
            "is_ambiguous": False
        }

    if row["is_ambiguous"]:
        return {
            "resolved": False,
            "original_column": row["original_column"],
            "error": f"The requested concept '{canonical_field}' has an ambiguous column mapping ({row['reasoning']}).",
            "is_ambiguous": True
        }

    return {
        "resolved": True,
        "original_column": row["original_column"],
        "error": None,
        "is_ambiguous": False
    }

