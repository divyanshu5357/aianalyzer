-- Migration 002: Add period/academic-year metadata to system.datasets
-- Safe: All columns are nullable with defaults; no data is deleted or modified.
-- Run: psql $DATABASE_URL < backend/migrations/002_add_period_columns.sql

BEGIN;

-- Add period metadata columns to system.datasets
ALTER TABLE system.datasets
    ADD COLUMN IF NOT EXISTS period_start_year  SMALLINT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS period_end_year    SMALLINT        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS academic_label     VARCHAR(10)     DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS upload_version     INTEGER         DEFAULT 1,
    ADD COLUMN IF NOT EXISTS is_period_active   BOOLEAN         DEFAULT FALSE;

-- Unique partial index: only one active version per academic period
-- Prevents two datasets from both being active for e.g. "2025-26"
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'system'
          AND tablename  = 'datasets'
          AND indexname  = 'uniq_active_period'
    ) THEN
        CREATE UNIQUE INDEX uniq_active_period
            ON system.datasets (academic_label)
            WHERE is_period_active = TRUE;
    END IF;
END $$;

-- Index for fast period-range queries
CREATE INDEX IF NOT EXISTS idx_datasets_period_end_year
    ON system.datasets (period_end_year);

CREATE INDEX IF NOT EXISTS idx_datasets_academic_label
    ON system.datasets (academic_label);

COMMIT;
