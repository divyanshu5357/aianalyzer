
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable vector search for future RAG
CREATE EXTENSION IF NOT EXISTS vector;


-- ============================================
-- SCHEMAS
-- ============================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS intelligence;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS system;


-- ============================================
-- SYSTEM
-- ============================================

CREATE TABLE IF NOT EXISTS system.data_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- DATASET REGISTRY
-- ============================================

CREATE TABLE IF NOT EXISTS system.datasets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    source_id UUID REFERENCES system.data_sources(id),

    dataset_name VARCHAR(255) NOT NULL,
    original_filename VARCHAR(500),

    dataset_type VARCHAR(100),

    row_count BIGINT DEFAULT 0,
    column_count INTEGER DEFAULT 0,

    status VARCHAR(50) DEFAULT 'uploaded',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- DATA QUALITY
-- ============================================

CREATE TABLE IF NOT EXISTS system.data_quality_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    dataset_id UUID REFERENCES system.datasets(id),

    total_rows BIGINT DEFAULT 0,
    total_columns INTEGER DEFAULT 0,

    missing_values BIGINT DEFAULT 0,
    duplicate_rows BIGINT DEFAULT 0,

    invalid_values BIGINT DEFAULT 0,

    quality_score NUMERIC(5,2),

    report JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- BUSINESS DICTIONARY
-- ============================================

CREATE TABLE IF NOT EXISTS intelligence.business_terms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    term VARCHAR(255) NOT NULL UNIQUE,

    meaning TEXT,

    description TEXT,

    examples JSONB,

    confidence NUMERIC(5,2),

    verified BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- COLUMN MAPPINGS
-- ============================================

CREATE TABLE IF NOT EXISTS intelligence.column_mappings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    dataset_id UUID REFERENCES system.datasets(id),

    original_column VARCHAR(255) NOT NULL,

    canonical_column VARCHAR(255),

    business_meaning TEXT,

    data_type VARCHAR(100),

    confidence NUMERIC(5,2),

    verified BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- METRIC REGISTRY
-- ============================================

CREATE TABLE IF NOT EXISTS intelligence.metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    metric_name VARCHAR(255) NOT NULL UNIQUE,

    description TEXT,

    business_definition TEXT,

    calculation_logic TEXT,

    source_tables JSONB,

    filters JSONB,

    time_dimension VARCHAR(255),

    confidence NUMERIC(5,2),

    verified BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- ENTITY REGISTRY
-- ============================================

CREATE TABLE IF NOT EXISTS intelligence.entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    entity_type VARCHAR(100) NOT NULL,

    canonical_name VARCHAR(500) NOT NULL,

    description TEXT,

    metadata JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- ENTITY ALIASES
-- ============================================

CREATE TABLE IF NOT EXISTS intelligence.entity_aliases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    entity_id UUID REFERENCES intelligence.entities(id),

    alias VARCHAR(500) NOT NULL,

    source VARCHAR(255),

    confidence NUMERIC(5,2),

    verified BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- RAG DOCUMENTS
-- ============================================

CREATE TABLE IF NOT EXISTS rag.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    filename VARCHAR(500) NOT NULL,

    document_type VARCHAR(100),

    title VARCHAR(500),

    source VARCHAR(500),

    metadata JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- RAG DOCUMENT CHUNKS
-- ============================================

CREATE TABLE IF NOT EXISTS rag.document_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    document_id UUID REFERENCES rag.documents(id) ON DELETE CASCADE,

    chunk_index INTEGER NOT NULL,

    content TEXT NOT NULL,

    metadata JSONB,

    embedding vector(1536),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- AUDIT LOG
-- ============================================

CREATE TABLE IF NOT EXISTS system.audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    user_id UUID,

    action VARCHAR(255),

    resource VARCHAR(255),

    details JSONB,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);