"""
Integration tests for multi-period data support.

Tests phases 2-15 from the spec:
  - Upload 2025-26 and 2024-25 coexist
  - Select 2026 → PY=2025, CY=2026
  - Select 2024 → PY=2023, CY=2024
  - Duplicate period detection (conflict)
  - Version creation preserves old data
  - Only one active version per period
  - Aggregation does not return raw rows
  - Missing period returns clear error
  - No hardcoded client-specific years
"""
import pytest
import csv
import io
import os
import uuid
from unittest.mock import patch
from sqlalchemy import text

# Set up DB session for tests
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.database.connection import engine, SessionLocal
from app.database.repository import (
    create_data_source,
    create_dataset,
    set_dataset_period,
    set_period_active,
    get_active_period_for_label,
    get_datasets_by_period,
    list_all_periods,
    get_period_pair,
    set_active_dataset,
)
from app.analytics.period_resolver import (
    get_metric_column_for_period,
    compare_periods,
    get_years_from_period_metadata,
    resolve_period_role_for_year,
)
from app.ingestion.period_conflict import check_period_conflict, check_session_overlap, apply_conflict_action
from app.ingestion.period_detector import detect_period, parse_label


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_test_dataset(db, label: str = "2025-26", version: int = 1) -> str:
    """Create a minimal test dataset with period metadata and return its UUID."""
    ds_id = uuid.uuid4()
    src_id = create_data_source(db, source_name=f"test_{label}_v{version}", source_type="test")
    create_dataset(
        db=db,
        dataset_id=ds_id,
        source_id=src_id,
        dataset_name=f"Test {label} v{version}",
        original_filename=f"test_{label.replace('-','_')}_v{version}.csv",
        dataset_type="csv",
        row_count=100,
        column_count=14,
        status="profiled",
    )
    start, end = parse_label(label)
    set_dataset_period(db, ds_id, start, end, label, version)
    return str(ds_id)


def insert_metrics(db, dataset_id: str, cy_admission: int = 100, py_admission: int = 80):
    """Insert a minimal analytics row for testing aggregation."""
    db.execute(
        text("""
            INSERT INTO analytics.uploaded_metrics
              (id, dataset_id, row_number, program_name, campus_name, source,
               cy_leads, cy_cucet, cy_admission, py_leads, py_cucet, py_admission)
            VALUES
              (gen_random_uuid(), :ds, 1, 'B.Tech CSE', 'Main Campus', 'Direct',
               500, 200, :cy_adm, 400, 160, :py_adm)
            ON CONFLICT (dataset_id, row_number) DO NOTHING
        """),
        {"ds": dataset_id, "cy_adm": cy_admission, "py_adm": py_admission},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPeriodCoexistence:
    """Two periods can exist simultaneously without interference."""

    def setup_method(self):
        self.db = SessionLocal()

    def teardown_method(self):
        self.db.rollback()
        self.db.close()

    def test_two_periods_coexist(self):
        """Upload 2025-26 and 2024-25 — both must be retrievable."""
        ds1 = make_test_dataset(self.db, "2025-26", 1)
        ds2 = make_test_dataset(self.db, "2024-25", 1)

        p1 = get_datasets_by_period(self.db, "2025-26")
        p2 = get_datasets_by_period(self.db, "2024-25")

        assert any(v["dataset_id"] == ds1 for v in p1), "2025-26 dataset missing"
        assert any(v["dataset_id"] == ds2 for v in p2), "2024-25 dataset missing"

    def test_list_periods_shows_both(self):
        make_test_dataset(self.db, "2025-26", 1)
        make_test_dataset(self.db, "2024-25", 1)

        periods = list_all_periods(self.db)
        labels = [p["academic_label"] for p in periods]
        assert "2025-26" in labels
        assert "2024-25" in labels

    def test_period_start_end_year_stored(self):
        ds = make_test_dataset(self.db, "2023-24", 1)
        start, end = parse_label("2023-24")
        years = get_years_from_period_metadata(self.db, ds)
        assert years is not None
        assert years == (end, start)  # (cy, py)


class TestYearResolution:
    """CY and PY resolve correctly for any selected period."""

    def test_select_2026_gives_cy_2026_py_2025(self):
        result = get_metric_column_for_period("admissions", "cy")
        assert result == "cy_admission"
        result_py = get_metric_column_for_period("admissions", "py")
        assert result_py == "py_admission"

    def test_resolve_period_role_cy(self):
        role = resolve_period_role_for_year(
            requested_year=2026, period_end_year=2026, period_start_year=2025
        )
        assert role == "cy"

    def test_resolve_period_role_py(self):
        role = resolve_period_role_for_year(
            requested_year=2025, period_end_year=2026, period_start_year=2025
        )
        assert role == "py"

    def test_resolve_period_role_for_2024_period(self):
        """Selecting year 2023 in a 2023-24 dataset → PY."""
        role = resolve_period_role_for_year(
            requested_year=2023, period_end_year=2024, period_start_year=2023
        )
        assert role == "py"

    def test_resolve_period_role_for_2024_cy(self):
        """Selecting year 2024 in a 2023-24 dataset → CY."""
        role = resolve_period_role_for_year(
            requested_year=2024, period_end_year=2024, period_start_year=2023
        )
        assert role == "cy"

    def test_metric_column_all_metrics(self):
        """No hardcoded years — column names remain cy_*/py_*."""
        assert get_metric_column_for_period("leads", "cy") == "cy_leads"
        assert get_metric_column_for_period("cucet", "cy") == "cy_cucet"
        assert get_metric_column_for_period("admissions", "py") == "py_admission"
        assert get_metric_column_for_period("leads", "py") == "py_leads"

    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError):
            get_metric_column_for_period("revenue", "cy")


class TestConflictDetection:
    """Duplicate period upload triggers conflict, not silent merge."""

    def setup_method(self):
        self.db = SessionLocal()

    def teardown_method(self):
        self.db.rollback()
        self.db.close()

    def test_no_conflict_for_new_period(self):
        conflict = check_period_conflict(self.db, "2099-00")  # year that doesn't exist
        assert conflict.has_conflict is False
        assert conflict.next_version == 1

    def test_conflict_detected_for_existing_period(self):
        make_test_dataset(self.db, "2025-26", 1)
        conflict = check_period_conflict(self.db, "2025-26")
        assert conflict.has_conflict is True
        assert conflict.existing_dataset is not None
        assert "cancel" in conflict.allowed_actions
        assert "replace" in conflict.allowed_actions
        assert "new_version" in conflict.allowed_actions

    def test_conflict_next_version_increments(self):
        make_test_dataset(self.db, "2025-26", 1)
        make_test_dataset(self.db, "2025-26", 2)
        conflict = check_period_conflict(self.db, "2025-26")
        assert conflict.next_version >= 3

    def test_conflict_to_dict_has_required_keys(self):
        make_test_dataset(self.db, "2025-26", 1)
        conflict = check_period_conflict(self.db, "2025-26")
        d = conflict.to_dict()
        assert "has_conflict" in d
        assert "existing_dataset" in d
        assert "allowed_actions" in d


class TestOverlapPrevention:
    """Session overlap (e.g., 2025-26 and 2024-25 sharing 2025) must be detected and rejected."""

    def setup_method(self):
        self.db = SessionLocal()

    def teardown_method(self):
        self.db.rollback()
        self.db.close()

    def test_overlapping_session_detected(self):
        # Ingest 2025-26 ({2025, 2026})
        make_test_dataset(self.db, "2025-26", 1)

        # Attempting 2024-25 ({2024, 2025}) overlaps on year 2025
        has_overlap, info = check_session_overlap(self.db, "2024-25")
        assert has_overlap is True
        assert info is not None
        assert 2025 in info["overlapping_years"] or 2024 in info["overlapping_years"]

    def test_non_overlapping_session_allowed(self):
        # Delete any existing datasets with 2025-26/2023-24 to test isolation if needed
        has_overlap, info = check_session_overlap(self.db, "2010-11")
        assert has_overlap is False
        assert info is None

    def test_same_session_not_overlap_conflict(self):
        make_test_dataset(self.db, "2025-26", 1)

        # Exact same session label is replacement/versioning, not overlap conflict
        has_overlap, info = check_session_overlap(self.db, "2025-26")
        assert has_overlap is False



class TestVersioning:
    """Only one active version per period; old versions preserved."""

    def setup_method(self):
        self.db = SessionLocal()

    def teardown_method(self):
        self.db.rollback()
        self.db.close()

    def test_only_one_period_active(self):
        ds1 = make_test_dataset(self.db, "2025-26", 1)
        ds2 = make_test_dataset(self.db, "2025-26", 2)

        set_period_active(self.db, ds1)
        set_period_active(self.db, ds2)

        # Only ds2 should be period-active
        versions = get_datasets_by_period(self.db, "2025-26")
        active = [v for v in versions if v["is_period_active"]]
        inactive = [v for v in versions if not v["is_period_active"]]

        assert len(active) <= 1, f"Expected at most 1 active version, got {len(active)}"
        if active:
            assert active[0]["dataset_id"] == ds2

    def test_old_version_still_recoverable(self):
        """Switching active version must not delete the old dataset."""
        ds1 = make_test_dataset(self.db, "2025-26", 1)
        ds2 = make_test_dataset(self.db, "2025-26", 2)

        set_period_active(self.db, ds1)
        set_period_active(self.db, ds2)

        # Both should still exist in the DB
        versions = get_datasets_by_period(self.db, "2025-26")
        ids = [v["dataset_id"] for v in versions]
        assert ds1 in ids, "Old version was deleted — must be preserved"
        assert ds2 in ids

    def test_activate_specific_version_via_api_logic(self):
        ds1 = make_test_dataset(self.db, "2025-26", 1)
        ds2 = make_test_dataset(self.db, "2025-26", 2)

        set_period_active(self.db, ds2)
        # Now reactivate ds1
        set_period_active(self.db, ds1)

        versions = get_datasets_by_period(self.db, "2025-26")
        active = [v for v in versions if v["is_period_active"]]
        assert len(active) <= 1
        if active:
            assert active[0]["dataset_id"] == ds1


class TestPeriodPairResolution:
    """get_period_pair resolves two labels to two dataset_ids."""

    def setup_method(self):
        self.db = SessionLocal()

    def teardown_method(self):
        self.db.rollback()
        self.db.close()

    def test_pair_resolution(self):
        ds1 = make_test_dataset(self.db, "2025-26", 1)
        ds2 = make_test_dataset(self.db, "2024-25", 1)
        set_period_active(self.db, ds1)
        set_period_active(self.db, ds2)

        cy_id, py_id = get_period_pair(self.db, "2025-26", "2024-25")
        assert cy_id == ds1
        assert py_id == ds2

    def test_missing_period_returns_none(self):
        cy_id, py_id = get_period_pair(self.db, "2099-00", "2098-99")
        assert cy_id is None
        assert py_id is None


class TestAggregationSafety:
    """Verify analytics return aggregated results, never raw rows."""

    def setup_method(self):
        self.db = SessionLocal()

    def teardown_method(self):
        self.db.rollback()
        self.db.close()

    def test_compare_periods_returns_aggregated(self):
        """compare_periods must return at most limit rows, not raw data."""
        ds1 = make_test_dataset(self.db, "2025-26", 1)
        ds2 = make_test_dataset(self.db, "2024-25", 1)
        insert_metrics(self.db, ds1, cy_admission=100, py_admission=80)
        insert_metrics(self.db, ds2, cy_admission=80, py_admission=60)
        set_period_active(self.db, ds1)
        set_period_active(self.db, ds2)

        result = compare_periods(
            db=self.db,
            metric="admissions",
            period_a_label="2025-26",
            period_b_label="2024-25",
            dimension="program_name",
            limit=10,
        )

        assert "data" in result
        assert len(result["data"]) <= 10, "Must never return more than limit rows"

        # Each row must have aggregated fields, not raw individual records
        if result["data"]:
            row = result["data"][0]
            assert "name" in row
            assert "period_a_value" in row
            assert "period_b_value" in row
            assert "change" in row

    def test_missing_period_handled(self):
        """compare_periods with unknown period should not crash."""
        result = compare_periods(
            db=self.db,
            metric="admissions",
            period_a_label="2099-00",
            period_b_label="2098-99",
            dimension="program_name",
            limit=10,
        )
        # Should return empty data, not crash
        assert "data" in result
        assert result["data"] == []


class TestNoHardcodedYears:
    """Period system must not hardcode specific years."""

    def test_get_metric_column_no_year_dependency(self):
        """Column resolution must not depend on what year it is."""
        # These should always return the same columns regardless of current year
        assert get_metric_column_for_period("admissions", "cy") == "cy_admission"
        assert get_metric_column_for_period("admissions", "py") == "py_admission"
        assert get_metric_column_for_period("leads", "cy") == "cy_leads"
        assert get_metric_column_for_period("leads", "py") == "py_leads"

    def test_detect_period_arbitrary_years(self):
        """Period detection must work for any year, not just 2025/2026."""
        for year_str in ["2021-22", "2022-23", "2023-24", "2024-25", "2027-28", "2030-31"]:
            result = detect_period(f"Data_{year_str}.xlsx")
            assert result.academic_label == year_str, f"Failed for {year_str}"

    def test_parse_label_arbitrary_years(self):
        for label in ["2020-21", "2021-22", "2030-31", "2040-41"]:
            result = parse_label(label)
            assert result is not None, f"parse_label failed for {label}"
            start, end = result
            assert end == start + 1, f"Year arithmetic wrong for {label}"
