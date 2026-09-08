"""
Canonical Business Dimension Registry & Semantic Layer
Authoritative registry mapping dimension aliases, canonical database columns, and master tables.
"""

from typing import Dict, Any, Optional, List

DIMENSION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "source": {
        "canonical_name": "source",
        "column_name": "source",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.source_master",
        "master_join_col": "source_name",
        "default_null_value": "Unknown Source",
        "aliases": ["source", "lead source", "marketing source", "channel", "acquisition source"],
    },
    "report_source": {
        "canonical_name": "report_source",
        "column_name": "source",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.source_master",
        "master_join_col": "report_source",
        "default_null_value": "Unknown Source",
        "aliases": ["report source", "reporting source", "report_source"],
    },
    "main_source": {
        "canonical_name": "main_source",
        "column_name": "main_source",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.source_master",
        "master_join_col": "main_source",
        "default_null_value": "Unknown Origin",
        "aliases": ["main source", "origin", "main_source", "channel origin"],
    },
    "source_cluster": {
        "canonical_name": "source_cluster",
        "column_name": "cluster",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.source_master",
        "master_join_col": "source_cluster",
        "default_null_value": "Unclustered",
        "aliases": ["source cluster", "source_cluster", "channel cluster", "channel group"],
    },
    "lead_type": {
        "canonical_name": "lead_type",
        "column_name": "lead_type",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.source_master",
        "master_join_col": "lead_type",
        "default_null_value": "Unspecified",
        "aliases": ["lead type", "lead_type", "stage", "prospect stage", "lead status", "status", "inhouse", "in house", "outsource", "outsourced", "out sourced"],
    },
    "state": {
        "canonical_name": "state",
        "column_name": "state",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.state_master",
        "master_join_col": "state_name",
        "default_null_value": "Unknown State",
        "aliases": ["state", "state group", "region", "province"],
    },
    "state_code": {
        "canonical_name": "state_code",
        "column_name": "state_code",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.state_master",
        "master_join_col": "state_code",
        "default_null_value": "N/A",
        "aliases": ["state code", "state_code", "state iso"],
    },
    "zone": {
        "canonical_name": "zone",
        "column_name": "zone",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.state_master",
        "master_join_col": "zone",
        "default_null_value": "Unknown Zone",
        "aliases": ["zone", "geographic zone", "territory"],
    },
    "campus": {
        "canonical_name": "campus",
        "column_name": "campus_name",
        "table_name": "analytics.uploaded_metrics",
        "master_table": None,
        "master_join_col": None,
        "default_null_value": "Unknown Campus",
        "aliases": ["campus", "campus name", "location", "center"],
    },
    "academic_year": {
        "canonical_name": "academic_year",
        "column_name": "academic_year",
        "table_name": "analytics.uploaded_metrics",
        "master_table": None,
        "master_join_col": None,
        "default_null_value": 2026,
        "aliases": ["year", "academic year", "reporting year", "session year", "session"],
    },
    "owner": {
        "canonical_name": "owner",
        "column_name": "owner",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.employee_master",
        "master_join_col": "employee_name",
        "default_null_value": "Unassigned",
        "aliases": ["owner", "counsellor", "counsellors", "counselor", "counselors", "agent", "assigned to", "telecounselor"],
    },
    "team": {
        "canonical_name": "team",
        "column_name": "team",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.employee_master",
        "master_join_col": "team_name",
        "default_null_value": "Unassigned Team",
        "aliases": ["team", "sales team", "counseling team"],
    },
    "program_name": {
        "canonical_name": "program_name",
        "column_name": "program_name",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.course_master",
        "master_join_col": "program_name",
        "default_null_value": "Unmapped Program",
        "aliases": ["program", "program name", "course", "degree", "course name", "programme"],
    },
    "program_code": {
        "canonical_name": "program_code",
        "column_name": "program_code",
        "table_name": "organization.course_master",
        "master_table": "organization.course_master",
        "master_join_col": "program_code",
        "default_null_value": "N/A",
        "aliases": ["program code", "program_code", "course code"],
    },
    "course_cluster": {
        "canonical_name": "course_cluster",
        "column_name": "course_cluster",
        "table_name": "analytics.uploaded_metrics",
        "master_table": "organization.course_master",
        "master_join_col": "course_cluster",
        "default_null_value": "Unclustered Course",
        "aliases": ["course cluster", "course_cluster", "program cluster", "department"],
    },
    "specialization": {
        "canonical_name": "specialization",
        "column_name": "degree_type",
        "table_name": "organization.course_master",
        "master_table": "organization.course_master",
        "master_join_col": "degree_type",
        "default_null_value": "General",
        "aliases": ["specialization", "stream", "degree type", "branch"],
    },
}

DIMENSION_ALIAS_MAP: Dict[str, str] = {}
for dim_key, spec in DIMENSION_REGISTRY.items():
    DIMENSION_ALIAS_MAP[dim_key.lower()] = dim_key
    for alias in spec["aliases"]:
        DIMENSION_ALIAS_MAP[alias.lower()] = dim_key


def resolve_dimension_name(user_term: str) -> Optional[str]:
    """Resolve a raw user string to a canonical dimension name."""
    if not user_term:
        return None
    normalized = str(user_term).strip().lower().replace("-", " ").replace("_", " ")
    if normalized in DIMENSION_ALIAS_MAP:
        return DIMENSION_ALIAS_MAP[normalized]
    for key, spec in DIMENSION_REGISTRY.items():
        if normalized == key.replace("_", " "):
            return key
    return None


def get_dimension(dim_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve dimension definition for a canonical dimension name."""
    canonical = resolve_dimension_name(dim_name) or dim_name
    return DIMENSION_REGISTRY.get(canonical)
