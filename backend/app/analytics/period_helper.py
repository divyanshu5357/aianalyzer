"""
Dynamic period, academic year, and campus resolution helpers.
Guarantees zero hardcoded business values across analytics and reports.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_active_or_max_academic_year(db: Session) -> int:
    """
    Dynamically resolves the active or maximum analytical academic year.
    Never relies on hardcoded year integers.
    
    Resolution order:
    1. Active dataset period_end_year or academic_year from system.datasets.
    2. MAX(academic_year) from system.datasets WHERE is_analytics_enabled = true.
    3. MAX(period_end_year) from system.datasets.
    4. MAX(academic_year) from analytics.dashboard_agg.
    5. Current calendar year as last-resort safety fallback.
    """
    try:
        # 1. Active dataset
        row = db.execute(
            text("""
                SELECT academic_year, period_end_year
                FROM system.datasets
                WHERE is_active = true OR is_period_active = true
                ORDER BY is_period_active DESC, is_active DESC, created_at DESC
                LIMIT 1
            """)
        ).mappings().first()
        if row:
            if row.get("academic_year"):
                return int(row["academic_year"])
            if row.get("period_end_year"):
                return int(row["period_end_year"])

        # 2. Max academic_year from analytics-enabled datasets
        row_max = db.execute(
            text("""
                SELECT MAX(academic_year) as max_year
                FROM system.datasets
                WHERE is_analytics_enabled = true AND academic_year IS NOT NULL
            """)
        ).mappings().first()
        if row_max and row_max.get("max_year"):
            return int(row_max["max_year"])

        # 3. Max period_end_year from all datasets
        row_period = db.execute(
            text("""
                SELECT MAX(period_end_year) as max_year
                FROM system.datasets
                WHERE period_end_year IS NOT NULL
            """)
        ).mappings().first()
        if row_period and row_period.get("max_year"):
            return int(row_period["max_year"])

        # 4. Max academic_year from aggregate table
        row_agg = db.execute(
            text("""
                SELECT MAX(academic_year) as max_year
                FROM analytics.dashboard_agg
                WHERE academic_year IS NOT NULL
            """)
        ).mappings().first()
        if row_agg and row_agg.get("max_year"):
            return int(row_agg["max_year"])

    except Exception as exc:
        logger.warning("Could not dynamically resolve active academic year: %s", exc)

    # 5. Last resort fallback
    return datetime.now().year


def get_available_campuses_from_db(db: Session) -> list[str]:
    """
    Dynamically returns distinct campus names present in database.
    """
    try:
        # Check campus master
        rows = db.execute(
            text("SELECT DISTINCT campus_name FROM organization.campus_master WHERE campus_name IS NOT NULL ORDER BY campus_name")
        ).scalars().all()
        if rows:
            return [str(r).strip() for r in rows if str(r).strip()]

        # Check aggregate table
        rows_agg = db.execute(
            text("SELECT DISTINCT campus FROM analytics.dashboard_agg WHERE campus IS NOT NULL AND campus != '' ORDER BY campus")
        ).scalars().all()
        if rows_agg:
            return [str(r).strip() for r in rows_agg if str(r).strip()]
    except Exception as exc:
        logger.warning("Could not dynamically resolve available campuses: %s", exc)

    return []
