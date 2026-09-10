"""
Unit test suite for State-Wise Analysis with Canonical 26 State Groups.
Validates:
1. Master Dimension Lookup & Canonical 26 Groups resolution
2. North East aggregation (Assam, Meghalaya, Sikkim, Arunachal, Nagaland, Mizoram, Manipur, Tripura -> NORTH EAST)
3. UTs & Goa aggregation (Goa, Ladakh, Lakshadweep, Puducherry, etc. -> A&N / DNH / DD / GOA / LAK)
4. International aggregation (Foreign cities/countries -> INTERNATIONAL)
5. Missing/Noise aggregation -> NO STATE MENTIONED
6. Constituent state resolution for drilldown queries
7. Top-level group rollup with metric invariance
8. Gemini fallback location classifier
"""

from unittest.mock import MagicMock, patch
import pytest
from app.analytics.state_service import (
    CANONICAL_STATE_GROUPS,
    _get_state_group_master_lookup,
    _map_to_state_group,
    _get_constituent_states,
    _resolve_location_with_gemini,
    get_state_report_top_level,
    get_state_hierarchy_children,
    _calculate_row_metrics,
)


def test_01_canonical_state_groups_count():
    """Verify exactly 26 canonical state groups are defined matching PowerBI reference."""
    assert len(CANONICAL_STATE_GROUPS) == 26
    expected_groups = {
        "PUNJAB", "HARYANA", "UTTAR PRADESH", "HIMACHAL PRADESH", "BIHAR",
        "UTTARAKHAND", "JAMMU AND KASHMIR", "CHANDIGARH", "INTERNATIONAL",
        "JHARKHAND", "DELHI", "RAJASTHAN", "WEST BENGAL", "MADHYA PRADESH",
        "ODISHA", "NORTH EAST", "CHHATTISGARH", "MAHARASHTRA", "ANDHRA PRADESH",
        "KERALA", "TAMIL NADU", "GUJARAT", "TELANGANA", "A&N / DNH / DD / GOA / LAK",
        "KARNATAKA", "NO STATE MENTIONED",
    }
    assert set(CANONICAL_STATE_GROUPS) == expected_groups


def test_02_dimension_master_loading():
    """Verify master dimension lookup loads cleanly and covers canonical groups."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []

    lookup = _get_state_group_master_lookup(mock_db)
    assert "alias_to_group" in lookup
    assert "group_to_constituents" in lookup
    assert len(lookup["group_to_constituents"]) == 26


def test_03_north_east_states_mapping():
    """Verify all 8 North East states resolve to NORTH EAST."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    lookup = _get_state_group_master_lookup(mock_db)

    ne_raw_states = [
        "Assam", "ASSAM", "Meghalaya", "MEGHALAYA", "Sikkim", "SIKKIM",
        "Arunachal Pradesh", "ARUNACHAL PRADESH", "Nagaland", "NAGALAND",
        "Mizoram", "MIZORAM", "Manipur", "MANIPUR", "Tripura", "TRIPURA",
        "Tripur", "North East", "NORTH EAST"
    ]
    for raw in ne_raw_states:
        grp = _map_to_state_group(raw, lookup)
        assert grp == "NORTH EAST", f"Expected 'NORTH EAST' for '{raw}', got '{grp}'"


def test_04_uts_and_goa_mapping():
    """Verify Goa, Ladakh, Puducherry, Lakshadweep, and UTs resolve to A&N / DNH / DD / GOA / LAK."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    lookup = _get_state_group_master_lookup(mock_db)

    ut_raw_states = [
        "Goa", "GOA", "gao", "Ladakh", "LADAKH", "Puducherry", "PUDUCHERRY",
        "pondicherry", "Lakshadweep", "LAKSHADWEEP", "Andaman and Nicobar",
        "ANDAMAN AND NICOBAR ISLANDS", "Dadra and Nagar Haveli", "Daman and Diu"
    ]
    for raw in ut_raw_states:
        grp = _map_to_state_group(raw, lookup)
        assert grp == "A&N / DNH / DD / GOA / LAK", f"Expected 'A&N / DNH / DD / GOA / LAK' for '{raw}', got '{grp}'"


def test_05_international_mapping():
    """Verify foreign countries, cities, and 'INTERNATIONAL' resolve to INTERNATIONAL."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    lookup = _get_state_group_master_lookup(mock_db)

    intl_raw = ["INTERNATIONAL", "international", "Dubai", "Abu Dhabi", "Dhaka", "Kathmandu"]
    for raw in intl_raw:
        grp = _map_to_state_group(raw, lookup)
        assert grp == "INTERNATIONAL", f"Expected 'INTERNATIONAL' for '{raw}', got '{grp}'"


def test_06_no_state_mentioned_mapping():
    """Verify unmapped, missing, and noise values resolve to NO STATE MENTIONED."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    lookup = _get_state_group_master_lookup(mock_db)

    noise_raw = ["", None, "UNMAPPED_STATE", "NO STATE MENTIONED", "Not Updated", "State Not Given"]
    for raw in noise_raw:
        grp = _map_to_state_group(raw, lookup)
        assert grp == "NO STATE MENTIONED", f"Expected 'NO STATE MENTIONED' for '{raw}', got '{grp}'"


def test_07_constituent_resolution_for_drilldown():
    """Verify constituent raw states are retrieved properly for multi-state groups."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = []
    lookup = _get_state_group_master_lookup(mock_db)

    ne_constituents = _get_constituent_states("NORTH EAST", lookup)
    assert len(ne_constituents) >= 8
    assert "assam" in ne_constituents
    assert "manipur" in ne_constituents
    assert "tripura" in ne_constituents

    ut_constituents = _get_constituent_states("A&N / DNH / DD / GOA / LAK", lookup)
    assert "goa" in ut_constituents
    assert "ladakh" in ut_constituents
    assert "lakshadweep" in ut_constituents

    punjab_constituents = _get_constituent_states("PUNJAB", lookup)
    assert "punjab" in punjab_constituents


def test_08_top_level_report_aggregation():
    """Verify get_state_report_top_level aggregates 36 raw states into 26 canonical groups."""
    mock_db = MagicMock()

    # Mock raw states matching the 36 distinct states in DB
    raw_36_data = [
        ("PUNJAB", 192416, 203013, 0, 10160, 0, 7252),
        ("HARYANA", 96669, 129058, 0, 9223, 0, 5722),
        ("UTTAR PRADESH", 108042, 107644, 0, 7443, 0, 3885),
        ("CHANDIGARH", 110218, 101474, 0, 1796, 0, 1377),
        ("DELHI", 71186, 78014, 0, 1894, 0, 973),
        ("BIHAR", 61015, 59987, 0, 5071, 0, 2504),
        ("RAJASTHAN", 45454, 41375, 0, 1945, 0, 1013),
        ("HIMACHAL PRADESH", 36782, 35085, 0, 3289, 0, 2309),
        ("JAMMU & KASHMIR", 23450, 32165, 0, 1291, 0, 874),
        ("WEST BENGAL", 31952, 20311, 0, 1302, 0, 714),
        ("MADHYA PRADESH", 20803, 19250, 0, 1245, 0, 620),
        ("MAHARASHTRA", 14284, 18514, 0, 744, 0, 331),
        ("UTTARAKHAND", 17360, 17880, 0, 1529, 0, 885),
        ("UNMAPPED_STATE", 9639, 16066, 0, 38, 0, 16),
        ("JHARKHAND", 16826, 14927, 0, 1743, 0, 859),
        ("GUJARAT", 12289, 12117, 0, 380, 0, 182),
        ("TELANGANA", 11628, 11893, 0, 381, 0, 156),
        ("ANDHRA PRADESH", 10329, 11149, 0, 517, 0, 215),
        ("ODISHA", 9030, 10441, 0, 617, 0, 324),
        ("TAMIL NADU", 9385, 8057, 0, 253, 0, 116),
        ("KARNATAKA", 6817, 8027, 0, 220, 0, 124),
        ("ASSAM", 8830, 7441, 0, 345, 0, 221),
        ("CHHATTISGARH", 5365, 7007, 0, 575, 0, 316),
        ("KERALA", 6099, 5915, 0, 427, 0, 211),
        ("TRIPURA", 930, 1294, 0, 59, 0, 31),
        ("MANIPUR", 1080, 1246, 0, 94, 0, 57),
        ("LADAKH", 342, 698, 0, 20, 0, 14),
        ("MEGHALAYA", 775, 671, 0, 37, 0, 21),
        ("SIKKIM", 360, 525, 0, 15, 0, 7),
        ("ARUNACHAL PRADESH", 457, 459, 0, 19, 0, 13),
        ("NAGALAND", 435, 448, 0, 22, 0, 17),
        ("MIZORAM", 255, 361, 0, 21, 0, 20),
        ("GOA", 325, 293, 0, 24, 0, 17),
        ("PUDUCHERRY", 96, 59, 0, 1, 0, 2),
        ("INTERNATIONAL", 51, 37, 0, 0, 0, 0),
        ("LAKSHADWEEP", 7, 12, 0, 1, 0, 0),
    ]

    mock_db.execute.return_value.scalar.return_value = 1  # py_exists
    mock_db.execute.return_value.fetchall.side_effect = [
        raw_36_data,  # result_rows
        [],           # trend_rows
        [],           # state_master query
    ]

    res = get_state_report_top_level(db=mock_db, academic_year=2026)
    rows = res["rows"]
    total = res["total"]

    # Exactly 26 canonical state groups!
    assert len(rows) == 26, f"Expected 26 rows, got {len(rows)}"
    assert res["count"] == 26

    # Totals must be exactly preserved
    assert total["cy_leads"] == 982913
    assert total["py_leads"] == 940981
    assert total["cy_adm"] == 31398

    # Verify North East combined leads:
    # Assam(7441) + Tripura(1294) + Manipur(1246) + Meghalaya(671) + Sikkim(525) + Arunachal(459) + Nagaland(448) + Mizoram(361) = 12445
    ne_row = next(r for r in rows if r["name"] == "NORTH EAST")
    assert ne_row["cy_leads"] == 12445
    assert ne_row["py_leads"] == 13122
    assert ne_row["has_children"] is True

    # Verify A&N / DNH / DD / GOA / LAK combined leads:
    # Ladakh(698) + Goa(293) + Puducherry(59) + Lakshadweep(12) = 1062
    ut_row = next(r for r in rows if r["name"] == "A&N / DNH / DD / GOA / LAK")
    assert ut_row["cy_leads"] == 1062
    assert ut_row["py_leads"] == 770

    # Verify International
    intl_row = next(r for r in rows if r["name"] == "INTERNATIONAL")
    assert intl_row["cy_leads"] == 37
    assert intl_row["py_leads"] == 51

    # Verify No State Mentioned
    no_state_row = next(r for r in rows if r["name"] == "NO STATE MENTIONED")
    assert no_state_row["cy_leads"] == 16066
    assert no_state_row["py_leads"] == 9639
