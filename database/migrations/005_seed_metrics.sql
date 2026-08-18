INSERT INTO intelligence.metrics
(
    metric_name,
    description,
    business_definition,
    calculation_logic,
    source_tables,
    filters,
    time_dimension,
    confidence,
    verified
)
VALUES

(
    'leads',
    'Number of student leads.',
    'Count of prospective student leads or enquiries.',
    'PENDING_SOURCE_MAPPING',
    '[]'::jsonb,
    '{}'::jsonb,
    'year',
    0.70,
    false
),

(
    'cucet',
    'Number of CUCET candidates or CUCET events.',
    'Count of records representing CUCET participation according to the organization data model.',
    'PENDING_SOURCE_MAPPING',
    '[]'::jsonb,
    '{}'::jsonb,
    'year',
    0.70,
    false
),

(
    'admission',
    'Number of student admissions.',
    'Count of records representing successful admissions according to the organization data model.',
    'PENDING_SOURCE_MAPPING',
    '[]'::jsonb,
    '{}'::jsonb,
    'year',
    0.70,
    false
),

(
    'penetration',
    'Penetration percentage.',
    'Organization-defined penetration percentage.',
    'PENDING_BUSINESS_DEFINITION',
    '[]'::jsonb,
    '{}'::jsonb,
    'year',
    0.50,
    false
),

(
    'lead_cucet_rate',
    'Lead to CUCET percentage.',
    'Percentage of leads resulting in CUCET.',
    'CUCET / Leads * 100',
    '[]'::jsonb,
    '{}'::jsonb,
    'year',
    0.80,
    false
),

(
    'lead_admission_rate',
    'Lead to Admission percentage.',
    'Percentage of leads resulting in admission.',
    'Admission / Leads * 100',
    '[]'::jsonb,
    '{}'::jsonb,
    'year',
    0.80,
    false
),

(
    'cucet_admission_rate',
    'CUCET to Admission percentage.',
    'Percentage of CUCET candidates resulting in admission.',
    'Admission / CUCET * 100',
    '[]'::jsonb,
    '{}'::jsonb,
    'year',
    0.80,
    false
)

ON CONFLICT (metric_name)
DO UPDATE SET
    description = EXCLUDED.description,
    business_definition = EXCLUDED.business_definition,
    calculation_logic = EXCLUDED.calculation_logic,
    source_tables = EXCLUDED.source_tables,
    filters = EXCLUDED.filters,
    time_dimension = EXCLUDED.time_dimension,
    confidence = EXCLUDED.confidence,
    verified = EXCLUDED.verified,
    updated_at = CURRENT_TIMESTAMP;