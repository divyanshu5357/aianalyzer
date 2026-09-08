"""
State & Lead Type Canonicalization Migration Script (Instant Index-Backed)

Normalizes state and lead_type values in analytics.uploaded_metrics using
state_resolver and lead_type_resolver via index-backed IN lists, then refreshes analytics.dashboard_agg.
"""

import logging
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.normalization.state_resolver import resolve_state, STATE_LOOKUP, FOREIGN_LOCATIONS
from app.normalization.lead_type_resolver import resolve_lead_type, IN_HOUSE_KEYWORDS, OUT_SOURCED_KEYWORDS
from app.analytics.aggregate_refresh import refresh_dashboard_agg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_canonicalization() -> dict:
    session = SessionLocal()
    try:
        # 1. Count distinct states before
        before_query = text("SELECT COUNT(DISTINCT state) FROM analytics.uploaded_metrics WHERE state IS NOT NULL AND state != '';")
        before_count = session.execute(before_query).scalar() or 0

        # Fetch distinct state values
        states_query = text("SELECT DISTINCT state FROM analytics.uploaded_metrics WHERE state IS NOT NULL AND state != '';")
        distinct_states = [r[0] for r in session.execute(states_query).fetchall()]

        state_mapping = {raw: resolve_state(raw) for raw in distinct_states}

        # Group raw states by canonical state
        canonical_groups = {}
        for raw, canonical in state_mapping.items():
            if raw != canonical:
                canonical_groups.setdefault(canonical, []).append(raw)

        # Batch update states using index on state
        for canonical, raws in canonical_groups.items():
            session.execute(
                text("UPDATE analytics.uploaded_metrics SET state = :canonical WHERE state = ANY(:raws);"),
                {"canonical": canonical, "raws": raws},
            )

        # Handle NULL / empty / unrecognized -> UNMAPPED_STATE
        session.execute(text("UPDATE analytics.uploaded_metrics SET state = 'UNMAPPED_STATE' WHERE state IS NULL OR TRIM(state) = '';"))
        session.commit()

        # 2. Count distinct states after
        after_query = text("SELECT COUNT(DISTINCT state) FROM analytics.uploaded_metrics;")
        after_count = session.execute(after_query).scalar() or 0

        # 3. Canonicalize Lead Type based on source
        distinct_sources_query = text("SELECT DISTINCT source FROM analytics.uploaded_metrics WHERE source IS NOT NULL AND source != '';")
        distinct_sources = [r[0] for r in session.execute(distinct_sources_query).fetchall()]

        in_house_sources = []
        out_sourced_sources = []
        other_sources = []

        for src in distinct_sources:
            ltype = resolve_lead_type(src)
            if ltype == "IN HOUSE":
                in_house_sources.append(src)
            elif ltype == "OUT SOURCED":
                out_sourced_sources.append(src)
            else:
                other_sources.append(src)

        if in_house_sources:
            session.execute(
                text("UPDATE analytics.uploaded_metrics SET lead_type = 'IN HOUSE' WHERE source = ANY(:srcs);"),
                {"srcs": in_house_sources},
            )

        if out_sourced_sources:
            session.execute(
                text("UPDATE analytics.uploaded_metrics SET lead_type = 'OUT SOURCED' WHERE source = ANY(:srcs);"),
                {"srcs": out_sourced_sources},
            )

        if other_sources:
            session.execute(
                text("UPDATE analytics.uploaded_metrics SET lead_type = 'OTHERS' WHERE source = ANY(:srcs) OR lead_type IS NULL;"),
                {"srcs": other_sources},
            )

        session.execute(text("UPDATE analytics.uploaded_metrics SET lead_type = 'OTHERS' WHERE lead_type IS NULL OR TRIM(lead_type) = '';"))
        session.commit()

        # 4. Refresh pre-aggregated table
        logger.info("Refreshing analytics.dashboard_agg...")
        refresh_dashboard_agg(session)
        logger.info("Aggregate refresh complete!")

        res = {
            "distinct_states_before": before_count,
            "distinct_states_after": after_count,
            "state_reduction_pct": round((1 - (after_count / before_count if before_count else 1)) * 100, 2),
        }
        logger.info(f"Canonicalization Complete: {res}")
        print(f"RESULT_JSON={res}")
        return res

    except Exception as e:
        session.rollback()
        logger.error(f"Error during state canonicalization: {e}")
        raise e
    finally:
        session.close()


if __name__ == "__main__":
    run_canonicalization()
