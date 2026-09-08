"""
Automated Regression Test Suite — Phase 9.6: Dimension Canonicalization & Comparison UI Correction

Validates state resolver, lead_type resolver, database aggregate canonicalization,
and comparison API endpoints against baseline invariants.
"""

import pytest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.normalization.state_resolver import resolve_state, CANONICAL_INDIAN_STATES
from app.normalization.lead_type_resolver import resolve_lead_type


def test_state_resolver_units():
    """Unit tests for state resolver normalization rules."""
    # Case & Whitespace normalization
    assert resolve_state("  BIHAR  ") == "Bihar"
    assert resolve_state("bihar") == "Bihar"
    assert resolve_state("PUNJAB") == "Punjab"
    assert resolve_state("uttar pradesh") == "Uttar Pradesh"

    # Known Indian cities mapping to state
    assert resolve_state("Patna") == "Bihar"
    assert resolve_state("Ludhiana") == "Punjab"
    assert resolve_state("Mohali") == "Punjab"
    assert resolve_state("Unnao") == "Uttar Pradesh"
    assert resolve_state("Gurgaon") == "Haryana"

    # Known Foreign locations -> INTERNATIONAL
    assert resolve_state("Nepal") == "INTERNATIONAL"
    assert resolve_state("UAE") == "INTERNATIONAL"
    assert resolve_state("Dubai") == "INTERNATIONAL"
    assert resolve_state("United States") == "INTERNATIONAL"

    # Unknown / Garbage values -> UNMAPPED_STATE
    assert resolve_state("XYZ_UNKNOWN_LOC_123") == "UNMAPPED_STATE"
    assert resolve_state("") == "UNMAPPED_STATE"
    assert resolve_state(None) == "UNMAPPED_STATE"


def test_lead_type_resolver_units():
    """Unit tests for lead type business classification."""
    # IN HOUSE keywords
    assert resolve_lead_type("Direct") == "IN HOUSE"
    assert resolve_lead_type("Website") == "IN HOUSE"
    assert resolve_lead_type("Superbot Chatbot") == "IN HOUSE"
    assert resolve_lead_type("Quick Add Form") == "IN HOUSE"
    assert resolve_lead_type("Walk-in") == "IN HOUSE"

    # OUT SOURCED keywords
    assert resolve_lead_type("Twigz") == "OUT SOURCED"
    assert resolve_lead_type("Shiksha") == "OUT SOURCED"
    assert resolve_lead_type("Career360") == "OUT SOURCED"
    assert resolve_lead_type("Collegedekho Vendor") == "OUT SOURCED"

    # Unrecognized / Default -> OTHERS
    assert resolve_lead_type("Unknown Marketing Campaign") == "OTHERS"
    assert resolve_lead_type("") == "OTHERS"
    assert resolve_lead_type(None) == "OTHERS"


def test_database_dashboard_agg_canonicalization():
    """Database integration test for analytics.dashboard_agg canonicalization."""
    db = SessionLocal()
    try:
        # Check state values in dashboard_agg
        states = [r[0] for r in db.execute(text("SELECT DISTINCT state FROM analytics.dashboard_agg;")).fetchall()]
        assert len(states) > 0, "dashboard_agg has no states"

        allowed_states = set(CANONICAL_INDIAN_STATES) | {"INTERNATIONAL", "UNMAPPED_STATE"}
        invalid_states = [s for s in states if s not in allowed_states]
        assert len(invalid_states) == 0, f"Found non-canonical state values in dashboard_agg: {invalid_states}"

        # Check lead_type values in dashboard_agg
        lead_types = [r[0] for r in db.execute(text("SELECT DISTINCT lead_type FROM analytics.dashboard_agg;")).fetchall()]
        allowed_lead_types = {"IN HOUSE", "OUT SOURCED", "OTHERS"}
        invalid_lead_types = [lt for lt in lead_types if lt not in allowed_lead_types]
        assert len(invalid_lead_types) == 0, f"Found invalid lead_type values in dashboard_agg: {invalid_lead_types}"

        # Check course_cluster values in dashboard_agg
        clusters = [r[0] for r in db.execute(text("SELECT DISTINCT course_cluster FROM analytics.dashboard_agg;")).fetchall()]
        assert len(clusters) > 0, "dashboard_agg has no course_clusters"
    finally:
        db.close()


def test_dashboard_agg_totals_baseline_invariant():
    """Verify total leads and admissions in dashboard_agg remain consistent."""
    db = SessionLocal()
    try:
        tot_leads = db.execute(text("SELECT SUM(leads_cy) FROM analytics.dashboard_agg;")).scalar() or 0
        tot_admissions = db.execute(text("SELECT SUM(admission_cy) FROM analytics.dashboard_agg;")).scalar() or 0

        assert tot_leads > 0, "Total CY leads in dashboard_agg must be greater than 0"
        assert tot_admissions > 0, "Total CY admissions in dashboard_agg must be greater than 0"
    finally:
        db.close()


def test_lead_source_hierarchy_level_1_and_2():
    """Verify Lead Source Level 1 clusters and Level 2 drill-down."""
    from app.analytics.dashboard import get_hierarchy_clusters, get_hierarchy_drilldown

    db = SessionLocal()
    try:
        # Level 1 Clusters
        res_l1 = get_hierarchy_clusters(db, dimension="source")
        assert res_l1["level"] == 1
        assert len(res_l1["clusters"]) > 0

        cluster_names = [c["cluster_name"] for c in res_l1["clusters"]]
        assert "IN HOUSE" in cluster_names or "OUT SOURCED" in cluster_names or "OTHERS" in cluster_names

        # Level 2 Drill-down for IN HOUSE
        in_house_cluster = "IN HOUSE" if "IN HOUSE" in cluster_names else cluster_names[0]
        res_l2 = get_hierarchy_drilldown(db, dimension="source", cluster_name=in_house_cluster)
        assert res_l2["level"] == 2
        assert res_l2["cluster_name"] == in_house_cluster
        assert len(res_l2["items"]) > 0
        assert "item_name text" not in str(res_l2)
    finally:
        db.close()


def test_program_hierarchy_level_1_and_2():
    """Verify Academic Program Level 1 clusters and Level 2 course drill-down."""
    from app.analytics.dashboard import get_hierarchy_clusters, get_hierarchy_drilldown

    db = SessionLocal()
    try:
        # Level 1 Program Clusters
        res_l1 = get_hierarchy_clusters(db, dimension="program_name")
        assert res_l1["level"] == 1
        assert len(res_l1["clusters"]) > 0

        cluster_names = [c["cluster_name"] for c in res_l1["clusters"]]
        # Level 2 Drill-down
        first_cluster = cluster_names[0]
        res_l2 = get_hierarchy_drilldown(db, dimension="program_name", cluster_name=first_cluster)
        assert res_l2["level"] == 2
        assert res_l2["cluster_name"] == first_cluster
        assert len(res_l2["items"]) > 0
    finally:
        db.close()


def test_multi_entity_comparison_service():
    """Verify multi-entity comparison with 3+ entities and top-performer winner logic."""
    from app.analytics.dashboard import get_manual_comparison

    db = SessionLocal()
    try:
        res = get_manual_comparison(
            db,
            dimension="state",
            entities_list=["Punjab", "Uttar Pradesh", "Haryana"],
        )
        assert res is not None
        assert "entities" in res
        assert len(res["entities"]) == 3

        # Check top_performer calculation
        assert "top_performer" in res
        top_ent = res["top_performer"]["entity"]
        assert top_ent in ["Punjab", "Uttar Pradesh", "Haryana"]

        # Check is_top_performer flag on items
        winner_items = [e for e in res["entities"] if e["is_top_performer"]]
        assert len(winner_items) == 1
        assert winner_items[0]["entity"] == top_ent
    finally:
        db.close()
