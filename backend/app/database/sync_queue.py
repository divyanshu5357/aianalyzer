"""
Phase 12: Transactional Sync Queue Producer

Enqueues graph projection sync events directly into system.neo4j_sync_queue
within the active PostgreSQL transaction.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def enqueue_sync_event(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    """
    Enqueues a durable sync event into system.neo4j_sync_queue within the active PostgreSQL transaction.
    Returns the generated UUID event ID if successful.
    """
    try:
        query = text("""
            INSERT INTO system.neo4j_sync_queue (
                entity_type,
                entity_id,
                action,
                payload,
                status
            ) VALUES (
                :entity_type,
                :entity_id,
                :action,
                :payload,
                'pending'
            )
            RETURNING id;
        """)
        result = db.execute(
            query,
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "payload": json.dumps(payload, default=str),
            },
        )
        row = result.fetchone()
        event_id = str(row[0]) if row else None
        logger.debug(f"Enqueued Neo4j sync event {event_id} for {entity_type}:{entity_id}")
        return event_id
    except Exception as e:
        logger.error(f"Failed to enqueue Neo4j sync event for {entity_type}:{entity_id}: {e}")
        # Does not re-raise to guarantee PostgreSQL primary CRM transaction remains unblocked if queue logging fails
        return None
