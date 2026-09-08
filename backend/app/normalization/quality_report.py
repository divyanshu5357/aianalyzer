"""
Phase 5 — Data Quality Report Generator

Produces a comprehensive per-dataset quality report including:
  - Row count reconciliation (staging/analytics/loss)
  - NULL counts per dimension
  - Dimension resolution coverage
  - Duplicate detection
  - Unknown status/source/state counts
  - Anomaly summary
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.normalization.status_registry import resolve_prospect_stage, PROSPECT_STAGE_REGISTRY
from app.normalization.dimension_resolver import DimensionResolverSuite

logger = logging.getLogger(__name__)


@dataclass
class DatasetQualityReport:
    dataset_id: str
    dataset_name: str
    campus_name: str
    academic_year: int

    # Row counts
    staging_rows: int = 0
    analytics_rows: int = 0
    system_row_count: int = 0
    row_loss: int = 0

    # NULL counts per dimension
    null_counts: Dict[str, int] = field(default_factory=dict)

    # Status resolution
    known_statuses: int = 0
    unknown_statuses: int = 0
    status_distribution: Dict[str, int] = field(default_factory=dict)
    unmapped_statuses: List[Dict[str, Any]] = field(default_factory=list)

    # Dimension resolution coverage
    state_resolved: int = 0
    state_unresolved: int = 0
    state_coverage_pct: float = 0.0
    top_unresolved_states: List[Dict[str, Any]] = field(default_factory=list)

    source_resolved: int = 0
    source_unresolved: int = 0
    source_coverage_pct: float = 0.0
    top_unresolved_sources: List[Dict[str, Any]] = field(default_factory=list)

    employee_resolved: int = 0
    employee_unresolved: int = 0
    employee_coverage_pct: float = 0.0

    program_resolved: int = 0
    program_unresolved: int = 0
    program_null: int = 0

    # Duplicates
    duplicate_prospect_ids: int = 0

    # Anomalies
    anomaly_count: int = 0

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "campus_name": self.campus_name,
            "academic_year": self.academic_year,
            "rows": {
                "staging": self.staging_rows,
                "analytics": self.analytics_rows,
                "system_row_count": self.system_row_count,
                "loss": self.row_loss,
            },
            "null_counts": self.null_counts,
            "status": {
                "known": self.known_statuses,
                "unknown": self.unknown_statuses,
                "distribution": self.status_distribution,
                "unmapped": self.unmapped_statuses,
            },
            "state": {
                "resolved": self.state_resolved,
                "unresolved": self.state_unresolved,
                "coverage_pct": self.state_coverage_pct,
                "top_unresolved": self.top_unresolved_states,
            },
            "source": {
                "resolved": self.source_resolved,
                "unresolved": self.source_unresolved,
                "coverage_pct": self.source_coverage_pct,
                "top_unresolved": self.top_unresolved_sources,
            },
            "employee": {
                "resolved": self.employee_resolved,
                "unresolved": self.employee_unresolved,
                "coverage_pct": self.employee_coverage_pct,
            },
            "program": {
                "resolved": self.program_resolved,
                "unresolved": self.program_unresolved,
                "null": self.program_null,
            },
            "duplicates": self.duplicate_prospect_ids,
            "anomaly_count": self.anomaly_count,
        }


def generate_quality_report(db: Session, dataset_id: str) -> DatasetQualityReport:
    """Generate a comprehensive quality report for one dataset."""

    # Dataset metadata
    ds = db.execute(text(
        "SELECT dataset_name, campus_name, academic_year, row_count "
        "FROM system.datasets WHERE id = :id"
    ), {"id": dataset_id}).mappings().first()

    if not ds:
        raise ValueError(f"Dataset {dataset_id} not found")

    report = DatasetQualityReport(
        dataset_id=dataset_id,
        dataset_name=ds["dataset_name"],
        campus_name=ds["campus_name"] or "Unknown",
        academic_year=ds["academic_year"] or 0,
        system_row_count=ds["row_count"] or 0,
    )

    # Row counts
    report.staging_rows = db.execute(text(
        "SELECT COUNT(*) FROM staging.records WHERE dataset_id = :id"
    ), {"id": dataset_id}).scalar() or 0

    report.analytics_rows = db.execute(text(
        "SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :id"
    ), {"id": dataset_id}).scalar() or 0

    report.row_loss = max(0, report.staging_rows - report.analytics_rows) if report.staging_rows > 0 else 0

    # NULL counts per dimension
    for col in ["owner", "source", "state", "lead_type", "campus_name", "program_name", 
                 "course_cluster", "state_code", "zone", "team", "source_cluster"]:
        cnt = db.execute(text(f"""
            SELECT COUNT(*) FROM analytics.uploaded_metrics
            WHERE dataset_id = :id AND ({col} IS NULL OR TRIM({col}) = '')
        """), {"id": dataset_id}).scalar() or 0
        report.null_counts[col] = int(cnt)

    # Status distribution (lead_type = ProspectStage in analytics)
    status_rows = db.execute(text("""
        SELECT lead_type, COUNT(*) as cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :id
        GROUP BY lead_type ORDER BY cnt DESC
    """), {"id": dataset_id}).fetchall()

    resolvers = DimensionResolverSuite(db)

    known = 0
    unknown = 0
    for raw_status, cnt in status_rows:
        cnt = int(cnt)
        mapping = resolve_prospect_stage(raw_status)
        report.status_distribution[raw_status or "<NULL>"] = cnt
        if mapping.resolution_status == "RESOLVED":
            known += cnt
        else:
            unknown += cnt
            report.unmapped_statuses.append({"value": raw_status, "count": cnt})
    report.known_statuses = known
    report.unknown_statuses = unknown

    # State resolution coverage
    state_rows = db.execute(text("""
        SELECT state, COUNT(*) as cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :id AND state IS NOT NULL AND TRIM(state) != ''
        GROUP BY state ORDER BY cnt DESC
    """), {"id": dataset_id}).fetchall()

    state_resolved = 0
    state_unresolved = 0
    unresolved_states = []
    for raw_state, cnt in state_rows:
        cnt = int(cnt)
        res = resolvers.state.resolve(raw_state)
        if res.resolution_status == "RESOLVED":
            state_resolved += cnt
        else:
            state_unresolved += cnt
            unresolved_states.append({"value": raw_state, "count": cnt})

    report.state_resolved = state_resolved
    report.state_unresolved = state_unresolved
    total_with_state = state_resolved + state_unresolved
    report.state_coverage_pct = round(state_resolved / total_with_state * 100, 2) if total_with_state > 0 else 0.0
    report.top_unresolved_states = sorted(unresolved_states, key=lambda x: -x["count"])[:20]

    # Source resolution coverage
    source_rows = db.execute(text("""
        SELECT source, COUNT(*) as cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :id AND source IS NOT NULL AND TRIM(source) != ''
        GROUP BY source ORDER BY cnt DESC
    """), {"id": dataset_id}).fetchall()

    src_resolved = 0
    src_unresolved = 0
    unresolved_sources = []
    for raw_src, cnt in source_rows:
        cnt = int(cnt)
        res = resolvers.source.resolve(raw_src)
        if res.resolution_status == "RESOLVED":
            src_resolved += cnt
        else:
            src_unresolved += cnt
            unresolved_sources.append({"value": raw_src, "count": cnt})

    report.source_resolved = src_resolved
    report.source_unresolved = src_unresolved
    total_with_src = src_resolved + src_unresolved
    report.source_coverage_pct = round(src_resolved / total_with_src * 100, 2) if total_with_src > 0 else 0.0
    report.top_unresolved_sources = sorted(unresolved_sources, key=lambda x: -x["count"])[:20]

    # Employee resolution coverage
    emp_rows = db.execute(text("""
        SELECT owner, COUNT(*) as cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :id AND owner IS NOT NULL AND TRIM(owner) != ''
        GROUP BY owner ORDER BY cnt DESC
    """), {"id": dataset_id}).fetchall()

    emp_resolved = 0
    emp_unresolved = 0
    for raw_emp, cnt in emp_rows:
        cnt = int(cnt)
        res = resolvers.employee.resolve(raw_emp)
        if res.resolution_status == "RESOLVED":
            emp_resolved += cnt
        else:
            emp_unresolved += cnt

    report.employee_resolved = emp_resolved
    report.employee_unresolved = emp_unresolved
    total_with_emp = emp_resolved + emp_unresolved
    report.employee_coverage_pct = round(emp_resolved / total_with_emp * 100, 2) if total_with_emp > 0 else 0.0

    # Program — mostly NULL for CRM data
    report.program_null = report.null_counts.get("program_name", 0)
    report.program_resolved = 0  # Will be computed if non-null programs exist
    report.program_unresolved = 0

    # Duplicate ProspectIDs (only for datasets with staging)
    if report.staging_rows > 0:
        dup_count = db.execute(text("""
            SELECT COUNT(*) FROM (
                SELECT raw_data->>'ProspectID' as pid
                FROM staging.records
                WHERE dataset_id = :id AND raw_data->>'ProspectID' IS NOT NULL
                GROUP BY raw_data->>'ProspectID'
                HAVING COUNT(*) > 1
            ) dups
        """), {"id": dataset_id}).scalar() or 0
        report.duplicate_prospect_ids = int(dup_count)

    return report


def generate_all_quality_reports(db: Session) -> List[DatasetQualityReport]:
    """Generate quality reports for all analytics-enabled datasets."""
    datasets = db.execute(text(
        "SELECT id FROM system.datasets WHERE is_analytics_enabled = TRUE ORDER BY campus_name, academic_year"
    )).fetchall()

    reports = []
    for (ds_id,) in datasets:
        try:
            report = generate_quality_report(db, str(ds_id))
            reports.append(report)
        except Exception as e:
            logger.error(f"Failed to generate quality report for {ds_id}: {e}")
    return reports
