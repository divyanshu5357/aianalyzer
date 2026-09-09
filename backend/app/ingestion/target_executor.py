import logging
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_targets_table(db: Session) -> None:
    """Ensures analytics.targets table and indexes exist idempotently."""
    try:
        db.execute(
            text(
                """
                CREATE SCHEMA IF NOT EXISTS analytics;
                CREATE TABLE IF NOT EXISTS analytics.targets (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    target_batch_id VARCHAR(100),
                    dataset_id UUID REFERENCES system.datasets(id) ON DELETE CASCADE,
                    academic_year INT NOT NULL,
                    campus_name VARCHAR(100) DEFAULT 'All',
                    month INT,
                    dimension_type VARCHAR(50) NOT NULL,
                    dimension_value VARCHAR(255) NOT NULL,
                    target_leads INT DEFAULT 0,
                    target_admissions INT DEFAULT 0,
                    target_cucet INT DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_targets_scope
                ON analytics.targets (academic_year, LOWER(campus_name), dimension_type, LOWER(dimension_value), month);
                CREATE INDEX IF NOT EXISTS idx_targets_dataset_id ON analytics.targets (dataset_id);
                CREATE INDEX IF NOT EXISTS idx_targets_batch_id ON analytics.targets (target_batch_id);
                """
            )
        )
        db.commit()
    except Exception as e:
        logger.warning("Notice ensuring analytics.targets table: %s", e)
        db.rollback()


def execute_target_ingestion(
    db: Session,
    dataset_id: str,
    target_batch_id: Optional[str] = None,
    academic_year: int = 2026,
    campus_name: str = "All",
) -> Dict[str, Any]:
    """
    Reads staging.records for target dataset_id, projects columns to canonical target schema,
    and inserts normalized target records into analytics.targets.
    Supports multi-sheet real target workbooks (Source, Program, State) as well as legacy schemas.
    """
    ensure_targets_table(db)

    if not target_batch_id:
        target_batch_id = f"target_batch_{uuid.uuid4().hex[:8]}"

    # Delete existing target records for this dataset_id if re-ingesting
    db.execute(
        text("DELETE FROM analytics.targets WHERE dataset_id = :dataset_id"),
        {"dataset_id": dataset_id},
    )

    # Check if this dataset has authentic multi-sheet target structure ('Target For' column)
    has_target_for = db.execute(
        text("SELECT 1 FROM staging.records WHERE dataset_id = :dataset_id AND raw_data ->> 'Target For' IS NOT NULL LIMIT 1"),
        {"dataset_id": dataset_id},
    ).scalar()

    if has_target_for:
        inserted_count = 0

        # 1. Overall from Source sheet
        sql_overall = """
        WITH src AS (
            SELECT 
                CASE 
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%mohali%' THEN 'Mohali'
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%unnao%' THEN 'Unnao'
                    ELSE 'All'
                END as campus_name,
                CASE LOWER(TRIM(COALESCE(r.raw_data->>'Month', '')))
                    WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3
                    WHEN 'apr' THEN 4 WHEN 'may' THEN 5 WHEN 'jun' THEN 6
                    WHEN 'jul' THEN 7 WHEN 'aug' THEN 8 WHEN 'sep' THEN 9
                    WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
                    ELSE NULL
                END as month,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('lead', 'leads') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_lead,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('admission', 'admissions') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_adm,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('cucet') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_cucet
            FROM staging.records r
            WHERE r.dataset_id = CAST(:dataset_id AS uuid)
              AND (r.raw_data->>'sheet_name' = 'Source' OR r.raw_data->>'sheet_name' IS NULL)
            GROUP BY 1, 2
        )
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, campus_name,
            month, 'overall', 'Overall', tgt_lead, tgt_adm, tgt_cucet
        FROM src
        WHERE month IS NOT NULL;
        """
        res1 = db.execute(text(sql_overall), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res1.rowcount or 0

        # 2. Overall 'All' campus
        sql_overall_all = """
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, 'All',
            month, 'overall', 'Overall', SUM(target_leads), SUM(target_admissions), SUM(target_cucet)
        FROM analytics.targets
        WHERE dataset_id = CAST(:dataset_id AS uuid)
          AND dimension_type = 'overall'
          AND campus_name != 'All'
        GROUP BY month;
        """
        res2 = db.execute(text(sql_overall_all), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res2.rowcount or 0

        # 3. Source dimension from Source sheet
        sql_source = """
        WITH src AS (
            SELECT 
                CASE 
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%mohali%' THEN 'Mohali'
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%unnao%' THEN 'Unnao'
                    ELSE 'All'
                END as campus_name,
                CASE LOWER(TRIM(COALESCE(r.raw_data->>'Month', '')))
                    WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3
                    WHEN 'apr' THEN 4 WHEN 'may' THEN 5 WHEN 'jun' THEN 6
                    WHEN 'jul' THEN 7 WHEN 'aug' THEN 8 WHEN 'sep' THEN 9
                    WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
                    ELSE NULL
                END as month,
                TRIM(COALESCE(r.raw_data->>'Source', 'Unknown')) as source_val,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('lead', 'leads') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_lead,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('admission', 'admissions') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_adm,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('cucet') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_cucet
            FROM staging.records r
            WHERE r.dataset_id = CAST(:dataset_id AS uuid)
              AND (r.raw_data->>'sheet_name' = 'Source' OR r.raw_data->>'sheet_name' IS NULL)
            GROUP BY 1, 2, 3
        )
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, campus_name,
            month, 'source', source_val, tgt_lead, tgt_adm, tgt_cucet
        FROM src
        WHERE month IS NOT NULL;
        """
        res3 = db.execute(text(sql_source), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res3.rowcount or 0

        # Source 'All' campus
        sql_source_all = """
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, 'All',
            month, 'source', dimension_value, SUM(target_leads), SUM(target_admissions), SUM(target_cucet)
        FROM analytics.targets
        WHERE dataset_id = CAST(:dataset_id AS uuid)
          AND dimension_type = 'source'
          AND campus_name != 'All'
        GROUP BY month, dimension_value;
        """
        res4 = db.execute(text(sql_source_all), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res4.rowcount or 0

        # 4. Program dimension from Program sheet
        sql_prog = """
        WITH src AS (
            SELECT 
                CASE 
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%mohali%' THEN 'Mohali'
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%unnao%' THEN 'Unnao'
                    ELSE 'All'
                END as campus_name,
                CASE LOWER(TRIM(COALESCE(r.raw_data->>'Month', '')))
                    WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3
                    WHEN 'apr' THEN 4 WHEN 'may' THEN 5 WHEN 'jun' THEN 6
                    WHEN 'jul' THEN 7 WHEN 'aug' THEN 8 WHEN 'sep' THEN 9
                    WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
                    ELSE NULL
                END as month,
                TRIM(COALESCE(r.raw_data->>'Program Code', 'Unknown')) as prog_code,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('lead', 'leads') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_lead,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('admission', 'admissions') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_adm,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('cucet') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_cucet
            FROM staging.records r
            WHERE r.dataset_id = CAST(:dataset_id AS uuid)
              AND r.raw_data->>'sheet_name' = 'Program'
            GROUP BY 1, 2, 3
        )
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, campus_name,
            month, 'program', prog_code, tgt_lead, tgt_adm, tgt_cucet
        FROM src
        WHERE month IS NOT NULL;
        """
        res5 = db.execute(text(sql_prog), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res5.rowcount or 0

        # Program 'All' campus
        sql_prog_all = """
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, 'All',
            month, 'program', dimension_value, SUM(target_leads), SUM(target_admissions), SUM(target_cucet)
        FROM analytics.targets
        WHERE dataset_id = CAST(:dataset_id AS uuid)
          AND dimension_type = 'program'
          AND campus_name != 'All'
        GROUP BY month, dimension_value;
        """
        res6 = db.execute(text(sql_prog_all), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res6.rowcount or 0

        # 5. State dimension from State sheet
        sql_state = """
        WITH src AS (
            SELECT 
                CASE 
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%mohali%' THEN 'Mohali'
                    WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Campus', ''))) LIKE '%unnao%' THEN 'Unnao'
                    ELSE 'All'
                END as campus_name,
                CASE LOWER(TRIM(COALESCE(r.raw_data->>'Month', '')))
                    WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3
                    WHEN 'apr' THEN 4 WHEN 'may' THEN 5 WHEN 'jun' THEN 6
                    WHEN 'jul' THEN 7 WHEN 'aug' THEN 8 WHEN 'sep' THEN 9
                    WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12
                    ELSE NULL
                END as month,
                TRIM(COALESCE(NULLIF(r.raw_data->>'State', ''), NULLIF(r.raw_data->>'Program Code', ''), 'Unknown')) as state_val,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('lead', 'leads') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_lead,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('admission', 'admissions') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_adm,
                ROUND(SUM(CASE WHEN LOWER(TRIM(COALESCE(r.raw_data->>'Target For', ''))) IN ('cucet') 
                    THEN CAST(COALESCE(NULLIF(r.raw_data->>'Final Target', ''), NULLIF(r.raw_data->>'Target', ''), '0') AS numeric) ELSE 0 END)) as tgt_cucet
            FROM staging.records r
            WHERE r.dataset_id = CAST(:dataset_id AS uuid)
              AND r.raw_data->>'sheet_name' = 'State'
            GROUP BY 1, 2, 3
        )
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, campus_name,
            month, 'state', state_val, tgt_lead, tgt_adm, tgt_cucet
        FROM src
        WHERE month IS NOT NULL;
        """
        res7 = db.execute(text(sql_state), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res7.rowcount or 0

        # State 'All' campus
        sql_state_all = """
        INSERT INTO analytics.targets (
            id, target_batch_id, dataset_id, academic_year, campus_name,
            month, dimension_type, dimension_value,
            target_leads, target_admissions, target_cucet
        )
        SELECT 
            gen_random_uuid(), :batch_id, CAST(:dataset_id AS uuid), :academic_year, 'All',
            month, 'state', dimension_value, SUM(target_leads), SUM(target_admissions), SUM(target_cucet)
        FROM analytics.targets
        WHERE dataset_id = CAST(:dataset_id AS uuid)
          AND dimension_type = 'state'
          AND campus_name != 'All'
        GROUP BY month, dimension_value;
        """
        res8 = db.execute(text(sql_state_all), {"dataset_id": dataset_id, "batch_id": target_batch_id, "academic_year": academic_year})
        inserted_count += res8.rowcount or 0

        db.commit()
        logger.info(f"Target multi-sheet ingestion complete for {dataset_id}: inserted {inserted_count} rows into analytics.targets.")
        return {
            "target_batch_id": target_batch_id,
            "dataset_id": dataset_id,
            "inserted_count": inserted_count,
        }

    # Fetch staged raw records for legacy schema
    rows = db.execute(
        text("SELECT raw_data FROM staging.records WHERE dataset_id = :dataset_id"),
        {"dataset_id": dataset_id},
    ).fetchall()

    if not rows:
        logger.warning(f"No staging records found for target dataset {dataset_id}")
        return {"target_batch_id": target_batch_id, "inserted_count": 0}

    inserted_count = 0
    for r in rows:
        raw = r[0] if isinstance(r[0], dict) else {}

        # Column mapping aliases
        t_leads = raw.get("Target Leads") or raw.get("target_leads") or raw.get("target_enquiries") or 0
        t_admissions = raw.get("Target Admissions") or raw.get("target_admissions") or raw.get("admissions_target") or 0
        t_cucet = raw.get("Target CUCET") or raw.get("target_cucet") or raw.get("cucet_target") or 0

        dim_type = str(raw.get("Dimension Type") or raw.get("dimension_type") or raw.get("level") or "overall").lower().strip()
        dim_value = str(raw.get("Dimension Value") or raw.get("dimension_value") or raw.get("value_name") or "Overall").strip()
        raw_month = raw.get("Target Month") or raw.get("target_month") or raw.get("month")

        month_val = None
        if raw_month is not None and str(raw_month).strip().isdigit():
            m_int = int(str(raw_month).strip())
            if 1 <= m_int <= 12:
                month_val = m_int

        # Parse metric floats (preserves small daily/granular target decimals)
        def safe_float(v: Any) -> float:
            if v is None:
                return 0.0
            try:
                s = str(v).strip().replace(",", "")
                return float(s)
            except (ValueError, TypeError):
                return 0.0

        target_leads = safe_float(t_leads)
        target_admissions = safe_float(t_admissions)
        target_cucet = safe_float(t_cucet)

        db.execute(
            text(
                """
                INSERT INTO analytics.targets (
                    id, target_batch_id, dataset_id, academic_year, campus_name,
                    month, dimension_type, dimension_value,
                    target_leads, target_admissions, target_cucet
                ) VALUES (
                    gen_random_uuid(), :batch_id, :dataset_id, :academic_year, :campus_name,
                    :month, :dim_type, :dim_value,
                    :target_leads, :target_admissions, :target_cucet
                )
                """
            ),
            {
                "batch_id": target_batch_id,
                "dataset_id": dataset_id,
                "academic_year": academic_year,
                "campus_name": campus_name,
                "month": month_val,
                "dim_type": dim_type,
                "dim_value": dim_value,
                "target_leads": target_leads,
                "target_admissions": target_admissions,
                "target_cucet": target_cucet,
            },
        )
        inserted_count += 1

    db.commit()
    logger.info(f"Target ingestion complete for {dataset_id}: inserted {inserted_count} target rows into analytics.targets.")

    return {
        "target_batch_id": target_batch_id,
        "dataset_id": dataset_id,
        "inserted_count": inserted_count,
    }
