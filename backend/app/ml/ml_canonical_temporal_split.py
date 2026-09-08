"""
Phase 11.5: Time-Aware Chronological Dataset Splitter
Prevents random data leakage across time periods by creating strict temporal splits:
- Train Set: 2025 Historical RAW records
- Validation Set: 2026 Early Cohort RAW records
- Test Set: 2026 Late Cohort RAW records
"""

import logging
from typing import Tuple, Dict, Any
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.ml_canonical_feature_pipeline import (
    CanonicalMLFeaturePipeline,
    CANONICAL_FEATURE_COLUMNS,
    TARGET_COLUMN,
)

logger = logging.getLogger(__name__)


def load_canonical_temporal_splits(
    db: Session,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Loads and returns (df_train, df_val, df_test, stats_dict)."""
    pipeline = CanonicalMLFeaturePipeline(db)

    # Extract all raw features across historical & current datasets
    df_all = pipeline.extract_features()
    if df_all.empty:
        raise ValueError("No canonical RAW dataset records found for ML training.")

    # Sort chronologically
    df_all = df_all.sort_values(by=["academic_year", "created_month", "created_dayofweek"]).reset_index(drop=True)

    # Dynamic chronological split based on available academic years
    distinct_years = [int(y) for y in sorted(list(df_all["academic_year"].unique()))]
    max_year = distinct_years[-1] if distinct_years else None

    if len(distinct_years) > 1 and max_year is not None:
        # Train: all historical records prior to latest cohort
        df_train = df_all[df_all["academic_year"] < max_year].reset_index(drop=True)
        df_latest = df_all[df_all["academic_year"] == max_year].reset_index(drop=True)

        # Split latest cohort chronologically: 50% validation, 50% test
        n_latest = len(df_latest)
        val_end = int(n_latest * 0.5)

        df_val = df_latest.iloc[:val_end].reset_index(drop=True)
        df_test = df_latest.iloc[val_end:].reset_index(drop=True)
    else:
        # Fallback to 70/15/15 chronological split if single year exists
        n = len(df_all)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)

        df_train = df_all.iloc[:train_end].reset_index(drop=True)
        df_val = df_all.iloc[train_end:val_end].reset_index(drop=True)
        df_test = df_all.iloc[val_end:].reset_index(drop=True)

    stats = {
        "total_records": len(df_all),
        "train_records": len(df_train),
        "val_records": len(df_val),
        "test_records": len(df_test),
        "train_positive_count": int(df_train[TARGET_COLUMN].sum()) if not df_train.empty else 0,
        "val_positive_count": int(df_val[TARGET_COLUMN].sum()) if not df_val.empty else 0,
        "test_positive_count": int(df_test[TARGET_COLUMN].sum()) if not df_test.empty else 0,
        "academic_years": [int(y) for y in sorted(list(df_all["academic_year"].unique()))],
    }

    logger.info(f"Canonical ML Temporal Split Stats: {stats}")
    return df_train, df_val, df_test, stats
