"""
Dynamic Relationship & Column Mapping Detector.

Inspects profiled sheets and tables to detect relationships using common keys,
synonym clusters, and sample value overlap. Calculates confidence scores and
enforces confirmation guardrails for ambiguous or low-confidence matches.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple


def normalize_slug(col_name: str) -> str:
    """Normalize column name to an alphanumeric lowercase slug."""
    if not col_name:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(col_name).lower())


def tokenize_name(col_name: str) -> Set[str]:
    """Tokenize a column name into clean alphanumeric words."""
    if not col_name:
        return set()
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", str(col_name)).lower()
    return {w for w in cleaned.split() if w}


# ─────────────────────────────────────────────────────────────────────────────
# Canonical Keys and Synonym Registry
# ─────────────────────────────────────────────────────────────────────────────

CANONICAL_KEYS: Dict[str, Dict[str, Any]] = {
    "ProspectID": {
        "entity": "Prospect",
        "primary_column": "ProspectID",
        "variations": [
            "prospectid", "prospect_id", "prospect id", "leadid", "lead_id", "lead id",
            "inquiryid", "inquiry_id", "inquiry id", "enquiryid", "enquiry_id", "enquiry id",
            "application_id", "applicationid"
        ],
        "description": "Unique prospect or lead identifier",
        "is_primary_key": True,
    },
    "Program Code": {
        "entity": "Program",
        "primary_column": "Program Code",
        "variations": [
            "programcode", "program_code", "program code", "coursecode", "course_code",
            "course code", "program_id", "course_id", "program_name_short", "degree_code",
            "prog_code", "progcode"
        ],
        "description": "Academic program or course code",
        "is_primary_key": True,
    },
    "State Code": {
        "entity": "State",
        "primary_column": "State Code",
        "variations": [
            "statecode", "state_code", "state code", "state_cd", "region_code", "state_id",
            "state_abbr", "state group", "state_group", "state"
        ],
        "description": "Geographic state abbreviation or code",
        "is_primary_key": True,
    },
    "EmployeeID": {
        "entity": "Employee",
        "primary_column": "EmployeeID",
        "variations": [
            "employeeid", "employee_id", "employee id", "ownerid", "owner_id", "owner id",
            "counselorid", "counselor_id", "counselor id", "empid", "emp_id", "emp id",
            "counsellor_id", "counsellorid", "staff_id", "agent_id"
        ],
        "description": "Counselor or employee identifier",
        "is_primary_key": True,
    },
    "Source Code": {
        "entity": "Source",
        "primary_column": "Source Code",
        "variations": [
            "sourcecode", "source_code", "source code", "sourceid", "source_id", "source id",
            "channel_code", "channel_id", "leaf_source_id"
        ],
        "description": "Marketing channel or source identifier",
        "is_primary_key": True,
    },
    "Target Leads": {
        "entity": "Target",
        "primary_column": "Target Leads",
        "variations": [
            "target_leads", "target leads", "target_enquiries", "leads_target", "target_leads_cnt"
        ],
        "description": "Target number of leads/enquiries",
        "is_primary_key": False,
    },
    "Target Admissions": {
        "entity": "Target",
        "primary_column": "Target Admissions",
        "variations": [
            "target_admissions", "target admissions", "admissions_target", "target_adm"
        ],
        "description": "Target number of admissions",
        "is_primary_key": False,
    },
    "Target CUCET": {
        "entity": "Target",
        "primary_column": "Target CUCET",
        "variations": [
            "target_cucet", "target cucet", "cucet_target", "target_reg"
        ],
        "description": "Target number of CUCET registrations",
        "is_primary_key": False,
    },
    "Target Month": {
        "entity": "Target",
        "primary_column": "Target Month",
        "variations": [
            "target_month", "month", "period_month", "month_num", "target_period"
        ],
        "description": "Target month number (1..12 or NULL for annual)",
        "is_primary_key": False,
    },
    "Dimension Type": {
        "entity": "Target",
        "primary_column": "Dimension Type",
        "variations": [
            "dimension_type", "dim_type", "level", "target_level", "dimension"
        ],
        "description": "Target breakdown dimension type (program, state, source, campus, overall)",
        "is_primary_key": False,
    },
    "Dimension Value": {
        "entity": "Target",
        "primary_column": "Dimension Value",
        "variations": [
            "dimension_value", "dim_value", "target_value", "value_name"
        ],
        "description": "Target breakdown dimension value",
        "is_primary_key": False,
    },
    "Campus": {
        "entity": "Campus",
        "primary_column": "Campus",
        "variations": [
            "campus", "campus_name", "campus name", "location", "center", "branch"
        ],
        "description": "University campus or location",
        "is_primary_key": False,
    },
    "Academic Year": {
        "entity": "AcademicYear",
        "primary_column": "Academic Year",
        "variations": [
            "academic_year", "academicyear", "academic year", "session_year", "session",
            "academic_session", "admission_year", "year"
        ],
        "description": "Academic intake session year",
        "is_primary_key": False,
    },
}

# Inverted slug index for rapid lookup
_SLUG_TO_CANONICAL: Dict[str, str] = {}
for can_key, meta in CANONICAL_KEYS.items():
    for var in meta["variations"]:
        _SLUG_TO_CANONICAL[normalize_slug(var)] = can_key
    _SLUG_TO_CANONICAL[normalize_slug(can_key)] = can_key
    _SLUG_TO_CANONICAL[normalize_slug(meta["primary_column"])] = can_key


def resolve_canonical_key(col_name: str) -> Optional[str]:
    """Resolve a column name to its canonical key group if known."""
    slug = normalize_slug(col_name)
    if slug in _SLUG_TO_CANONICAL:
        return _SLUG_TO_CANONICAL[slug]

    # Partial substring match for key suffixes (e.g., 'student_prospect_id')
    for var_slug, can_key in _SLUG_TO_CANONICAL.items():
        if len(var_slug) >= 6 and (slug.endswith(var_slug) or slug.startswith(var_slug)):
            return can_key

    return None


def calculate_jaccard_similarity(samples_a: List[Any], samples_b: List[Any]) -> float:
    """Calculate Jaccard overlap between sample value sets."""
    set_a = {str(x).strip().lower() for x in samples_a if x is not None and str(x).strip()}
    set_b = {str(x).strip().lower() for x in samples_b if x is not None and str(x).strip()}
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return round(intersection / union, 4) if union > 0 else 0.0


def score_column_pair(
    src_col: Dict[str, Any],
    tgt_col: Dict[str, Any],
) -> Tuple[float, str, bool]:
    """
    Score similarity between a source column and target column.
    Returns: (confidence, match_type, is_key_relationship)
    """
    src_name = src_col.get("name", "")
    tgt_name = tgt_col.get("name", "")

    src_slug = normalize_slug(src_name)
    tgt_slug = normalize_slug(tgt_name)

    src_is_key = src_col.get("is_likely_key", False)
    tgt_is_key = tgt_col.get("is_likely_key", False)

    src_samples = src_col.get("sample_values") or []
    tgt_samples = tgt_col.get("sample_values") or []
    jaccard = calculate_jaccard_similarity(src_samples, tgt_samples)

    # 1. Exact slug match
    if src_slug == tgt_slug:
        confidence = 0.98 if (src_is_key and tgt_is_key) else 0.95
        if jaccard > 0.2:
            confidence = 1.0
        return (round(confidence, 4), "exact", src_is_key and tgt_is_key)

    # 2. Canonical synonym group match
    src_can = resolve_canonical_key(src_name)
    tgt_can = resolve_canonical_key(tgt_name)

    if src_can and tgt_can and src_can == tgt_can:
        confidence = 0.88
        if src_is_key or tgt_is_key:
            confidence += 0.04
        if jaccard > 0.15:
            confidence = min(1.0, confidence + 0.08)
        return (round(confidence, 4), "synonym", True)

    # 3. Token overlap match
    src_tokens = tokenize_name(src_name)
    tgt_tokens = tokenize_name(tgt_name)
    overlap = src_tokens & tgt_tokens
    if overlap:
        token_ratio = len(overlap) / max(len(src_tokens), len(tgt_tokens))
        if token_ratio >= 0.66:
            conf = 0.75 + (0.10 if (src_is_key and tgt_is_key) else 0.0)
            if jaccard > 0.2:
                conf = min(0.95, conf + 0.10)
            return (round(conf, 4), "token_overlap", src_is_key or tgt_is_key)
        elif token_ratio >= 0.5:
            return (round(0.65, 4), "partial", False)

    # 4. Pure data overlap match (same type, high sample overlap)
    if jaccard >= 0.5 and src_col.get("dtype") == tgt_col.get("dtype"):
        return (round(0.70 + (jaccard * 0.15), 4), "value_overlap", src_is_key and tgt_is_key)

    return (0.0, "none", False)


# ─────────────────────────────────────────────────────────────────────────────
# Relationship Detection Engine
# ─────────────────────────────────────────────────────────────────────────────

HIGH_CONFIDENCE_THRESHOLD = 0.85


def detect_sheet_relationships(
    source_sheet: Dict[str, Any],
    target_sheet: Dict[str, Any],
    source_file: str = "source",
    target_file: str = "target",
) -> List[Dict[str, Any]]:
    """
    Detects relationship candidates between columns in two sheets/tables.
    Flags ambiguous matches and marks confirmation requirements.
    """
    source_cols = source_sheet.get("columns_profile") or source_sheet.get("columns_info") or []
    target_cols = target_sheet.get("columns_profile") or target_sheet.get("columns_info") or []

    s_sheet_name = source_sheet.get("sheet_name", "default")
    t_sheet_name = target_sheet.get("sheet_name", "default")

    candidates: List[Dict[str, Any]] = []

    for s_col in source_cols:
        s_name = s_col.get("name")
        if not s_name:
            continue

        best_matches: List[Dict[str, Any]] = []

        for t_col in target_cols:
            t_name = t_col.get("name")
            if not t_name:
                continue

            conf, match_type, is_key = score_column_pair(s_col, t_col)
            if conf >= 0.50:
                best_matches.append({
                    "source_file": source_file,
                    "source_sheet": s_sheet_name,
                    "source_column": s_name,
                    "target_entity": target_file,
                    "target_sheet": t_sheet_name,
                    "target_column": t_name,
                    "confidence": conf,
                    "match_type": match_type,
                    "is_key_relationship": is_key,
                    "source_type": s_col.get("dtype", "string"),
                    "target_type": t_col.get("dtype", "string"),
                    "source_sample": (s_col.get("sample_values") or [])[:3],
                    "target_sample": (t_col.get("sample_values") or [])[:3],
                })

        if not best_matches:
            continue

        # Sort candidate matches by confidence descending
        best_matches.sort(key=lambda x: x["confidence"], reverse=True)
        top = best_matches[0]

        # Check for ambiguity: multiple targets within close range (< 0.12 diff)
        is_ambiguous = False
        if len(best_matches) > 1 and (top["confidence"] - best_matches[1]["confidence"]) < 0.12:
            is_ambiguous = True

        requires_confirmation = (top["confidence"] < HIGH_CONFIDENCE_THRESHOLD) or is_ambiguous
        status = "suggested" if (top["confidence"] >= HIGH_CONFIDENCE_THRESHOLD and not is_ambiguous) else "requires_confirmation"

        top["is_ambiguous"] = is_ambiguous
        top["requires_confirmation"] = requires_confirmation
        top["status"] = status
        top["competing_candidates"] = [m["target_column"] for m in best_matches[1:3]] if is_ambiguous else []

        candidates.append(top)

    return candidates


def detect_relationships_against_canonical_entities(
    source_sheet: Dict[str, Any],
    source_file: str = "upload",
) -> List[Dict[str, Any]]:
    """
    Detects relationships between an uploaded sheet and standard organizational entities:
    Prospect, Program, State, Employee, Source, Campus, AcademicYear.
    """
    source_cols = source_sheet.get("columns_profile") or source_sheet.get("columns_info") or []
    s_sheet_name = source_sheet.get("sheet_name", "default")

    results: List[Dict[str, Any]] = []

    for s_col in source_cols:
        s_name = s_col.get("name")
        if not s_name:
            continue

        can_key = resolve_canonical_key(s_name)
        if not can_key:
            continue

        meta = CANONICAL_KEYS[can_key]
        target_entity = meta["entity"]
        target_column = meta["primary_column"]

        # Calculate exact vs synonym confidence
        s_slug = normalize_slug(s_name)
        t_slug = normalize_slug(target_column)

        if s_slug == t_slug:
            conf = 0.98
            match_type = "exact"
        else:
            conf = 0.88
            match_type = "synonym"

        s_is_key = s_col.get("is_likely_key", False)
        if s_is_key and meta["is_primary_key"]:
            conf = min(1.0, conf + 0.02)

        requires_confirmation = conf < HIGH_CONFIDENCE_THRESHOLD
        status = "suggested" if not requires_confirmation else "requires_confirmation"

        results.append({
            "source_file": source_file,
            "source_sheet": s_sheet_name,
            "source_column": s_name,
            "target_entity": target_entity,
            "target_sheet": "default",
            "target_column": target_column,
            "confidence": round(conf, 4),
            "confidence_rating": "HIGH" if conf >= 0.85 else "MEDIUM",
            "status": status,
            "match_type": match_type,
            "is_key_relationship": meta["is_primary_key"],
            "value_overlap_pct": 0.0,
            "value_overlap_label": "Not evaluated",
            "requires_confirmation": requires_confirmation,
            "is_ambiguous": False,
            "competing_candidates": [],
            "source_type": s_col.get("dtype", "string"),
            "target_type": "string",
            "source_sample": (s_col.get("sample_values") or [])[:3],
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Blank Program Code Policy (Rule 9)
# ─────────────────────────────────────────────────────────────────────────────

def clean_or_unmap_program_code(code_value: Any) -> Optional[str]:
    """
    Enforces Phase 1 & 2 rule:
    If raw Program Code is blank, DO NOT invent a Program.
    Mark the record as unmapped (None).
    Do NOT query course_master or use hashing to guess programs.
    """
    if code_value is None:
        return None
    cleaned = str(code_value).strip()
    if not cleaned or cleaned.lower() in ("null", "none", "nan", "n/a", "undefined", "-", "--"):
        return None
    return cleaned


def detect_multisheet_workbook_relationships(
    workbook_profiles: List[Dict[str, Any]],
    saved_mappings: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Cross-file, multi-sheet relationship detector supporting RAW, DIMENSION, and TARGET workbooks.
    Uses column names, synonyms, data types, sample value overlap (Jaccard), and saved mappings.
    Assigns confidence rating: HIGH (>= 0.85), MEDIUM (0.60-0.84), LOW (< 0.60).
    """
    from app.mapping.workbook_classifier import calculate_value_overlap, classify_sheet

    detected_relationships: List[Dict[str, Any]] = []
    saved_lookup = {}
    if saved_mappings:
        for sm in saved_mappings:
            key = (
                str(sm.get("source_file", "")).lower(),
                str(sm.get("source_column", "")).lower(),
            )
            saved_lookup[key] = sm

    # Extract all sheet profiles across all workbooks
    all_sheets = []
    for wb in workbook_profiles:
        wb_name = wb.get("filename") or wb.get("source_file") or "workbook"
        for s in wb.get("sheets", []):
            classification = classify_sheet(s)
            all_sheets.append({
                "filename": wb_name,
                "sheet_name": s.get("sheet_name", "Sheet1"),
                "sheet_type": classification["sheet_type"],
                "columns": s.get("columns", []) or s.get("columns_profile", []),
            })

    # Compare column pairs across sheets
    for i, sheet_a in enumerate(all_sheets):
        for j, sheet_b in enumerate(all_sheets):
            if i >= j and sheet_a["filename"] == sheet_b["filename"]:
                continue

            for col_a in sheet_a["columns"]:
                name_a = col_a.get("name")
                if not name_a:
                    continue

                for col_b in sheet_b["columns"]:
                    name_b = col_b.get("name")
                    if not name_b:
                        continue

                    # Calculate column pair score
                    score, match_type, is_key = score_column_pair(col_a, col_b)

                    # Compute value overlap percentage if sample values present
                    samples_a = col_a.get("sample_values") or []
                    samples_b = col_b.get("sample_values") or []
                    value_overlap = calculate_value_overlap(samples_a, samples_b)

                    # Boost score if value overlap is high
                    if value_overlap >= 0.5:
                        score = min(1.0, score + 0.10)
                    elif value_overlap >= 0.2:
                        score = min(1.0, score + 0.05)

                    # Check saved mapping match
                    saved_match = saved_lookup.get((sheet_a["filename"].lower(), name_a.lower()))
                    if saved_match and str(saved_match.get("canonical_field", "")).lower() == name_b.lower():
                        score = 0.98
                        match_type = "saved_mapping"

                    if score < 0.60:
                        rating = "LOW"
                    elif score >= 0.85:
                        rating = "HIGH"
                    else:
                        rating = "MEDIUM"

                    # Value overlap label for code/identifier mappings vs string overlap
                    is_code_or_key = is_key or (resolve_canonical_key(name_a) is not None)
                    if is_code_or_key or not samples_a or not samples_b or value_overlap == 0.0:
                        val_label = "Not evaluated"
                    else:
                        val_label = f"{round(value_overlap * 100, 1)}% match"

                    if rating in ("HIGH", "MEDIUM"):
                        detected_relationships.append({
                            "source_file": sheet_a["filename"],
                            "source_sheet": sheet_a["sheet_name"],
                            "source_column": name_a,
                            "target_file": sheet_b["filename"],
                            "target_sheet": sheet_b["sheet_name"],
                            "target_column": name_b,
                            "confidence": round(score, 4),
                            "confidence_rating": rating,
                            "match_type": match_type,
                            "value_overlap_pct": round(value_overlap * 100, 1),
                            "value_overlap_label": val_label,
                            "is_key_relationship": is_key,
                            "requires_confirmation": rating == "MEDIUM",
                            "status": "suggested" if rating == "HIGH" else "requires_confirmation",
                        })

    return detected_relationships

