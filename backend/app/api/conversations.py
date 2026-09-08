import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.conversations import get_conversation_messages, get_conversation_context

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


@router.get("/{conversation_id}/transcript")
def get_conversation_transcript(
    conversation_id: str,
    format: str = Query("txt", pattern="^(txt|csv)$"),
    db: Session = Depends(get_db),
):
    """
    Generate and download on-demand conversation transcript in TXT or CSV format.
    Includes user questions, assistant answers, timestamps, and applied filters/context.
    """
    msgs = get_conversation_messages(db, conversation_id, limit=200)
    ctx = get_conversation_context(db, conversation_id, None) or {}

    if not msgs:
        raise HTTPException(status_code=404, detail="Conversation transcript not found or empty.")

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "Role", "Message", "Dataset ID", "Applied Filters", "Last Intent"])

        filters_str = str(ctx.get("filters", {}))
        last_intent = str(ctx.get("last_intent", ""))
        ds_id = str(ctx.get("dataset_id", ""))

        for msg in msgs:
            ts = msg.get("created_at")
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts)
            writer.writerow([ts_str, msg.get("role", "").upper(), msg.get("content", ""), ds_id, filters_str, last_intent])

        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=transcript_{conversation_id}.csv"},
        )

    else:  # txt format
        lines = []
        lines.append("=" * 80)
        lines.append("ADMISSIONS INTELLIGENCE ANALYST — CHAT TRANSCRIPT")
        lines.append(f"Conversation ID : {conversation_id}")
        lines.append(f"Exported At     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Active Dataset  : {ctx.get('dataset_id', 'Default')}")
        lines.append("-" * 80)
        lines.append("APPLIED ANALYTICAL CONTEXT:")
        lines.append(f"  Year        : {ctx.get('year', 'N/A')}")
        lines.append(f"  Campus      : {ctx.get('campus', 'All')}")
        lines.append(f"  Metric      : {ctx.get('metric', 'N/A')}")
        lines.append(f"  Group By    : {ctx.get('group_by', 'N/A')}")
        lines.append(f"  Filters     : {ctx.get('filters', {})}")
        lines.append(f"  Last Intent : {ctx.get('last_intent', 'N/A')}")
        lines.append("=" * 80)
        lines.append("")

        for msg in msgs:
            ts = msg.get("created_at")
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts)
            role = str(msg.get("role", "")).upper()
            content = str(msg.get("content", ""))

            lines.append(f"[{ts_str}] {role}:")
            lines.append(content)
            lines.append("-" * 40)
            lines.append("")

        txt_content = "\n".join(lines)
        return Response(
            content=txt_content,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=transcript_{conversation_id}.txt"},
        )
