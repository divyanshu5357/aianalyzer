import csv
import io
import json
import uuid
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VALID_EVAL_STATUSES = {"unreviewed", "correct", "incorrect", "partially_correct"}

VALID_ERROR_CATEGORIES = {
    "intent_error",
    "entity_error",
    "period_error",
    "metric_error",
    "context_error",
    "tool_selection_error",
    "sql_error",
    "result_interpretation_error",
    "formatting_error",
    "unsupported_question_error",
    "hallucination_error",
    "other",
}


def ensure_ai_audit_tables(db: Session) -> None:
    """
    Ensure the ai_audit schema and audit tables exist in PostgreSQL.
    """
    try:
        db.execute(text("CREATE SCHEMA IF NOT EXISTS ai_audit;"))

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ai_audit.conversations (
                    id VARCHAR(255) PRIMARY KEY,
                    dataset_id VARCHAR(255),
                    academic_label VARCHAR(100),
                    period_start_year INT,
                    period_end_year INT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ai_audit.messages (
                    id VARCHAR(255) PRIMARY KEY,
                    conversation_id VARCHAR(255) REFERENCES ai_audit.conversations(id) ON DELETE CASCADE,
                    user_question TEXT NOT NULL,
                    assistant_answer TEXT NOT NULL,
                    dataset_id VARCHAR(255),
                    academic_label VARCHAR(100),
                    period_a VARCHAR(100),
                    period_b VARCHAR(100),
                    selected_years JSONB,
                    response_type VARCHAR(50),
                    detected_intent VARCHAR(100),
                    operation VARCHAR(100),
                    metric VARCHAR(100),
                    dimension VARCHAR(100),
                    resolved_entities JSONB,
                    filters JSONB,
                    tool_used VARCHAR(100),
                    success BOOLEAN DEFAULT TRUE,
                    error_category VARCHAR(100),
                    result_summary JSONB,
                    result_row_count INT DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ai_audit.turn_evaluations (
                    id VARCHAR(255) PRIMARY KEY,
                    message_id VARCHAR(255) REFERENCES ai_audit.messages(id) ON DELETE CASCADE,
                    status VARCHAR(50) NOT NULL DEFAULT 'unreviewed',
                    correct_answer TEXT,
                    correct_intent VARCHAR(100),
                    correct_metric VARCHAR(100),
                    correct_dimension VARCHAR(100),
                    correct_entities JSONB,
                    correct_period_a VARCHAR(100),
                    correct_period_b VARCHAR(100),
                    correction_notes TEXT,
                    error_category VARCHAR(100),
                    evaluated_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ai_audit.golden_cases (
                    id VARCHAR(255) PRIMARY KEY,
                    case_code VARCHAR(100) UNIQUE,
                    question TEXT NOT NULL,
                    conversation_context JSONB,
                    expected_intent VARCHAR(100),
                    expected_metric VARCHAR(100),
                    expected_dimension VARCHAR(100),
                    expected_entities JSONB,
                    expected_periods JSONB,
                    expected_result_characteristics JSONB,
                    expected_answer_requirements TEXT,
                    source_message_id VARCHAR(255) REFERENCES ai_audit.messages(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )

        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Error creating ai_audit schema tables: {e}")


def record_turn_audit(
    db: Session,
    conversation_id: str,
    user_question: str,
    assistant_answer: str,
    dataset_id: Optional[str] = None,
    academic_label: Optional[str] = None,
    period_a: Optional[str] = None,
    period_b: Optional[str] = None,
    selected_years: Optional[List[int]] = None,
    response_type: Optional[str] = "text",
    detected_intent: Optional[str] = None,
    operation: Optional[str] = None,
    metric: Optional[str] = None,
    dimension: Optional[str] = None,
    resolved_entities: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    tool_used: Optional[str] = None,
    success: bool = True,
    error_category: Optional[str] = None,
    raw_data: Optional[List[Dict[str, Any]]] = None,
    columns: Optional[List[str]] = None,
) -> str:
    """
    Records a complete conversation turn and its execution metadata.
    Applies strict data minimization: does NOT store raw million-row results.
    Auto-initializes a turn evaluation with status 'unreviewed'.
    """
    ensure_ai_audit_tables(db)
    msg_id = f"msg_audit_{uuid.uuid4().hex[:12]}"

    # Data Minimization: Create result summary rather than dumping huge tables
    full_data = raw_data or []
    row_count = len(full_data)
    sample_rows = full_data[:10]  # Store at most 10 representative rows for reproduction

    result_summary = {
        "columns": columns or (list(sample_rows[0].keys()) if sample_rows else []),
        "total_row_count": row_count,
        "sample_rows": sample_rows,
    }

    try:
        # 1. Upsert Conversation Record
        db.execute(
            text(
                """
                INSERT INTO ai_audit.conversations (id, dataset_id, academic_label, created_at, updated_at)
                VALUES (:id, :dataset_id, :academic_label, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE
                SET dataset_id = COALESCE(EXCLUDED.dataset_id, ai_audit.conversations.dataset_id),
                    academic_label = COALESCE(EXCLUDED.academic_label, ai_audit.conversations.academic_label),
                    updated_at = NOW()
                """
            ),
            {
                "id": conversation_id,
                "dataset_id": dataset_id,
                "academic_label": academic_label,
            },
        )

        # 2. Insert Turn Audit Record
        db.execute(
            text(
                """
                INSERT INTO ai_audit.messages (
                    id, conversation_id, user_question, assistant_answer,
                    dataset_id, academic_label, period_a, period_b, selected_years, response_type,
                    detected_intent, operation, metric, dimension, resolved_entities, filters,
                    tool_used, success, error_category, result_summary, result_row_count, created_at
                )
                VALUES (
                    :id, :conversation_id, :user_question, :assistant_answer,
                    :dataset_id, :academic_label, :period_a, :period_b, CAST(:selected_years AS JSONB), :response_type,
                    :detected_intent, :operation, :metric, :dimension, CAST(:resolved_entities AS JSONB), CAST(:filters AS JSONB),
                    :tool_used, :success, :error_category, CAST(:result_summary AS JSONB), :result_row_count, NOW()
                )
                """
            ),
            {
                "id": msg_id,
                "conversation_id": str(conversation_id),
                "user_question": str(user_question),
                "assistant_answer": str(assistant_answer),
                "dataset_id": str(dataset_id) if dataset_id else None,
                "academic_label": str(academic_label) if academic_label else None,
                "period_a": str(period_a) if period_a else None,
                "period_b": str(period_b) if period_b else None,
                "selected_years": json.dumps(selected_years or [], default=str),
                "response_type": str(response_type) if response_type else "text",
                "detected_intent": str(detected_intent) if detected_intent else None,
                "operation": str(operation) if operation else None,
                "metric": str(metric) if metric else None,
                "dimension": str(dimension) if dimension else None,
                "resolved_entities": json.dumps(resolved_entities or [], default=str),
                "filters": json.dumps(filters or {}, default=str),
                "tool_used": str(tool_used) if tool_used else None,
                "success": success,
                "error_category": str(error_category) if error_category else None,
                "result_summary": json.dumps(result_summary, default=str),
                "result_row_count": row_count,
            },
        )

        # 3. Create Default Unreviewed Human Evaluation
        eval_id = f"eval_{uuid.uuid4().hex[:12]}"
        db.execute(
            text(
                """
                INSERT INTO ai_audit.turn_evaluations (id, message_id, status, error_category, evaluated_at, updated_at)
                VALUES (:id, :message_id, 'unreviewed', :error_category, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": eval_id,
                "message_id": msg_id,
                "error_category": error_category,
            },
        )

        db.commit()
        return msg_id
    except Exception as e:
        db.rollback()
        logger.warning(f"Error saving turn audit: {e}")
        return msg_id


def evaluate_turn(
    db: Session,
    message_id: str,
    status: str,
    correct_answer: Optional[str] = None,
    correct_intent: Optional[str] = None,
    correct_metric: Optional[str] = None,
    correct_dimension: Optional[str] = None,
    correct_entities: Optional[List[str]] = None,
    correct_period_a: Optional[str] = None,
    correct_period_b: Optional[str] = None,
    correction_notes: Optional[str] = None,
    error_category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluates or corrects a specific AI conversation turn.
    """
    ensure_ai_audit_tables(db)

    if status not in VALID_EVAL_STATUSES:
        raise ValueError(f"Invalid evaluation status '{status}'. Must be one of {VALID_EVAL_STATUSES}")

    if error_category and error_category not in VALID_ERROR_CATEGORIES:
        raise ValueError(f"Invalid error category '{error_category}'. Must be one of {VALID_ERROR_CATEGORIES}")

    existing_row = db.execute(
        text("SELECT id FROM ai_audit.turn_evaluations WHERE message_id = :message_id LIMIT 1"),
        {"message_id": message_id},
    ).mappings().first()

    eval_id = existing_row["id"] if existing_row else f"eval_{uuid.uuid4().hex[:12]}"

    db.execute(
        text(
            """
            INSERT INTO ai_audit.turn_evaluations (
                id, message_id, status, correct_answer, correct_intent, correct_metric,
                correct_dimension, correct_entities, correct_period_a, correct_period_b,
                correction_notes, error_category, evaluated_at, updated_at
            )
            VALUES (
                :id, :message_id, :status, :correct_answer, :correct_intent, :correct_metric,
                :correct_dimension, CAST(:correct_entities AS JSONB), :correct_period_a, :correct_period_b,
                :correction_notes, :error_category, NOW(), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                correct_answer = EXCLUDED.correct_answer,
                correct_intent = EXCLUDED.correct_intent,
                correct_metric = EXCLUDED.correct_metric,
                correct_dimension = EXCLUDED.correct_dimension,
                correct_entities = EXCLUDED.correct_entities,
                correct_period_a = EXCLUDED.correct_period_a,
                correct_period_b = EXCLUDED.correct_period_b,
                correction_notes = EXCLUDED.correction_notes,
                error_category = EXCLUDED.error_category,
                updated_at = NOW()
            """
        ),
        {
            "id": eval_id,
            "message_id": message_id,
            "status": status,
            "correct_answer": correct_answer,
            "correct_intent": correct_intent,
            "correct_metric": correct_metric,
            "correct_dimension": correct_dimension,
            "correct_entities": json.dumps(correct_entities or [], default=str),
            "correct_period_a": correct_period_a,
            "correct_period_b": correct_period_b,
            "correction_notes": correction_notes,
            "error_category": error_category,
        },
    )

    db.commit()

    return {
        "evaluation_id": eval_id,
        "message_id": message_id,
        "status": status,
        "error_category": error_category,
    }


def promote_to_golden_case(
    db: Session,
    question: str,
    expected_intent: Optional[str] = None,
    expected_metric: Optional[str] = None,
    expected_dimension: Optional[str] = None,
    expected_entities: Optional[List[str]] = None,
    expected_periods: Optional[List[str]] = None,
    expected_result_characteristics: Optional[Dict[str, Any]] = None,
    expected_answer_requirements: Optional[str] = None,
    conversation_context: Optional[Dict[str, Any]] = None,
    case_code: Optional[str] = None,
    source_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Promotes an evaluated failure or key test question into a permanent golden regression case.
    """
    ensure_ai_audit_tables(db)

    case_id = f"gc_{uuid.uuid4().hex[:12]}"
    if not case_code:
        case_code = f"GOLDEN_{uuid.uuid4().hex[:8].upper()}"

    db.execute(
        text(
            """
            INSERT INTO ai_audit.golden_cases (
                id, case_code, question, conversation_context, expected_intent,
                expected_metric, expected_dimension, expected_entities, expected_periods,
                expected_result_characteristics, expected_answer_requirements, source_message_id,
                created_at, updated_at
            )
            VALUES (
                :id, :case_code, :question, CAST(:conversation_context AS JSONB), :expected_intent,
                :expected_metric, :expected_dimension, CAST(:expected_entities AS JSONB), CAST(:expected_periods AS JSONB),
                CAST(:expected_result_characteristics AS JSONB), :expected_answer_requirements, :source_message_id,
                NOW(), NOW()
            )
            ON CONFLICT (case_code) DO UPDATE SET
                question = EXCLUDED.question,
                conversation_context = EXCLUDED.conversation_context,
                expected_intent = EXCLUDED.expected_intent,
                expected_metric = EXCLUDED.expected_metric,
                expected_dimension = EXCLUDED.expected_dimension,
                expected_entities = EXCLUDED.expected_entities,
                expected_periods = EXCLUDED.expected_periods,
                expected_result_characteristics = EXCLUDED.expected_result_characteristics,
                expected_answer_requirements = EXCLUDED.expected_answer_requirements,
                source_message_id = EXCLUDED.source_message_id,
                updated_at = NOW()
            """
        ),
        {
            "id": case_id,
            "case_code": case_code,
            "question": question,
            "conversation_context": json.dumps(conversation_context or {}, default=str),
            "expected_intent": expected_intent,
            "expected_metric": expected_metric,
            "expected_dimension": expected_dimension,
            "expected_entities": json.dumps(expected_entities or [], default=str),
            "expected_periods": json.dumps(expected_periods or [], default=str),
            "expected_result_characteristics": json.dumps(expected_result_characteristics or {}, default=str),
            "expected_answer_requirements": expected_answer_requirements,
            "source_message_id": source_message_id,
        },
    )

    db.commit()

    return {
        "golden_case_id": case_id,
        "case_code": case_code,
        "question": question,
    }


def seed_initial_golden_cases(db: Session) -> None:
    """
    Seeds the 4 required failure golden regression cases into ai_audit.golden_cases.
    """
    ensure_ai_audit_tables(db)

    initial_cases = [
        {
            "case_code": "CASE_1",
            "question": 'Analyze the performance of program "B.E. CSE : CS201"',
            "conversation_context": {"dimension": "program_name", "entity": "B.E. CSE : CS201"},
            "expected_intent": "breakdown",
            "expected_metric": "admission",
            "expected_dimension": "program_name",
            "expected_entities": ["B.E. CSE : CS201"],
            "expected_periods": ["2025-26"],
            "expected_result_characteristics": {"requires_entity_specific_analysis": True},
            "expected_answer_requirements": "An entity-specific performance analysis for B.E. CSE : CS201, not a generic ranking answer.",
        },
        {
            "case_code": "CASE_2",
            "question": "Show PY vs CY admissions for B.E. CSE : CS201 and B.E. CSE AIML : CS221",
            "conversation_context": {
                "previous_turns": [
                    "Compare B.E. CSE : CS201 vs B.E. CSE AIML : CS221 admissions"
                ],
                "entities": ["B.E. CSE : CS201", "B.E. CSE AIML : CS221"],
            },
            "expected_intent": "comparison",
            "expected_metric": "admission",
            "expected_dimension": "program_name",
            "expected_entities": ["B.E. CSE : CS201", "B.E. CSE AIML : CS221"],
            "expected_periods": ["PY", "CY"],
            "expected_result_characteristics": {"filtered_to_requested_entities": True},
            "expected_answer_requirements": "Return PY/CY admissions for exactly those two programs, not overall 2026 admissions.",
        },
        {
            "case_code": "CASE_3",
            "question": "how much admission in 2025",
            "conversation_context": {},
            "expected_intent": "metric",
            "expected_metric": "admission",
            "expected_dimension": None,
            "expected_entities": [],
            "expected_periods": ["2025"],
            "expected_result_characteristics": {"resolved_year": 2025},
            "expected_answer_requirements": "If 2025 exists in analytical data, answer 2025 total admissions. Do not treat '2025' as an entity.",
        },
        {
            "case_code": "CASE_4",
            "question": "Which program had the highest admissions?",
            "conversation_context": {"all_values_zero": True},
            "expected_intent": "ranking",
            "expected_metric": "admission",
            "expected_dimension": "program_name",
            "expected_entities": [],
            "expected_periods": ["2025-26"],
            "expected_result_characteristics": {"zero_value_handling": True},
            "expected_answer_requirements": 'If all matching values are zero, answer "No admissions were recorded for the matching programs in the selected period." Do not claim a zero-valued program is a meaningful highest performer.',
        },
    ]

    for c in initial_cases:
        try:
            promote_to_golden_case(
                db=db,
                case_code=c["case_code"],
                question=c["question"],
                conversation_context=c["conversation_context"],
                expected_intent=c["expected_intent"],
                expected_metric=c["expected_metric"],
                expected_dimension=c["expected_dimension"],
                expected_entities=c["expected_entities"],
                expected_periods=c["expected_periods"],
                expected_result_characteristics=c["expected_result_characteristics"],
                expected_answer_requirements=c["expected_answer_requirements"],
            )
        except Exception as e:
            logger.warning(f"Error seeding golden case {c['case_code']}: {e}")


def query_transcripts(
    db: Session,
    conversation_id: Optional[str] = None,
    status: Optional[str] = None,
    error_category: Optional[str] = None,
    dataset_id: Optional[str] = None,
    period: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Queries audit transcripts joined with turn evaluations.
    Supports filtering by conversation_id, status, error category, dataset, and period.
    """
    ensure_ai_audit_tables(db)

    where_clauses = ["1=1"]
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    if conversation_id:
        where_clauses.append("m.conversation_id = :conversation_id")
        params["conversation_id"] = conversation_id

    if status:
        where_clauses.append("COALESCE(e.status, 'unreviewed') = :status")
        params["status"] = status

    if error_category:
        where_clauses.append("(m.error_category = :error_category OR e.error_category = :error_category)")
        params["error_category"] = error_category

    if dataset_id:
        where_clauses.append("m.dataset_id = :dataset_id")
        params["dataset_id"] = dataset_id

    if period:
        where_clauses.append("(m.academic_label = :period OR m.period_a = :period OR m.period_b = :period)")
        params["period"] = period

    where_stmt = " AND ".join(where_clauses)

    sql = f"""
        SELECT
            m.id AS message_id,
            m.conversation_id,
            m.user_question,
            m.assistant_answer,
            m.dataset_id,
            m.academic_label,
            m.period_a,
            m.period_b,
            m.selected_years,
            m.response_type,
            m.detected_intent,
            m.operation,
            m.metric,
            m.dimension,
            m.resolved_entities,
            m.filters,
            m.tool_used,
            m.success,
            m.error_category AS system_error_category,
            m.result_summary,
            m.result_row_count,
            m.created_at,
            COALESCE(e.status, 'unreviewed') AS eval_status,
            e.correct_answer,
            e.correct_intent,
            e.correct_metric,
            e.correct_dimension,
            e.correct_entities,
            e.correction_notes,
            e.error_category AS eval_error_category
        FROM ai_audit.messages m
        LEFT JOIN ai_audit.turn_evaluations e ON e.message_id = m.id
        WHERE {where_stmt}
        ORDER BY m.created_at DESC
        LIMIT :limit OFFSET :offset
    """

    rows = db.execute(text(sql), params).mappings().all()

    results = []
    for r in rows:
        item = dict(r)
        # Parse JSON fields if necessary
        for k in ["selected_years", "resolved_entities", "filters", "result_summary", "correct_entities"]:
            if isinstance(item.get(k), str):
                try:
                    item[k] = json.loads(item[k])
                except Exception:
                    pass
        results.append(item)

    return results


def export_transcripts(
    db: Session,
    format_type: str = "jsonl",
    status: Optional[str] = None,
    error_category: Optional[str] = None,
    dataset_id: Optional[str] = None,
    period: Optional[str] = None,
    limit: int = 1000,
) -> str:
    """
    Exports transcript records in JSONL or CSV format for developer analysis.
    """
    records = query_transcripts(
        db,
        status=status,
        error_category=error_category,
        dataset_id=dataset_id,
        period=period,
        limit=limit,
        offset=0,
    )

    if format_type.lower() == "csv":
        output = io.StringIO()
        if not records:
            return ""
        fieldnames = list(records[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            row = {}
            for k, v in rec.items():
                if isinstance(v, (dict, list)):
                    row[k] = json.dumps(v)
                else:
                    row[k] = v
            writer.writerow(row)
        return output.getvalue()

    # JSONL default format
    lines = [json.dumps(r, default=str) for r in records]
    return "\n".join(lines)
