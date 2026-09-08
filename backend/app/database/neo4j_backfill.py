"""
Phase 12: Neo4j Graph Schema Initialization & Batch Backfill Script

Applies database uniqueness constraints and performance indexes,
and executes full historical backfill from PostgreSQL into Neo4j using UNWIND batching.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.neo4j_driver import neo4j_manager
from app.normalization.graph_canonicalizer import GraphCanonicalizer

logger = logging.getLogger(__name__)

CYPHER_CONSTRAINTS = [
    "CREATE CONSTRAINT cstr_lead_enquiry_id IF NOT EXISTS FOR (l:Lead) REQUIRE l.enquiry_id IS UNIQUE;",
    "CREATE CONSTRAINT cstr_cucet_reg_id IF NOT EXISTS FOR (c:CUCETRegistration) REQUIRE c.registration_id IS UNIQUE;",
    "CREATE CONSTRAINT cstr_admission_id IF NOT EXISTS FOR (a:Admission) REQUIRE a.admission_id IS UNIQUE;",
    "CREATE CONSTRAINT cstr_program_code IF NOT EXISTS FOR (p:Program) REQUIRE p.program_code IS UNIQUE;",
    "CREATE CONSTRAINT cstr_campus_id IF NOT EXISTS FOR (c:Campus) REQUIRE c.campus_id IS UNIQUE;",
    "CREATE CONSTRAINT cstr_source_key IF NOT EXISTS FOR (s:Source) REQUIRE s.source_key IS UNIQUE;",
    "CREATE CONSTRAINT cstr_state_code IF NOT EXISTS FOR (st:State) REQUIRE st.state_code IS UNIQUE;",
    "CREATE CONSTRAINT cstr_owner_emp_id IF NOT EXISTS FOR (o:Owner) REQUIRE o.employee_id IS UNIQUE;",
    "CREATE CONSTRAINT cstr_ml_pred_id IF NOT EXISTS FOR (mp:MLPrediction) REQUIRE mp.prediction_id IS UNIQUE;",
]

CYPHER_INDEXES = [
    "CREATE INDEX idx_lead_tier IF NOT EXISTS FOR (l:Lead) ON (l.latest_operational_tier);",
    "CREATE INDEX idx_lead_year IF NOT EXISTS FOR (l:Lead) ON (l.academic_year);",
    "CREATE INDEX idx_ml_pred_version IF NOT EXISTS FOR (mp:MLPrediction) ON (mp.model_version, mp.operational_tier);",
]


def init_neo4j_schema() -> bool:
    """Initialize all constraints and indexes in Neo4j."""
    if not neo4j_manager.is_healthy():
        logger.warning("Cannot initialize Neo4j schema: Neo4j server unavailable.")
        return False

    logger.info("Initializing Neo4j graph constraints and indexes...")
    for query in CYPHER_CONSTRAINTS + CYPHER_INDEXES:
        try:
            neo4j_manager.execute_write(query)
        except Exception as e:
            logger.error(f"Failed to execute Cypher schema statement [{query}]: {e}")
            return False

    logger.info("Neo4j schema initialization complete.")
    return True


def backfill_full_graph(db: Session, batch_size: int = 1000) -> Dict[str, Any]:
    """
    Executes full historical graph backfill reading from PostgreSQL organization sandbox tables.
    Returns audit counts.
    """
    start_time = time.time()
    if not init_neo4j_schema():
        return {"status": "failed", "reason": "Neo4j database unavailable or schema init failed"}

    canonicalizer = GraphCanonicalizer(db)

    # 1. Backfill Enquiries / Leads
    enquiries_query = text("""
        SELECT enquiry_id, user_id, state, country, source, main_source,
               campus_name, cluster, program_code, program_name, lead_type, enquiry_date
        FROM organization.enquiries
        ORDER BY created_at ASC;
    """)
    rows = db.execute(enquiries_query).mappings().all()

    total_leads = 0
    batch: List[Dict[str, Any]] = []

    for r in rows:
        try:
            enq_id = canonicalizer.canonicalize_lead_id(r["enquiry_id"])
            state_data = canonicalizer.canonicalize_state(r["state"], r["country"])
            owner_data = canonicalizer.canonicalize_owner(None, None) # Default unassigned
            source_data = canonicalizer.canonicalize_source(r["source"] or r["main_source"])
            program_data = canonicalizer.canonicalize_program(r["program_name"], r["program_code"])
            campus_data = canonicalizer.canonicalize_campus(r["campus_name"])

            batch.append({
                "enquiry_id": enq_id,
                "academic_year": 2026,
                "lead_type": r["lead_type"] or "Inquiry",
                "enquiry_date": str(r["enquiry_date"]) if r["enquiry_date"] else None,
                "state_code": state_data["state_code"],
                "state_name": state_data["state_name"],
                "zone": state_data["zone"],
                "is_international": state_data["is_international"],
                "employee_id": owner_data["employee_id"],
                "employee_name": owner_data["employee_name"],
                "display_name": owner_data["display_name"],
                "source_key": source_data["source_key"],
                "source_name": source_data["source_name"],
                "main_source": source_data["main_source"],
                "program_code": program_data["program_code"],
                "program_name": program_data["program_name"],
                "campus_id": campus_data["campus_id"],
                "campus_name": campus_data["campus_name"],
            })

            if len(batch) >= batch_size:
                _unwind_upsert_leads(batch)
                total_leads += len(batch)
                batch = []
        except Exception as e:
            logger.error(f"Error preparing lead record {r.get('enquiry_id')}: {e}")

    if batch:
        _unwind_upsert_leads(batch)
        total_leads += len(batch)

    # 2. Backfill CUCET Registrations
    cucet_query = text("""
        SELECT registration_id, enquiry_id, registration_date, exam_status
        FROM organization.cucet_registrations
        WHERE enquiry_id IS NOT NULL;
    """)
    cucet_rows = db.execute(cucet_query).mappings().all()
    cucet_batch = [
        {
            "registration_id": str(r["registration_id"]).strip().upper(),
            "enquiry_id": canonicalizer.canonicalize_lead_id(r["enquiry_id"]),
            "registration_date": str(r["registration_date"]) if r["registration_date"] else None,
            "exam_status": r["exam_status"] or "Registered",
        }
        for r in cucet_rows if r["enquiry_id"]
    ]
    if cucet_batch:
        _unwind_upsert_cucet(cucet_batch)

    # 3. Backfill Admissions
    adm_query = text("""
        SELECT admission_id, enquiry_id, admission_date, admission_status
        FROM organization.admissions
        WHERE enquiry_id IS NOT NULL;
    """)
    adm_rows = db.execute(adm_query).mappings().all()
    adm_batch = [
        {
            "admission_id": str(r["admission_id"]).strip().upper(),
            "enquiry_id": canonicalizer.canonicalize_lead_id(r["enquiry_id"]),
            "admission_date": str(r["admission_date"]) if r["admission_date"] else None,
            "admission_status": r["admission_status"] or "Admitted",
        }
        for r in adm_rows if r["enquiry_id"]
    ]
    if adm_batch:
        _unwind_upsert_admissions(adm_batch)

    duration = round(time.time() - start_time, 2)
    logger.info(f"Full graph backfill complete in {duration}s. Leads: {total_leads}, CUCET: {len(cucet_batch)}, Admissions: {len(adm_batch)}")

    return {
        "status": "success",
        "duration_seconds": duration,
        "total_leads_backfilled": total_leads,
        "cucet_registrations_backfilled": len(cucet_batch),
        "admissions_backfilled": len(adm_batch),
    }


def _unwind_upsert_leads(batch: List[Dict[str, Any]]) -> None:
    cypher = """
    UNWIND $batch AS row
    MERGE (l:Lead {enquiry_id: row.enquiry_id})
    ON CREATE SET
        l.created_at = datetime(),
        l.academic_year = row.academic_year,
        l.lead_type = row.lead_type,
        l.enquiry_date = row.enquiry_date
    ON MATCH SET
        l.academic_year = row.academic_year,
        l.lead_type = row.lead_type,
        l.updated_at = datetime()

    MERGE (st:State {state_code: row.state_code})
    ON CREATE SET st.state_name = row.state_name, st.zone = row.zone, st.is_international = row.is_international
    MERGE (l)-[:LOCATED_IN]->(st)

    MERGE (o:Owner {employee_id: row.employee_id})
    ON CREATE SET o.employee_name = row.employee_name, o.display_name = row.display_name
    MERGE (l)-[:ASSIGNED_TO]->(o)

    MERGE (s:Source {source_key: row.source_key})
    ON CREATE SET s.source_name = row.source_name, s.main_source = row.main_source
    MERGE (l)-[:ORIGINATED_FROM]->(s)

    MERGE (p:Program {program_code: row.program_code})
    ON CREATE SET p.program_name = row.program_name
    MERGE (l)-[:INTERESTED_IN]->(p)

    MERGE (c:Campus {campus_id: row.campus_id})
    ON CREATE SET c.campus_name = row.campus_name
    MERGE (l)-[:TARGETS_CAMPUS]->(c)
    MERGE (p)-[:OFFERED_AT]->(c)
    """
    neo4j_manager.execute_write(cypher, {"batch": batch})


def _unwind_upsert_cucet(batch: List[Dict[str, Any]]) -> None:
    cypher = """
    UNWIND $batch AS row
    MATCH (l:Lead {enquiry_id: row.enquiry_id})
    MERGE (c:CUCETRegistration {registration_id: row.registration_id})
    ON CREATE SET c.registration_date = row.registration_date, c.exam_status = row.exam_status, c.created_at = datetime()
    ON MATCH SET c.exam_status = row.exam_status, c.updated_at = datetime()
    MERGE (l)-[r:REGISTERED_FOR_CUCET]->(c)
    SET r.registration_date = row.registration_date, r.exam_status = row.exam_status
    """
    neo4j_manager.execute_write(cypher, {"batch": batch})


def _unwind_upsert_admissions(batch: List[Dict[str, Any]]) -> None:
    cypher = """
    UNWIND $batch AS row
    MATCH (l:Lead {enquiry_id: row.enquiry_id})
    MERGE (a:Admission {admission_id: row.admission_id})
    ON CREATE SET a.admission_date = row.admission_date, a.admission_status = row.admission_status, a.created_at = datetime()
    ON MATCH SET a.admission_status = row.admission_status, a.updated_at = datetime()
    MERGE (l)-[r:CONVERTED_TO_ADMISSION]->(a)
    SET r.admission_date = row.admission_date, r.admission_status = row.admission_status
    """
    neo4j_manager.execute_write(cypher, {"batch": batch})
