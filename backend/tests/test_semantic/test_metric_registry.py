"""
Unit tests covering every canonical metric in METRIC_REGISTRY.
"""

from app.semantic.metric_registry import (
    METRIC_REGISTRY,
    resolve_metric_name,
    get_metric,
    calculate_ratio,
)


def test_all_canonical_metrics_exist():
    expected_metrics = [
        "leads",
        "cucet",
        "admission",
        "gross_admission",
        "refunded",
        "lead_cucet_rate",
        "lead_admission_rate",
        "cucet_admission_rate",
        "conversion_rate",
    ]
    for m in expected_metrics:
        assert m in METRIC_REGISTRY, f"Missing canonical metric: {m}"
        spec = get_metric(m)
        assert spec is not None
        assert spec["canonical_name"] == m
        assert "sql_expression" in spec


def test_metric_additivity_properties():
    additive_metrics = ["leads", "cucet", "admission", "gross_admission", "refunded"]
    ratio_metrics = ["lead_cucet_rate", "lead_admission_rate", "cucet_admission_rate", "conversion_rate"]

    for m in additive_metrics:
        spec = get_metric(m)
        assert spec["is_additive"] is True
        assert spec["can_sum"] is True
        assert spec["is_ratio"] is False

    for m in ratio_metrics:
        spec = get_metric(m)
        assert spec["is_additive"] is False
        assert spec["can_sum"] is False
        assert spec["is_ratio"] is True


def test_resolve_metric_synonyms():
    assert resolve_metric_name("total leads") == "leads"
    assert resolve_metric_name("cucet registration") == "cucet"
    assert resolve_metric_name("admissions") == "admission"
    assert resolve_metric_name("gross admissions") == "gross_admission"
    assert resolve_metric_name("refunds") == "refunded"
    assert resolve_metric_name("conversion rate") == "conversion_rate"
    assert resolve_metric_name("lead to cucet") == "lead_cucet_rate"


def test_calculate_ratio_division_by_zero():
    assert calculate_ratio(50, 100) == 50.0
    assert round(calculate_ratio(22546, 974328), 3) == 2.314
    assert calculate_ratio(10, 0) == 0.0
    assert calculate_ratio(0, 0) == 0.0


def pytest_approx(val, tol):
    return val
