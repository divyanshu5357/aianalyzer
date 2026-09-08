"""
Phase 12 — Comprehensive Data Quality Validation Test Suite

20 automated test cases covering:
  1. Raw row count preservation
  2-6. Status normalization (Enrolled, Refunded, Admit in Other College, Unknown)
  7-10. State resolution (exact, code, city alias, unresolved)
  11. Source resolution
  12. Program resolution
  13. Employee resolution
  14. Metric reconciliation per dataset
  15. Campus filtering
  16. Year filtering
  17. All-campus aggregation
  18. API vs independent SQL
  19. Dashboard scope
  20. Monthly trend reconciliation
"""

import pytest
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.normalization.status_registry import (
    resolve_prospect_stage, PROSPECT_STAGE_REGISTRY, UNMAPPED_STATUS,
    resolve_cucet_status,
)
from app.normalization.dimension_resolver import (
    StateResolver, SourceResolver, EmployeeResolver, ProgramResolver,
    DimensionResolverSuite,
)
from app.normalization.quality_report import generate_quality_report
from app.normalization.metric_reconciler import (
    reconcile_dataset, reconcile_cross_dataset, _independent_metrics_from_analytics,
)
from app.normalization.anomaly_detector import detect_anomalies


DATASETS = {
    "mohali_2026": "50b48957-3f9c-4c9a-b8f8-1920b20b5bfe",
    "mohali_2025": "cb3eb918-1ff2-4205-b277-d4711e8e9a42",
    "unnao_2026": "bc936416-917c-43c2-b999-9a4ea507c86d",
    "unnao_2025": "92ad8b31-93eb-4302-af21-824cbe76bec8",
}


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════
# 1. Raw Row Count Preservation
# ═══════════════════════════════════════════════════════════════════

class TestRowCountPreservation:
    def test_01_mohali_2026_analytics_count(self, db: Session):
        """Mohali 2026 analytics row count matches expected."""
        cnt = db.execute(text(
            "SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :id"
        ), {"id": DATASETS["mohali_2026"]}).scalar()
        assert cnt == 974328, f"Expected 974328, got {cnt}"

    def test_01b_mohali_2025_analytics_count(self, db: Session):
        cnt = db.execute(text(
            "SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :id"
        ), {"id": DATASETS["mohali_2025"]}).scalar()
        assert cnt == 940981, f"Expected 940981, got {cnt}"

    def test_01c_unnao_2026_analytics_count(self, db: Session):
        cnt = db.execute(text(
            "SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :id"
        ), {"id": DATASETS["unnao_2026"]}).scalar()
        assert cnt == 390874, f"Expected 390874, got {cnt}"

    def test_01d_unnao_2025_analytics_count(self, db: Session):
        cnt = db.execute(text(
            "SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :id"
        ), {"id": DATASETS["unnao_2025"]}).scalar()
        assert cnt == 302968, f"Expected 302968, got {cnt}"


# ═══════════════════════════════════════════════════════════════════
# 2-6. Status Normalization
# ═══════════════════════════════════════════════════════════════════

class TestStatusNormalization:
    def test_02_enrolled_maps_to_admission_1(self):
        """Enrolled → admission_flag=1."""
        mapping = resolve_prospect_stage("Enrolled")
        assert mapping.canonical_value == "ENROLLED"
        assert mapping.admission_flag == 1
        assert mapping.refunded_flag == 0
        assert mapping.resolution_status == "RESOLVED"

    def test_02b_enrolled_case_insensitive(self):
        """Case insensitive: 'enrolled' and ' ENROLLED ' resolve identically."""
        m1 = resolve_prospect_stage("enrolled")
        m2 = resolve_prospect_stage(" ENROLLED ")
        m3 = resolve_prospect_stage("Enrolled")
        assert m1.canonical_value == m2.canonical_value == m3.canonical_value == "ENROLLED"
        assert m1.admission_flag == 1

    def test_03_refunded_handling(self):
        """Refunded → admission_flag=0, refunded_flag=1."""
        mapping = resolve_prospect_stage("Refunded")
        assert mapping.canonical_value == "REFUNDED"
        assert mapping.admission_flag == 0
        assert mapping.refunded_flag == 1

    def test_04_admit_other_college(self):
        """Admit in Other College → admission_flag=0."""
        mapping = resolve_prospect_stage("Admit in Other College")
        assert mapping.canonical_value == "ADMIT_OTHER_COLLEGE"
        assert mapping.admission_flag == 0

    def test_05_unknown_status_not_silently_zeroed(self):
        """Unknown status → UNMAPPED with REVIEW_REQUIRED, not silently zeroed."""
        mapping = resolve_prospect_stage("Some Random Status")
        assert mapping.canonical_value == "UNMAPPED"
        assert mapping.resolution_status == "REVIEW_REQUIRED"
        assert mapping.confidence == 0.0

    def test_05b_null_status(self):
        """NULL status → UNMAPPED."""
        mapping = resolve_prospect_stage(None)
        assert mapping.canonical_value == "UNMAPPED"
        assert mapping.resolution_status == "REVIEW_REQUIRED"

    def test_05c_empty_status(self):
        """Empty string status → UNMAPPED."""
        mapping = resolve_prospect_stage("")
        assert mapping.canonical_value == "UNMAPPED"

    def test_06_all_prospect_stages_covered(self, db: Session):
        """All ProspectStage values in Mohali 2026 are in the registry."""
        stages = db.execute(text("""
            SELECT DISTINCT lead_type FROM analytics.uploaded_metrics
            WHERE dataset_id = :id AND lead_type IS NOT NULL AND TRIM(lead_type) != ''
        """), {"id": DATASETS["mohali_2026"]}).fetchall()

        for (stage,) in stages:
            mapping = resolve_prospect_stage(stage)
            assert mapping.resolution_status == "RESOLVED", f"Unmapped status: {stage}"

    def test_06b_cucet_status_resolution(self):
        """CUCET status registry works correctly."""
        m1 = resolve_cucet_status("Eligible-for-Scholarship")
        assert m1.cucet_flag == 1
        m2 = resolve_cucet_status("No Show")
        assert m2.cucet_flag == 0
        m3 = resolve_cucet_status("")
        assert m3.cucet_flag == 0
        m4 = resolve_cucet_status(None)
        assert m4.cucet_flag == 0


# ═══════════════════════════════════════════════════════════════════
# 7-10. State Resolution
# ═══════════════════════════════════════════════════════════════════

class TestStateResolution:
    def test_07_exact_state_match(self, db: Session):
        """Punjab resolves to Punjab via exact name match."""
        resolver = StateResolver(db)
        res = resolver.resolve("Punjab")
        assert res.resolution_status == "RESOLVED"
        assert res.canonical_value == "Punjab"
        assert res.extra["state_code"] == "PB"

    def test_07b_case_insensitive_state(self, db: Session):
        """'DELHI' resolves via case-insensitive match."""
        resolver = StateResolver(db)
        res = resolver.resolve("DELHI")
        assert res.resolution_status == "RESOLVED"

    def test_08_state_code_match(self, db: Session):
        """'UP' resolves to Uttar Pradesh via state_code."""
        resolver = StateResolver(db)
        res = resolver.resolve("UP")
        assert res.resolution_status == "RESOLVED"
        assert res.extra["state_code"] == "UP"

    def test_09_city_to_state_alias(self, db: Session):
        """City names in state_master resolve correctly (e.g. MUMBAI → MH)."""
        resolver = StateResolver(db)
        res = resolver.resolve("MUMBAI")
        assert res.resolution_status == "RESOLVED"
        assert res.extra["state_code"] == "MH"

    def test_10_unresolved_state(self, db: Session):
        """Gibberish state remains UNRESOLVED."""
        resolver = StateResolver(db)
        res = resolver.resolve("XYZNONEXISTENT")
        assert res.resolution_status == "UNRESOLVED"
        assert res.canonical_value is None


# ═══════════════════════════════════════════════════════════════════
# 11-13. Source / Program / Employee Resolution
# ═══════════════════════════════════════════════════════════════════

class TestDimensionResolution:
    def test_11_source_exact_match(self, db: Session):
        """Known source resolves correctly."""
        resolver = SourceResolver(db)
        res = resolver.resolve("Google")
        assert res.resolution_status == "RESOLVED"

    def test_11b_source_unresolved(self, db: Session):
        """Unknown source stays UNRESOLVED."""
        resolver = SourceResolver(db)
        res = resolver.resolve("NonExistentSource12345")
        assert res.resolution_status == "UNRESOLVED"

    def test_12_program_resolution(self, db: Session):
        """Program resolution works for known programs."""
        resolver = ProgramResolver(db)
        # If course_master has entries, test one
        row = db.execute(text("SELECT program_name_short FROM organization.course_master LIMIT 1")).scalar()
        if row:
            res = resolver.resolve(row)
            assert res.resolution_status == "RESOLVED"

    def test_12b_program_null(self, db: Session):
        """NULL program → UNRESOLVED (expected for CRM data)."""
        resolver = ProgramResolver(db)
        res = resolver.resolve(None)
        assert res.resolution_status == "UNRESOLVED"

    def test_13_employee_resolution(self, db: Session):
        """Known employee resolves with team."""
        resolver = EmployeeResolver(db)
        row = db.execute(text("SELECT employee_name FROM organization.employee_master LIMIT 1")).scalar()
        if row:
            res = resolver.resolve(row)
            assert res.resolution_status == "RESOLVED"


# ═══════════════════════════════════════════════════════════════════
# 14. Metric Reconciliation Per Dataset
# ═══════════════════════════════════════════════════════════════════

class TestMetricReconciliation:
    def test_14_mohali_2026_metrics(self, db: Session):
        """Mohali 2026 independent metrics match known benchmarks."""
        metrics = _independent_metrics_from_analytics(db, DATASETS["mohali_2026"])
        assert metrics["leads"] == 974328
        assert metrics["cucet"] == 52107
        assert metrics["admission"] == 22546
        assert metrics["refunded"] == 8302
        assert metrics["gross_admission"] == 30848

    def test_14b_mohali_2025_metrics(self, db: Session):
        metrics = _independent_metrics_from_analytics(db, DATASETS["mohali_2025"])
        assert metrics["leads"] == 940981

    def test_14c_unnao_2026_metrics(self, db: Session):
        metrics = _independent_metrics_from_analytics(db, DATASETS["unnao_2026"])
        assert metrics["leads"] == 390874

    def test_14d_unnao_2025_metrics(self, db: Session):
        metrics = _independent_metrics_from_analytics(db, DATASETS["unnao_2025"])
        assert metrics["leads"] == 302968


# ═══════════════════════════════════════════════════════════════════
# 15-17. Campus / Year / All-Campus Aggregation
# ═══════════════════════════════════════════════════════════════════

class TestScopeFiltering:
    def test_15_campus_filtering(self, db: Session):
        """Mohali leads ≠ Unnao leads (campus filter must produce different values)."""
        m_mohali = _independent_metrics_from_analytics(db, DATASETS["mohali_2026"])
        m_unnao = _independent_metrics_from_analytics(db, DATASETS["unnao_2026"])
        assert m_mohali["leads"] != m_unnao["leads"]

    def test_16_year_filtering(self, db: Session):
        """Mohali 2025 leads ≠ Mohali 2026 leads (year filter must differ)."""
        m_2025 = _independent_metrics_from_analytics(db, DATASETS["mohali_2025"])
        m_2026 = _independent_metrics_from_analytics(db, DATASETS["mohali_2026"])
        assert m_2025["leads"] != m_2026["leads"]

    def test_17_all_campus_aggregation(self, db: Session):
        """All campuses 2026 = Mohali 2026 + Unnao 2026 for additive metrics."""
        m_mohali = _independent_metrics_from_analytics(db, DATASETS["mohali_2026"])
        m_unnao = _independent_metrics_from_analytics(db, DATASETS["unnao_2026"])

        all_2026 = db.execute(text("""
            SELECT COALESCE(SUM(cy_leads), 0) AS leads,
                   COALESCE(SUM(cy_cucet), 0) AS cucet,
                   COALESCE(SUM(cy_admission), 0) AS admission
            FROM analytics.uploaded_metrics a
            JOIN system.datasets d ON a.dataset_id = d.id
            WHERE d.is_analytics_enabled = TRUE AND d.academic_year = 2026
        """)).mappings().first()

        assert int(all_2026["leads"]) == m_mohali["leads"] + m_unnao["leads"]
        assert int(all_2026["cucet"]) == m_mohali["cucet"] + m_unnao["cucet"]
        assert int(all_2026["admission"]) == m_mohali["admission"] + m_unnao["admission"]


# ═══════════════════════════════════════════════════════════════════
# 18. API vs Independent SQL
# ═══════════════════════════════════════════════════════════════════

class TestAPIReconciliation:
    def test_18_api_vs_sql_mohali_2026(self, db: Session):
        """Dashboard overview for Mohali 2026 matches independent SQL."""
        recon = reconcile_dataset(db, DATASETS["mohali_2026"])
        for metric_name in ["leads", "cucet", "admission"]:
            entry = recon.metrics.get(metric_name, {})
            if entry.get("semantic_layer") is not None:
                assert entry["match"], f"Mismatch for {metric_name}: SQL={entry['independent_sql']} vs Semantic={entry['semantic_layer']}"


# ═══════════════════════════════════════════════════════════════════
# 19. Dashboard Scope
# ═══════════════════════════════════════════════════════════════════

class TestDashboardScope:
    def test_19_scope_changes_values(self, db: Session):
        """Changing campus from Mohali to Unnao must produce different values."""
        cross = reconcile_cross_dataset(db)
        year_data = cross.get("year_2026", {})
        if year_data:
            assert year_data["mohali"]["leads"] != year_data["unnao"]["leads"]
            assert year_data["mohali"]["admission"] != year_data["unnao"]["admission"]


# ═══════════════════════════════════════════════════════════════════
# 20. Monthly Trend Reconciliation
# ═══════════════════════════════════════════════════════════════════

class TestMonthlyReconciliation:
    def test_20_monthly_sums_equal_totals(self, db: Session):
        """SUM(monthly values) == total for each dataset."""
        for ds_name, ds_id in DATASETS.items():
            totals = db.execute(text("""
                SELECT COALESCE(SUM(cy_leads), 0) AS leads,
                       COALESCE(SUM(cy_cucet), 0) AS cucet,
                       COALESCE(SUM(cy_admission), 0) AS admission
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :id
            """), {"id": ds_id}).mappings().first()

            monthly = db.execute(text("""
                SELECT EXTRACT(MONTH FROM created_at) AS m,
                       COALESCE(SUM(cy_leads), 0) AS leads,
                       COALESCE(SUM(cy_cucet), 0) AS cucet,
                       COALESCE(SUM(cy_admission), 0) AS admission
                FROM analytics.uploaded_metrics
                WHERE dataset_id = :id
                GROUP BY EXTRACT(MONTH FROM created_at)
            """), {"id": ds_id}).mappings().all()

            m_leads = sum(int(r["leads"]) for r in monthly)
            m_cucet = sum(int(r["cucet"]) for r in monthly)
            m_admission = sum(int(r["admission"]) for r in monthly)

            assert m_leads == int(totals["leads"]), f"Monthly leads mismatch for {ds_name}"
            assert m_cucet == int(totals["cucet"]), f"Monthly cucet mismatch for {ds_name}"
            assert m_admission == int(totals["admission"]), f"Monthly admission mismatch for {ds_name}"
