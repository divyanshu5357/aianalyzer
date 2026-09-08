"""
Phase 12: Durable Neo4j Sync Queue Worker

Polls and processes system.neo4j_sync_queue events from PostgreSQL,
executing idempotent Cypher MERGE operations into Neo4j.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.neo4j_driver import neo4j_manager
from app.normalization.graph_canonicalizer import GraphCanonicalizer

logger = logging.getLogger(__name__)


class Neo4jSyncWorker:
    def __init__(self, db: Session):
        self.db = db
        self.canonicalizer = GraphCanonicalizer(db)

    def process_pending_events(self, batch_size: int = 50) -> Dict[str, int]:
        """Fetch and process a batch of pending events from system.neo4j_sync_queue."""
        if not neo4j_manager.is_healthy():
            logger.warning("Neo4j driver is unhealthy or unreachable. Skipping queue processing cycle.")
            return {"processed": 0, "succeeded": 0, "failed": 0}

        query = text("""
            SELECT id, entity_type, entity_id, action, payload, retry_count, max_retries
            FROM system.neo4j_sync_queue
            WHERE status IN ('pending', 'failed')
              AND retry_count < max_retries
            ORDER BY created_at ASC
            LIMIT :batch_size
            FOR UPDATE SKIP LOCKED;
        """)

        rows = self.db.execute(query, {"batch_size": batch_size}).mappings().all()

        if not rows:
            return {"processed": 0, "succeeded": 0, "failed": 0}

        succeeded = 0
        failed = 0

        for row in rows:
            event_id = str(row["id"])
            entity_type = row["entity_type"]
            entity_id = row["entity_id"]
            action = row["action"]
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            retry_count = row["retry_count"]
            max_retries = row["max_retries"]

            try:
                self._dispatch_event(entity_type, entity_id, action, payload)
                # Mark as completed
                self.db.execute(
                    text("""
                        UPDATE system.neo4j_sync_queue
                        SET status = 'completed',
                            processed_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                    """),
                    {"id": event_id},
                )
                self.db.commit()
                succeeded += 1
            except Exception as e:
                self.db.rollback()
                new_retry = retry_count + 1
                new_status = "failed" if new_retry >= max_retries else "pending"
                self.db.execute(
                    text("""
                        UPDATE system.neo4j_sync_queue
                        SET status = :status,
                            retry_count = :retry_count,
                            last_error = :last_error,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                    """),
                    {
                        "id": event_id,
                        "status": new_status,
                        "retry_count": new_retry,
                        "last_error": str(e)[:1000],
                    },
                )
                self.db.commit()
                failed += 1
                logger.error(f"Error processing sync event {event_id} ({entity_type}:{entity_id}): {e}")

        return {"processed": len(rows), "succeeded": succeeded, "failed": failed}

    def _dispatch_event(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        payload: Dict[str, Any],
    ) -> None:
        if action == "UPSERT_LEAD" or entity_type == "LEAD":
            self._upsert_lead(payload)
        elif action == "UPSERT_CUCET" or entity_type == "CUCET":
            self._upsert_cucet(payload)
        elif action == "UPSERT_ADMISSION" or entity_type == "ADMISSION":
            self._upsert_admission(payload)
        elif action == "UPSERT_ML_PREDICTION" or entity_type == "ML_PREDICTION":
            self._upsert_ml_prediction(payload)
        elif action == "DELETE_LEAD":
            self._delete_lead(entity_id)
        else:
            raise ValueError(f"Unknown graph sync action/type: {action} / {entity_type}")

    def _upsert_lead(self, payload: Dict[str, Any]) -> None:
        enquiry_id = self.canonicalizer.canonicalize_lead_id(payload.get("enquiry_id"))
        academic_year = int(payload.get("academic_year") or 2026)
        lead_type = payload.get("lead_type") or "Inquiry"
        enquiry_date = payload.get("enquiry_date") or None

        # Canonical dimensions
        state_data = self.canonicalizer.canonicalize_state(
            payload.get("state"), payload.get("country")
        )
        owner_data = self.canonicalizer.canonicalize_owner(
            payload.get("owner_name") or payload.get("owner_canonical"),
            payload.get("employee_id"),
        )
        source_data = self.canonicalizer.canonicalize_source(
            payload.get("source") or payload.get("main_source")
        )
        program_data = self.canonicalizer.canonicalize_program(
            payload.get("program_name"), payload.get("program_code")
        )
        campus_data = self.canonicalizer.canonicalize_campus(payload.get("campus_name"))

        cypher = """
        MERGE (l:Lead {enquiry_id: $enquiry_id})
        ON CREATE SET
            l.created_at = datetime(),
            l.academic_year = $academic_year,
            l.lead_type = $lead_type,
            l.enquiry_date = $enquiry_date
        ON MATCH SET
            l.academic_year = $academic_year,
            l.lead_type = $lead_type,
            l.updated_at = datetime()

        // Location / State Node
        MERGE (st:State {state_code: $state_code})
        ON CREATE SET st.state_name = $state_name, st.zone = $zone, st.is_international = $is_international
        MERGE (l)-[:LOCATED_IN]->(st)

        // Owner Node (Keyed on stable employee_id)
        MERGE (o:Owner {employee_id: $employee_id})
        ON CREATE SET o.employee_name = $employee_name, o.display_name = $display_name
        ON MATCH SET o.employee_name = $employee_name
        MERGE (l)-[:ASSIGNED_TO]->(o)

        // Source Node
        MERGE (s:Source {source_key: $source_key})
        ON CREATE SET s.source_name = $source_name, s.main_source = $main_source
        MERGE (l)-[:ORIGINATED_FROM]->(s)

        // Program Node
        MERGE (p:Program {program_code: $program_code})
        ON CREATE SET p.program_name = $program_name
        MERGE (l)-[:INTERESTED_IN]->(p)

        // Campus Node
        MERGE (c:Campus {campus_id: $campus_id})
        ON CREATE SET c.campus_name = $campus_name
        MERGE (l)-[:TARGETS_CAMPUS]->(c)
        MERGE (p)-[:OFFERED_AT]->(c)
        """

        params = {
            "enquiry_id": enquiry_id,
            "academic_year": academic_year,
            "lead_type": lead_type,
            "enquiry_date": str(enquiry_date) if enquiry_date else None,
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
        }

        neo4j_manager.execute_write(cypher, params)

    def _upsert_cucet(self, payload: Dict[str, Any]) -> None:
        reg_id = str(payload["registration_id"]).strip().upper()
        enquiry_id = self.canonicalizer.canonicalize_lead_id(payload["enquiry_id"])

        cypher = """
        MATCH (l:Lead {enquiry_id: $enquiry_id})
        MERGE (c:CUCETRegistration {registration_id: $registration_id})
        ON CREATE SET
            c.registration_date = $registration_date,
            c.exam_status = $exam_status,
            c.created_at = datetime()
        ON MATCH SET
            c.exam_status = $exam_status,
            c.updated_at = datetime()
        MERGE (l)-[r:REGISTERED_FOR_CUCET]->(c)
        SET r.registration_date = $registration_date, r.exam_status = $exam_status
        """

        params = {
            "registration_id": reg_id,
            "enquiry_id": enquiry_id,
            "registration_date": str(payload.get("registration_date") or ""),
            "exam_status": payload.get("exam_status") or "Registered",
        }

        neo4j_manager.execute_write(cypher, params)

    def _upsert_admission(self, payload: Dict[str, Any]) -> None:
        adm_id = str(payload["admission_id"]).strip().upper()
        enquiry_id = self.canonicalizer.canonicalize_lead_id(payload["enquiry_id"])

        cypher = """
        MATCH (l:Lead {enquiry_id: $enquiry_id})
        MERGE (a:Admission {admission_id: $admission_id})
        ON CREATE SET
            a.admission_date = $admission_date,
            a.admission_status = $admission_status,
            a.created_at = datetime()
        ON MATCH SET
            a.admission_status = $admission_status,
            a.updated_at = datetime()
        MERGE (l)-[r:CONVERTED_TO_ADMISSION]->(a)
        SET r.admission_date = $admission_date, r.admission_status = $admission_status
        """

        params = {
            "admission_id": adm_id,
            "enquiry_id": enquiry_id,
            "admission_date": str(payload.get("admission_date") or ""),
            "admission_status": payload.get("admission_status") or "Admitted",
        }

        neo4j_manager.execute_write(cypher, params)

    def _upsert_ml_prediction(self, payload: Dict[str, Any]) -> None:
        enquiry_id = self.canonicalizer.canonicalize_lead_id(payload["enquiry_id"])
        model_version = payload.get("model_version") or "2026_lightgbm_calibrated_v1"
        predicted_at = payload.get("predicted_at") or datetime.utcnow().isoformat()
        pred_id = f"{enquiry_id}_{model_version}_{predicted_at}"

        cypher = """
        MATCH (l:Lead {enquiry_id: $enquiry_id})
        SET l.latest_operational_tier = $operational_tier

        MERGE (mp:MLPrediction {prediction_id: $prediction_id})
        ON CREATE SET
            mp.model_version = $model_version,
            mp.calibrated_admission_probability = $prob,
            mp.predictive_score_pct = $score_pct,
            mp.operational_tier = $operational_tier,
            mp.decision_recommendation = $recommendation,
            mp.t0_threshold_applied = $threshold,
            mp.predicted_at = $predicted_at
        MERGE (l)-[:HAS_PREDICTION]->(mp)
        """

        params = {
            "enquiry_id": enquiry_id,
            "prediction_id": pred_id,
            "model_version": model_version,
            "prob": float(payload.get("calibrated_admission_probability") or 0.0),
            "score_pct": float(payload.get("predictive_score_pct") or 0.0),
            "operational_tier": payload.get("operational_tier") or "Low Priority",
            "recommendation": payload.get("decision_recommendation") or "STANDARD_NURTURE",
            "threshold": float(payload.get("t0_threshold_applied") or 0.05),
            "predicted_at": predicted_at,
        }

        neo4j_manager.execute_write(cypher, params)

    def _delete_lead(self, enquiry_id: str) -> None:
        clean_id = self.canonicalizer.canonicalize_lead_id(enquiry_id)
        cypher = """
        MATCH (l:Lead {enquiry_id: $enquiry_id})
        DETACH DELETE l
        """
        neo4j_manager.execute_write(cypher, {"enquiry_id": clean_id})
