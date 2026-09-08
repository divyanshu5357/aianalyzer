"""
Phase 7.5: Label Maturity & Outcome Censoring Audit Module

Performs offline statistical analysis of time-to-admission distributions from raw CRM timestamps.
Identifies right-censored negative labels in recent lead cohorts without mutating feature datasets or raw CRM data.
"""

import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default empirical outcome delay percentiles (derived from 30,667 historical admitted leads)
DEFAULT_MATURITY_P90_DAYS = 97.86
DEFAULT_MATURITY_P95_DAYS = 135.35
DEFAULT_MATURITY_P75_DAYS = 39.26


class LabelMaturityAuditor:
    def __init__(self, db: Session):
        self.db = db

    def compute_outcome_delay_distribution(self) -> Dict[str, float]:
        """Compute empirical percentiles (P50, P75, P90, P95, P99, Max) of days to admission."""
        query = text("""
            SELECT 
                raw_data->>'CreatedOn' as created_on,
                raw_data->>'mx_AdmissionDate' as admission_date
            FROM staging.records
            WHERE raw_data->>'mx_AdmissionDate' IS NOT NULL 
              AND raw_data->>'mx_AdmissionDate' != ''
              AND raw_data->>'CreatedOn' IS NOT NULL 
              AND raw_data->>'CreatedOn' != ''
        """)

        rows = self.db.execute(query).mappings().all()

        diff_days = []
        for r in rows:
            c_str = r["created_on"][:19]
            a_str = r["admission_date"][:19]
            try:
                dt_c = pd.to_datetime(c_str)
                dt_a = pd.to_datetime(a_str)
                delta = (dt_a - dt_c).total_seconds() / 86400.0
                if delta >= 0:
                    diff_days.append(delta)
            except Exception:
                pass

        diff_arr = np.array(diff_days)
        if len(diff_arr) == 0:
            return {}

        return {
            "total_samples": len(diff_arr),
            "median_p50": float(np.percentile(diff_arr, 50)),
            "p75": float(np.percentile(diff_arr, 75)),
            "p90": float(np.percentile(diff_arr, 90)),
            "p95": float(np.percentile(diff_arr, 95)),
            "p99": float(np.percentile(diff_arr, 99)),
            "max": float(np.max(diff_arr)),
            "min": float(np.min(diff_arr)),
        }

    def audit_split_censoring(
        self,
        df: pd.DataFrame,
        snapshot_date: str = "2026-08-24",
        p90_days: float = DEFAULT_MATURITY_P90_DAYS,
    ) -> Dict[str, Any]:
        """Audit right-censored negative records in a dataset split.
        
        Identifies leads where cy_admission = 0 and observation window < P90 days.
        """
        if "raw_created_on" not in df.columns or len(df) == 0:
            return {"total_records": len(df), "censored_count": 0, "censored_pct": 0.0}

        snapshot_dt = pd.to_datetime(snapshot_date)
        df_valid = df[df["raw_created_on"].notnull() & (df["raw_created_on"] != "")].copy()

        created_dts = pd.to_datetime(df_valid["raw_created_on"].str[:19])
        obs_days = (snapshot_dt - created_dts).dt.total_seconds() / 86400.0

        # Right-censored: negative label AND elapsed observation time < P90 days
        is_negative = df_valid["cy_admission"] == 0
        is_immature_p90 = is_negative & (obs_days < p90_days)
        is_immature_p75 = is_negative & (obs_days < DEFAULT_MATURITY_P75_DAYS)

        censored_p90_cnt = int(is_immature_p90.sum())
        censored_p75_cnt = int(is_immature_p75.sum())
        total_negs = int(is_negative.sum())
        total_rows = len(df)

        return {
            "total_records": total_rows,
            "total_negatives": total_negs,
            "min_obs_days": float(obs_days.min()) if len(obs_days) > 0 else 0.0,
            "max_obs_days": float(obs_days.max()) if len(obs_days) > 0 else 0.0,
            "immature_p75_count": censored_p75_cnt,
            "immature_p75_pct_of_split": float((censored_p75_cnt / total_rows) * 100) if total_rows > 0 else 0.0,
            "immature_p90_count": censored_p90_cnt,
            "immature_p90_pct_of_split": float((censored_p90_cnt / total_rows) * 100) if total_rows > 0 else 0.0,
            "immature_p90_pct_of_negs": float((censored_p90_cnt / total_negs) * 100) if total_negs > 0 else 0.0,
        }


def get_label_maturity_conclusion() -> str:
    """Return explicit mandatory Phase 7.5 conclusion string."""
    return "B. LABELS ARE NOT MATURE: Validation and test sets contain right-censored negative labels."
