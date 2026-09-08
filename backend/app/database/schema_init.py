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
            ("is_analytics_enabled", "BOOLEAN DEFAULT TRUE"),
            ("analytics_status", "VARCHAR(50) DEFAULT 'ANALYTICS_READY'"),
            ("academic_label", "VARCHAR(100)"),
            ("academic_year", "INT"),
            ("campus_name", "VARCHAR(255)"),
            ("period_start_year", "INT"),
            ("period_end_year", "INT"),
            ("upload_version", "INT DEFAULT 1"),
            ("file_checksum", "VARCHAR(255)"),
            ("upload_batch_id", "VARCHAR(100)"),
            ("distinct_prospect_count", "BIGINT DEFAULT 0"),
            ("rows_inserted", "BIGINT DEFAULT 0"),
            ("rows_updated", "BIGINT DEFAULT 0"),
            ("start_date", "TIMESTAMP"),
            ("end_date", "TIMESTAMP"),
            ("month", "VARCHAR(50)"),
            ("month_num", "INT"),
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

        # 6b. intelligence.schema_mappings (Dynamic Mapping Foundation)
        db.execute(
            text(
                """
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
                    status VARCHAR(50) NOT NULL DEFAULT 'suggested',
                    mapping_version INT NOT NULL DEFAULT 1,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    match_type VARCHAR(100),
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_schema_mappings_source ON intelligence.schema_mappings(source_column);
                CREATE INDEX IF NOT EXISTS idx_schema_mappings_target ON intelligence.schema_mappings(target_entity, target_column);
                CREATE INDEX IF NOT EXISTS idx_schema_mappings_status ON intelligence.schema_mappings(status, is_active);
                CREATE INDEX IF NOT EXISTS idx_schema_mappings_file_sheet ON intelligence.schema_mappings(source_file, source_sheet);
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
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.ingestion_jobs (
                    job_id VARCHAR(255) PRIMARY KEY,
                    dataset_id VARCHAR(255),
                    filename VARCHAR(550),
                    stage VARCHAR(100) NOT NULL DEFAULT 'parsing',
                    status VARCHAR(50) NOT NULL DEFAULT 'processing',
                    progress_percent NUMERIC(5,2) NOT NULL DEFAULT 0.0,
                    total_rows BIGINT NOT NULL DEFAULT 0,
                    processed_rows BIGINT NOT NULL DEFAULT 0,
                    message TEXT,
                    error TEXT,
                    result_data JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                ALTER TABLE system.ingestion_jobs ADD COLUMN IF NOT EXISTS result_data JSONB;
                """
            )
        )

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS system.neo4j_sync_queue (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_type VARCHAR(100) NOT NULL,
                    entity_id VARCHAR(255) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    payload JSONB NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    retry_count INT DEFAULT 0,
                    max_retries INT DEFAULT 5,
                    last_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_neo4j_sync_queue_status_retry ON system.neo4j_sync_queue(status, retry_count, created_at);
                CREATE INDEX IF NOT EXISTS idx_neo4j_sync_queue_entity ON system.neo4j_sync_queue(entity_type, entity_id);
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

        try:
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_staging_records_dataset_id ON staging.records(dataset_id);"))
            db.commit()
        except Exception as e:
            logger.debug("staging.records index notice: %s", e)
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
            ("academic_year", "INT"),
            ("cy_leads", "BIGINT DEFAULT 0"),
            ("py_leads", "BIGINT DEFAULT 0"),
            ("cy_cucet", "BIGINT DEFAULT 0"),
            ("py_cucet", "BIGINT DEFAULT 0"),
            ("cy_admission", "BIGINT DEFAULT 0"),
            ("py_admission", "BIGINT DEFAULT 0"),
            ("course_cluster", "VARCHAR(255)"),
            ("state_code", "VARCHAR(100)"),
            ("zone", "VARCHAR(100)"),
            ("team", "VARCHAR(255)"),
            ("source_cluster", "VARCHAR(255)"),
            ("created_month", "VARCHAR(7)"),
            ("admission_month", "VARCHAR(7)"),
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

        # 13b. analytics.dashboard_agg
        try:
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS analytics.dashboard_agg (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        campus_name VARCHAR(255),
                        academic_year INT,
                        state VARCHAR(255),
                        source VARCHAR(255),
                        program_name VARCHAR(255),
                        created_month VARCHAR(7),
                        admission_month VARCHAR(7),
                        leads_cy BIGINT DEFAULT 0,
                        cucet_cy BIGINT DEFAULT 0,
                        admission_cy BIGINT DEFAULT 0,
                        leads_py BIGINT DEFAULT 0,
                        cucet_py BIGINT DEFAULT 0,
                        admission_py BIGINT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    ALTER TABLE analytics.uploaded_metrics ADD COLUMN IF NOT EXISTS raw_program_code VARCHAR(100);
                    ALTER TABLE analytics.uploaded_metrics ADD COLUMN IF NOT EXISTS program_code VARCHAR(100);
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS dataset_id UUID;
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS owner VARCHAR(255);
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS lead_type VARCHAR(100);
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS course_cluster VARCHAR(255);
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS raw_program_code VARCHAR(100);
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS program_code VARCHAR(100);
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS created_month VARCHAR(7);
                    ALTER TABLE analytics.dashboard_agg ADD COLUMN IF NOT EXISTS admission_month VARCHAR(7);
                    ALTER TABLE analytics.dashboard_agg DROP CONSTRAINT IF EXISTS uq_dashboard_agg_dimensions;
                    """
                )
            )
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_agg_dataset_id ON analytics.dashboard_agg(dataset_id);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_agg_campus_year ON analytics.dashboard_agg(LOWER(campus_name), academic_year);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_agg_year_campus ON analytics.dashboard_agg(academic_year, LOWER(campus_name));"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_agg_created_month ON analytics.dashboard_agg(created_month);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_agg_admission_month ON analytics.dashboard_agg(admission_month);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_agg_program_code ON analytics.dashboard_agg(program_code);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_agg_year_owner ON analytics.dashboard_agg(academic_year, owner) WHERE owner IS NOT NULL;"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_academic_year ON analytics.uploaded_metrics(academic_year);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_campus_year ON analytics.uploaded_metrics(campus_name, academic_year);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_dataset_id ON analytics.uploaded_metrics(dataset_id);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_ds_year ON analytics.uploaded_metrics(dataset_id, academic_year);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_program_code ON analytics.uploaded_metrics(program_code);"))
            db.commit()
        except Exception as e:
            logger.debug("dashboard_agg table creation notice: %s", e)
            db.rollback()

        # Additive migration: Populate academic_year for pre-existing datasets and metrics if NULL
        try:
            db.execute(text("""
                UPDATE system.datasets
                SET academic_year = COALESCE(
                    period_end_year,
                    CAST(SUBSTRING(academic_label FROM '[0-9]{4}$') AS INT),
                    CAST(SUBSTRING(academic_label FROM '^[0-9]{4}') AS INT)
                )
                WHERE academic_year IS NULL AND (period_end_year IS NOT NULL OR academic_label IS NOT NULL);

                UPDATE analytics.uploaded_metrics m
                SET academic_year = d.academic_year
                FROM system.datasets d
                WHERE m.dataset_id = d.id AND m.academic_year IS NULL AND d.academic_year IS NOT NULL;
            """))
            db.commit()
        except Exception as e:
            logger.debug("Academic year migration notice: %s", e)
            db.rollback()

        # 14. organization master tables
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS organization.source_master (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source VARCHAR(255) UNIQUE NOT NULL,
                    report_source VARCHAR(255),
                    main_source VARCHAR(255),
                    lead_type VARCHAR(255),
                    source_cluster VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        source_cols = [
            ("report_source", "VARCHAR(255)"),
            ("main_source", "VARCHAR(255)"),
            ("lead_type", "VARCHAR(255)"),
            ("source_cluster", "VARCHAR(255)"),
        ]
        for col_n, col_t in source_cols:
            try:
                db.execute(text(f"ALTER TABLE organization.source_master ADD COLUMN IF NOT EXISTS {col_n} {col_t};"))
            except Exception as e:
                db.rollback()

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS organization.course_master (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    program_key VARCHAR(255) UNIQUE NOT NULL,
                    program_code VARCHAR(100),
                    program_name TEXT,
                    program_name_short TEXT,
                    course_cluster VARCHAR(255),
                    degree_type VARCHAR(100),
                    program_group VARCHAR(100),
                    program_category VARCHAR(100),
                    program_campus VARCHAR(100),
                    program_status VARCHAR(100),
                    leet_to_gen VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        course_cols = [
            ("program_key", "VARCHAR(255)"),
            ("program_code", "VARCHAR(100)"),
            ("program_name", "TEXT"),
            ("program_name_short", "TEXT"),
            ("course_cluster", "VARCHAR(255)"),
            ("degree_type", "VARCHAR(100)"),
            ("program_group", "VARCHAR(100)"),
            ("program_category", "VARCHAR(100)"),
            ("program_campus", "VARCHAR(100)"),
            ("program_status", "VARCHAR(100)"),
            ("leet_to_gen", "VARCHAR(100)"),
        ]
        for col_n, col_t in course_cols:
            try:
                db.execute(text(f"ALTER TABLE organization.course_master ADD COLUMN IF NOT EXISTS {col_n} {col_t};"))
            except Exception as e:
                db.rollback()

        # Drop old program_name unique constraint if present on course_master
        try:
            db.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'course_master_program_name_key'
                        ) THEN
                            ALTER TABLE organization.course_master DROP CONSTRAINT course_master_program_name_key;
                        END IF;
                    END $$;
                    """
                )
            )
        except Exception:
            db.rollback()

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS organization.state_master (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    state_name VARCHAR(255) UNIQUE NOT NULL,
                    state_group VARCHAR(255),
                    state_code VARCHAR(100),
                    zone VARCHAR(100),
                    new_zone VARCHAR(100),
                    country VARCHAR(100),
                    country_code VARCHAR(100),
                    priority_mohali VARCHAR(100),
                    priority_unnao VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        state_cols = [
            ("state_group", "VARCHAR(255)"),
            ("state_code", "VARCHAR(100)"),
            ("zone", "VARCHAR(100)"),
            ("new_zone", "VARCHAR(100)"),
            ("country", "VARCHAR(100)"),
            ("country_code", "VARCHAR(100)"),
            ("priority_mohali", "VARCHAR(100)"),
            ("priority_unnao", "VARCHAR(100)"),
        ]
        for col_n, col_t in state_cols:
            try:
                db.execute(text(f"ALTER TABLE organization.state_master ADD COLUMN IF NOT EXISTS {col_n} {col_t};"))
            except Exception as e:
                db.rollback()

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS organization.employee_master (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    employee_name VARCHAR(255) UNIQUE NOT NULL,
                    office VARCHAR(255),
                    state VARCHAR(255),
                    zone VARCHAR(100),
                    status VARCHAR(100),
                    team VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        emp_cols = [
            ("office", "VARCHAR(255)"),
            ("state", "VARCHAR(255)"),
            ("zone", "VARCHAR(100)"),
            ("status", "VARCHAR(100)"),
            ("team", "VARCHAR(255)"),
        ]
        for col_n, col_t in emp_cols:
            try:
                db.execute(text(f"ALTER TABLE organization.employee_master ADD COLUMN IF NOT EXISTS {col_n} {col_t};"))
            except Exception as e:
                db.rollback()

        # 15. analytics.physical_mappings & intelligence.physical_mappings
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

        # 16. analytics.program_refunds_summary
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analytics.program_refunds_summary (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    academic_year INT NOT NULL,
                    campus_name VARCHAR(255),
                    program_code VARCHAR(255),
                    source VARCHAR(255),
                    lead_type VARCHAR(100),
                    refund_month VARCHAR(7),
                    refund_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_prog_refunds_lookup ON analytics.program_refunds_summary (academic_year, LOWER(campus_name), LOWER(program_code));
                CREATE INDEX IF NOT EXISTS idx_dashboard_agg_prog_lookup ON analytics.dashboard_agg (academic_year, LOWER(campus_name), LOWER(program_code));
                """
            )
        )

        db.commit()
        logger.info("Successfully verified all PostgreSQL schemas, tables, columns, and constraints.")
    except Exception as exc:
        logger.error("Error ensuring database tables on startup: %s", exc)
        db.rollback()
