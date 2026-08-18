-- Migration: Add composite index (dataset_id, row_number) on staging.records for fast chunking and pagination
CREATE INDEX IF NOT EXISTS idx_staging_records_dataset_row
ON staging.records(dataset_id, row_number);
