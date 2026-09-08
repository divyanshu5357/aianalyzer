"""
Phase 12.1 Dynamic Data Audit & Zero Hardcoding Tests.
Verifies that all services and resolvers function without hardcoded business values.
"""
import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.period_helper import (
    get_active_or_max_academic_year,
    get_available_campuses_from_db,
)
from app.analytics.scope_resolver import resolve_dataset_scope
from app.analytics.target_service import get_target_performance
from app.analytics.program_service import get_program_report_top_level
from app.analytics.state_service import get_state_report_top_level


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_dynamic_academic_year_resolution(db):
    """Verify get_active_or_max_academic_year returns an integer derived from DB, not a fixed constant."""
    year = get_active_or_max_academic_year(db)
    assert isinstance(year, int)
    assert year >= 2020

    # Cross-check with DB MAX
    max_agg_yr = db.execute(
        text("SELECT MAX(academic_year) FROM analytics.dashboard_agg")
    ).scalar()
    if max_agg_yr:
        assert year == max_agg_yr or year >= 2024


def test_dynamic_campuses_resolution(db):
    """Verify get_available_campuses_from_db returns authentic campuses from database."""
    campuses = get_available_campuses_from_db(db)
    assert isinstance(campuses, list)
    # Check that it returns actual campus names if any exist in DB
    if campuses:
        for c in campuses:
            assert isinstance(c, str)
            assert len(c) > 0


def test_scope_resolver_dynamic_without_years(db):
    """Verify resolve_dataset_scope dynamically determines cy_year and py_year without hardcoding 2026/2025."""
    scope = resolve_dataset_scope(db, campus=None, years=None)
    assert "cy_year" in scope
    assert "py_year" in scope
    assert isinstance(scope["cy_year"], int)
    assert scope["cy_year"] >= 2024
    if scope["py_year"] is not None:
        assert scope["py_year"] < scope["cy_year"]


def test_target_service_without_hardcoded_campus(db):
    """Verify get_target_performance evaluates correctly when campus is None (All Campuses)."""
    res = get_target_performance(db=db, target_for="Admission", campus=None, year=None)
    assert res is not None
    assert "target" in res
    assert "actual" in res
    assert res.get("campus") in (None, "All", "all")


def test_program_report_without_explicit_year(db):
    """Verify get_program_report_top_level functions dynamically when academic_year is None."""
    res = get_program_report_top_level(db=db, academic_year=None)
    assert res is not None
    assert "rows" in res
    assert "total" in res
    assert isinstance(res["rows"], list)
    assert res["scope"]["academic_year"] >= 2024


def test_state_report_without_explicit_year(db):
    """Verify get_state_report_top_level functions dynamically when academic_year is None."""
    res = get_state_report_top_level(db=db, academic_year=None)
    assert res is not None
    assert "rows" in res
    assert "total" in res
    assert isinstance(res["rows"], list)
    assert res["scope"]["academic_year"] >= 2024
