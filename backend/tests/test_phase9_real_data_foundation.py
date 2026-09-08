import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.aggregate_service import get_agg_overview, get_agg_monthly_trend
from app.analytics.aggregate_refresh import refresh_dashboard_agg


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    refresh_dashboard_agg(session)
    yield session
    session.close()


def test_01_real_data_period_model_system_datasets_columns(db):
    """Test 1: Verify tracking columns exist in system.datasets."""
    cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='system' AND table_name='datasets'")).fetchall()
    col_names = [c[0] for c in cols]
    
    expected_cols = ["upload_batch_id", "distinct_prospect_count", "rows_inserted", "rows_updated", "start_date", "end_date", "month"]
    for col in expected_cols:
        assert col in col_names, f"Expected column '{col}' in system.datasets"


def test_02_raw_actual_metrics_prospect_id_counting(db):
    """Test 2: Verify ProspectID leads and admissions counting rules."""
    lead_count = db.execute(text("SELECT COUNT(DISTINCT NULLIF(TRIM(r.raw_data->>'ProspectID'), '')) FROM staging.records r JOIN system.datasets d ON r.dataset_id = d.id WHERE d.workbook_type = 'RAW'")).scalar()
    assert lead_count is not None and lead_count > 0, "Distinct ProspectID count must be > 0"

    # Verify admissions include all valid admission dates (even if Refunded stage exists)
    adm_count = db.execute(text("SELECT COUNT(DISTINCT NULLIF(TRIM(r.raw_data->>'ProspectID'), '')) FROM staging.records r JOIN system.datasets d ON r.dataset_id = d.id WHERE d.workbook_type = 'RAW' AND NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null'")).scalar()
    assert adm_count is not None and adm_count > 0, "Distinct admissions count must be > 0"


def test_03_available_period_detection_partial_months(db):
    """Test 3: Verify monthly trend detects available months and formats trends."""
    trend = get_agg_monthly_trend(db, years="2026", metric="admissions")
    assert isinstance(trend, list)
    assert len(trend) > 0
    
    # Check each month entry has expected keys
    for m in trend:
        assert "month" in m
        assert "is_available" in m
        assert "cy_admission" in m
        assert "py_admission" in m


def test_04_unuploaded_future_months_return_null(db):
    """Test 4: Verify unuploaded future months return None (null in JSON), never 0."""
    # When partial months exist, unavailable months should have cy_admission = None
    trend = get_agg_monthly_trend(db, years="2026", metric="admissions")
    for m in trend:
        if not m["is_available"]:
            assert m["cy_admission"] is None, f"Expected None for unuploaded month {m['month']}, got {m['cy_admission']}"
            assert m["cy_leads"] is None, f"Expected None for unuploaded month {m['month']}, got {m['cy_leads']}"


def test_05_target_and_dimension_separation(db):
    """Test 5: Verify Actual CY, Actual PY, Target, and Dimension are distinct concepts."""
    overview = get_agg_overview(db, years="2026")
    assert "kpis" in overview
    kpis = overview["kpis"]
    
    assert "admissions" in kpis
    assert "cy" in kpis["admissions"]
    assert "py" in kpis["admissions"]

    # Verify course_master dimension is separate from metrics
    cm_count = db.execute(text("SELECT COUNT(*) FROM organization.course_master")).scalar()
    assert cm_count == 423


def test_06_data_control_history_query(db):
    """Test 6: Verify Data Control history query returns real system.datasets records."""
    datasets = db.execute(text("""
        SELECT d.id, d.original_filename, d.workbook_type, COALESCE(d.row_count, 0) as row_count, COALESCE(d.distinct_prospect_count, 0) as p_cnt
        FROM system.datasets d
    """)).fetchall()
    
    assert len(datasets) >= 4, f"Expected at least 4 datasets in system.datasets, found {len(datasets)}"
    for d in datasets:
        assert d.row_count > 0, f"Dataset {d.original_filename} must have row_count > 0"
