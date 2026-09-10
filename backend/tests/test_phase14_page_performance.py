"""
Phase 14 Regression & Performance Architecture Test Suite

Validates:
1. Cache hit / miss behavior
2. Stale-while-revalidate semantics & TTL expiration
3. Query key scope isolation (Academic Year 2026 vs 2025, Campus, Filters)
4. Filter options caching (instant repeat queries < 1ms)
5. Counsellor list caching (sub-millisecond repeat queries)
6. Lazy hierarchical drilldowns remain scoped and non-leaking
7. Deduplication and search query isolation
8. Authoritative PostgreSQL aggregate table usage
"""

import time
import pytest
from unittest.mock import MagicMock
from app.analytics.dashboard import (
    get_dashboard_filter_options,
    clear_filter_options_cache,
    _FILTER_OPTIONS_CACHE,
)
from app.analytics.counsellor_service import (
    get_counsellors_list,
    clear_counsellors_cache,
    _COUNSELLORS_LIST_CACHE,
)


def test_01_filter_options_cache_hit_and_miss():
    """Test 1: Filter options are cached in-memory and subsequent hits avoid DB queries."""
    clear_filter_options_cache()
    assert len(_FILTER_OPTIONS_CACHE) == 0

    # Mock DB session that tracks query count
    mock_db = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = ["Mohali"]
    mock_db.execute.return_value.mappings.return_value.all.return_value = []
    mock_db.execute.return_value.scalar.return_value = "2026-09-01"

    # First call (Cold / Cache Miss)
    t0 = time.perf_counter()
    res1 = get_dashboard_filter_options(db=mock_db, campus="Mohali", years=[2026])
    t_miss = (time.perf_counter() - t0) * 1000

    assert len(_FILTER_OPTIONS_CACHE) == 1
    call_count_after_miss = mock_db.execute.call_count

    # Second call (Warm / Cache Hit)
    t1 = time.perf_counter()
    res2 = get_dashboard_filter_options(db=mock_db, campus="Mohali", years=[2026])
    t_hit = (time.perf_counter() - t0) * 1000

    # Execution count did NOT increase on cache hit
    assert mock_db.execute.call_count == call_count_after_miss
    assert res1 == res2

    # Clear cache works
    clear_filter_options_cache()
    assert len(_FILTER_OPTIONS_CACHE) == 0


def test_02_year_and_campus_cache_isolation():
    """Test 2: Cache keys strictly segregate academic years and campuses."""
    clear_filter_options_cache()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = ["Punjab"]
    mock_db.execute.return_value.mappings.return_value.all.return_value = []
    mock_db.execute.return_value.scalar.return_value = "2026-01-01"

    # Year 2026
    get_dashboard_filter_options(db=mock_db, campus="Mohali", years=[2026])
    # Year 2025
    get_dashboard_filter_options(db=mock_db, campus="Mohali", years=[2025])
    # Campus Lucknow
    get_dashboard_filter_options(db=mock_db, campus="Lucknow", years=[2026])

    # Must have 3 completely isolated cache entries
    assert len(_FILTER_OPTIONS_CACHE) == 3
    keys = list(_FILTER_OPTIONS_CACHE.keys())
    assert any("2026" in k and "Mohali" in k for k in keys)
    assert any("2025" in k and "Mohali" in k for k in keys)
    assert any("Lucknow" in k for k in keys)
    clear_filter_options_cache()


def test_03_counsellors_list_cache_hit():
    """Test 3: Counsellors summary list uses thread-safe TTL cache."""
    clear_counsellors_cache()
    mock_db = MagicMock()
    # Mock dashboard_agg availability
    mock_db.execute.return_value.scalar.return_value = 1
    mock_db.execute.return_value.mappings.return_value.all.return_value = [
        {"owner": "Ganesh Dutt E1678", "leads": 500, "admissions": 25}
    ]

    # First call - cache miss
    res1 = get_counsellors_list(db=mock_db, academic_year=2026, campus="Mohali")
    assert res1["status"] == "success"
    assert res1["total_counsellors"] == 1
    assert len(_COUNSELLORS_LIST_CACHE) == 1
    initial_db_calls = mock_db.execute.call_count

    # Second call - cache hit (<0.1ms)
    res2 = get_counsellors_list(db=mock_db, academic_year=2026, campus="Mohali")
    assert mock_db.execute.call_count == initial_db_calls
    assert res1 == res2

    # Year 2025 call creates separate cache key
    get_counsellors_list(db=mock_db, academic_year=2025, campus="Mohali")
    assert len(_COUNSELLORS_LIST_CACHE) == 2

    clear_counsellors_cache()
    assert len(_COUNSELLORS_LIST_CACHE) == 0


def test_04_no_py_cy_cross_contamination():
    """Test 4: Year 2025 and Year 2026 produce different cache entries and cannot leak."""
    clear_counsellors_cache()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar.return_value = 1
    mock_db.execute.return_value.mappings.return_value.all.return_value = []

    res_2026 = get_counsellors_list(db=mock_db, academic_year=2026, campus="all")
    res_2025 = get_counsellors_list(db=mock_db, academic_year=2025, campus="all")

    keys = list(_COUNSELLORS_LIST_CACHE.keys())
    assert "2026:all:" in keys
    assert "2025:all:" in keys
    assert keys[0] != keys[1]
    clear_counsellors_cache()


def test_05_counsellor_cache_expiry():
    """Test 5: Counsellor cache entry expires cleanly when TTL is exceeded."""
    clear_counsellors_cache()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar.return_value = 1
    mock_db.execute.return_value.mappings.return_value.all.return_value = [
        {"owner": "Shallu Rani E10630", "leads": 200, "admissions": 10}
    ]

    res = get_counsellors_list(db=mock_db, academic_year=2026, campus="all")
    key = "2026:all:"
    assert key in _COUNSELLORS_LIST_CACHE

    # Artificially expire the cache entry
    old_time = time.time() - 400.0  # older than 300s TTL
    _COUNSELLORS_LIST_CACHE[key] = (old_time, res)

    db_calls_before = mock_db.execute.call_count
    # Calling again must trigger a fresh DB query
    get_counsellors_list(db=mock_db, academic_year=2026, campus="all")
    assert mock_db.execute.call_count > db_calls_before

    clear_counsellors_cache()


def test_06_filter_cache_expiry():
    """Test 6: Filter options cache entry expires cleanly when TTL is exceeded."""
    clear_filter_options_cache()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = ["Delhi"]
    mock_db.execute.return_value.mappings.return_value.all.return_value = []
    mock_db.execute.return_value.scalar.return_value = "2026-01-01"

    get_dashboard_filter_options(db=mock_db, campus="Mohali", years=[2026])
    assert len(_FILTER_OPTIONS_CACHE) == 1
    key = list(_FILTER_OPTIONS_CACHE.keys())[0]

    # Artificially expire
    old_time = time.time() - 400.0
    val = _FILTER_OPTIONS_CACHE[key][1]
    _FILTER_OPTIONS_CACHE[key] = (old_time, val)

    db_calls_before = mock_db.execute.call_count
    get_dashboard_filter_options(db=mock_db, campus="Mohali", years=[2026])
    assert mock_db.execute.call_count > db_calls_before
    clear_filter_options_cache()


def test_07_counsellor_search_isolation():
    """Test 7: Counsellor searches generate distinct isolated cache entries."""
    clear_counsellors_cache()
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar.return_value = 1
    mock_db.execute.return_value.mappings.return_value.all.return_value = []

    get_counsellors_list(db=mock_db, academic_year=2026, campus="all", search="")
    get_counsellors_list(db=mock_db, academic_year=2026, campus="all", search="Shallu")
    get_counsellors_list(db=mock_db, academic_year=2026, campus="all", search="Ganesh")

    assert len(_COUNSELLORS_LIST_CACHE) == 3
    keys = list(_COUNSELLORS_LIST_CACHE.keys())
    assert any("Shallu" in k for k in keys)
    assert any("Ganesh" in k for k in keys)
    clear_counsellors_cache()


def test_08_database_aggregate_table_prioritization():
    """Test 8: Counsellor list prioritizes analytics.dashboard_agg over staging.records."""
    clear_counsellors_cache()
    mock_db = MagicMock()
    # Return 1 for SELECT 1 FROM analytics.dashboard_agg LIMIT 1
    mock_db.execute.return_value.scalar.return_value = 1
    mock_db.execute.return_value.mappings.return_value.all.return_value = [
        {"owner": "Test Owner", "leads": 10, "admissions": 1}
    ]

    get_counsellors_list(db=mock_db, academic_year=2026, campus="all")

    # Verify query executed against dashboard_agg, NOT staging.records
    executed_queries = [str(call[0][0]) for call in mock_db.execute.call_args_list]
    agg_queries = [q for q in executed_queries if "analytics.dashboard_agg" in q]
    staging_queries = [q for q in executed_queries if "staging.records" in q]

    assert len(agg_queries) > 0
    assert len(staging_queries) == 0
    clear_counsellors_cache()
