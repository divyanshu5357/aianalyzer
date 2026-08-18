import re
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.ingestion.schema_mapper import resolve_canonical_field

METRIC_COLUMN_MAP = {
    "admission": "cy_admission",
    "admissions": "cy_admission",
    "leads": "cy_leads",
    "lead": "cy_leads",
    "enquiries": "cy_leads",
    "enquiry": "cy_leads",
    "cucet": "cy_cucet",
    "registration": "cy_cucet",
    "py_leads": "py_leads",
    "py_admission": "py_admission",
    "py_cucet": "py_cucet",
}

CANONICAL_ANALYTICS_COLUMNS = {
    "main_source": "main_source",
    "source": "source",
    "sub_source": "sub_source",
    "channel": "source",
    "category": "main_source",
    "lead_type": "lead_type",
    "program_name": "program_name",
    "program": "program_name",
    "course": "program_name",
    "courses": "program_name",
    "campus_name": "campus_name",
    "campus": "campus_name",
    "state": "state",
    "owner": "owner",
    "counselor": "owner",
    "counsellor": "owner",
    "cluster": "cluster",
}


def get_metric_column(metric: str, requested_year: int | None, current_year: int, previous_year: int) -> str:
    m = metric.lower().strip()
    is_py = False
    
    if requested_year is not None:
        if requested_year == previous_year:
            is_py = True
            
    if is_py:
        if "lead" in m or "enquir" in m:
            return "py_leads"
        elif "cucet" in m or "regist" in m:
            return "py_cucet"
        else:
            return "py_admission"
    else:
        if "lead" in m or "enquir" in m:
            return "cy_leads"
        elif "cucet" in m or "regist" in m:
            return "cy_cucet"
        else:
            return "cy_admission"


def get_missing_filter_clauses(question: str, cols: list[str]) -> list[str]:
    q_lower = question.lower()
    # Explicitly check for queries asking about missing / empty / null data
    missing_keywords = ["missing", "unknown", "null", "none", "no ", "without", "unassigned", "blank", "empty"]
    if any(kw in q_lower for kw in missing_keywords):
        return []
    
    clauses = []
    for col in cols:
        clauses.append(
            f"\"{col}\" IS NOT NULL AND TRIM(LOWER(\"{col}\")) NOT IN ('', 'none', 'null', 'n/a', 'na', 'unknown', '-', 'none/unknown', 'total', 'grand total', 'grand_total')"
        )
    return clauses


def resolve_canonical_dim(db: Session, dataset_id: Any, dim_raw: str) -> dict[str, Any]:
    dim_lower = dim_raw.lower().strip()
    if dim_lower in CANONICAL_ANALYTICS_COLUMNS:
        return {"resolved": True, "original_column": CANONICAL_ANALYTICS_COLUMNS[dim_lower], "error": None}

    # Fallback to system.column_mappings lookup
    res = resolve_canonical_field(db, dataset_id, dim_lower)
    if res["resolved"]:
        # Map original raw CSV name to canonical analytics column if possible
        orig = res["original_column"]
        for can_col in ["program_name", "campus_name", "owner", "source", "main_source", "sub_source", "state", "lead_type", "cluster"]:
            if can_col in orig.lower() or dim_lower in can_col:
                return {"resolved": True, "original_column": can_col, "error": None}

    return {"resolved": False, "original_column": None, "error": f"Could not map dimension '{dim_raw}' to a database column."}


def validate_dataset_value(db: Session, dataset_id: Any, col_name: str, requested_val: str) -> tuple[bool, str | None]:
    """Validate if requested_val exists in staging/analytics under col_name using fast DB queries."""
    if not requested_val or not col_name:
        return False, None

    req_clean = requested_val.strip()
    req_lower = req_clean.lower()
    req_upper = req_clean.upper()

    # 1. Exact case-sensitive match (B-tree index, instant)
    try:
        sql = text(
            f'SELECT "{col_name}" FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id AND "{col_name}" = :val LIMIT 1'
        )
        res = db.execute(sql, {"ds_id": dataset_id, "val": req_clean}).scalar()
        if res is not None:
            return True, str(res)
    except Exception:
        db.rollback()

    # 2. Uppercase match (since most DB values are stored in uppercase, hits B-tree index, instant)
    try:
        sql = text(
            f'SELECT "{col_name}" FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id AND "{col_name}" = :val LIMIT 1'
        )
        res = db.execute(sql, {"ds_id": dataset_id, "val": req_upper}).scalar()
        if res is not None:
            return True, str(res)
    except Exception:
        db.rollback()

    # 3. Case-insensitive exact match fallback (runs sequential scan)
    try:
        sql = text(
            f'SELECT "{col_name}" FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id AND LOWER("{col_name}") = :val LIMIT 1'
        )
        res = db.execute(sql, {"ds_id": dataset_id, "val": req_lower}).scalar()
        if res is not None:
            return True, str(res)
    except Exception:
        db.rollback()

    return False, None


def get_distinct_dimension_values(db: Session, dataset_id: str, col: str) -> list[str]:
    try:
        sql = text(f'SELECT DISTINCT "{col}" FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id AND "{col}" IS NOT NULL AND "{col}" != \'\'')
        res = db.execute(sql, {"ds_id": dataset_id}).scalars().all()
        return [str(x) for x in res]
    except Exception:
        db.rollback()
        return []


def resolve_flexible_entity(db: Session, dataset_id: str, user_val: str) -> dict[str, Any]:
    """
    Resolves user-provided partial name to a distinct dataset entity across canonical dimensions.
    Returns a dict with: {
        'resolved': bool,
        'dimension': str | None,
        'value': str | None,
        'candidates': list[tuple[str, str]] | None,
        'ambiguous': bool
    }
    """
    from difflib import SequenceMatcher
    clean_val = str(user_val).strip()
    if not clean_val:
        return {"resolved": False, "dimension": None, "value": None, "candidates": None, "ambiguous": False}

    dims_to_check = ["program_name", "campus_name", "state", "owner", "source", "main_source"]
    dim_values = {}
    for d in dims_to_check:
        dim_values[d] = get_distinct_dimension_values(db, dataset_id, d)

    def _normalize(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    user_norm = _normalize(clean_val)

    # 1. Exact case-sensitive match
    exact_matches = []
    for d, vals in dim_values.items():
        for v in vals:
            if v == clean_val:
                exact_matches.append((d, v))
    if len(exact_matches) == 1:
        return {"resolved": True, "dimension": exact_matches[0][0], "value": exact_matches[0][1], "candidates": None, "ambiguous": False}
    elif len(exact_matches) > 1:
        return {"resolved": False, "dimension": None, "value": None, "candidates": exact_matches, "ambiguous": True}

    # 2. Case-insensitive match
    ci_matches = []
    for d, vals in dim_values.items():
        for v in vals:
            if v.lower() == clean_val.lower():
                ci_matches.append((d, v))
    if len(ci_matches) == 1:
        return {"resolved": True, "dimension": ci_matches[0][0], "value": ci_matches[0][1], "candidates": None, "ambiguous": False}
    elif len(ci_matches) > 1:
        return {"resolved": False, "dimension": None, "value": None, "candidates": ci_matches, "ambiguous": True}

    # 3. Whitespace / punctuation normalization match
    norm_matches = []
    for d, vals in dim_values.items():
        for v in vals:
            if _normalize(v) == user_norm:
                norm_matches.append((d, v))
    if len(norm_matches) == 1:
        return {"resolved": True, "dimension": norm_matches[0][0], "value": norm_matches[0][1], "candidates": None, "ambiguous": False}
    elif len(norm_matches) > 1:
        return {"resolved": False, "dimension": None, "value": None, "candidates": norm_matches, "ambiguous": True}

    # 4. Normalized substring match (e.g., "B.E CSE" matching "B.E. CSE : CS201")
    norm_sub_matches = []
    for d, vals in dim_values.items():
        for v in vals:
            if user_norm in _normalize(v):
                norm_sub_matches.append((d, v))
    if len(norm_sub_matches) == 1:
        return {"resolved": True, "dimension": norm_sub_matches[0][0], "value": norm_sub_matches[0][1], "candidates": None, "ambiguous": False}
    elif len(norm_sub_matches) > 1:
        prefix_matches = [m for m in norm_sub_matches if _normalize(m[1]).startswith(user_norm)]
        if len(prefix_matches) == 1:
            return {"resolved": True, "dimension": prefix_matches[0][0], "value": prefix_matches[0][1], "candidates": None, "ambiguous": False}
        unique_candidates = list(set(norm_sub_matches))
        if len(unique_candidates) == 1:
            return {"resolved": True, "dimension": unique_candidates[0][0], "value": unique_candidates[0][1], "candidates": None, "ambiguous": False}
        return {"resolved": False, "dimension": None, "value": None, "candidates": unique_candidates, "ambiguous": True}

    # 5. Token-based matching (e.g. CS201)
    token_matches = []
    for d, vals in dim_values.items():
        for v in vals:
            tokens = [t.lower() for t in re.split(r"[^a-zA-Z0-9]", v) if t]
            if clean_val.lower() in tokens:
                token_matches.append((d, v))
    if len(token_matches) == 1:
        return {"resolved": True, "dimension": token_matches[0][0], "value": token_matches[0][1], "candidates": None, "ambiguous": False}
    elif len(token_matches) > 1:
        unique_token_candidates = list(set(token_matches))
        if len(unique_token_candidates) == 1:
            return {"resolved": True, "dimension": unique_token_candidates[0][0], "value": unique_token_candidates[0][1], "candidates": None, "ambiguous": False}
        return {"resolved": False, "dimension": None, "value": None, "candidates": unique_token_candidates, "ambiguous": True}

    # 6. Substring match
    sub_matches = []
    for d, vals in dim_values.items():
        for v in vals:
            if clean_val.lower() in v.lower():
                sub_matches.append((d, v))
    if len(sub_matches) == 1:
        return {"resolved": True, "dimension": sub_matches[0][0], "value": sub_matches[0][1], "candidates": None, "ambiguous": False}
    elif len(sub_matches) > 1:
        unique_sub_candidates = list(set(sub_matches))
        if len(unique_sub_candidates) == 1:
            return {"resolved": True, "dimension": unique_sub_candidates[0][0], "value": unique_sub_candidates[0][1], "candidates": None, "ambiguous": False}
        return {"resolved": False, "dimension": None, "value": None, "candidates": unique_sub_candidates, "ambiguous": True}

    # 7. Fuzzy matching (SequenceMatcher, high threshold > 0.8)
    fuzzy_matches = []
    for d, vals in dim_values.items():
        for v in vals:
            ratio = SequenceMatcher(None, _normalize(v), user_norm).ratio()
            if ratio >= 0.8:
                fuzzy_matches.append((ratio, d, v))
    if fuzzy_matches:
        fuzzy_matches.sort(key=lambda x: x[0], reverse=True)
        highest_score = fuzzy_matches[0][0]
        best_matches = [f for f in fuzzy_matches if f[0] == highest_score]
        if len(best_matches) == 1:
            return {"resolved": True, "dimension": best_matches[0][1], "value": best_matches[0][2], "candidates": None, "ambiguous": False}
        else:
            candidates = list(set([(b[1], b[2]) for b in best_matches]))
            if len(candidates) == 1:
                return {"resolved": True, "dimension": candidates[0][0], "value": candidates[0][1], "candidates": None, "ambiguous": False}
            return {"resolved": False, "dimension": None, "value": None, "candidates": candidates, "ambiguous": True}

    return {"resolved": False, "dimension": None, "value": None, "candidates": None, "ambiguous": False}
