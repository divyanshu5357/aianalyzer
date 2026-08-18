UPDATE intelligence.metrics
SET
    description =
        'Number of prospective student inquiries generated.',

    business_definition =
        'Leads represent inquiries generated from prospective students.',

    calculation_logic =
        'COUNT of lead records according to the organization source data.',

    time_dimension =
        'year',

    confidence =
        0.95,

    verified =
        false,

    updated_at =
        CURRENT_TIMESTAMP

WHERE metric_name = 'leads';


UPDATE intelligence.metrics
SET
    description =
        'Number of candidates registered for CUCET.',

    business_definition =
        'CUCET represents candidates registered for the Chandigarh University Common Entrance Test.',

    calculation_logic =
        'COUNT of CUCET registrations according to the organization source data.',

    time_dimension =
        'year',

    confidence =
        0.95,

    verified =
        false,

    updated_at =
        CURRENT_TIMESTAMP

WHERE metric_name = 'cucet';


UPDATE intelligence.metrics
SET
    description =
        'Number of final enrolled/admitted students.',

    business_definition =
        'Admission represents final enrolled/admitted students.',

    calculation_logic =
        'COUNT of final admission records according to the organization source data.',

    time_dimension =
        'year',

    confidence =
        0.95,

    verified =
        false,

    updated_at =
        CURRENT_TIMESTAMP

WHERE metric_name = 'admission';


UPDATE intelligence.metrics
SET
    description =
        'Conversion rate from Leads to CUCET registration.',

    business_definition =
        'Percentage of current-year Leads that result in CUCET registration.',

    calculation_logic =
        '(CY CUCET / CY Leads) * 100',

    time_dimension =
        'year',

    confidence =
        1.00,

    verified =
        true,

    updated_at =
        CURRENT_TIMESTAMP

WHERE metric_name = 'lead_cucet_rate';


UPDATE intelligence.metrics
SET
    description =
        'Conversion rate from Leads to final Admission.',

    business_definition =
        'Percentage of current-year Leads that result in final Admission.',

    calculation_logic =
        '(CY Admission / CY Leads) * 100',

    time_dimension =
        'year',

    confidence =
        1.00,

    verified =
        true,

    updated_at =
        CURRENT_TIMESTAMP

WHERE metric_name = 'lead_admission_rate';


UPDATE intelligence.metrics
SET
    description =
        'Conversion rate from CUCET registration to final Admission.',

    business_definition =
        'Percentage of current-year CUCET registrations that result in final Admission.',

    calculation_logic =
        '(CY Admission / CY CUCET) * 100',

    time_dimension =
        'year',

    confidence =
        1.00,

    verified =
        true,

    updated_at =
        CURRENT_TIMESTAMP

WHERE metric_name = 'cucet_admission_rate';


UPDATE intelligence.metrics
SET
    description =
        'Lead / Channel Penetration Efficiency for the 2026 intake.',

    business_definition =
        'Penetration 2026 represents Lead / Channel Penetration Efficiency for the 2026 intake.',

    calculation_logic =
        'PENDING_ORGANIZATION_SOURCE_DEFINITION',

    time_dimension =
        '2026',

    confidence =
        0.90,

    verified =
        false,

    updated_at =
        CURRENT_TIMESTAMP

WHERE metric_name = 'penetration';