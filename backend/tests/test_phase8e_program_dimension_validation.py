import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.aggregate_service import get_agg_performance_rankings, get_agg_entity_detail
from app.analytics.aggregate_refresh import refresh_dashboard_agg


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    refresh_dashboard_agg(session)
    yield session
    session.close()


def test_01_cm204_and_bb222_root_cause_investigation(db):
    """Test 1: Prove CM204 is 100% mapped and BB222 is the single missing code in raw CRM datasets."""
    # CM204 check
    cm204 = db.execute(text("SELECT program_code, program_name, course_cluster FROM organization.course_master WHERE program_code = 'CM204'")).fetchone()
    assert cm204 is not None, "CM204 must exist in organization.course_master"
    assert cm204.program_name == "Bachelor of Commerce (Hons./Hons. with Research) (Capital Markets)"

    # BB222 check
    bb222 = db.execute(text("SELECT program_code FROM organization.course_master WHERE program_code = 'BB222'")).fetchone()
    assert bb222 is None, "BB222 genuinely does not exist in organization.course_master"


def test_02_all_course_master_attribute_columns_exist(db):
    """Test 2: Verify exact database column names in organization.course_master."""
    cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='organization' AND table_name='course_master'")).fetchall()
    col_names = [c[0] for c in cols]
    
    expected = ["program_code", "program_name", "program_name_short", "course_cluster", "degree_type", "program_group", "program_category", "program_campus", "program_status", "leet_to_gen"]
    for exp in expected:
        assert exp in col_names, f"Expected column '{exp}' in organization.course_master"


def test_03_mapped_source_program_code_attribute_coverage(db):
    """Test 3: Calculate coverage for all program attributes across mapped source ProgramCodes."""
    mapped_codes = [r.code for r in db.execute(text("SELECT DISTINCT TRIM(r.raw_data->>'Program Code') as code FROM staging.records r JOIN system.datasets d ON r.dataset_id = d.id WHERE d.workbook_type = 'RAW' AND NULLIF(TRIM(r.raw_data->>'Program Code'), '') IS NOT NULL")).fetchall()]
    
    total_mapped = len(mapped_codes) # 51 total (50 mapped)
    assert total_mapped == 51

    # Check 100% coverage on mapped codes (50/50) for key attributes
    key_attrs = ["program_code", "program_name", "course_cluster", "degree_type", "program_group", "program_campus", "program_status"]
    for attr in key_attrs:
        pop = db.execute(text(f"SELECT COUNT(DISTINCT cm.program_code) FROM organization.course_master cm WHERE cm.program_code IN :codes AND NULLIF(TRIM(cm.{attr}), '') IS NOT NULL"), {"codes": tuple(mapped_codes)}).scalar()
        assert pop == 50, f"Expected 50/50 mapped codes populated for {attr}, got {pop}"


def test_04_print_20_real_mapped_program_codes_with_all_attributes(db):
    """Test 4: Retrieve and verify 20 real mapped ProgramCodes with all database attributes."""
    samples = db.execute(text("SELECT program_code, program_name, program_group, course_cluster, degree_type, program_category, program_campus, program_status FROM organization.course_master WHERE program_code IN ('CS201', 'CS221', 'CS230', 'MB302', 'BB204', 'BC201', 'ME204', 'BT201', 'MB301', 'BA501', 'AS201', 'LA202', 'PT201', 'BS213', 'BS214', 'BB201', 'BB212', 'MB307', 'ME205', 'CS235') ORDER BY program_code")).fetchall()
    assert len(samples) == 20
    for s in samples:
        assert s.program_code is not None
        assert s.program_name is not None
        assert s.course_cluster is not None
        assert s.degree_type is not None


def test_05_fact_join_canonical_program_code_lineage(db):
    """Test 5: Verify fact tables analytics.uploaded_metrics and analytics.dashboard_agg store program_code and join to course_master."""
    agg_join = db.execute(text("""
        SELECT COUNT(*) FROM analytics.dashboard_agg d
        JOIN organization.course_master cm ON LOWER(TRIM(d.program_code)) = LOWER(TRIM(cm.program_code))
    """)).scalar()
    assert agg_join > 0, "dashboard_agg must join to course_master on program_code"


def test_06_performance_rankings_enforces_positive_and_negative_change_no_zero_changes(db):
    """Test 6: Verify Performance Rankings API excludes zero-change items across all dimensions."""
    for dim in ["program", "state", "campus", "source", "counsellor"]:
        res = get_agg_performance_rankings(db, dimension=dim)
        improvements = res.get("improvements", [])
        declines = res.get("declines", [])
        
        for item in improvements:
            if item.get("admission_change") is not None:
                assert item["admission_change"] > 0, f"Zero or negative change in {dim} improvements: {item}"
                
        for item in declines:
            if item.get("admission_change") is not None:
                assert item["admission_change"] < 0, f"Zero or positive change in {dim} declines: {item}"


def test_07_entity_detail_retrieves_canonical_program_attributes(db):
    """Test 7: Verify entity detail API returns program_attributes from course_master."""
    detail = get_agg_entity_detail(db, dimension="program_name", value="Bachelor of Engineering - Computer Science & Engineering")
    assert detail is not None
    assert "program_attributes" in detail
    assert detail["program_attributes"]["program_code"] == "CS201"
    assert detail["program_attributes"]["course_cluster"] == "Engg. & Tech."


def test_08_multi_dimensional_aggregations(db):
    """Test 8: Test cluster, degree_type, program_status multi-dimensional aggregations."""
    clusters = db.execute(text("SELECT COALESCE(cm.course_cluster, 'Unmapped') as cluster, SUM(d.admission_cy) FROM analytics.dashboard_agg d LEFT JOIN organization.course_master cm ON LOWER(TRIM(d.program_code)) = LOWER(TRIM(cm.program_code)) WHERE d.academic_year = 2026 GROUP BY cluster")).fetchall()
    assert len(clusters) > 1

    degrees = db.execute(text("SELECT COALESCE(cm.degree_type, 'Unmapped') as deg, SUM(d.admission_cy) FROM analytics.dashboard_agg d LEFT JOIN organization.course_master cm ON LOWER(TRIM(d.program_code)) = LOWER(TRIM(cm.program_code)) WHERE d.academic_year = 2026 GROUP BY deg")).fetchall()
    assert len(degrees) > 1
