"""
Authoritative Program Resolution Service
Resolves user program text/abbreviations to canonical ProgramCode and ProgramName.
Uses PostgreSQL analytics.uploaded_metrics and organization.course_master dynamically.
"""
import re
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _unwrap_dataset_id(ds_id: Any) -> Optional[str]:
    if not ds_id:
        return None
    if isinstance(ds_id, (list, tuple)):
        return str(ds_id[0]) if ds_id else None
    return str(ds_id)


def get_program_directory(db: Session, dataset_id: Any = None) -> List[Dict[str, Any]]:
    """
    Query distinct programs dynamically from analytics.uploaded_metrics + organization.course_master.
    Prioritizes active programs in analytics.uploaded_metrics if dataset_id is provided.
    """
    try:
        ds_str = _unwrap_dataset_id(dataset_id)
        if ds_str:
            sql_ds = text("""
                SELECT DISTINCT 
                    COALESCE(m.program_code, cm.program_code) as program_code,
                    COALESCE(m.program_name, cm.program_name) as program_name,
                    cm.program_name_short
                FROM analytics.uploaded_metrics m
                LEFT JOIN organization.course_master cm ON LOWER(TRIM(m.program_code)) = LOWER(TRIM(cm.program_code))
                WHERE m.dataset_id = :ds AND COALESCE(m.program_code, cm.program_code) IS NOT NULL
            """)
            rows_ds = db.execute(sql_ds, {"ds": ds_str}).mappings().all()
            if rows_ds:
                return [dict(r) for r in rows_ds if r.get("program_code")]


        sql = text("""
            SELECT DISTINCT 
                COALESCE(m.program_code, cm.program_code) as program_code,
                COALESCE(m.program_name, cm.program_name) as program_name,
                cm.program_name_short
            FROM analytics.uploaded_metrics m
            FULL OUTER JOIN organization.course_master cm ON LOWER(TRIM(m.program_code)) = LOWER(TRIM(cm.program_code))
            WHERE COALESCE(m.program_code, cm.program_code) IS NOT NULL
        """)
        rows = db.execute(sql).mappings().all()
        return [dict(r) for r in rows if r.get("program_code")]
    except Exception as e:
        logger.warning(f"Error fetching program directory: {e}")
        db.rollback()
        return []



def tokenize_program_str(s: str) -> set:
    if not s:
        return set()
    s = s.lower()
    s = s.replace("ai & ml", "artificial intelligence machine learning")
    s = s.replace("ai&ml", "artificial intelligence machine learning")
    s = s.replace("ai", "artificial intelligence")
    s = s.replace("ml", "machine learning")
    s = s.replace("cse", "computer science engineering")
    tokens = set(re.findall(r"[a-z0-9]+", s))
    return tokens


def resolve_canonical_program(db: Session, dataset_id: Any, user_str: str) -> Dict[str, Any]:
    """
    Resolves user program string to canonical ProgramCode and ProgramName.
    """
    if not user_str or not str(user_str).strip():
        return {"resolved": False, "program_code": None, "program_name": None, "candidates": []}

    clean = str(user_str).strip()
    clean_lower = clean.lower()
    clean_upper = clean.upper()

    progs = get_program_directory(db, dataset_id)
    if not progs:
        return {"resolved": False, "program_code": None, "program_name": clean, "candidates": []}

    # 1. Exact code match (e.g. CS221, CS201)
    for p in progs:
        code = (p.get("program_code") or "").upper().strip()
        if code and code == clean_upper:
            return {
                "resolved": True,
                "program_code": code,
                "program_name": p["program_name"],
                "program_name_short": p.get("program_name_short"),
                "candidates": None
            }

    # 2. Code embedded in user string (e.g. "CS221" or "(CS221)" or ": CS221")
    for p in progs:
        code = (p.get("program_code") or "").upper().strip()
        if code and re.search(rf"\b{re.escape(code)}\b", clean_upper):
            return {
                "resolved": True,
                "program_code": code,
                "program_name": p["program_name"],
                "program_name_short": p.get("program_name_short"),
                "candidates": None
            }

    # 3. Exact name match or short name match
    for p in progs:
        name = (p.get("program_name") or "").lower().strip()
        short = (p.get("program_name_short") or "").lower().strip()
        if clean_lower == name or clean_lower == short:
            return {
                "resolved": True,
                "program_code": p["program_code"],
                "program_name": p["program_name"],
                "program_name_short": p.get("program_name_short"),
                "candidates": None
            }

    user_tokens = tokenize_program_str(clean)
    
    # 4. Token Overlap & Specialization Scoring
    scored = []
    for p in progs:
        p_name = p.get("program_name") or ""
        p_short = p.get("program_name_short") or ""
        p_tokens = tokenize_program_str(p_name) | tokenize_program_str(p_short) | tokenize_program_str(p.get("program_code") or "")
        
        if not p_tokens or not user_tokens:
            continue

        overlap = user_tokens.intersection(p_tokens)
        score = len(overlap) / len(user_tokens)
        
        key_specs = {"ibm", "artificial", "intelligence", "learning", "blockchain", "cloud", "cyber", "data", "iot", "tcs", "virtusa", "leet"}
        user_specs = user_tokens.intersection(key_specs)
        p_specs = p_tokens.intersection(key_specs)

        if user_specs and user_specs == p_specs:
            score += 0.3
        elif user_specs and not user_specs.issubset(p_specs):
            score -= 0.5

        if score > 0.4:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)

    if scored:
        top_score = scored[0][0]
        top_matches = [item[1] for item in scored if item[0] >= top_score - 0.05]
        
        if len(top_matches) == 1:
            return {
                "resolved": True,
                "program_code": top_matches[0]["program_code"],
                "program_name": top_matches[0]["program_name"],
                "program_name_short": top_matches[0].get("program_name_short"),
                "candidates": None
            }
        else:
            # Check general B.E CSE vs specialized CSE fallback
            has_spec = any(w in user_tokens for w in ["artificial", "intelligence", "ibm", "cloud", "blockchain", "cyber", "leet", "data", "iot", "tcs", "virtusa", "applied"])
            if not has_spec and "computer" in user_tokens:
                general_cse = [m for m in top_matches if m["program_code"] == "CS201" or m["program_name"] == "Bachelor of Engineering - Computer Science & Engineering"]
                if general_cse:
                    return {
                        "resolved": True,
                        "program_code": general_cse[0]["program_code"],
                        "program_name": general_cse[0]["program_name"],
                        "program_name_short": general_cse[0].get("program_name_short"),
                        "candidates": None
                    }
                    
            unique_cands = []
            seen_codes = set()
            for m in top_matches:
                if m["program_code"] not in seen_codes:
                    seen_codes.add(m["program_code"])
                    unique_cands.append(m)
            
            if len(unique_cands) == 1:
                return {
                    "resolved": True,
                    "program_code": unique_cands[0]["program_code"],
                    "program_name": unique_cands[0]["program_name"],
                    "program_name_short": unique_cands[0].get("program_name_short"),
                    "candidates": None
                }

            return {
                "resolved": False,
                "program_code": None,
                "program_name": None,
                "candidates": unique_cands
            }

    return {"resolved": False, "program_code": None, "program_name": None, "candidates": []}
