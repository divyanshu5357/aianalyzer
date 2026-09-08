"""
Phase 12: ML Prediction Graph Connector

Connects Phase 10 ML inference outputs to the durable system.neo4j_sync_queue
without altering ML model contracts, Phase 7 parquet files, Phase 9.5 artifacts, or Phase 11 replay.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.database.sync_queue import enqueue_sync_event

logger = logging.getLogger(__name__)


def record_ml_prediction_to_graph(
    db: Session,
    enquiry_id: str,
    prediction_result: Dict[str, Any],
) -> Optional[str]:
    """
    Enqueues a versioned ML prediction graph sync event into system.neo4j_sync_queue
    within the active PostgreSQL transaction.
    """
    if not enquiry_id or not str(enquiry_id).strip():
        logger.warning("Cannot record ML prediction to graph: enquiry_id is null or empty.")
        return None

    payload = {
        "enquiry_id": str(enquiry_id).strip().upper(),
        "model_version": prediction_result.get("model_version", "2026_lightgbm_calibrated_v1"),
        "calibrated_admission_probability": prediction_result.get("calibrated_admission_probability", 0.0),
        "predictive_score_pct": prediction_result.get("predictive_score_pct", 0.0),
        "operational_tier": prediction_result.get("operational_tier", "Low Priority"),
        "decision_recommendation": prediction_result.get("decision_recommendation", "STANDARD_NURTURE"),
        "t0_threshold_applied": prediction_result.get("t0_threshold_applied", 0.05),
        "predicted_at": datetime.utcnow().isoformat(),
    }

    event_id = enqueue_sync_event(
        db=db,
        entity_type="ML_PREDICTION",
        entity_id=payload["enquiry_id"],
        action="UPSERT_ML_PREDICTION",
        payload=payload,
    )

    logger.info(f"Recorded ML prediction sync event {event_id} for lead {payload['enquiry_id']}")
    return event_id
