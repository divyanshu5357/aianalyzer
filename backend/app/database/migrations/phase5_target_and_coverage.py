"""
Phase 5 Migration: Targets Schema & Dataset Coverage Extensions.

Creates:
1. analytics.targets table for annual & monthly target storage by dimension.
2. Extensions to system.datasets for months_covered, start_month, end_month, workbook_type.
3. Extensions to intelligence.schema_mappings for workbook_type.
"""
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_phase5_migration(db: Session) -> None:
    logger.info("Executing Phase 5 database migration...")

    # 1. Create analytics.targets table
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS analytics.targets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            target_batch_id VARCHAR(100),
            dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
            academic_year INT NOT NULL,
            campus_name VARCHAR(100) DEFAULT 'All',
            month INT,
            dimension_type VARCHAR(50) NOT NULL,
            dimension_value VARCHAR(255) NOT NULL,
            target_leads INT DEFAULT 0,
            target_admissions INT DEFAULT 0,
            target_cucet INT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """))

    db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_targets_scope
        ON analytics.targets (academic_year, LOWER(campus_name), dimension_type, LOWER(dimension_value), month);
    """))

    # 2. Extend system.datasets table for data coverage and workbook type
    db.execute(text("""
        ALTER TABLE system.datasets
        ADD COLUMN IF NOT EXISTS workbook_type VARCHAR(50) DEFAULT 'raw_data',
        ADD COLUMN IF NOT EXISTS start_month INT,
        ADD COLUMN IF NOT EXISTS end_month INT,
        ADD COLUMN IF NOT EXISTS months_covered JSONB DEFAULT '[]'::jsonb,
        ADD COLUMN IF NOT EXISTS upload_batch_id VARCHAR(100);
    """))

    # 3. Extend intelligence.schema_mappings for workbook_type
    db.execute(text("""
        ALTER TABLE intelligence.schema_mappings
        ADD COLUMN IF NOT EXISTS workbook_type VARCHAR(50) DEFAULT 'raw_data';
    """))

    db.commit()
    logger.info("Phase 5 database migration completed successfully.")


if __name__ == "__main__":
    from app.database.connection import SessionLocal
    db = SessionLocal()
    try:
        run_phase5_migration(db)
    finally:
        db.close()
