-- Migration 015: Create Schema Mappings Table for Dynamic Mapping Foundation
CREATE TABLE IF NOT EXISTS intelligence.schema_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mapping_name VARCHAR(255),
    source_file VARCHAR(255) NOT NULL,
    source_sheet VARCHAR(255) NOT NULL DEFAULT 'default',
    source_column VARCHAR(255) NOT NULL,
    target_entity VARCHAR(255) NOT NULL,
    target_sheet VARCHAR(255) NOT NULL DEFAULT 'default',
    target_column VARCHAR(255) NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL DEFAULT 0.0,
    status VARCHAR(50) NOT NULL DEFAULT 'suggested', -- 'suggested', 'approved', 'rejected', 'modified'
    mapping_version INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    match_type VARCHAR(100), -- 'exact', 'synonym', 'value_overlap', 'manual'
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_schema_mappings_source 
ON intelligence.schema_mappings(source_column);

CREATE INDEX IF NOT EXISTS idx_schema_mappings_target 
ON intelligence.schema_mappings(target_entity, target_column);

CREATE INDEX IF NOT EXISTS idx_schema_mappings_status 
ON intelligence.schema_mappings(status, is_active);

CREATE INDEX IF NOT EXISTS idx_schema_mappings_file_sheet
ON intelligence.schema_mappings(source_file, source_sheet);
