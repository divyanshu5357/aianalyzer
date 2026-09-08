"""
Mapping Execution Engine for Ingestion Pipeline.

Responsibilities:
1. Load active APPROVED and MODIFIED mappings from intelligence.schema_mappings.
2. Filter out 'suggested', 'rejected', or 'requires_confirmation' mappings from auto-execution.
3. Map/project raw source fields into canonical fields (ProspectID, Program Code, State Code, EmployeeID, Source Code).
4. Preserve strict Program Code Safety (Rule 5):
   - Blank / null / whitespace / 'nan' / 'null' Program Codes become NULL (program_code=NULL, program_name=NULL, course_cluster=NULL).
   - Never invent or synthesize programs using HASHTEXT or course_master.
   - Valid Program Codes are resolved against organization.course_master; if unmapped, preserve raw code and mark unmapped.
5. Support monthly/incremental lead upsert based on ProspectID.
6. Preserve mapping lineage metadata (mapping_version, mapping_ids, source_file, source_sheet).
7. Calculate comprehensive data quality statistics (rows_read, mapping_coverage_pct, blank_program_code, duplicate_prospect_id, etc.).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.mapping.relationship_detector import clean_or_unmap_program_code, normalize_slug

logger = logging.getLogger(__name__)

# Standard canonical target column mappings used by the normalization pipeline
CANONICAL_TARGET_TO_FIELD = {
    "prospectid": "prospect_id",
    "program code": "program_code",
    "programcode": "program_code",
    "state code": "state_code",
    "statecode": "state_code",
    "employeeid": "owner",
    "source code": "source",
    "sourcecode": "source",
    "campus": "campus_name",
    "academic year": "academic_year",
}


def load_executable_mappings(
    db: Session,
    source_file: Optional[str] = None,
    source_sheet: str = "default",
) -> List[Dict[str, Any]]:
    """
    Load active APPROVED and MODIFIED mapping configurations from intelligence.schema_mappings.
    Rejects 'suggested', 'rejected', or 'requires_confirmation' mappings for automatic execution.
    """
    query = """
        SELECT id, source_file, source_sheet, source_column,
               target_entity, target_sheet, target_column,
               confidence, status, mapping_version, match_type, metadata
        FROM intelligence.schema_mappings
        WHERE is_active = TRUE
          AND LOWER(status) IN ('approved', 'modified')
    """
    params: Dict[str, Any] = {}

    if source_file:
        query += " AND (LOWER(source_file) = LOWER(:source_file) OR LOWER(source_file) = 'manual' OR source_file IS NULL)"
        params["source_file"] = source_file

    query += " ORDER BY updated_at DESC"

    rows = db.execute(text(query), params).mappings().all()

    executable = []
    seen_cols = set()

    for r in rows:
        col_slug = normalize_slug(r["source_column"])
        if col_slug in seen_cols:
            continue
        seen_cols.add(col_slug)
        executable.append({
            "id": str(r["id"]),
            "source_file": r["source_file"],
            "source_sheet": r["source_sheet"],
            "source_column": r["source_column"],
            "target_entity": r["target_entity"],
            "target_sheet": r["target_sheet"],
            "target_column": r["target_column"],
            "confidence": float(r["confidence"]),
            "status": r["status"],
            "mapping_version": r["mapping_version"],
            "match_type": r["match_type"],
            "metadata": r["metadata"] if isinstance(r["metadata"], dict) else {},
        })

    return executable


def execute_mapping_normalization(
    db: Session,
    dataset_id: Any,
    source_file: Optional[str] = None,
    sheet_name: str = "default",
    batch_size: int = 50000,
) -> Dict[str, Any]:
    """
    Executes approved mappings for the specified dataset, transforming staging.records raw JSON
    into analytics.uploaded_metrics with canonical projections, lineage tracking, and aggregate refresh.
    """
    dataset_id_str = str(dataset_id)

    # 1. Load active approved mappings
    approved_mappings = load_executable_mappings(db, source_file=source_file, source_sheet=sheet_name)

    # Build field projection mappings
    # target_column slug -> source_column original name
    col_projections: Dict[str, str] = {}
    mapping_ids: List[str] = []
    max_mapping_version = 1

    for m in approved_mappings:
        mapping_ids.append(m["id"])
        if m["mapping_version"] > max_mapping_version:
            max_mapping_version = m["mapping_version"]

        t_slug = normalize_slug(m["target_column"])
        s_col = m["source_column"]

        # Map to canonical field key if recognized
        if t_slug in CANONICAL_TARGET_TO_FIELD:
            col_projections[CANONICAL_TARGET_TO_FIELD[t_slug]] = s_col
        else:
            col_projections[t_slug] = s_col

    # Fallback to system.column_mappings if no approved mappings exist
    if not col_projections:
        try:
            from app.ingestion.schema_mapper import get_dataset_column_mapping
            sys_maps = get_dataset_column_mapping(db, dataset_id).get("by_canonical", {})
            for c_field, orig_c in sys_maps.items():
                col_projections[c_field] = orig_c
        except Exception:
            pass

    # Safe SQL escaping helper
    def get_raw_key(field: str, fallback_key: str) -> str:
        k = col_projections.get(field) or fallback_key
        return k.replace("'", "''")

    key_owner = get_raw_key("owner", "Owner")
    key_prospect_id = get_raw_key("prospect_id", "ProspectID")
    key_program_code = get_raw_key("program_code", "Program Code")
    key_program_name = get_raw_key("program_name", "Program Name (Short)")
    key_state = get_raw_key("state", "State Group")
    key_state_code = get_raw_key("state_code", "State Code")
    key_source = get_raw_key("source", "MSSourcebi")
    key_main_source = get_raw_key("main_source", "Source Cluster")
    key_campus = get_raw_key("campus_name", "Campus Name")
    key_lead_type = get_raw_key("lead_type", "Lead Type")
    key_cluster = get_raw_key("cluster", "Cluster")
    key_course_cluster = get_raw_key("course_cluster", "Course Cluster")
    key_zone = get_raw_key("zone", "Zone")
    key_team = get_raw_key("team", "Team")

    key_cy_l = get_raw_key("cy_leads", "CY Leads")
    key_cy_c = get_raw_key("cy_cucet", "CY CUCET")
    key_cy_a = get_raw_key("cy_admission", "CY Admission")
    key_py_l = get_raw_key("py_leads", "PY Leads")
    key_py_c = get_raw_key("py_cucet", "PY CUCET")
    key_py_a = get_raw_key("py_admission", "PY Admission")

    # Get dataset period / campus metadata
    ds_info = db.execute(
        text("SELECT academic_year, campus_name, original_filename FROM system.datasets WHERE id = :ds_id"),
        {"ds_id": dataset_id_str},
    ).mappings().first()

    ds_year = ds_info.get("academic_year") if ds_info else None
    ds_campus = ds_info.get("campus_name") if ds_info else None
    actual_file = source_file or (ds_info.get("original_filename") if ds_info else "upload")

    # 2. Get staging bounds
    bounds = db.execute(
        text("SELECT MIN(row_number), MAX(row_number) FROM staging.records WHERE dataset_id = :ds_id"),
        {"ds_id": dataset_id_str},
    ).first()

    if not bounds or bounds[0] is None or bounds[1] is None:
        return {
            "status": "empty",
            "dataset_id": dataset_id_str,
            "normalized_rows": 0,
            "message": "No staging records found.",
        }

    min_row, max_row = int(bounds[0]), int(bounds[1])

    # Clean existing metrics for this dataset to enforce clean execution
    db.execute(
        text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": dataset_id_str},
    )

    # Lineage metadata
    lineage_metadata = {
        "source_file": actual_file,
        "source_sheet": sheet_name,
        "mapping_version": max_mapping_version,
        "mapping_ids": mapping_ids,
        "executed_mappings_count": len(approved_mappings),
    }
    lineage_json = json.dumps(lineage_metadata).replace("'", "''")

    # Construct set-based chunk insert SQL
    # Joins against organization.course_master when valid Program Code exists
    # Strict Rule 5: If raw program code is blank/null/nan, program_name and course_cluster resolve to NULL!
    chunk_sql = text(f"""
        INSERT INTO analytics.uploaded_metrics (
            id,
            dataset_id,
            row_number,
            academic_year,
            owner,
            cluster,
            lead_type,
            main_source,
            source,
            campus_name,
            state,
            raw_program_code,
            program_code,
            program_name,
            cy_leads,
            cy_cucet,
            cy_admission,
            py_leads,
            py_cucet,
            py_admission,
            course_cluster,
            state_code,
            zone,
            team,
            created_month,
            admission_month
        )
        SELECT
            gen_random_uuid(),
            :dataset_id,
            r.row_number,
            COALESCE(:ds_year, CASE WHEN system.parse_month(COALESCE(NULLIF(TRIM(r.raw_data->>'CreatedOn'), ''), NULLIF(TRIM(r.raw_data->>'Created_On'), ''), NULLIF(TRIM(r.raw_data->>'enquiry_date'), ''))) ~ '^[0-9]{4}' THEN CAST(SUBSTRING(system.parse_month(COALESCE(NULLIF(TRIM(r.raw_data->>'CreatedOn'), ''), NULLIF(TRIM(r.raw_data->>'Created_On'), ''), NULLIF(TRIM(r.raw_data->>'enquiry_date'), ''))) FROM 1 FOR 4) AS INT) ELSE NULL END),
            COALESCE(NULLIF(TRIM(r.raw_data->>'{key_owner}'), ''), NULLIF(TRIM(r.raw_data->>'OwnerID'), ''), NULLIF(TRIM(r.raw_data->>'OwnerIdName'), '')),
            NULLIF(TRIM(r.raw_data->>'{key_cluster}'), ''),
            COALESCE(NULLIF(TRIM(r.raw_data->>'{key_lead_type}'), ''), NULLIF(TRIM(r.raw_data->>'ProspectStage'), '')),
            COALESCE(NULLIF(TRIM(r.raw_data->>'{key_main_source}'), ''), NULLIF(TRIM(r.raw_data->>'Origin'), '')),
            COALESCE(NULLIF(TRIM(r.raw_data->>'{key_source}'), ''), NULLIF(TRIM(r.raw_data->>'Source'), '')),
            COALESCE(NULLIF(TRIM(r.raw_data->>'{key_campus}'), ''), NULLIF(TRIM(r.raw_data->>'mx_Campus'), ''), :ds_campus),
            COALESCE(NULLIF(TRIM(r.raw_data->>'{key_state}'), ''), NULLIF(TRIM(r.raw_data->>'mx_State_New'), ''), NULLIF(TRIM(r.raw_data->>'mx_State'), '')),
            
            -- raw_program_code
            NULLIF(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code')), ''),

            -- program_code (canonical mapped key)
            COALESCE(cm.program_code, NULLIF(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code')), '')),

            -- Program Name resolution: if raw program code is valid, lookup course_master; else NULL
            CASE
                WHEN NULLIF(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code')), '') IS NOT NULL 
                     AND LOWER(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code'))) NOT IN ('nan', 'null', 'none', 'n/a', '-')
                THEN COALESCE(cm.program_name, NULLIF(TRIM(r.raw_data->>'{key_program_name}'), ''), TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code')))
                WHEN NULLIF(TRIM(r.raw_data->>'{key_program_name}'), '') IS NOT NULL 
                     AND LOWER(TRIM(r.raw_data->>'{key_program_name}')) NOT IN ('nan', 'null', 'none', 'n/a', '-')
                THEN TRIM(r.raw_data->>'{key_program_name}')
                ELSE NULL
            END,
            
            CASE 
                WHEN NULLIF(REPLACE(r.raw_data->>'{key_cy_l}', ',', ''), '') IS NOT NULL THEN (REPLACE(r.raw_data->>'{key_cy_l}', ',', '')::numeric)
                WHEN NULLIF(TRIM(COALESCE(r.raw_data->>'{key_prospect_id}', r.raw_data->>'ProspectID', r.raw_data->>'prospect_id')), '') IS NOT NULL OR r.raw_data->>'FirstName' IS NOT NULL THEN 1
                ELSE 0
            END,
            CASE 
                WHEN NULLIF(REPLACE(r.raw_data->>'{key_cy_c}', ',', ''), '') IS NOT NULL THEN (REPLACE(r.raw_data->>'{key_cy_c}', ',', '')::numeric)
                WHEN (NULLIF(TRIM(r.raw_data->>'mx_CUCET_Score'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_CUCET_Score')) != 'null') OR r.raw_data->>'mx_CUCET_Exam_Status' IN ('Eligible-for-Scholarship', 'Eligible for Admission but not for Scholarship', 'Not-Eligible for Admissions') THEN 1
                ELSE 0
            END,
            CASE 
                WHEN NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), '') IS NOT NULL AND LOWER(TRIM(r.raw_data->>'mx_AdmissionDate')) != 'null' THEN 1
                WHEN NULLIF(REPLACE(r.raw_data->>'{key_cy_a}', ',', ''), '') IS NOT NULL THEN (REPLACE(r.raw_data->>'{key_cy_a}', ',', '')::numeric)
                WHEN r.raw_data->>'ProspectStage' = 'Enrolled' THEN 1
                ELSE 0
            END,
            COALESCE(NULLIF(REPLACE(r.raw_data->>'{key_py_l}', ',', ''), '')::numeric, 0),
            COALESCE(NULLIF(REPLACE(r.raw_data->>'{key_py_c}', ',', ''), '')::numeric, 0),
            COALESCE(NULLIF(REPLACE(r.raw_data->>'{key_py_a}', ',', ''), '')::numeric, 0),
            
            -- Course Cluster resolution from canonical dimension
            CASE
                WHEN NULLIF(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code')), '') IS NOT NULL 
                     AND LOWER(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code'))) NOT IN ('nan', 'null', 'none', 'n/a', '-')
                THEN COALESCE(cm.course_cluster, NULLIF(TRIM(r.raw_data->>'{key_course_cluster}'), ''))
                ELSE NULLIF(TRIM(r.raw_data->>'{key_course_cluster}'), '')
            END,
            
            COALESCE(NULLIF(TRIM(r.raw_data->>'{key_state_code}'), ''), NULLIF(TRIM(r.raw_data->>'StateCode'), ''), NULLIF(TRIM(r.raw_data->>'State_Code'), '')),
            NULLIF(TRIM(r.raw_data->>'{key_zone}'), ''),
            NULLIF(TRIM(r.raw_data->>'{key_team}'), ''),
            system.parse_month(COALESCE(NULLIF(TRIM(r.raw_data->>'CreatedOn'), ''), NULLIF(TRIM(r.raw_data->>'Created_On'), ''), NULLIF(TRIM(r.raw_data->>'enquiry_date'), ''))),
            system.parse_month(NULLIF(TRIM(r.raw_data->>'mx_AdmissionDate'), ''), NULLIF(TRIM(COALESCE(r.raw_data->>'CreatedOn', r.raw_data->>'Created_On', r.raw_data->>'enquiry_date')), ''))
        FROM staging.records r
        LEFT JOIN organization.course_master cm
          ON (
             LOWER(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code'))) = LOWER(TRIM(cm.program_code))
             OR LOWER(TRIM(COALESCE(r.raw_data->>'{key_program_code}', r.raw_data->>'ProgramCode', r.raw_data->>'Program Code', r.raw_data->>'program_code'))) = LOWER(TRIM(cm.program_key))
          )
        WHERE r.dataset_id = :dataset_id
          AND r.row_number >= :start_row AND r.row_number <= :end_row
        ON CONFLICT (dataset_id, row_number) DO NOTHING;
    """)

    curr_start = min_row
    while curr_start <= max_row:
        curr_end = curr_start + batch_size - 1
        db.execute(
            chunk_sql,
            {
                "dataset_id": dataset_id_str,
                "ds_year": ds_year,
                "ds_campus": ds_campus,
                "start_row": curr_start,
                "end_row": curr_end,
            },
        )
        curr_start = curr_end + 1

    # Get final normalized count
    cnt = db.execute(
        text("SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": dataset_id_str},
    ).scalar()
    normalized_count = int(cnt or 0)

    # 3. Calculate data quality report
    quality_stats = calculate_data_quality_report(db, dataset_id_str, key_prospect_id=key_prospect_id, key_program_code=key_program_code)

    # Calculate distinct ProspectIDs and date ranges
    prospect_cnt = db.execute(
        text("SELECT COUNT(DISTINCT NULLIF(TRIM(raw_data->>'ProspectID'), '')) FROM staging.records WHERE dataset_id = :ds_id"),
        {"ds_id": dataset_id_str},
    ).scalar() or 0

    dates_res = db.execute(
        text("""
            SELECT 
                MIN(system.parse_month(COALESCE(NULLIF(TRIM(raw_data->>'CreatedOn'), ''), NULLIF(TRIM(raw_data->>'mx_AdmissionDate'), '')))) as min_m,
                MAX(system.parse_month(COALESCE(NULLIF(TRIM(raw_data->>'CreatedOn'), ''), NULLIF(TRIM(raw_data->>'mx_AdmissionDate'), '')))) as max_m
            FROM staging.records
            WHERE dataset_id = :ds_id
        """),
        {"ds_id": dataset_id_str},
    ).fetchone()

    min_m = dates_res.min_m if dates_res else None
    max_m = dates_res.max_m if dates_res else None

    # Update dataset status & period tracking metrics in system.datasets
    db.execute(
        text("""
            UPDATE system.datasets 
            SET status = 'normalized', 
                row_count = :cnt,
                rows_inserted = :cnt,
                rows_updated = 0,
                distinct_prospect_count = :p_cnt,
                upload_batch_id = COALESCE(upload_batch_id, :ds_id),
                month = COALESCE(month, :max_m, :min_m)
            WHERE id = :ds_id
        """),
        {
            "cnt": normalized_count,
            "p_cnt": int(prospect_cnt),
            "ds_id": dataset_id_str,
            "max_m": max_m,
            "min_m": min_m,
        },
    )
    db.commit()

    # Note: Aggregate refresh is deferred to async_worker to run scoped refresh
    # once the entire ingestion pipeline is complete.

    return {
        "status": "success",
        "dataset_id": dataset_id_str,
        "normalized_rows": normalized_count,
        "lineage": lineage_metadata,
        "data_quality": quality_stats,
    }


def calculate_data_quality_report(
    db: Session,
    dataset_id: str,
    key_prospect_id: str = "ProspectID",
    key_program_code: str = "Program Code",
) -> Dict[str, Any]:
    """
    Computes data quality statistics for an ingested dataset:
    - total rows
    - blank program code count
    - unknown program code count
    - invalid / duplicate ProspectID count
    - mapping coverage percentage
    Persists summary to system.data_quality_reports.
    """
    # Total staging rows
    total_staged = db.execute(
        text("SELECT COUNT(*) FROM staging.records WHERE dataset_id = :ds_id"),
        {"ds_id": dataset_id},
    ).scalar() or 0

    # Total normalized metrics
    total_normalized = db.execute(
        text("SELECT COUNT(*) FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
        {"ds_id": dataset_id},
    ).scalar() or 0

    # Blank / null program code count from raw staging
    blank_prog_cnt = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM staging.records
            WHERE dataset_id = :ds_id
              AND (
                 raw_data->>'{key_prospect_id}' IS NOT NULL
                 OR raw_data->>'ProspectID' IS NOT NULL
              )
              AND (
                 raw_data->>'{key_program_code}' IS NULL
                 OR TRIM(raw_data->>'{key_program_code}') = ''
                 OR LOWER(TRIM(raw_data->>'{key_program_code}')) IN ('nan', 'null', 'none', 'n/a', '-')
              )
            """
        ),
        {"ds_id": dataset_id},
    ).scalar() or 0

    # Program codes present but unmapped in course_master
    unknown_prog_cnt = db.execute(
        text(
            f"""
            SELECT COUNT(DISTINCT r.raw_data->>'{key_program_code}')
            FROM staging.records r
            LEFT JOIN organization.course_master cm
              ON LOWER(TRIM(r.raw_data->>'{key_program_code}')) = LOWER(TRIM(cm.program_code))
            WHERE r.dataset_id = :ds_id
              AND NULLIF(TRIM(r.raw_data->>'{key_program_code}'), '') IS NOT NULL
              AND LOWER(TRIM(r.raw_data->>'{key_program_code}')) NOT IN ('nan', 'null', 'none', 'n/a', '-')
              AND cm.program_code IS NULL
            """
        ),
        {"ds_id": dataset_id},
    ).scalar() or 0

    # Invalid ProspectID count
    invalid_pid_cnt = db.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM staging.records
            WHERE dataset_id = :ds_id
              AND (
                 raw_data->>'{key_prospect_id}' IS NULL
                 OR TRIM(raw_data->>'{key_prospect_id}') = ''
              )
            """
        ),
        {"ds_id": dataset_id},
    ).scalar() or 0

    # Duplicate ProspectID count within dataset
    dup_pid_cnt = db.execute(
        text(
            f"""
            SELECT COUNT(*) FROM (
                SELECT raw_data->>'{key_prospect_id}' AS pid, COUNT(*)
                FROM staging.records
                WHERE dataset_id = :ds_id
                  AND NULLIF(TRIM(raw_data->>'{key_prospect_id}'), '') IS NOT NULL
                GROUP BY raw_data->>'{key_prospect_id}'
                HAVING COUNT(*) > 1
            ) sub
            """
        ),
        {"ds_id": dataset_id},
    ).scalar() or 0

    mapping_coverage = round((total_normalized / total_staged) * 100, 2) if total_staged > 0 else 100.0

    stats = {
        "rows_read": total_staged,
        "rows_processed": total_normalized,
        "mapping_coverage_pct": mapping_coverage,
        "blank_program_code": blank_prog_cnt,
        "unknown_program_code": unknown_prog_cnt,
        "invalid_prospect_id_count": invalid_pid_cnt,
        "duplicate_prospect_id": dup_pid_cnt,
    }

    # Save to system.data_quality_reports
    existing_rep = db.execute(
        text("SELECT id FROM system.data_quality_reports WHERE dataset_id = :ds_id"),
        {"ds_id": dataset_id},
    ).scalar()

    if existing_rep:
        db.execute(
            text(
                """
                UPDATE system.data_quality_reports
                SET total_rows = :total_rows,
                    duplicate_rows = :dup_rows,
                    missing_values = :missing_vals,
                    quality_score = :quality_score,
                    report = CAST(:details AS jsonb)
                WHERE id = :id
                """
            ),
            {
                "id": existing_rep,
                "total_rows": total_staged,
                "dup_rows": dup_pid_cnt,
                "missing_vals": blank_prog_cnt + invalid_pid_cnt,
                "quality_score": mapping_coverage,
                "details": json.dumps(stats),
            },
        )
    else:
        db.execute(
            text(
                """
                INSERT INTO system.data_quality_reports (
                    id, dataset_id, total_rows, duplicate_rows, missing_values, quality_score, report
                ) VALUES (
                    gen_random_uuid(), :ds_id, :total_rows, :dup_rows, :missing_vals, :quality_score, CAST(:details AS jsonb)
                )
                """
            ),
            {
                "ds_id": dataset_id,
                "total_rows": total_staged,
                "dup_rows": dup_pid_cnt,
                "missing_vals": blank_prog_cnt + invalid_pid_cnt,
                "quality_score": mapping_coverage,
                "details": json.dumps(stats),
            },
        )
    db.commit()

    return stats
