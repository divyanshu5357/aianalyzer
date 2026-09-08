"""
Integration tests verifying Agent Intent Parser alignment with Canonical Semantic Layer.
"""

from app.agent.intent_parser import METRIC_ALIASES, DIMENSION_ALIASES
from app.semantic.metric_registry import resolve_metric_name
from app.semantic.dimension_registry import resolve_dimension_name


def test_agent_intent_parser_metric_alignment():
    test_queries = [
        ("admissions", "admission"),
        ("leads", "leads"),
        ("cucet", "cucet"),
        ("gross admissions", "gross_admission"),
        ("refunded", "refunded"),
        ("lead to cucet", "lead_cucet_rate"),
        ("lead admission rate", "lead_admission_rate"),
        ("conversion rate", "conversion_rate"),
    ]
    for raw, expected in test_queries:
        assert resolve_metric_name(raw) == expected, f"Failed for {raw}"


def test_agent_intent_parser_dimension_alignment():
    test_dims = [
        ("counselor", "owner"),
        ("course", "program_name"),
        ("campus", "campus"),
        ("state", "state"),
        ("origin", "main_source"),
        ("course cluster", "course_cluster"),
    ]
    for raw, expected in test_dims:
        assert resolve_dimension_name(raw) == expected, f"Failed for {raw}"
