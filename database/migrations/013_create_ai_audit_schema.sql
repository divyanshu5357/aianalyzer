-- 013_create_ai_audit_schema.sql
-- Migration: Create ai_audit schema and store for AI agent transcript, execution metadata, evaluation, and golden cases.

CREATE SCHEMA IF NOT EXISTS ai_audit;

-- 1. Audit Conversations
CREATE TABLE IF NOT EXISTS ai_audit.conversations (
    id VARCHAR(255) PRIMARY KEY,
    dataset_id VARCHAR(255),
    academic_label VARCHAR(100),
    period_start_year INT,
    period_end_year INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Audit Messages / Turns
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
    
    -- Structured Agent Execution Metadata
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

-- 3. Turn Human Evaluations
CREATE TABLE IF NOT EXISTS ai_audit.turn_evaluations (
    id VARCHAR(255) PRIMARY KEY,
    message_id VARCHAR(255) REFERENCES ai_audit.messages(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'unreviewed', -- unreviewed, correct, incorrect, partially_correct
    correct_answer TEXT,
    correct_intent VARCHAR(100),
    correct_metric VARCHAR(100),
    correct_dimension VARCHAR(100),
    correct_entities JSONB,
    correct_period_a VARCHAR(100),
    correct_period_b VARCHAR(100),
    correction_notes TEXT,
    error_category VARCHAR(100), -- intent_error, entity_error, period_error, metric_error, context_error, tool_selection_error, sql_error, result_interpretation_error, formatting_error, unsupported_question_error, hallucination_error, other
    evaluated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Golden Evaluation Cases
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_audit_messages_conv_id ON ai_audit.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_audit_messages_dataset_id ON ai_audit.messages(dataset_id);
CREATE INDEX IF NOT EXISTS idx_audit_messages_created_at ON ai_audit.messages(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_eval_status ON ai_audit.turn_evaluations(status);
CREATE INDEX IF NOT EXISTS idx_audit_eval_error_cat ON ai_audit.turn_evaluations(error_category);
