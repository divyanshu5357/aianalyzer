-- ============================================================
-- ORGANIZATION SQL SANDBOX
-- Development/testing database structure
-- ============================================================

CREATE SCHEMA IF NOT EXISTS organization;


-- ============================================================
-- ENQUIRIES
-- ============================================================

CREATE TABLE IF NOT EXISTS organization.enquiries
(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    enquiry_id VARCHAR(100) NOT NULL UNIQUE,

    user_id VARCHAR(100),

    name VARCHAR(255),

    email VARCHAR(255),

    city VARCHAR(150),

    district VARCHAR(150),

    state VARCHAR(150),

    country VARCHAR(100),

    source VARCHAR(150),

    main_source VARCHAR(150),

    campus_name VARCHAR(255),

    cluster VARCHAR(255),

    program_code VARCHAR(100),

    program_name VARCHAR(255),

    lead_type VARCHAR(100),

    enquiry_date DATE,

    prospectus_payment_date DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- CUCET REGISTRATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS organization.cucet_registrations
(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    registration_id VARCHAR(100) NOT NULL UNIQUE,

    user_id VARCHAR(100),

    enquiry_id VARCHAR(100),

    program_name VARCHAR(255),

    campus_name VARCHAR(255),

    registration_date DATE,

    exam_status VARCHAR(100),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- ADMISSIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS organization.admissions
(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    admission_id VARCHAR(100) NOT NULL UNIQUE,

    user_id VARCHAR(100),

    enquiry_id VARCHAR(100),

    program_name VARCHAR(255),

    campus_name VARCHAR(255),

    cluster VARCHAR(255),

    state VARCHAR(150),

    admission_date DATE,

    admission_status VARCHAR(100),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_enquiries_user_id
ON organization.enquiries(user_id);

CREATE INDEX IF NOT EXISTS idx_enquiries_date
ON organization.enquiries(enquiry_date);

CREATE INDEX IF NOT EXISTS idx_enquiries_program
ON organization.enquiries(program_name);

CREATE INDEX IF NOT EXISTS idx_enquiries_campus
ON organization.enquiries(campus_name);


CREATE INDEX IF NOT EXISTS idx_cucet_user_id
ON organization.cucet_registrations(user_id);

CREATE INDEX IF NOT EXISTS idx_cucet_date
ON organization.cucet_registrations(registration_date);


CREATE INDEX IF NOT EXISTS idx_admissions_user_id
ON organization.admissions(user_id);

CREATE INDEX IF NOT EXISTS idx_admissions_date
ON organization.admissions(admission_date);

CREATE INDEX IF NOT EXISTS idx_admissions_program
ON organization.admissions(program_name);

CREATE INDEX IF NOT EXISTS idx_admissions_campus
ON organization.admissions(campus_name);