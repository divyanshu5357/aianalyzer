"""
Unit tests covering every canonical dimension in DIMENSION_REGISTRY.
"""

from app.semantic.dimension_registry import (
    DIMENSION_REGISTRY,
    resolve_dimension_name,
    get_dimension,
)


def test_all_16_canonical_dimensions_exist():
    expected_dimensions = [
        "source",
        "report_source",
        "main_source",
        "source_cluster",
        "lead_type",
        "state",
        "state_code",
        "zone",
        "campus",
        "academic_year",
        "owner",
        "team",
        "program_name",
        "program_code",
        "course_cluster",
        "specialization",
    ]
    for d in expected_dimensions:
        assert d in DIMENSION_REGISTRY, f"Missing canonical dimension: {d}"
        spec = get_dimension(d)
        assert spec is not None
        assert spec["canonical_name"] == d
        assert "column_name" in spec
        assert "default_null_value" in spec


def test_resolve_dimension_aliases():
    assert resolve_dimension_name("lead source") == "source"
    assert resolve_dimension_name("reporting source") == "report_source"
    assert resolve_dimension_name("origin") == "main_source"
    assert resolve_dimension_name("channel cluster") == "source_cluster"
    assert resolve_dimension_name("prospect stage") == "lead_type"
    assert resolve_dimension_name("state group") == "state"
    assert resolve_dimension_name("territory") == "zone"
    assert resolve_dimension_name("location") == "campus"
    assert resolve_dimension_name("session year") == "academic_year"
    assert resolve_dimension_name("counsellor") == "owner"
    assert resolve_dimension_name("course") == "program_name"
    assert resolve_dimension_name("department") == "course_cluster"
    assert resolve_dimension_name("stream") == "specialization"


def test_dimension_master_table_mappings():
    assert DIMENSION_REGISTRY["source"]["master_table"] == "organization.source_master"
    assert DIMENSION_REGISTRY["state"]["master_table"] == "organization.state_master"
    assert DIMENSION_REGISTRY["owner"]["master_table"] == "organization.employee_master"
    assert DIMENSION_REGISTRY["program_name"]["master_table"] == "organization.course_master"
