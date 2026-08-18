-- ============================================================
-- ENQUIRIES
-- ============================================================

INSERT INTO organization.enquiries
(
    enquiry_id,
    user_id,
    name,
    email,
    city,
    district,
    state,
    country,
    source,
    main_source,
    campus_name,
    cluster,
    program_code,
    program_name,
    lead_type,
    enquiry_date,
    prospectus_payment_date
)
VALUES

(
    'ENQ001',
    'U001',
    'Rahul',
    'rahul@example.com',
    'Delhi',
    'Delhi',
    'Delhi',
    'India',
    'Google',
    'Digital',
    'Main Campus',
    'North',
    'MCA',
    'MCA',
    'Domestic',
    '2026-01-10',
    '2026-01-12'
),

(
    'ENQ002',
    'U002',
    'Aman',
    'aman@example.com',
    'Gurgaon',
    'Gurgaon',
    'Haryana',
    'India',
    'Facebook',
    'Digital',
    'Main Campus',
    'North',
    'BCA',
    'BCA',
    'Domestic',
    '2026-01-15',
    NULL
),

(
    'ENQ003',
    'U003',
    'Priya',
    'priya@example.com',
    'Delhi',
    'Delhi',
    'Delhi',
    'India',
    'Website',
    'Organic',
    'Main Campus',
    'North',
    'MCA',
    'MCA',
    'Domestic',
    '2026-02-05',
    '2026-02-06'
),

(
    'ENQ004',
    'U004',
    'Neha',
    'neha@example.com',
    'Chandigarh',
    'Chandigarh',
    'Punjab',
    'India',
    'Education Fair',
    'Offline',
    'City Campus',
    'North',
    'BBA',
    'BBA',
    'Domestic',
    '2026-02-20',
    NULL
),

(
    'ENQ005',
    'U005',
    'Rohit',
    'rohit@example.com',
    'Noida',
    'Gautam Buddha Nagar',
    'Uttar Pradesh',
    'India',
    'Google',
    'Digital',
    'Main Campus',
    'North',
    'MCA',
    'MCA',
    'Domestic',
    '2025-03-10',
    '2025-03-15'
),

(
    'ENQ006',
    'U006',
    'Anjali',
    'anjali@example.com',
    'Jaipur',
    'Jaipur',
    'Rajasthan',
    'India',
    'Website',
    'Organic',
    'City Campus',
    'West',
    'BBA',
    'BBA',
    'Domestic',
    '2025-04-12',
    NULL
);


-- ============================================================
-- CUCET REGISTRATIONS
-- ============================================================

INSERT INTO organization.cucet_registrations
(
    registration_id,
    user_id,
    enquiry_id,
    program_name,
    campus_name,
    registration_date,
    exam_status
)
VALUES

(
    'CUC001',
    'U001',
    'ENQ001',
    'MCA',
    'Main Campus',
    '2026-01-20',
    'Registered'
),

(
    'CUC002',
    'U003',
    'ENQ003',
    'MCA',
    'Main Campus',
    '2026-02-10',
    'Registered'
),

(
    'CUC003',
    'U004',
    'ENQ004',
    'BBA',
    'City Campus',
    '2026-02-25',
    'Registered'
),

(
    'CUC004',
    'U005',
    'ENQ005',
    'MCA',
    'Main Campus',
    '2025-03-20',
    'Registered'
);


-- ============================================================
-- ADMISSIONS
-- ============================================================

INSERT INTO organization.admissions
(
    admission_id,
    user_id,
    enquiry_id,
    program_name,
    campus_name,
    cluster,
    state,
    admission_date,
    admission_status
)
VALUES

(
    'ADM001',
    'U001',
    'ENQ001',
    'MCA',
    'Main Campus',
    'North',
    'Delhi',
    '2026-03-01',
    'Admitted'
),

(
    'ADM002',
    'U003',
    'ENQ003',
    'MCA',
    'Main Campus',
    'North',
    'Delhi',
    '2026-03-05',
    'Admitted'
),

(
    'ADM003',
    'U004',
    'ENQ004',
    'BBA',
    'City Campus',
    'North',
    'Punjab',
    '2026-03-10',
    'Admitted'
),

(
    'ADM004',
    'U005',
    'ENQ005',
    'MCA',
    'Main Campus',
    'North',
    'Uttar Pradesh',
    '2025-04-01',
    'Admitted'
);
