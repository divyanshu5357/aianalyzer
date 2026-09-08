import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.aggregate_service import get_agg_performance_rankings, get_agg_entity_detail
from app.analytics.aggregate_refresh import refresh_dashboard_agg


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    # Refresh dashboard_agg to ensure latest schema and joins are populated
    refresh_dashboard_agg(session)
    yield session
    session.close()


def test_01_program_dimension_course_master_exists(db):
    """Test 1: Inspect organization.course_master table and verify records exist."""
    cm_count = db.execute(text("SELECT COUNT(*) FROM organization.course_master")).scalar()
    assert cm_count is not None and cm_count > 0, "organization.course_master must contain records"
    print(f"Total Course Master records: {cm_count}")


def test_02_program_code_uniqueness(db):
    """Test 2: Verify ProgramCode values are unique in organization.course_master."""
    dup_count = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT program_code FROM organization.course_master
            GROUP BY program_code HAVING COUNT(*) > 1
        ) dups;
    """)).scalar()
    assert dup_count == 0, f"Expected 0 duplicate program_codes in course_master, found {dup_count}"


def test_03_source_program_code_coverage_audit(db):
    """Test 3: Audit ProgramCode coverage against raw CRM staging records."""
    audit_res = db.execute(text("""
        WITH raw_summary AS (
            SELECT r.raw_data->>'Program Code' as raw_program_code, COUNT(*) as row_count
            FROM staging.records r
            JOIN system.datasets d ON r.dataset_id = d.id
            WHERE d.workbook_type = 'RAW'
            GROUP BY raw_program_code
        )
        SELECT 
            rs.raw_program_code,
            rs.row_count,
            CASE WHEN cm.program_code IS NOT NULL THEN 'YES' ELSE 'NO' END as is_matched
        FROM raw_summary rs
        LEFT JOIN (
            SELECT DISTINCT ON (program_code) program_code
            FROM organization.course_master
        ) cm ON TRIM(UPPER(rs.raw_program_code)) = TRIM(UPPER(cm.program_code))
    """)).fetchall()

    total_codes = len(audit_res)
    matched_codes = sum(1 for a in audit_res if a.is_matched == 'YES')
    matched_rows = sum(a.row_count for a in audit_res if a.is_matched == 'YES')
    total_rows = sum(a.row_count for a in audit_res)

    match_rate = (matched_codes / total_codes * 100) if total_codes > 0 else 0
    row_rate = (matched_rows / total_rows * 100) if total_rows > 0 else 0

    print(f"Distinct ProgramCodes matched: {matched_codes}/{total_codes} ({match_rate:.2f}%)")
    print(f"CRM rows mapped: {matched_rows}/{total_rows} ({row_rate:.2f}%)")

    assert match_rate >= 95.0, f"Expected >= 95% ProgramCode match rate, got {match_rate:.2f}%"
    assert row_rate >= 99.0, f"Expected >= 99% CRM row match rate, got {row_rate:.2f}%"


def test_04_canonical_cluster_resolution_no_hardcoding(db):
    """Test 4: Verify Computer Science (CS201) resolves canonically to 'Engg. & Tech.' (not Sciences)."""
    cs_row = db.execute(text("""
        SELECT program_code, program_name, course_cluster 
        FROM organization.course_master 
        WHERE program_code = 'CS201'
    """)).fetchone()
    assert cs_row is not None, "CS201 must exist in course_master"
    assert cs_row.course_cluster == "Engg. & Tech.", f"Expected 'Engg. & Tech.', got '{cs_row.course_cluster}'"


def test_05_performance_rankings_removes_zero_changes(db):
    """Test 5: Verify Performance Rankings excludes '+0' items from improvements and declines."""
    rankings = get_agg_performance_rankings(db, dimension="program_name")
    improvements = rankings.get("improvements", [])
    declines = rankings.get("declines", [])

    for item in improvements:
        if item.get("admission_change") is not None:
            assert item["admission_change"] > 0, f"Improvement item '{item['entity']}' has non-positive change: {item['admission_change']}"

    for item in declines:
        if item.get("admission_change") is not None:
            assert item["admission_change"] < 0, f"Decline item '{item['entity']}' has non-negative change: {item['admission_change']}"


def test_06_entity_detail_returns_program_attributes(db):
    """Test 6: Verify entity detail returns canonical program_attributes from course_master."""
    detail = get_agg_entity_detail(db, dimension="program_name", value="Bachelor of Engineering - Computer Science & Engineering")
    assert detail is not None, "Entity detail should return data"
    assert "program_attributes" in detail, "Detail must contain program_attributes"
    p_meta = detail["program_attributes"]
    if p_meta:
        assert "program_code" in p_meta
        assert "course_cluster" in p_meta
        print("Retrieved program attributes:", p_meta)


def test_07_inspect_10_real_mapped_program_codes(db):
    """Test 7: Print canonical metadata for 10 real mapped ProgramCodes."""
    cm_samples = db.execute(text("""
        SELECT program_code, program_name, course_cluster, degree_type, program_category, program_campus
        FROM organization.course_master
        WHERE program_code IN ('CS201', 'CS221', 'CS230', 'MB302', 'BB204', 'BC201', 'ME204', 'BT201', 'MB301', 'BA501')
        ORDER BY program_code
    """)).fetchall()

    print("\n--- 10 REAL MAPPED PROGRAM CODES ---")
    print(f"{'Code':<8} | {'Program Name':<45} | {'Cluster':<18} | {'Degree Type':<15} | {'Campus':<10}")
    print("-" * 105)
    for c in cm_samples:
        pname = (c.program_name[:42] + '...') if len(c.program_name) > 42 else c.program_name
        print(f"{c.program_code:<8} | {pname:<45} | {str(c.course_cluster):<18} | {str(c.degree_type):<15} | {str(c.program_campus):<10}")

    assert len(cm_samples) == 10, f"Expected 10 sample programs, retrieved {len(cm_samples)}"
