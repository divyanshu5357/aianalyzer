"""
Workbook and Sheet Classification Engine.
Classifies multi-sheet Excel/CSV files and individual sheets into functional roles:
- RAW (CRM leads, enquiries, raw transaction data)
- DIMENSION (Master lookup tables: Program, State, Source, EMP/Counselor, Campus)
- TARGET (Annual/Monthly target tables)

Also computes Jaccard sample value overlap between column pairs.
"""
import re
import logging
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def calculate_value_overlap(sample_values_a: List[Any], sample_values_b: List[Any]) -> float:
    """
    Computes Jaccard similarity ratio between two lists of sample values.
    Returns float between 0.0 and 1.0.
    """
    if not sample_values_a or not sample_values_b:
        return 0.0

    set_a: Set[str] = {
        str(v).strip().lower()
        for v in sample_values_a
        if v is not None and str(v).strip() != "" and str(v).strip().lower() not in ("null", "none", "n/a")
    }
    set_b: Set[str] = {
        str(v).strip().lower()
        for v in sample_values_b
        if v is not None and str(v).strip() != "" and str(v).strip().lower() not in ("null", "none", "n/a")
    }

    if not set_a or not set_b:
        return 0.0

    intersection = set_a.intersection(set_b)
    union = set_a.union(set_b)

    if not union:
        return 0.0

    return round(len(intersection) / len(union), 4)


def classify_sheet(sheet_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classifies a single sheet based on name, columns, and metric keys.
    Returns dict with sheet_type, confidence, and primary_entity.
    """
    sheet_name = str(sheet_profile.get("sheet_name", "")).strip().lower()
    columns = sheet_profile.get("columns") or sheet_profile.get("column_names") or sheet_profile.get("columns_profile") or []

    col_names_lower: List[str] = []
    if isinstance(columns, list):
        for c in columns:
            if isinstance(c, dict):
                col_names_lower.append(str(c.get("name", "")).strip().lower())
            elif isinstance(c, str):
                col_names_lower.append(c.strip().lower())

    # Keyword check in sheet name
    if any(k in sheet_name for k in ("target", "goal", "budget")):
        return {"sheet_type": "TARGET_TABLE", "confidence": 0.95, "primary_entity": "Target"}

    if any(k in sheet_name for k in ("program", "course", "degree")):
        return {"sheet_type": "DIMENSION_PROGRAM", "confidence": 0.90, "primary_entity": "Program"}

    if any(k in sheet_name for k in ("state", "region", "geo")):
        return {"sheet_type": "DIMENSION_STATE", "confidence": 0.90, "primary_entity": "State"}

    if any(k in sheet_name for k in ("source", "channel", "utm")):
        return {"sheet_type": "DIMENSION_SOURCE", "confidence": 0.90, "primary_entity": "Source"}

    if any(k in sheet_name for k in ("emp", "employee", "counselor", "counsellor", "owner")):
        return {"sheet_type": "DIMENSION_EMP", "confidence": 0.90, "primary_entity": "Employee"}

    if any(k in sheet_name for k in ("campus", "center", "location")):
        return {"sheet_type": "DIMENSION_CAMPUS", "confidence": 0.90, "primary_entity": "Campus"}

    # Column header analysis
    has_prospect_id = any(
        k in c for c in col_names_lower for k in ("prospectid", "prospect_id", "leadid", "lead_id", "inquiryid", "enquiryid")
    )
    has_target_metric = any(
        k in c for c in col_names_lower for k in ("target_leads", "target_admissions", "target_cucet", "target leads")
    )

    if has_target_metric:
        return {"sheet_type": "TARGET_TABLE", "confidence": 0.95, "primary_entity": "Target"}

    if has_prospect_id:
        return {"sheet_type": "RAW_LEADS", "confidence": 0.95, "primary_entity": "Prospect"}

    # Fallback default
    return {"sheet_type": "RAW_LEADS", "confidence": 0.70, "primary_entity": "Prospect"}


def classify_workbook(file_profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classifies an entire multi-sheet workbook into RAW, DIMENSION, or TARGET based on filename and sheet profiles.
    """
    fname = str(file_profile.get("filename") or file_profile.get("original_filename") or "").strip().lower()
    
    # Filename-based explicit classification checks
    if any(k in fname for k in ("tgt", "target")):
        return {"workbook_type": "TARGET", "confidence": 0.98, "sheet_count": len(file_profile.get("sheets", [])), "sheets_summary": []}

    if "dimension" in fname:
        return {"workbook_type": "DIMENSION", "confidence": 0.98, "sheet_count": len(file_profile.get("sheets", [])), "sheets_summary": []}

    sheets = file_profile.get("sheets", [])
    if not sheets:
        return {"workbook_type": "RAW", "confidence": 0.60, "sheets_summary": []}

    sheets_summary = []
    types_count: Dict[str, int] = {}

    for s in sheets:
        res = classify_sheet(s)
        stype = res["sheet_type"]
        types_count[stype] = types_count.get(stype, 0) + 1
        sheets_summary.append({
            "sheet_name": s.get("sheet_name"),
            "sheet_type": stype,
            "confidence": res["confidence"],
            "primary_entity": res["primary_entity"],
        })

    # Overall workbook classification decision
    if types_count.get("TARGET_TABLE", 0) > 0:
        wb_type = "TARGET"
        conf = 0.95
    elif any(k in types_count for k in ("DIMENSION_PROGRAM", "DIMENSION_STATE", "DIMENSION_SOURCE", "DIMENSION_EMP", "DIMENSION_CAMPUS")):
        wb_type = "DIMENSION"
        conf = 0.90
    else:
        wb_type = "RAW"
        conf = 0.85

    return {
        "workbook_type": wb_type,
        "confidence": conf,
        "sheet_count": len(sheets),
        "sheets_summary": sheets_summary,
    }
