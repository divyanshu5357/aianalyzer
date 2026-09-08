-- ============================================
-- PHASE 12: NEO4J SYNC QUEUE MIGRATION
-- Durable, transactional queue for Neo4j graph projections
-- ============================================

CREATE TABLE IF NOT EXISTS system.neo4j_sync_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL, -- UPSERT | DELETE | ML_PREDICTION
    payload JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending | processing | completed | failed
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 5,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_neo4j_sync_queue_status_retry
ON system.neo4j_sync_queue(status, retry_count, created_at);

CREATE INDEX IF NOT EXISTS idx_neo4j_sync_queue_entity
ON system.neo4j_sync_queue(entity_type, entity_id);
