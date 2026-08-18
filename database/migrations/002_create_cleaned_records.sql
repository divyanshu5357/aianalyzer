CREATE TABLE IF NOT EXISTS staging.cleaned_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    dataset_id UUID NOT NULL
        REFERENCES system.datasets(id)
        ON DELETE CASCADE,

    staging_record_id UUID NOT NULL
        REFERENCES staging.records(id)
        ON DELETE CASCADE,

    cleaned_data JSONB NOT NULL,

    issues JSONB NOT NULL DEFAULT '[]'::jsonb,

    issue_count INTEGER NOT NULL DEFAULT 0,

    cleaning_status VARCHAR(50) DEFAULT 'cleaned',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_cleaned_records_dataset
ON staging.cleaned_records(dataset_id);


CREATE INDEX IF NOT EXISTS idx_cleaned_records_status
ON staging.cleaned_records(cleaning_status);