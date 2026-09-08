"""
Mapping Persistence & Reuse Service.

Persists dynamic schema and relationship mappings to PostgreSQL (intelligence.schema_mappings).
Enables approved mappings to be automatically reused for subsequent recurring uploads.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.mapping.relationship_detector import normalize_slug

logger = logging.getLogger(__name__)


def save_mapping_configuration(
    db: Session,
    source_file: str,
    source_sheet: str,
    source_column: str,
    target_entity: str,
    target_column: str,
    confidence: float,
    status: str = "suggested",
    target_sheet: str = "default",
    match_type: str = "exact",
    metadata: Optional[Dict[str, Any]] = None,
    mapping_version: int = 1,
) -> Dict[str, Any]:
    """Persist a single mapping configuration to intelligence.schema_mappings."""
    meta_json = json.dumps(metadata or {})

    # Check for existing record
    existing = db.execute(
        text(
            """
            SELECT id, mapping_version, status
            FROM intelligence.schema_mappings
            WHERE source_file = :source_file
              AND source_sheet = :source_sheet
              AND source_column = :source_column
              AND target_entity = :target_entity
              AND target_column = :target_column
              AND is_active = TRUE
            LIMIT 1
            """
        ),
        {
            "source_file": source_file,
            "source_sheet": source_sheet,
            "source_column": source_column,
            "target_entity": target_entity,
            "target_column": target_column,
        },
    ).mappings().first()

    if existing:
        record_id = existing["id"]
        db.execute(
            text(
                """
                UPDATE intelligence.schema_mappings
                SET confidence = :confidence,
                    status = :status,
                    match_type = :match_type,
                    metadata = CAST(:metadata AS jsonb),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
                """
            ),
            {
                "id": record_id,
                "confidence": confidence,
                "status": status,
                "match_type": match_type,
                "metadata": meta_json,
            },
        )
    else:
        res = db.execute(
            text(
                """
                INSERT INTO intelligence.schema_mappings (
                    source_file, source_sheet, source_column,
                    target_entity, target_sheet, target_column,
                    confidence, status, mapping_version, is_active,
                    match_type, metadata
                ) VALUES (
                    :source_file, :source_sheet, :source_column,
                    :target_entity, :target_sheet, :target_column,
                    :confidence, :status, :mapping_version, TRUE,
                    :match_type, CAST(:metadata AS jsonb)
                )
                RETURNING id
                """
            ),
            {
                "source_file": source_file,
                "source_sheet": source_sheet,
                "source_column": source_column,
                "target_entity": target_entity,
                "target_sheet": target_sheet,
                "target_column": target_column,
                "confidence": confidence,
                "status": status,
                "mapping_version": mapping_version,
                "match_type": match_type,
                "metadata": meta_json,
            },
        )
        record_id = res.scalar()

    db.commit()
    return {
        "id": str(record_id),
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_column": source_column,
        "target_entity": target_entity,
        "target_sheet": target_sheet,
        "target_column": target_column,
        "confidence": confidence,
        "status": status,
        "mapping_version": mapping_version,
        "match_type": match_type,
    }


def save_multiple_mapping_configurations(
    db: Session,
    mappings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Persist a list of mapping candidates."""
    results = []
    for m in mappings:
        saved = save_mapping_configuration(
            db=db,
            source_file=m.get("source_file", "upload"),
            source_sheet=m.get("source_sheet", "default"),
            source_column=m.get("source_column", ""),
            target_entity=m.get("target_entity", "default"),
            target_column=m.get("target_column", ""),
            confidence=float(m.get("confidence", 0.0)),
            status=m.get("status", "suggested"),
            target_sheet=m.get("target_sheet", "default"),
            match_type=m.get("match_type", "exact"),
            metadata=m.get("metadata") or {
                "requires_confirmation": m.get("requires_confirmation", False),
                "is_ambiguous": m.get("is_ambiguous", False),
            },
            mapping_version=int(m.get("mapping_version", 1)),
        )
        results.append(saved)
    return results


def approve_or_edit_mappings(
    db: Session,
    mapping_decisions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Approve, edit, or reject mapping candidates.
    Approved mappings become active and reusable for future uploads.
    """
    approved_count = 0
    rejected_count = 0
    modified_count = 0

    for decision in mapping_decisions:
        rec_id = decision.get("id")
        action = decision.get("action", "approve").lower()  # approve, reject, edit

        if action == "reject":
            if rec_id:
                db.execute(
                    text("UPDATE intelligence.schema_mappings SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                    {"id": rec_id},
                )
                rejected_count += 1
            continue

        target_entity = decision.get("target_entity")
        target_column = decision.get("target_column")
        new_confidence = float(decision.get("confidence", 1.0))
        status = "approved"

        if rec_id:
            # If target was edited by user
            if target_entity or target_column:
                db.execute(
                    text(
                        """
                        UPDATE intelligence.schema_mappings
                        SET target_entity = COALESCE(:target_entity, target_entity),
                            target_column = COALESCE(:target_column, target_column),
                            status = 'approved',
                            confidence = 1.0,
                            match_type = 'manual',
                            mapping_version = mapping_version + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": rec_id,
                        "target_entity": target_entity,
                        "target_column": target_column,
                    },
                )
                modified_count += 1
            else:
                db.execute(
                    text(
                        """
                        UPDATE intelligence.schema_mappings
                        SET status = 'approved',
                            confidence = 1.0,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"id": rec_id},
                )
                approved_count += 1
        else:
            # New direct approval without existing ID
            save_mapping_configuration(
                db=db,
                source_file=decision.get("source_file", "manual"),
                source_sheet=decision.get("source_sheet", "default"),
                source_column=decision["source_column"],
                target_entity=decision["target_entity"],
                target_column=decision["target_column"],
                confidence=new_confidence,
                status="approved",
                match_type="manual",
            )
            approved_count += 1

    db.commit()
    return {
        "status": "success",
        "approved": approved_count,
        "rejected": rejected_count,
        "modified": modified_count,
    }


def get_reusable_mappings_for_columns(
    db: Session,
    columns: List[str],
    source_file: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Check if previously approved mappings exist for any of the columns.
    Returns: {original_column_name: mapping_details}
    """
    rows = db.execute(
        text(
            """
            SELECT id, source_file, source_sheet, source_column,
                   target_entity, target_sheet, target_column,
                   confidence, status, mapping_version, match_type, metadata
            FROM intelligence.schema_mappings
            WHERE is_active = TRUE
              AND status = 'approved'
            ORDER BY updated_at DESC
            """
        )
    ).mappings().all()

    # Build slug lookup for approved mappings
    approved_by_slug: Dict[str, Dict[str, Any]] = {}
    approved_by_file_slug: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        c_slug = normalize_slug(r["source_column"])
        f_slug = normalize_slug(r["source_file"])
        combo_key = f"{f_slug}::{c_slug}"

        m_dict = {
            "id": str(r["id"]),
            "source_column": r["source_column"],
            "target_entity": r["target_entity"],
            "target_sheet": r["target_sheet"],
            "target_column": r["target_column"],
            "confidence": 1.0,
            "status": "approved",
            "is_reused": True,
            "match_type": r["match_type"],
            "mapping_version": r["mapping_version"],
        }

        if combo_key not in approved_by_file_slug:
            approved_by_file_slug[combo_key] = m_dict
        if c_slug not in approved_by_slug:
            approved_by_slug[c_slug] = m_dict

    reusable_matches: Dict[str, Dict[str, Any]] = {}

    src_f_slug = normalize_slug(source_file) if source_file else ""

    for col in columns:
        c_slug = normalize_slug(col)
        combo_key = f"{src_f_slug}::{c_slug}"

        if combo_key in approved_by_file_slug:
            match = dict(approved_by_file_slug[combo_key])
            match["original_column"] = col
            reusable_matches[col] = match
        elif c_slug in approved_by_slug:
            match = dict(approved_by_slug[c_slug])
            match["original_column"] = col
            reusable_matches[col] = match

    return reusable_matches


def list_saved_mappings(
    db: Session,
    target_entity: Optional[str] = None,
    status: Optional[str] = None,
    source_file: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieve saved mappings with optional filters."""
    query_parts = ["SELECT * FROM intelligence.schema_mappings WHERE is_active = TRUE"]
    params: Dict[str, Any] = {"limit": limit}

    if target_entity:
        query_parts.append("AND LOWER(target_entity) = LOWER(:target_entity)")
        params["target_entity"] = target_entity
    if status:
        query_parts.append("AND LOWER(status) = LOWER(:status)")
        params["status"] = status
    if source_file:
        query_parts.append("AND LOWER(source_file) LIKE LOWER(:source_file)")
        params["source_file"] = f"%{source_file}%"

    query_parts.append("ORDER BY updated_at DESC LIMIT :limit")
    sql = " ".join(query_parts)

    rows = db.execute(text(sql), params).mappings().all()

    return [
        {
            "id": str(r["id"]),
            "mapping_name": r["mapping_name"],
            "source_file": r["source_file"],
            "source_sheet": r["source_sheet"],
            "source_column": r["source_column"],
            "target_entity": r["target_entity"],
            "target_sheet": r["target_sheet"],
            "target_column": r["target_column"],
            "confidence": float(r["confidence"]),
            "status": r["status"],
            "mapping_version": r["mapping_version"],
            "match_type": r["match_type"],
            "metadata": r["metadata"] if isinstance(r["metadata"], dict) else {},
            "created_at": str(r["created_at"]),
            "updated_at": str(r["updated_at"]),
        }
        for r in rows
    ]


def batch_save_multisheet_mappings(
    db: Session,
    mappings_batch: List[Dict[str, Any]],
    workbook_type: str = "raw_data",
) -> List[Dict[str, Any]]:
    """
    Saves a batch of multi-sheet approved/suggested relationship mappings with version increment.
    """
    results = []
    for m in mappings_batch:
        res = save_mapping_configuration(
            db=db,
            source_file=m.get("source_file", "workbook"),
            source_sheet=m.get("source_sheet", "Sheet1"),
            source_column=m.get("source_column", ""),
            target_entity=m.get("target_entity") or m.get("target_file") or "Target",
            target_column=m.get("target_column", ""),
            confidence=float(m.get("confidence", 0.95)),
            status=m.get("status", "approved"),
            target_sheet=m.get("target_sheet", "default"),
            match_type=m.get("match_type", "exact"),
            metadata={
                "value_overlap_pct": m.get("value_overlap_pct", 0.0),
                "confidence_rating": m.get("confidence_rating", "HIGH"),
                "workbook_type": workbook_type,
            },
        )
        results.append(res)
    return results


def get_reusable_multisheet_mappings(
    db: Session,
    source_file: str,
) -> List[Dict[str, Any]]:
    """
    Retrieves all active approved mappings for a multi-sheet workbook or matching file name pattern.
    """
    return list_saved_mappings(db=db, status="approved", source_file=source_file)

