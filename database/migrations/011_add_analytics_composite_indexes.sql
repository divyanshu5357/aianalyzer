-- Migration 011: Add composite indexes on analytics.uploaded_metrics to optimize dataset-isolated analytical aggregations

CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_dataset_campus 
    ON analytics.uploaded_metrics (dataset_id, campus_name);

CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_dataset_program 
    ON analytics.uploaded_metrics (dataset_id, program_name);

CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_dataset_source 
    ON analytics.uploaded_metrics (dataset_id, main_source);

CREATE INDEX IF NOT EXISTS idx_uploaded_metrics_dataset_owner 
    ON analytics.uploaded_metrics (dataset_id, owner);
