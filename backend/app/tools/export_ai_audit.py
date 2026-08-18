import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List

from app.database.connection import SessionLocal
from app.database.ai_audit import query_transcripts, ensure_ai_audit_tables


def export_audit_records(
    format_type: str = "jsonl",
    output_path: str | None = None,
    conversation_id: str | None = None,
    status: str | None = None,
    error_category: str | None = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    """
    Export audit transcripts from PostgreSQL database to JSONL or CSV.
    Returns summary stats of the exported data.
    """
    if not output_path:
        output_path = f"ai_audit.{format_type.lower()}"

    db = SessionLocal()
    try:
        ensure_ai_audit_tables(db)
        raw_items = query_transcripts(
            db=db,
            conversation_id=conversation_id,
            status=status,
            error_category=error_category,
            limit=limit,
            offset=0,
        )
    finally:
        db.close()

    exported_rows: List[Dict[str, Any]] = []
    unique_conversations = set()
    evaluated_turns_count = 0

    for item in raw_items:
        conv_id = item.get("conversation_id")
        if conv_id:
            unique_conversations.add(conv_id)

        eval_stat = item.get("eval_status") or "unreviewed"
        if eval_stat != "unreviewed" or item.get("correct_answer") or item.get("correction_notes"):
            evaluated_turns_count += 1

        selected_years = item.get("selected_years") or []
        year_a = item.get("period_a") or (selected_years[0] if len(selected_years) > 0 else None)
        year_b = item.get("period_b") or (selected_years[1] if len(selected_years) > 1 else None)

        err_cat = item.get("eval_error_category") or item.get("system_error_category")

        formatted_turn = {
            "conversation_id": conv_id,
            "message_id": item.get("message_id"),
            "role": "assistant",
            "question": item.get("user_question"),
            "assistant_answer": item.get("assistant_answer"),
            "created_at": str(item.get("created_at")),
            "dataset_id": item.get("dataset_id"),
            "session_period": item.get("academic_label"),
            "year_a": year_a,
            "year_b": year_b,
            "intent": item.get("detected_intent"),
            "metric": item.get("metric"),
            "dimension": item.get("dimension"),
            "resolved_entities": item.get("resolved_entities") or [],
            "filters": item.get("filters") or {},
            "tool_used": item.get("tool_used"),
            "success": item.get("success", True),
            "error_category": err_cat,
            "evaluation_status": eval_stat,
            "correct_answer": item.get("correct_answer"),
            "correction_notes": item.get("correction_notes"),
        }
        exported_rows.append(formatted_turn)

    # Write to file
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    if format_type.lower() == "csv":
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if exported_rows:
                fieldnames = list(exported_rows[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in exported_rows:
                    csv_row = {}
                    for k, v in row.items():
                        if isinstance(v, (dict, list)):
                            csv_row[k] = json.dumps(v, default=str)
                        else:
                            csv_row[k] = v
                    writer.writerow(csv_row)
    else:  # jsonl
        with open(output_path, "w", encoding="utf-8") as f:
            for row in exported_rows:
                f.write(json.dumps(row, default=str) + "\n")

    summary = {
        "conversations": len(unique_conversations),
        "messages": len(exported_rows),
        "evaluated_turns": evaluated_turns_count,
        "output_path": os.path.abspath(output_path),
    }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Export AI Audit transcripts to JSONL or CSV format.")
    parser.add_argument(
        "--format",
        "-f",
        choices=["jsonl", "csv"],
        default="jsonl",
        help="Export format (jsonl or csv). Default: jsonl",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file path (e.g. ai_audit.jsonl)",
    )
    parser.add_argument(
        "--conversation-id",
        type=str,
        default=None,
        help="Filter by specific conversation ID",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filter by evaluation status (e.g. incorrect, unreviewed, correct)",
    )
    parser.add_argument(
        "--error-category",
        type=str,
        default=None,
        help="Filter by error category (e.g. context_error, intent_error)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum number of turns to export. Default: 1000",
    )

    args = parser.parse_args()

    summary = export_audit_records(
        format_type=args.format,
        output_path=args.output,
        conversation_id=args.conversation_id,
        status=args.status,
        error_category=args.error_category,
        limit=args.limit,
    )

    print(f"Exported {summary['conversations']} conversations")
    print(f"Exported {summary['messages']} messages")
    print(f"Exported {summary['evaluated_turns']} evaluated turns")
    print(f"Output: {summary['output_path']}")


if __name__ == "__main__":
    main()
