import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_all_database_tables(db: Session) -> None:
    """
    Ensure all required PostgreSQL schemas, tables, and columns exist on application startup.
    Executes schema DDL and ALTER TABLE column additions idempotently.
    """
    try:
        # Enable extensions
        db.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
        db.commit()
    except Exception as exc:
        logger.info("uuid-ossp extension notice: %s", exc)
        db.rollback()

    try:
        # Create schemas
        schemas = ["raw", "staging", "core", "intelligence", "rag", "system", "analytics", "ai_audit", "organization"]
        for schema in schemas:
            db.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))
        db.commit()

        # system.data_sources
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.data_sources (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_name VARCHAR(255) NOT NULL,
                    source_type VARCHAR(50) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # system.datasets
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.datasets (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_id UUID,
                    dataset_name VARCHAR(255) NOT NULL,
                    original_filename VARCHAR(500),
                    dataset_type VARCHAR(100),
                    row_count BIGINT DEFAULT 0,
                    column_count INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'uploaded',
                    is_active BOOLEAN DEFAULT FALSE,
                    is_period_active BOOLEAN DEFAULT FALSE,
                    academic_label VARCHAR(100),
                    period_start_year INT,
                    period_end_year INT,
                    upload_version INT DEFAULT 1,
                    file_checksum VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # Ensure missing columns exist in system.datasets if pre-existed
        dataset_columns = [
            ("is_active", "BOOLEAN DEFAULT FALSE"),
            ("is_period_active", "BOOLEAN DEFAULT FALSE"),
            ("academic_label", "VARCHAR(100)"),
            ("period_start_year", "INT"),
            ("period_end_year", "INT"),
            ("upload_version", "INT DEFAULT 1"),
            ("file_checksum", "VARCHAR(255)"),
        ]
        for col_name, col_type in dataset_columns:
            try:
                db.execute(
                    text(
                        f"ALTER TABLE system.datasets ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                    )
                )
            except Exception as e:
                logger.debug("Column system.datasets.%s add notice: %s", col_name, e)
                db.rollback()

        # system.data_quality_reports
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.data_quality_reports (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    total_rows BIGINT DEFAULT 0,
                    total_columns INTEGER DEFAULT 0,
                    missing_values BIGINT DEFAULT 0,
                    duplicate_rows BIGINT DEFAULT 0,
                    invalid_values BIGINT DEFAULT 0,
                    quality_score NUMERIC(5,2),
                    report JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # staging.records
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS staging.records (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    row_number BIGINT NOT NULL DEFAULT 0,
                    raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    cleaned_data JSONB,
                    cleaning_status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # Ensure missing columns exist in staging.records if table was created with different schema
        staging_columns = [
            ("row_number", "BIGINT NOT NULL DEFAULT 0"),
            ("raw_data", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
            ("cleaned_data", "JSONB"),
            ("cleaning_status", "VARCHAR(50) DEFAULT 'pending'"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ]
        for col_name, col_type in staging_columns:
            try:
                db.execute(
                    text(
                        f"ALTER TABLE staging.records ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                    )
                )
            except Exception as e:
                logger.debug("Column staging.records.%s add notice: %s", col_name, e)
                db.rollback()

        # staging.cleaned_records
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS staging.cleaned_records (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    staging_record_id UUID REFERENCES staging.records(id) ON DELETE CASCADE,
                    cleaned_data JSONB NOT NULL,
                    issues JSONB NOT NULL DEFAULT '[]'::jsonb,
                    issue_count INTEGER NOT NULL DEFAULT 0,
                    cleaning_status VARCHAR(50) DEFAULT 'cleaned',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # analytics.uploaded_metrics
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analytics.uploaded_metrics (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    academic_session VARCHAR(100),
                    campus_name VARCHAR(255),
                    state VARCHAR(255),
                    source VARCHAR(255),
                    program_name VARCHAR(255),
                    specialization VARCHAR(255),
                    owner VARCHAR(255),
                    cy_leads BIGINT DEFAULT 0,
                    py_leads BIGINT DEFAULT 0,
                    cy_cucet BIGINT DEFAULT 0,
                    py_cucet BIGINT DEFAULT 0,
                    cy_admission BIGINT DEFAULT 0,
                    py_admission BIGINT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # analytics.physical_mappings
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analytics.physical_mappings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID,
                    column_name VARCHAR(255),
                    canonical_metric VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        db.commit()
        logger.info("Successfully verified all PostgreSQL schemas, tables, and columns.")
    except Exception as exc:
        logger.error("Error ensuring database tables on startup: %s", exc)
        db.rollback()
