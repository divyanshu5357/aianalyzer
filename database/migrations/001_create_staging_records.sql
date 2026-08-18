CREATE TABLE IF NOT EXISTS staging.records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    dataset_id UUID NOT NULL
        REFERENCES system.datasets(id)
        ON DELETE CASCADE,

    row_number BIGINT NOT NULL,

    raw_data JSONB NOT NULL,

    cleaned_data JSONB,

    cleaning_status VARCHAR(50) DEFAULT 'pending',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_staging_records_dataset
ON staging.records(dataset_id);


CREATE INDEX IF NOT EXISTS idx_staging_records_status
ON staging.records(cleaning_status);