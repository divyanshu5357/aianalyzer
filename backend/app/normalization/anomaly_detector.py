"""
Phase 11 — Anomaly Detection

Detects data quality anomalies without deleting or modifying any records.
Each finding is classified as ERROR, WARNING, or INFO.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    severity: str  # ERROR | WARNING | INFO
    category: str
    description: str
    count: int
    sample_values: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "count": self.count,
            "sample_values": self.sample_values[:10],
        }


def detect_anomalies(db: Session, dataset_id: str) -> List[Anomaly]:
    """Detect anomalies for a single dataset."""

    ds = db.execute(text(
        "SELECT dataset_name, campus_name, academic_year "
        "FROM system.datasets WHERE id = :id"
    ), {"id": dataset_id}).mappings().first()

    if not ds:
        return []

    anomalies: List[Anomaly] = []

    has_staging = db.execute(text(
        "SELECT COUNT(*) FROM staging.records WHERE dataset_id = :id LIMIT 1"
    ), {"id": dataset_id}).scalar() or 0

    # --- Staging-level checks (only if staging data exists) ---
    if has_staging > 0:
        # 1. Duplicate ProspectIDs
        dup_rows = db.execute(text("""
            SELECT raw_data->>'ProspectID' as pid, COUNT(*) as cnt
            FROM staging.records
            WHERE dataset_id = :id AND raw_data->>'ProspectID' IS NOT NULL
            GROUP BY raw_data->>'ProspectID'
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
            LIMIT 10
        """), {"id": dataset_id}).fetchall()

        if dup_rows:
            total_dups = db.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT raw_data->>'ProspectID'
                    FROM staging.records
                    WHERE dataset_id = :id AND raw_data->>'ProspectID' IS NOT NULL
                    GROUP BY raw_data->>'ProspectID'
                    HAVING COUNT(*) > 1
                ) t
            """), {"id": dataset_id}).scalar() or 0
            anomalies.append(Anomaly(
                severity="WARNING",
                category="DUPLICATE_PROSPECT_ID",
                description=f"Found {total_dups} ProspectIDs with duplicate records",
                count=int(total_dups),
                sample_values=[f"{r[0]} ({r[1]}x)" for r in dup_rows],
            ))

        # 2. Missing ProspectIDs
        missing_pid = db.execute(text("""
            SELECT COUNT(*) FROM staging.records
            WHERE dataset_id = :id
            AND (raw_data->>'ProspectID' IS NULL OR TRIM(raw_data->>'ProspectID') = '')
        """), {"id": dataset_id}).scalar() or 0
        if missing_pid > 0:
            anomalies.append(Anomaly(
                severity="ERROR",
                category="MISSING_PROSPECT_ID",
                description=f"Records with missing/empty ProspectID",
                count=int(missing_pid),
            ))

        # 3. Future dates (CreatedOn in the future)
        future_dates = db.execute(text("""
            SELECT COUNT(*) FROM staging.records
            WHERE dataset_id = :id
            AND raw_data->>'CreatedOn' IS NOT NULL
            AND raw_data->>'CreatedOn' != ''
            AND CASE
                WHEN raw_data->>'CreatedOn' ~ '^\d{4}-\d{2}-\d{2}'
                THEN (raw_data->>'CreatedOn')::timestamp > NOW() + INTERVAL '1 day'
                ELSE FALSE
            END
        """), {"id": dataset_id}).scalar() or 0
        if future_dates > 0:
            anomalies.append(Anomaly(
                severity="WARNING",
                category="FUTURE_DATE",
                description="Records with CreatedOn date in the future",
                count=int(future_dates),
            ))

        # 4. Impossible dates (before 2020)
        old_dates = db.execute(text("""
            SELECT COUNT(*) FROM staging.records
            WHERE dataset_id = :id
            AND raw_data->>'CreatedOn' IS NOT NULL
            AND raw_data->>'CreatedOn' != ''
            AND CASE
                WHEN raw_data->>'CreatedOn' ~ '^\d{4}-\d{2}-\d{2}'
                THEN (raw_data->>'CreatedOn')::timestamp < '2020-01-01'::timestamp
                ELSE FALSE
            END
        """), {"id": dataset_id}).scalar() or 0
        if old_dates > 0:
            anomalies.append(Anomaly(
                severity="WARNING",
                category="IMPOSSIBLE_DATE",
                description="Records with CreatedOn before 2020",
                count=int(old_dates),
            ))

    # --- Analytics-level checks ---
    # 5. Unknown/unmapped statuses
    unknown_status = db.execute(text("""
        SELECT lead_type, COUNT(*) as cnt
        FROM analytics.uploaded_metrics
        WHERE dataset_id = :id
        AND (lead_type IS NULL OR TRIM(lead_type) = '')
        GROUP BY lead_type
    """), {"id": dataset_id}).fetchall()
    total_unknown_status = sum(int(r[1]) for r in unknown_status)
    if total_unknown_status > 0:
        anomalies.append(Anomaly(
            severity="WARNING",
            category="UNKNOWN_STATUS",
            description="Records with NULL/empty lead_type",
            count=total_unknown_status,
        ))

    # 6. Unknown states (not in state_master)
    unresolved_states = db.execute(text("""
        SELECT a.state, COUNT(*) as cnt
        FROM analytics.uploaded_metrics a
        WHERE a.dataset_id = :id
        AND a.state IS NOT NULL AND TRIM(a.state) != ''
        AND NOT EXISTS (
            SELECT 1 FROM organization.state_master sm
            WHERE LOWER(TRIM(sm.state_name)) = LOWER(TRIM(a.state))
        )
        GROUP BY a.state
        ORDER BY cnt DESC
        LIMIT 15
    """), {"id": dataset_id}).fetchall()
    total_unresolved_states = sum(int(r[1]) for r in unresolved_states)
    if total_unresolved_states > 0:
        anomalies.append(Anomaly(
            severity="INFO",
            category="UNKNOWN_STATE",
            description="Records with state not found in state_master",
            count=total_unresolved_states,
            sample_values=[f"{r[0]} ({r[1]})" for r in unresolved_states],
        ))

    # 7. Unknown sources
    unresolved_sources = db.execute(text("""
        SELECT a.source, COUNT(*) as cnt
        FROM analytics.uploaded_metrics a
        WHERE a.dataset_id = :id
        AND a.source IS NOT NULL AND TRIM(a.source) != ''
        AND NOT EXISTS (
            SELECT 1 FROM organization.source_master sm
            WHERE LOWER(TRIM(sm.source)) = LOWER(TRIM(a.source))
        )
        GROUP BY a.source
        ORDER BY cnt DESC
        LIMIT 15
    """), {"id": dataset_id}).fetchall()
    total_unresolved_sources = sum(int(r[1]) for r in unresolved_sources)
    if total_unresolved_sources > 0:
        anomalies.append(Anomaly(
            severity="INFO",
            category="UNKNOWN_SOURCE",
            description="Records with source not found in source_master",
            count=total_unresolved_sources,
            sample_values=[f"{r[0]} ({r[1]})" for r in unresolved_sources],
        ))

    # 8. Inconsistent campus
    campus_vals = db.execute(text("""
        SELECT DISTINCT campus_name FROM analytics.uploaded_metrics WHERE dataset_id = :id
    """), {"id": dataset_id}).fetchall()
    campus_list = [r[0] for r in campus_vals if r[0]]
    if len(campus_list) > 1:
        anomalies.append(Anomaly(
            severity="WARNING",
            category="INCONSISTENT_CAMPUS",
            description="Multiple campus values found in single dataset",
            count=len(campus_list),
            sample_values=campus_list,
        ))

    # 9. Inconsistent academic year
    year_vals = db.execute(text("""
        SELECT DISTINCT academic_year FROM analytics.uploaded_metrics WHERE dataset_id = :id
    """), {"id": dataset_id}).fetchall()
    year_list = [str(r[0]) for r in year_vals if r[0] is not None]
    if len(year_list) > 1:
        anomalies.append(Anomaly(
            severity="WARNING",
            category="INCONSISTENT_ACADEMIC_YEAR",
            description="Multiple academic year values in single dataset",
            count=len(year_list),
            sample_values=year_list,
        ))

    # 10. Suspicious cy_leads values (> 1 per row)
    suspicious_leads = db.execute(text("""
        SELECT COUNT(*) FROM analytics.uploaded_metrics
        WHERE dataset_id = :id AND cy_leads > 1
    """), {"id": dataset_id}).scalar() or 0
    if suspicious_leads > 0:
        anomalies.append(Anomaly(
            severity="INFO",
            category="SUSPICIOUS_LEADS_VALUE",
            description="Records with cy_leads > 1 (expected 0 or 1 for CRM data)",
            count=int(suspicious_leads),
        ))

    return anomalies


def detect_all_anomalies(db: Session) -> Dict[str, List[Dict[str, Any]]]:
    """Run anomaly detection for all datasets."""
    datasets = db.execute(text(
        "SELECT id, dataset_name FROM system.datasets WHERE is_analytics_enabled = TRUE ORDER BY campus_name, academic_year"
    )).fetchall()

    results = {}
    for ds_id, ds_name in datasets:
        try:
            anomalies = detect_anomalies(db, str(ds_id))
            results[ds_name] = [a.to_dict() for a in anomalies]
        except Exception as e:
            logger.error(f"Anomaly detection failed for {ds_id}: {e}")
            results[ds_name] = [{"severity": "ERROR", "category": "DETECTION_FAILED", "description": str(e), "count": 0}]
    return results
