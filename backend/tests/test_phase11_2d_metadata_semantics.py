"""
Phase 11.2D — Dataset Metadata Semantics & Active Dataset Context Tests
"""
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.database.repository import (
    get_active_dataset,
    get_active_dataset_info,
    resolve_raw_dataset,
    resolve_target_dataset,
    resolve_dimension_dataset,
)
from app.agent.agent_service import answer_question
from app.analytics.target_service import get_target_performance


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_01_raw_2025_resolution(db: Session):
    """Verify RAW 2025 dataset resolves to 2025."""
    ds_id, cy_yr, py_yr = resolve_raw_dataset(db, target_year=2025)
    assert ds_id == "89281e52-5794-40ae-ab75-3c39239c821b"
    assert cy_yr == 2025
    assert py_yr == 2024


def test_02_raw_2026_resolution(db: Session):
    """Verify RAW 2026 dataset resolves to 2026."""
    ds_id, cy_yr, py_yr = resolve_raw_dataset(db, target_year=2026)
    assert ds_id == "47aa37e1-9949-4a01-a3e4-b33b7df93b1c"
    assert cy_yr == 2026
    assert py_yr == 2025


def test_03_dimension_not_treated_as_raw(db: Session):
    """Verify Dimension dataset is never selected as RAW dataset."""
    ds_id, cy_yr, py_yr = resolve_raw_dataset(db)
    wb_type = db.execute(
        text("SELECT workbook_type FROM system.datasets WHERE id = :id"),
        {"id": str(ds_id)}
    ).scalar()
    assert wb_type == "RAW"
    assert ds_id != "3cdf4cd5-83e0-4e05-b574-d94065b3859d"


def test_04_target_not_treated_as_raw(db: Session):
    """Verify Target dataset is never selected as RAW dataset."""
    ds_id, cy_yr, py_yr = resolve_raw_dataset(db)
    wb_type = db.execute(
        text("SELECT workbook_type FROM system.datasets WHERE id = :id"),
        {"id": str(ds_id)}
    ).scalar()
    assert wb_type == "RAW"
    assert ds_id != "0a991108-876e-42b2-8978-5e5ea2049a14"


def test_05_target_year_from_row_dates(db: Session):
    """Verify target year is determined from target row dates."""
    res = get_target_performance(db, target_for="Leads", campus="Mohali", start_date="2025-10-07", end_date="2026-07-28")
    assert res["target"] > 0
    assert res["target_for"] == "Leads"


def test_06_target_campus_from_row_values(db: Session):
    """Verify target campus is determined from target row values."""
    res_mohali = get_target_performance(db, target_for="Leads", campus="Mohali", month="August")
    assert res_mohali["target"] == 66715.31

    res_unnao = get_target_performance(db, target_for="Leads", campus="Unnao", month="August")
    assert res_unnao.get("target") == 0.0 or res_unnao.get("success") is True


def test_07_dimension_serves_multiple_raw_years(db: Session):
    """Verify Dimension tables serve both 2025 and 2026 RAW datasets."""
    dim_id = resolve_dimension_dataset(db)
    assert dim_id == "3cdf4cd5-83e0-4e05-b574-d94065b3859d"
    
    # Query Source_ms for 2025 RAW
    res2025 = answer_question(db, "Compare inhouse vs outsource leads", conversation_id="test_dim_2025")
    assert "In House" in res2025.get("answer", "") or "Inhouse" in res2025.get("answer", "")

    # Query Source_ms for 2026 RAW
    res2026 = answer_question(db, "Compare inhouse vs outsource leads in 2026", conversation_id="test_dim_2026")
    assert "In House" in res2026.get("answer", "") or "Inhouse" in res2026.get("answer", "")


def test_08_explicit_year_overrides_previous_year(db: Session):
    """Verify explicit year in query overrides previous conversation year."""
    cid = "test_year_override"
    res1 = answer_question(db, "How many admissions happened in 2025?", conversation_id=cid)
    assert res1.get("debug", {}).get("dataset_id") == "89281e52-5794-40ae-ab75-3c39239c821b"

    res2 = answer_question(db, "How many admissions happened in 2026?", conversation_id=cid)
    assert res2.get("debug", {}).get("dataset_id") == "47aa37e1-9949-4a01-a3e4-b33b7df93b1c"


def test_09_target_queries_do_not_select_raw(db: Session):
    """Verify target resolver explicitly selects TARGET dataset."""
    target_id = resolve_target_dataset(db)
    wb_type = db.execute(
        text("SELECT workbook_type FROM system.datasets WHERE id = :id"),
        {"id": str(target_id)}
    ).scalar()
    assert wb_type == "TARGET"


def test_10_actual_queries_do_not_select_target_or_dimension(db: Session):
    """Verify actual queries explicitly select RAW dataset."""
    active_info = get_active_dataset_info(db)
    assert active_info is not None
    wb_type = db.execute(
        text("SELECT workbook_type FROM system.datasets WHERE id = :id"),
        {"id": str(active_info["id"])}
    ).scalar()
    assert wb_type == "RAW"
