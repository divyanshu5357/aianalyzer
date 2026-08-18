CREATE TABLE IF NOT EXISTS intelligence.semantic_concepts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    concept_key VARCHAR(150) UNIQUE NOT NULL,

    display_name VARCHAR(200) NOT NULL,

    description TEXT,

    category VARCHAR(100),

    synonyms JSONB DEFAULT '[]'::jsonb,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS intelligence.semantic_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    dataset_id UUID NOT NULL
        REFERENCES system.datasets(id)
        ON DELETE CASCADE,

    source_column VARCHAR(255) NOT NULL,

    concept_key VARCHAR(150) NOT NULL,

    time_context VARCHAR(100),

    data_role VARCHAR(100),

    confidence NUMERIC(5,4) NOT NULL,

    evidence JSONB DEFAULT '{}'::jsonb,

    inference_method VARCHAR(100),

    status VARCHAR(50) DEFAULT 'suggested',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_semantic_mappings_dataset
ON intelligence.semantic_mappings(dataset_id);


CREATE INDEX IF NOT EXISTS idx_semantic_mappings_column
ON intelligence.semantic_mappings(source_column);


CREATE INDEX IF NOT EXISTS idx_semantic_mappings_concept
ON intelligence.semantic_mappings(concept_key);


CREATE TABLE IF NOT EXISTS intelligence.semantic_approvals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    mapping_id UUID NOT NULL
        REFERENCES intelligence.semantic_mappings(id)
        ON DELETE CASCADE,

    approved_concept VARCHAR(150) NOT NULL,

    approved_by VARCHAR(150),

    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);