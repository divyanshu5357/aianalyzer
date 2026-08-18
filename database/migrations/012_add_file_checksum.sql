-- Migration 012: Add file_checksum to system.datasets
-- Supports duplicate-file detection during upload.
-- SHA-256 hex digest = 64 chars.

ALTER TABLE system.datasets
    ADD COLUMN IF NOT EXISTS file_checksum VARCHAR(64);

-- Index for fast checksum lookups (not unique — same file may be
-- uploaded multiple times as different versions).
CREATE INDEX IF NOT EXISTS idx_datasets_file_checksum
    ON system.datasets (file_checksum)
    WHERE file_checksum IS NOT NULL;
