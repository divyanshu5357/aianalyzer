"""
Phase 12: Neo4j Graph Management API Router

Exposes REST endpoints for:
- Neo4j health & connectivity status
- Processing pending queue events
- Triggering full historical graph backfill
- Running ID-level graph reconciliation & auto-repair
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.neo4j_driver import neo4j_manager
from app.database.neo4j_sync_worker import Neo4jSyncWorker
from app.database.neo4j_backfill import backfill_full_graph, init_neo4j_schema
from app.database.neo4j_reconciler import Neo4jReconciler

router = APIRouter(prefix="/api/graph", tags=["Neo4j Graph Management"])


class ReconcileRequest(BaseModel):
    auto_repair: bool = Field(False, description="Enqueues missing leads and purges unexpected nodes if True")


class ProcessBatchRequest(BaseModel):
    batch_size: int = Field(50, ge=1, le=500)


@router.get("/status", summary="Get Neo4j Graph Driver Connectivity & Queue Depth")
def get_graph_status(db: Session = Depends(get_db)):
    is_healthy = neo4j_manager.is_healthy()
    queue_count = 0
    try:
        from sqlalchemy import text
        res = db.execute(text("SELECT count(*) FROM system.neo4j_sync_queue WHERE status = 'pending';")).scalar()
        queue_count = int(res or 0)
    except Exception:
        pass

    return {
        "neo4j_available": is_healthy,
        "pending_sync_queue_depth": queue_count,
    }


@router.post("/process-queue", summary="Process Pending Neo4j Sync Events")
def process_sync_queue(payload: ProcessBatchRequest, db: Session = Depends(get_db)):
    try:
        worker = Neo4jSyncWorker(db)
        summary = worker.process_pending_events(batch_size=payload.batch_size)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Queue processing error: {str(e)}",
        )


@router.post("/backfill", summary="Run Full Historical Graph Backfill from PostgreSQL")
def run_graph_backfill(batch_size: int = 1000, db: Session = Depends(get_db)):
    try:
        result = backfill_full_graph(db=db, batch_size=batch_size)
        if result.get("status") == "failed":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result.get("reason"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backfill error: {str(e)}",
        )


@router.post("/reconcile", summary="Run Deep ID-Level Graph Reconciliation & Auto-Repair")
def run_graph_reconciliation(payload: ReconcileRequest, db: Session = Depends(get_db)):
    try:
        reconciler = Neo4jReconciler(db)
        report = reconciler.reconcile(auto_repair=payload.auto_repair)
        return report
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reconciliation error: {str(e)}",
        )
