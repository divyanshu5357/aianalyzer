import json
import uuid
import logging
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_conversation_tables(db: Session) -> None:
    """
    Ensure system schema and conversation persistence tables exist in PostgreSQL.
    """
    try:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS system;"))
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.conversations (
                    id VARCHAR(255) PRIMARY KEY,
                    active_dataset_id VARCHAR(255),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.conversation_messages (
                    id VARCHAR(255) PRIMARY KEY,
                    conversation_id VARCHAR(255) REFERENCES system.conversations(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.conversation_context (
                    conversation_id VARCHAR(255) PRIMARY KEY REFERENCES system.conversations(id) ON DELETE CASCADE,
                    dataset_id VARCHAR(255),
                    context_json JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Error ensuring conversation tables: {e}")


def get_or_create_conversation(db: Session, conversation_id: str | None, active_dataset_id: str | None) -> str:
    """
    Retrieve or create a conversation session in system.conversations.
    Resets conversation context if active_dataset_id has changed.
    """
    ensure_conversation_tables(db)
    str_ds_id = str(active_dataset_id) if active_dataset_id else None

    if not conversation_id or not conversation_id.strip():
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"

    try:
        row = db.execute(
            text("SELECT id, active_dataset_id FROM system.conversations WHERE id = :id"),
            {"id": conversation_id},
        ).mappings().first()

        if not row:
            db.execute(
                text(
                    """
                    INSERT INTO system.conversations (id, active_dataset_id, created_at, updated_at)
                    VALUES (:id, :active_dataset_id, NOW(), NOW())
                    """
                ),
                {"id": conversation_id, "active_dataset_id": str_ds_id},
            )
            db.commit()
        else:
            prev_ds_id = row["active_dataset_id"]
            if str_ds_id and prev_ds_id != str_ds_id:
                reset_conversation_context(db, conversation_id, str_ds_id)
                db.execute(
                    text(
                        """
                        UPDATE system.conversations
                        SET active_dataset_id = :active_dataset_id, updated_at = NOW()
                        WHERE id = :id
                        """
                    ),
                    {"id": conversation_id, "active_dataset_id": str_ds_id},
                )
                db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Error in get_or_create_conversation: {e}")

    return conversation_id


def save_conversation_message(db: Session, conversation_id: str, role: str, content: str) -> None:
    """
    Save a user or assistant message to system.conversation_messages.
    """
    ensure_conversation_tables(db)
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    try:
        db.execute(
            text(
                """
                INSERT INTO system.conversation_messages (id, conversation_id, role, content, created_at)
                VALUES (:id, :conversation_id, :role, :content, NOW())
                """
            ),
            {"id": msg_id, "conversation_id": conversation_id, "role": role, "content": content},
        )
        db.execute(
            text("UPDATE system.conversations SET updated_at = NOW() WHERE id = :id"),
            {"id": conversation_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to save conversation message: {e}")


def get_conversation_messages(db: Session, conversation_id: str, limit: int = 6) -> list[dict[str, Any]]:
    """
    Get recent messages for a conversation session.
    """
    ensure_conversation_tables(db)
    try:
        rows = db.execute(
            text(
                """
                SELECT role, content, created_at
                FROM system.conversation_messages
                WHERE conversation_id = :id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"id": conversation_id, "limit": limit},
        ).mappings().all()

        msgs = [dict(r) for r in reversed(rows)]
        return msgs
    except Exception as e:
        db.rollback()
        logger.warning(f"Error fetching conversation messages: {e}")
        return []


def get_conversation_context(db: Session, conversation_id: str, active_dataset_id: str | None) -> dict[str, Any] | None:
    """
    Get the structured analytical context for a conversation session.
    Strictly verifies dataset isolation.
    """
    ensure_conversation_tables(db)
    str_ds_id = str(active_dataset_id) if active_dataset_id else None
    try:
        row = db.execute(
            text(
                """
                SELECT dataset_id, context_json
                FROM system.conversation_context
                WHERE conversation_id = :id
                """
            ),
            {"id": conversation_id},
        ).mappings().first()

        if not row:
            return None

        ctx_ds_id = row["dataset_id"]
        if str_ds_id and ctx_ds_id != str_ds_id:
            logger.info(f"Dataset changed for conversation {conversation_id}. Resetting stale context.")
            reset_conversation_context(db, conversation_id, str_ds_id)
            return None

        ctx = row["context_json"]
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        return ctx
    except Exception as e:
        db.rollback()
        logger.warning(f"Error reading conversation context: {e}")
        return None


def save_conversation_context(
    db: Session, conversation_id: str, dataset_id: str | None, context_data: dict[str, Any]
) -> None:
    """
    Upsert structured analytical context in system.conversation_context.
    """
    ensure_conversation_tables(db)
    str_ds_id = str(dataset_id) if dataset_id else None
    json_str = json.dumps(context_data)
    try:
        db.execute(
            text(
                """
                INSERT INTO system.conversation_context (conversation_id, dataset_id, context_json, updated_at)
                VALUES (:id, :dataset_id, CAST(:context_json AS JSONB), NOW())
                ON CONFLICT (conversation_id) DO UPDATE
                SET dataset_id = EXCLUDED.dataset_id,
                    context_json = EXCLUDED.context_json,
                    updated_at = NOW()
                """
            ),
            {"id": conversation_id, "dataset_id": str_ds_id, "context_json": json_str},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Error saving conversation context: {e}")


def reset_conversation_context(db: Session, conversation_id: str, new_dataset_id: str | None = None) -> None:
    """
    Reset/delete conversation context for a conversation session.
    """
    ensure_conversation_tables(db)
    try:
        db.execute(
            text("DELETE FROM system.conversation_context WHERE conversation_id = :id"),
            {"id": conversation_id},
        )
        if new_dataset_id:
            db.execute(
                text("UPDATE system.conversations SET active_dataset_id = :ds_id WHERE id = :id"),
                {"id": conversation_id, "ds_id": str(new_dataset_id)},
            )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Error resetting conversation context: {e}")
