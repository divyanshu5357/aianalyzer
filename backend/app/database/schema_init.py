import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_all_database_tables(db: Session) -> None:
    """
    Ensure all required PostgreSQL schemas, tables, columns, constraints, and indexes exist on application startup.
    Executes DDL and ALTER TABLE column additions idempotently.
    """
    try:
        # Enable extensions
        db.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
        db.commit()
    except Exception as exc:
        logger.info("uuid-ossp extension notice: %s", exc)
        db.rollback()

    try:
        # 1. Create all schemas
        schemas = ["raw", "staging", "core", "intelligence", "rag", "system", "analytics", "ai_audit", "organization"]
        for schema in schemas:
            db.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema};"))
        db.commit()

        # 2. system.data_sources
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

        # 3. system.datasets
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

        # 4. system.data_quality_reports
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

        # 5. system.column_mappings
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.column_mappings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    original_column VARCHAR(255) NOT NULL,
                    canonical_field VARCHAR(255),
                    confidence NUMERIC(5,2) DEFAULT 0.0,
                    is_ambiguous BOOLEAN DEFAULT FALSE,
                    reasoning TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_system_column_mappings UNIQUE (dataset_id, original_column)
                );
                """
            )
        )

        # 6. intelligence.column_mappings
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS intelligence.column_mappings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    original_column VARCHAR(255) NOT NULL,
                    canonical_column VARCHAR(255),
                    business_meaning TEXT,
                    data_type VARCHAR(100),
                    confidence NUMERIC(5,2),
                    verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # 7. intelligence.business_terms
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS intelligence.business_terms (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    term VARCHAR(255) NOT NULL UNIQUE,
                    meaning TEXT,
                    description TEXT,
                    examples JSONB,
                    confidence NUMERIC(5,2),
                    verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # 8. intelligence.metrics
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS intelligence.metrics (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
                """
            )
        )

        # 9. intelligence.entities & entity_aliases
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS intelligence.entities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_type VARCHAR(100) NOT NULL,
                    canonical_name VARCHAR(500) NOT NULL,
                    description TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS intelligence.entity_aliases (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_id UUID REFERENCES intelligence.entities(id) ON DELETE CASCADE,
                    alias VARCHAR(500) NOT NULL,
                    source VARCHAR(255),
                    confidence NUMERIC(5,2),
                    verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        # 10. system.conversations, conversation_messages, conversation_context
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.conversations (
                    id VARCHAR(255) PRIMARY KEY,
                    active_dataset_id VARCHAR(255),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.conversation_messages (
                    id VARCHAR(255) PRIMARY KEY,
                    conversation_id VARCHAR(255) REFERENCES system.conversations(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.conversation_context (
                    conversation_id VARCHAR(255) PRIMARY KEY REFERENCES system.conversations(id) ON DELETE CASCADE,
                    dataset_id VARCHAR(255),
                    context_json JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )

        # 11. staging.records
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

        # 12. staging.cleaned_records
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

        # 13. analytics.uploaded_metrics
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analytics.uploaded_metrics (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    row_number BIGINT NOT NULL DEFAULT 0,
                    academic_session VARCHAR(100),
                    campus_name VARCHAR(255),
                    state VARCHAR(255),
                    source VARCHAR(255),
                    main_source VARCHAR(255),
                    program_name VARCHAR(255),
                    specialization VARCHAR(255),
                    owner VARCHAR(255),
                    cluster VARCHAR(255),
                    lead_type VARCHAR(255),
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

        metrics_columns = [
            ("row_number", "BIGINT NOT NULL DEFAULT 0"),
            ("owner", "VARCHAR(255)"),
            ("cluster", "VARCHAR(255)"),
            ("lead_type", "VARCHAR(255)"),
            ("main_source", "VARCHAR(255)"),
            ("source", "VARCHAR(255)"),
            ("campus_name", "VARCHAR(255)"),
            ("state", "VARCHAR(255)"),
            ("program_name", "VARCHAR(255)"),
            ("specialization", "VARCHAR(255)"),
            ("academic_session", "VARCHAR(100)"),
            ("cy_leads", "BIGINT DEFAULT 0"),
            ("py_leads", "BIGINT DEFAULT 0"),
            ("cy_cucet", "BIGINT DEFAULT 0"),
            ("py_cucet", "BIGINT DEFAULT 0"),
            ("cy_admission", "BIGINT DEFAULT 0"),
            ("py_admission", "BIGINT DEFAULT 0"),
        ]
        for col_name, col_type in metrics_columns:
            try:
                db.execute(
                    text(
                        f"ALTER TABLE analytics.uploaded_metrics ADD COLUMN IF NOT EXISTS {col_name} {col_type};"
                    )
                )
            except Exception as e:
                logger.debug("Column analytics.uploaded_metrics.%s add notice: %s", col_name, e)
                db.rollback()

        # Ensure UNIQUE constraint on (dataset_id, row_number)
        try:
            db.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'uq_uploaded_metrics_dataset_row'
                        ) THEN
                            ALTER TABLE analytics.uploaded_metrics ADD CONSTRAINT uq_uploaded_metrics_dataset_row UNIQUE (dataset_id, row_number);
                        END IF;
                    END $$;
                    """
                )
            )
        except Exception as e:
            logger.debug("Constraint uq_uploaded_metrics_dataset_row notice: %s", e)
            db.rollback()

        # 14. analytics.physical_mappings & intelligence.physical_mappings
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
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS intelligence.physical_mappings (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    concept_key VARCHAR(150) NOT NULL,
                    table_schema VARCHAR(150) NOT NULL,
                    table_name VARCHAR(255) NOT NULL,
                    column_name VARCHAR(255) NOT NULL,
                    column_role VARCHAR(100),
                    data_type VARCHAR(100),
                    confidence NUMERIC(5,4) NOT NULL DEFAULT 0,
                    evidence JSONB DEFAULT '{}'::jsonb,
                    inference_method VARCHAR(100),
                    verified BOOLEAN DEFAULT false,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        db.commit()
        logger.info("Successfully verified all PostgreSQL schemas, tables, columns, and constraints.")
    except Exception as exc:
        logger.error("Error ensuring database tables on startup: %s", exc)
        db.rollback()
