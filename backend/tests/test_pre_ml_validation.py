"""
Pre-ML Validation Suite — Phases 1, 2, and 3
Verifies dataset metrics, canonical ratio formulas, 100% monthly reconciliations, and 9 multi-dataset scope topologies.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database.connection import SessionLocal
from app.analytics.scope_resolver import resolve_dataset_scope


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_phase_1_dataset_level_metrics(db: Session):
    """PHASE 1 — Validate leads, cucet, admission, gross_admission, refunded, and ratio metrics for every production dataset."""
    datasets = db.execute(
        text("SELECT id, dataset_name, academic_year, campus_name, row_count FROM system.datasets WHERE is_analytics_enabled = TRUE ORDER BY campus_name, academic_year")
    ).mappings().all()

    assert len(datasets) == 4, "Must have exactly 4 active production datasets"

    expected_benchmarks = {
        ("Mohali", 2025): {"rows": 940981, "leads": 940981, "cucet": 940981, "admission": 930115, "refunded": 0, "gross_admission": 930115},
        ("Mohali", 2026): {"rows": 974328, "leads": 974328, "cucet": 52107, "admission": 22546, "refunded": 8302, "gross_admission": 30848},
        ("Unnao", 2025): {"rows": 302968, "leads": 302968, "cucet": 302968, "admission": 301970, "refunded": 0, "gross_admission": 301970},
        ("Unnao", 2026): {"rows": 390874, "leads": 390874, "cucet": 10545, "admission": 5706, "refunded": 0, "gross_admission": 5706},
    }

    for d in datasets:
        key = (d["campus_name"], d["academic_year"])
        assert key in expected_benchmarks, f"Unexpected campus/year dataset: {key}"
        bench = expected_benchmarks[key]

        ds_id = str(d["id"])
        res = db.execute(text(f"""
            SELECT 
                COUNT(*) as rows,
                SUM(cy_leads) as leads,
                SUM(cy_cucet) as cucet,
                SUM(cy_admission) as admission,
                COUNT(*) FILTER (WHERE lead_type = 'Refunded') as refunded,
                SUM(cy_admission) + COUNT(*) FILTER (WHERE lead_type = 'Refunded') as gross_admission
            FROM analytics.uploaded_metrics
            WHERE dataset_id::text = '{ds_id}'
        """)).mappings().first()

        assert int(res["rows"]) == bench["rows"]
        assert int(res["leads"]) == bench["leads"]
        assert int(res["cucet"]) == bench["cucet"]
        assert int(res["admission"]) == bench["admission"]
        assert int(res["refunded"]) == bench["refunded"]
        assert int(res["gross_admission"]) == bench["gross_admission"]

        # Validate canonical ratio formulas
        l = float(res["leads"])
        c = float(res["cucet"])
        a = float(res["admission"])

        lead_cucet_rate = (c / l * 100.0) if l > 0 else 0.0
        lead_admission_rate = (a / l * 100.0) if l > 0 else 0.0
        cucet_admission_rate = (a / c * 100.0) if c > 0 else 0.0
        conversion_rate = lead_admission_rate

        assert lead_cucet_rate >= 0.0 and lead_cucet_rate <= 100.0
        assert lead_admission_rate >= 0.0 and lead_admission_rate <= 100.0
        assert cucet_admission_rate >= 0.0 and cucet_admission_rate <= 100.0
        assert conversion_rate == lead_admission_rate


def test_phase_2_monthly_trend_reconciliation(db: Session):
    """PHASE 2 — Validate SUM(monthly metrics) == total dataset metrics for leads, cucet, admission, refunded, gross admissions."""
    datasets = db.execute(
        text("SELECT id, dataset_name, academic_year, campus_name FROM system.datasets WHERE is_analytics_enabled = TRUE ORDER BY campus_name, academic_year")
    ).mappings().all()

    for d in datasets:
        ds_id = str(d["id"])
        totals = db.execute(text(f"""
            SELECT 
                SUM(cy_leads) as leads,
                SUM(cy_cucet) as cucet,
                SUM(cy_admission) as admission,
                COUNT(*) FILTER (WHERE lead_type = 'Refunded') as refunded,
                SUM(cy_admission) + COUNT(*) FILTER (WHERE lead_type = 'Refunded') as gross_admission
            FROM analytics.uploaded_metrics
            WHERE dataset_id::text = '{ds_id}'
        """)).mappings().first()

        monthly = db.execute(text(f"""
            SELECT 
                EXTRACT(MONTH FROM created_at) as m,
                SUM(cy_leads) as m_leads,
                SUM(cy_cucet) as m_cucet,
                SUM(cy_admission) as m_admission,
                COUNT(*) FILTER (WHERE lead_type = 'Refunded') as m_refunded,
                SUM(cy_admission) + COUNT(*) FILTER (WHERE lead_type = 'Refunded') as m_gross
            FROM analytics.uploaded_metrics
            WHERE dataset_id::text = '{ds_id}'
            GROUP BY EXTRACT(MONTH FROM created_at)
        """)).mappings().all()

        m_leads = sum(r["m_leads"] for r in monthly)
        m_cucet = sum(r["m_cucet"] for r in monthly)
        m_admission = sum(r["m_admission"] for r in monthly)
        m_refunded = sum(r["m_refunded"] for r in monthly)
        m_gross = sum(r["m_gross"] for r in monthly)

        # STRICT ASSERTIONS: Hard fail if any mismatch exists
        assert m_leads == totals["leads"], f"Monthly leads mismatch in {d['campus_name']} {d['academic_year']}"
        assert m_cucet == totals["cucet"], f"Monthly cucet mismatch in {d['campus_name']} {d['academic_year']}"
        assert m_admission == totals["admission"], f"Monthly admission mismatch in {d['campus_name']} {d['academic_year']}"
        assert m_refunded == totals["refunded"], f"Monthly refunded mismatch in {d['campus_name']} {d['academic_year']}"
        assert m_gross == totals["gross_admission"], f"Monthly gross admission mismatch in {d['campus_name']} {d['academic_year']}"


def test_phase_3_multi_dataset_scope_topologies(db: Session):
    """PHASE 3 — Verify correct dataset scope resolution before metric aggregation across 9 topologies (A through I)."""
    topologies = [
        ("A. Mohali 2025", {"campus": "Mohali", "years": [2025]}, 1, 0),
        ("B. Mohali 2026", {"campus": "Mohali", "years": [2026]}, 1, 0),
        ("C. Unnao 2025", {"campus": "Unnao", "years": [2025]}, 1, 0),
        ("D. Unnao 2026", {"campus": "Unnao", "years": [2026]}, 1, 0),
        ("E. Mohali 2025 vs 2026", {"campus": "Mohali", "years": [2025, 2026]}, 1, 1),
        ("F. Unnao 2025 vs 2026", {"campus": "Unnao", "years": [2025, 2026]}, 1, 1),
        ("G. Mohali vs Unnao", {"campus": "all", "years": [2026]}, 2, 0),
        ("H. All campuses 2025 vs 2026", {"campus": "all", "years": [2025, 2026]}, 2, 2),
        ("I. All 4 datasets", {"campus": "all", "years": None}, 2, 2),
    ]

    for label, params, exp_cy, exp_py in topologies:
        scope = resolve_dataset_scope(db, **params)
        assert len(scope["cy_dataset_ids"]) == exp_cy, f"Failed topology {label}: CY count mismatch"
        assert len(scope["py_dataset_ids"]) == exp_py, f"Failed topology {label}: PY count mismatch"
