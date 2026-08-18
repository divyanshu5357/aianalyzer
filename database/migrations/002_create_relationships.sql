CREATE TABLE IF NOT EXISTS intelligence.relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    left_schema VARCHAR(255) NOT NULL,
    left_table VARCHAR(255) NOT NULL,
    left_column VARCHAR(255) NOT NULL,

    right_schema VARCHAR(255) NOT NULL,
    right_table VARCHAR(255) NOT NULL,
    right_column VARCHAR(255) NOT NULL,

    relationship_key VARCHAR(255) NOT NULL,

    relationship_type VARCHAR(100),

    candidate_confidence NUMERIC(5,4),

    validation_score NUMERIC(5,4),

    left_row_count BIGINT,

    right_row_count BIGINT,

    matching_rows BIGINT,

    unmatched_left_rows BIGINT,

    unmatched_right_rows BIGINT,

    status VARCHAR(50) DEFAULT 'candidate',

    validation_details JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_relationships_left
ON intelligence.relationships (
    left_schema,
    left_table,
    left_column
);

CREATE INDEX IF NOT EXISTS idx_relationships_right
ON intelligence.relationships (
    right_schema,
    right_table,
    right_column
);

CREATE INDEX IF NOT EXISTS idx_relationships_status
ON intelligence.relationships(status);