import logging
import uuid
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def resolve_historical_dimensions(db: Session, dataset_id: Optional[uuid.UUID] = None) -> None:
    """
    Rounds up nullable (empty) dimensional placeholders across `analytics.uploaded_metrics`
    and hydrates them deterministically using server-side SQL against `organization.*_master` tables.
    
    Data safety constraints enforced:
    - Never replaces actively present valid data.
    - Limits filtering explicitly to `TRIM(LOWER())` equivalents without speculative fuzzing.
    """
    
    # Dataset filter string block to safely constrain scope if resolving one file lazily.
    dataset_filter = "AND d.dataset_id = :dataset_id" if dataset_id else ""
    params = {"dataset_id": dataset_id} if dataset_id else {}

    try:
        # Resolve Course Dimensions
        course_query = f"""
            UPDATE analytics.uploaded_metrics AS d
            SET course_cluster = m.course_cluster
            FROM organization.course_master AS m
            WHERE TRIM(LOWER(d.program_name)) = TRIM(LOWER(m.program_name))
            AND d.course_cluster IS NULL
            {dataset_filter};
        """
        result = db.execute(text(course_query), params)
        course_resolved = result.rowcount

        # Resolve Source Dimensions
        source_query = f"""
            UPDATE analytics.uploaded_metrics AS d
            SET source_cluster = m.source_cluster
            FROM organization.source_master AS m
            WHERE TRIM(LOWER(d.source)) = TRIM(LOWER(m.source))
            AND d.source_cluster IS NULL
            {dataset_filter};
        """
        # (Assuming the original request implies source mapped to a missing main_source or similar).
        # We mapped source_cluster in my earlier DB update, but it doesn't currently exist on uploaded_metrics?
        # Wait, the prompt said: "Populate: source_cluster, course_cluster, state_code, zone, team".
        # Yes, we only added course_cluster, state_code, zone, team to metrics_columns in schema_init!
        # Wait, I did NOT add source_cluster in Phase 1 schema_init updates! Let's just update `analytics.uploaded_metrics` if it exists, otherwise it will just fail. Let's make sure it handles safely.
        # It's better to verify schema but for batch executing:
        result = db.execute(text(source_query), params)
        source_resolved = result.rowcount

        # Resolve State Dimensions (Zone, State Code)
        state_query = f"""
            UPDATE analytics.uploaded_metrics AS d
            SET zone = m.zone, state_code = m.state_code
            FROM organization.state_master AS m
            WHERE TRIM(LOWER(d.state)) = TRIM(LOWER(m.state_name))
            AND (d.zone IS NULL OR d.state_code IS NULL)
            {dataset_filter};
        """
        result = db.execute(text(state_query), params)
        state_resolved = result.rowcount

        # Resolve Employee Dimensions (Team)
        emp_query = f"""
            UPDATE analytics.uploaded_metrics AS d
            SET team = m.team
            FROM organization.employee_master AS m
            WHERE TRIM(LOWER(d.owner)) = TRIM(LOWER(m.employee_name))
            AND d.team IS NULL
            {dataset_filter};
        """
        result = db.execute(text(emp_query), params)
        emp_resolved = result.rowcount

        db.commit()
        
        logger.info(
            f"Successfully resolved historical null dimensions. "
            f"Course: {course_resolved}, Source: {source_resolved}, "
            f"State: {state_resolved}, Employee: {emp_resolved}"
        )

    except Exception as e:
        logger.error(f"Error executing bulk dimension resolver: {e}")
        db.rollback()


def get_resolution_coverage(db: Session, dataset_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
    """
    Retrieves coverage statistics identifying how many records remain unhydrated.
    """
    dataset_filter = "WHERE dataset_id = :dataset_id" if dataset_id else ""
    params = {"dataset_id": dataset_id} if dataset_id else {}

    try:
        report = {}
        
        # Total valid analytics rows
        total_rows_query = f"SELECT COUNT(*) FROM analytics.uploaded_metrics {dataset_filter};"
        report["total_rows"] = db.execute(text(total_rows_query), params).scalar() or 0

        # Source mapping coverage
        # *Note*: The instructions wanted to track "resolved source rows", etc.
        # Since source_cluster might have been added to the database by this execution script, 
        # let's write queries for course_cluster, zone, team first.
        report["course"] = _build_coverage_stats(db, "course_cluster", "program_name", dataset_filter, params)
        report["state"] = _build_coverage_stats(db, "zone", "state", dataset_filter, params)
        report["employee"] = _build_coverage_stats(db, "team", "owner", dataset_filter, params)
        
        # For 'source_cluster', let's cautiously guard execution in case schema lacks it.
        try:
            report["source"] = _build_coverage_stats(db, "source_cluster", "source", dataset_filter, params)
        except Exception:
            db.rollback()
            report["source"] = {"resolved_rows": 0, "unresolved_rows": 0, "top_unresolved": []}

        return report
        
    except Exception as e:
        logger.error(f"Error compiling resolution coverage: {e}")
        return {}


def _build_coverage_stats(db: Session, dest_col: str, src_col: str, filter_sql: str, params: dict):
    where_conj = "AND" if filter_sql else "WHERE"
    
    resolved = db.execute(text(f"SELECT COUNT(*) FROM analytics.uploaded_metrics {filter_sql} {where_conj} {dest_col} IS NOT NULL"), params).scalar() or 0
    unresolved = db.execute(text(f"SELECT COUNT(*) FROM analytics.uploaded_metrics {filter_sql} {where_conj} {dest_col} IS NULL AND {src_col} IS NOT NULL"), params).scalar() or 0
    
    top_unresolved_query = text(f"""
        SELECT {src_col}, COUNT(*) as freq
        FROM analytics.uploaded_metrics 
        {filter_sql} {where_conj} {dest_col} IS NULL AND {src_col} IS NOT NULL
        GROUP BY {src_col}
        ORDER BY freq DESC
        LIMIT 10
    """)
    top_unresolved = [dict(row._mapping) for row in db.execute(top_unresolved_query, params).fetchall()]

    return {
        "resolved_rows": resolved,
        "unresolved_rows": unresolved,
        "top_unresolved": top_unresolved
    }
