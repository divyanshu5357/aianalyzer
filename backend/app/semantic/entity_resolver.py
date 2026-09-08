"""
Dimension-Aware Entity Resolver
Data-driven entity resolution mapping natural-language strings ('Google', 'Inhouse', 'Punjab')
to their authoritative database dimensions (Source, Lead Type, State, Program, Owner).
"""
import logging
from typing import Any, Dict
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def resolve_entity_dimension(db: Session, dataset_id: Any, term: str) -> Dict[str, Any]:
    """
    Data-driven dimension-aware entity resolution.
    Resolves natural-language terms e.g. 'Google', 'Inhouse', 'Punjab', 'Mohali'
    to their exact canonical dimension and value in PostgreSQL.
    """
    if not term or not str(term).strip():
        return {"resolved": False, "dimension": None, "value": term, "column": None}

    clean_term = str(term).strip().lower()

    # 1. Check Lead Type synonyms
    if clean_term in ("inhouse", "in house", "in-house", "internal"):
        return {"resolved": True, "dimension": "lead_type", "value": "In House", "column": "lead_type"}
    if clean_term in ("outsource", "out sourced", "outsourced", "out-sourced"):
        return {"resolved": True, "dimension": "lead_type", "value": "Out Sourced", "column": "lead_type"}

    # 2. Check Campus (Mohali, Lucknow, Jaipur, Bhopal, Patna or dataset campus)
    if clean_term in ("mohali", "lucknow", "jaipur", "bhopal", "patna"):
        return {"resolved": True, "dimension": "campus_name", "value": clean_term.title(), "column": "campus_name"}

    if dataset_id:
        camp_match = db.execute(text("""
            SELECT DISTINCT raw_data->>'mx_Campus' as campus
            FROM staging.records
            WHERE dataset_id = :ds AND LOWER(TRIM(COALESCE(raw_data->>'mx_Campus', ''))) = :t
            LIMIT 1
        """), {"ds": str(dataset_id), "t": clean_term}).scalar()
        if camp_match:
            return {"resolved": True, "dimension": "campus_name", "value": camp_match, "column": "campus_name"}

    # 3. Check organization.source_master (Source_ms) for exact source / report_source match
    sm_match = db.execute(text("""
        SELECT source, report_source, main_source, lead_type, source_cluster
        FROM organization.source_master
        WHERE LOWER(TRIM(source)) = :t OR LOWER(TRIM(report_source)) = :t OR LOWER(TRIM(source_cluster)) = :t OR LOWER(TRIM(main_source)) = :t
        LIMIT 1
    """), {"t": clean_term}).mappings().first()

    if sm_match:
        if sm_match.get("source") and clean_term == sm_match["source"].lower():
            return {"resolved": True, "dimension": "source", "value": sm_match["source"], "column": "source"}
        if sm_match.get("report_source") and clean_term == sm_match["report_source"].lower():
            return {"resolved": True, "dimension": "source", "value": sm_match["report_source"], "column": "source"}
        if sm_match.get("main_source") and clean_term == sm_match["main_source"].lower():
            return {"resolved": True, "dimension": "main_source", "value": sm_match["main_source"], "column": "main_source"}
        if sm_match.get("source_cluster") and clean_term == sm_match["source_cluster"].lower():
            return {"resolved": True, "dimension": "source_cluster", "value": sm_match["source_cluster"], "column": "source_cluster"}

    # 3. Check organization.state_master
    st_match = db.execute(text("""
        SELECT state_name, state_code
        FROM organization.state_master
        WHERE LOWER(TRIM(state_name)) = :t OR LOWER(TRIM(state_code)) = :t
        LIMIT 1
    """), {"t": clean_term}).mappings().first()

    if st_match:
        return {"resolved": True, "dimension": "state", "value": st_match["state_name"], "column": "state"}

    # 4. Check staging.records for campus, owner, program_code
    if dataset_id:
        rec_match = db.execute(text("""
            SELECT 
                raw_data->>'mx_Campus' as campus,
                raw_data->>'OwnerIdName' as owner,
                raw_data->>'ProgramCode' as prog_code
            FROM staging.records
            WHERE dataset_id = :ds
              AND (
                LOWER(TRIM(COALESCE(raw_data->>'mx_Campus', ''))) = :t OR
                LOWER(TRIM(COALESCE(raw_data->>'OwnerIdName', ''))) = :t OR
                LOWER(TRIM(COALESCE(raw_data->>'ProgramCode', ''))) = :t
              )
            LIMIT 1
        """), {"ds": str(dataset_id), "t": clean_term}).mappings().first()

        if rec_match:
            if rec_match.get("campus") and clean_term == rec_match["campus"].lower():
                return {"resolved": True, "dimension": "campus_name", "value": rec_match["campus"], "column": "campus_name"}
            if rec_match.get("owner") and clean_term == rec_match["owner"].lower():
                return {"resolved": True, "dimension": "owner", "value": rec_match["owner"], "column": "owner"}
            if rec_match.get("prog_code") and clean_term == rec_match["prog_code"].lower():
                return {"resolved": True, "dimension": "program_code", "value": rec_match["prog_code"], "column": "program_code"}

    return {"resolved": False, "dimension": None, "value": term, "column": None}
