"""
Phase 12: ID-Level Neo4j Graph Reconciliation Engine

Performs deep ID-level comparisons between PostgreSQL canonical Lead IDs and Neo4j Lead nodes.
Detects:
- Missing graph nodes (present in Postgres, absent in Neo4j)
- Unexpected graph nodes (absent in Postgres, present in Neo4j)
- Duplicate graph nodes (more than 1 node per enquiry_id)
- Relationship inconsistencies (orphaned nodes, missing required edges to State, Source, Program)
- Provides optional auto-repair capability via system.neo4j_sync_queue
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.neo4j_driver import neo4j_manager
from app.database.sync_queue import enqueue_sync_event
from app.normalization.graph_canonicalizer import GraphCanonicalizer

logger = logging.getLogger(__name__)


class Neo4jReconciler:
    def __init__(self, db: Session):
        self.db = db
        self.canonicalizer = GraphCanonicalizer(db)

    def reconcile(self, auto_repair: bool = False) -> Dict[str, Any]:
        """Perform full ID-level reconciliation and return discrepancy report."""
        if not neo4j_manager.is_healthy():
            return {
                "status": "failed",
                "reason": "Neo4j driver is offline or unreachable",
            }

        logger.info("Starting ID-level graph reconciliation...")

        # 1. Fetch canonical PostgreSQL Lead IDs
        pg_query = text("SELECT DISTINCT enquiry_id FROM organization.enquiries WHERE enquiry_id IS NOT NULL;")
        pg_rows = self.db.execute(pg_query).mappings().all()
        pg_lead_ids: Set[str] = {
            self.canonicalizer.canonicalize_lead_id(r["enquiry_id"]) for r in pg_rows
        }

        # 2. Fetch Neo4j Lead IDs
        cypher_neo4j_leads = "MATCH (l:Lead) RETURN l.enquiry_id AS enquiry_id;"
        neo4j_lead_records = neo4j_manager.execute_read(cypher_neo4j_leads)
        neo4j_lead_ids: Set[str] = {
            str(r["enquiry_id"]).strip().upper() for r in neo4j_lead_records if r.get("enquiry_id")
        }

        # 3. Detect duplicate Lead nodes in Neo4j
        cypher_duplicates = """
        MATCH (l:Lead)
        WITH l.enquiry_id AS id, count(l) AS cnt
        WHERE cnt > 1
        RETURN id, cnt;
        """
        duplicate_records = neo4j_manager.execute_read(cypher_duplicates)
        duplicate_in_neo4j = [
            {"enquiry_id": str(r["id"]), "count": r["cnt"]} for r in duplicate_records
        ]

        # 4. Set differences
        missing_in_neo4j = list(pg_lead_ids - neo4j_lead_ids)
        unexpected_in_neo4j = list(neo4j_lead_ids - pg_lead_ids)

        # 5. Relationship Inconsistencies
        cypher_missing_state = "MATCH (l:Lead) WHERE NOT (l)-[:LOCATED_IN]->(:State) RETURN l.enquiry_id AS id;"
        cypher_missing_source = "MATCH (l:Lead) WHERE NOT (l)-[:ORIGINATED_FROM]->(:Source) RETURN l.enquiry_id AS id;"
        cypher_missing_program = "MATCH (l:Lead) WHERE NOT (l)-[:INTERESTED_IN]->(:Program) RETURN l.enquiry_id AS id;"

        missing_state_ids = [r["id"] for r in neo4j_manager.execute_read(cypher_missing_state) if r.get("id")]
        missing_source_ids = [r["id"] for r in neo4j_manager.execute_read(cypher_missing_source) if r.get("id")]
        missing_program_ids = [r["id"] for r in neo4j_manager.execute_read(cypher_missing_program) if r.get("id")]

        reconciliation_report = {
            "status": "success",
            "postgres_lead_count": len(pg_lead_ids),
            "neo4j_lead_count": len(neo4j_lead_ids),
            "inconsistencies": {
                "missing_in_neo4j_count": len(missing_in_neo4j),
                "missing_in_neo4j_ids": missing_in_neo4j[:100], # Sample top 100
                "unexpected_in_neo4j_count": len(unexpected_in_neo4j),
                "unexpected_in_neo4j_ids": unexpected_in_neo4j[:100],
                "duplicate_in_neo4j_count": len(duplicate_in_neo4j),
                "duplicate_in_neo4j": duplicate_in_neo4j,
                "missing_state_edge_count": len(missing_state_ids),
                "missing_source_edge_count": len(missing_source_ids),
                "missing_program_edge_count": len(missing_program_ids),
            },
            "is_fully_consistent": (
                len(missing_in_neo4j) == 0 and
                len(unexpected_in_neo4j) == 0 and
                len(duplicate_in_neo4j) == 0 and
                len(missing_state_ids) == 0
            ),
            "auto_repaired": False,
        }

        # 6. Auto-Repair Action
        if auto_repair and not reconciliation_report["is_fully_consistent"]:
            repaired_count = self._auto_repair(missing_in_neo4j, unexpected_in_neo4j)
            reconciliation_report["auto_repaired"] = True
            reconciliation_report["repaired_events_enqueued"] = repaired_count

        return reconciliation_report

    def _auto_repair(self, missing_ids: List[str], unexpected_ids: List[str]) -> int:
        """Enqueues missing leads for sync and purges unexpected leads from Neo4j."""
        enqueued = 0

        # Enqueue missing leads
        if missing_ids:
            query = text("""
                SELECT enquiry_id, user_id, state, country, source, main_source,
                       campus_name, cluster, program_code, program_name, lead_type, enquiry_date
                FROM organization.enquiries
                WHERE enquiry_id = ANY(:ids);
            """)
            rows = self.db.execute(query, {"ids": missing_ids}).mappings().all()

            for r in rows:
                payload = dict(r)
                enqueue_sync_event(
                    self.db,
                    entity_type="LEAD",
                    entity_id=r["enquiry_id"],
                    action="UPSERT_LEAD",
                    payload=payload,
                )
                enqueued += 1

        # Purge unexpected graph leads directly
        if unexpected_ids:
            cypher_purge = "MATCH (l:Lead) WHERE l.enquiry_id IN $ids DETACH DELETE l;"
            neo4j_manager.execute_write(cypher_purge, {"ids": unexpected_ids})
            logger.info(f"Purged {len(unexpected_ids)} unexpected lead nodes from Neo4j.")

        self.db.commit()
        return enqueued
