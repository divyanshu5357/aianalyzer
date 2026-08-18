INSERT INTO intelligence.business_terms
(
    term,
    meaning,
    description,
    examples,
    confidence,
    verified
)
VALUES

(
    'PY',
    'Previous Year',
    'Indicates that a metric or value belongs to the previous year.',
    '["PY Leads", "PY CUCET", "PY Admission"]'::jsonb,
    1.00,
    true
),

(
    'CY',
    'Current Year',
    'Indicates that a metric or value belongs to the current year.',
    '["CY Leads", "CY CUCET", "CY Admission"]'::jsonb,
    1.00,
    true
),

(
    'Adm',
    'Admission',
    'Short form commonly used for admission.',
    '["Adm 2024", "Adm 2025", "PY Admission", "CY Admission"]'::jsonb,
    1.00,
    true
),

(
    'Leads',
    'Student Leads',
    'Prospective student leads or enquiries generated for the organization.',
    '["PY Leads", "CY Leads", "Leads 2024"]'::jsonb,
    1.00,
    true
),

(
    'CUCET',
    'CUCET',
    'CUCET examination or CUCET-related stage in the admission funnel.',
    '["PY CUCET", "CY CUCET", "Cucet 2024"]'::jsonb,
    1.00,
    true
),

(
    'Admission',
    'Student Admission',
    'A student successfully completing the organization admission process.',
    '["PY Admission", "CY Admission", "Adm 2024"]'::jsonb,
    1.00,
    true
),

(
    'Penetration',
    'Penetration Percentage',
    'A percentage-based business performance measure representing penetration.',
    '["Penetration 2026"]'::jsonb,
    0.90,
    false
),

(
    'Lead Admission',
    'Lead to Admission Percentage',
    'Percentage of leads that result in admission.',
    '["CY Lead - Admission%"]'::jsonb,
    0.90,
    false
),

(
    'Lead CUCET',
    'Lead to CUCET Percentage',
    'Percentage of leads that result in CUCET.',
    '["CY Lead - CUCET%"]'::jsonb,
    0.90,
    false
),

(
    'CUCET Admission',
    'CUCET to Admission Percentage',
    'Percentage of CUCET candidates that result in admission.',
    '["CY CUCET-Admission%"]'::jsonb,
    0.90,
    false
)

ON CONFLICT (term)
DO UPDATE SET
    meaning = EXCLUDED.meaning,
    description = EXCLUDED.description,
    examples = EXCLUDED.examples,
    confidence = EXCLUDED.confidence,
    verified = EXCLUDED.verified,
    updated_at = CURRENT_TIMESTAMP;