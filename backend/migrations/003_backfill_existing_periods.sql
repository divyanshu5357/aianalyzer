-- Migration 003: Backfill period metadata for datasets that were uploaded
-- before the period columns were introduced.
--
-- Strategy:
--   1. For any dataset with academic_label IS NULL, attempt to infer the period
--      from the original_filename (regex match on YYYY-YY or YYYY patterns).
--   2. If inference succeeds, write the period metadata.
--   3. Mark the currently active dataset (is_active=TRUE) as is_period_active=TRUE
--      for its detected period.
--   4. For datasets where year cannot be inferred from filename, default to
--      the current calendar year as CY (e.g. 2025-26 during 2026).
--   5. This is idempotent: safe to run multiple times.
--
-- Run: psql $DATABASE_URL < backend/migrations/003_backfill_existing_periods.sql

BEGIN;

-- Step 1: Attempt to backfill from filename pattern YYYY-YY (e.g. "2025-26")
UPDATE system.datasets
SET
    period_end_year   = (
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](2[0-9])\b')
    )[1]::SMALLINT + 1,  -- e.g. "25" from "2025-26" => end_year = 2026
    period_start_year = (
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](2[0-9])\b')
    )[1]::SMALLINT,
    academic_label    = (
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](2[0-9])\b')
    )[1] || '-' || (
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](2[0-9])\b')
    )[2],
    upload_version    = 1
WHERE academic_label IS NULL
  AND REGEXP_MATCH(original_filename, '(20\d{2})[-_](2[0-9])\b') IS NOT NULL;

-- Step 2: Attempt to backfill from filename pattern YYYY-YYYY (e.g. "2025-2026")
UPDATE system.datasets
SET
    period_start_year = (
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](20\d{2})\b')
    )[1]::SMALLINT,
    period_end_year   = (
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](20\d{2})\b')
    )[2]::SMALLINT,
    academic_label    = (
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](20\d{2})\b')
    )[1] || '-' || RIGHT((
        REGEXP_MATCH(original_filename, '(20\d{2})[-_](20\d{2})\b')
    )[2], 2),
    upload_version    = 1
WHERE academic_label IS NULL
  AND REGEXP_MATCH(original_filename, '(20\d{2})[-_](20\d{2})\b') IS NOT NULL;

-- Step 3: Attempt to backfill from filename pattern containing a single YYYY year
UPDATE system.datasets
SET
    period_end_year   = (
        REGEXP_MATCH(original_filename, '\b(20\d{2})\b')
    )[1]::SMALLINT,
    period_start_year = (
        REGEXP_MATCH(original_filename, '\b(20\d{2})\b')
    )[1]::SMALLINT - 1,
    academic_label    = ((
        REGEXP_MATCH(original_filename, '\b(20\d{2})\b')
    )[1]::SMALLINT - 1)::TEXT || '-' ||
        RIGHT((
            REGEXP_MATCH(original_filename, '\b(20\d{2})\b')
        )[1], 2),
    upload_version    = 1
WHERE academic_label IS NULL
  AND REGEXP_MATCH(original_filename, '\b(20\d{2})\b') IS NOT NULL;

-- Step 4: Any remaining datasets with no year in filename — default to current year
UPDATE system.datasets
SET
    period_end_year   = EXTRACT(YEAR FROM NOW())::SMALLINT,
    period_start_year = EXTRACT(YEAR FROM NOW())::SMALLINT - 1,
    academic_label    = (EXTRACT(YEAR FROM NOW())::INTEGER - 1)::TEXT || '-' ||
                        RIGHT(EXTRACT(YEAR FROM NOW())::TEXT, 2),
    upload_version    = 1
WHERE academic_label IS NULL;

-- Step 5: Mark currently active dataset as period_active for its label
-- (Only mark one per label — the currently active dataset)
UPDATE system.datasets
SET is_period_active = TRUE
WHERE is_active = TRUE
  AND academic_label IS NOT NULL
  AND is_period_active = FALSE;

COMMIT;
