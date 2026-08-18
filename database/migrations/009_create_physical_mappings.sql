CREATE TABLE IF NOT EXISTS intelligence.physical_mappings
(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    concept_key VARCHAR(150) NOT NULL,

    table_schema VARCHAR(150) NOT NULL,

    table_name VARCHAR(255) NOT NULL,

    column_name VARCHAR(255) NOT NULL,

    column_role VARCHAR(100),

    data_type VARCHAR(100),

    confidence NUMERIC(5,4) NOT NULL DEFAULT 0,

    evidence JSONB DEFAULT '{}'::jsonb,

    inference_method VARCHAR(100),

    verified BOOLEAN DEFAULT false,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_physical_mapping
    UNIQUE (
        concept_key,
        table_schema,
        table_name,
        column_name
    )
);

CREATE INDEX IF NOT EXISTS
idx_physical_mapping_concept
ON intelligence.physical_mappings(concept_key);

CREATE INDEX IF NOT EXISTS
idx_physical_mapping_table
ON intelligence.physical_mappings(
    table_schema,
    table_name
);