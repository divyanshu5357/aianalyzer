"""
Phase 7: Temporal Train / Validation / Test Dataset Construction Pipeline

Constructs leakage-safe, strictly chronological temporal splits across all production datasets.
Persists datasets to parquet format for Phase 8 baseline model training.
"""

import os
import logging
from typing import Dict, Any, Tuple
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ml.ml_feature_pipeline import (
    MLFeaturePipeline,
    validate_no_leakage,
    FORBIDDEN_LEAKAGE_FIELDS,
    TARGET_COLUMN,
)

logger = logging.getLogger(__name__)

# Pure t0 Accepted Feature Columns (Excludes cy_cucet per Phase 7 timing audit)
PURE_T0_FEATURE_COLUMNS = [
    "campus_name",
    "academic_year",
    "source_canonical",
    "state_canonical",
    "state_code",
    "zone",
    "owner_canonical",
    "team",
    "created_month",
    "created_dayofweek",
    "created_hour",
]

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


class TemporalSplitter:
    def __init__(self, db: Session, data_dir: str = DEFAULT_DATA_DIR):
        self.db = db
        self.data_dir = data_dir
        self.pipeline = MLFeaturePipeline(db)
        os.makedirs(self.data_dir, exist_ok=True)

    def build_and_save_splits(self) -> Dict[str, Any]:
        """Extract features, partition into chronological splits, validate, and persist to parquet."""
        logger.info("Extracting raw metrics and timestamps for temporal splitting...")

        query = text("""
            SELECT 
                u.id,
                u.dataset_id,
                u.campus_name,
                u.academic_year,
                u.owner,
                u.main_source,
                u.source,
                u.state,
                u.created_at,
                u.cy_admission,
                s.raw_data->>'CreatedOn' as raw_created_on
            FROM analytics.uploaded_metrics u
            JOIN system.datasets d ON u.dataset_id = d.id
            LEFT JOIN staging.records s ON s.dataset_id = u.dataset_id AND s.row_number = u.row_number
            WHERE d.is_analytics_enabled = TRUE
            ORDER BY u.created_at ASC
        """)

        rows = self.db.execute(query).mappings().all()
        logger.info(f"Total raw rows fetched for temporal splitting: {len(rows)}")

        train_rows = []
        val_rows = []
        test_rows = []

        seen_ids = set()

        for r in rows:
            record_id = str(r["id"])
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            raw_dt = r["raw_created_on"]
            ay = r["academic_year"]

            # Chronological splitting boundary definition
            if ay == 2025:
                split_tag = "train"
            elif raw_dt and raw_dt < "2026-05-01":
                split_tag = "train"
            elif raw_dt and raw_dt < "2026-07-01":
                split_tag = "val"
            elif raw_dt:
                split_tag = "test"
            else:
                split_tag = "train"

            # Feature Engineering & Normalization via Pipeline
            state_res = self.pipeline.state_resolver.resolve(r["state"])
            source_res = self.pipeline.source_resolver.resolve(r["source"] or r["main_source"])
            emp_res = self.pipeline.employee_resolver.resolve(r["owner"])

            state_canonical = state_res.canonical_value or "UNMAPPED_STATE"
            state_code = state_res.extra.get("state_code") or "UNMAPPED_CODE"
            zone = state_res.extra.get("zone") or emp_res.extra.get("zone") or "UNMAPPED_ZONE"

            source_canonical = source_res.canonical_value or "UNMAPPED_SOURCE"
            owner_canonical = emp_res.canonical_value or "UNMAPPED_OWNER"
            team = emp_res.extra.get("team") or "UNMAPPED_TEAM"

            created_dt = r["created_at"]
            if created_dt:
                created_month = created_dt.month
                created_dayofweek = created_dt.weekday()
                created_hour = created_dt.hour
            else:
                created_month = 1
                created_dayofweek = 0
                created_hour = 12

            target_val = int(r["cy_admission"]) if r["cy_admission"] is not None else 0
            if target_val not in (0, 1):
                target_val = 1 if target_val > 0 else 0

            feature_dict = {
                "id": record_id,
                "dataset_id": str(r["dataset_id"]),
                "campus_name": r["campus_name"] or "UNMAPPED_CAMPUS",
                "academic_year": int(r["academic_year"]),
                "source_canonical": source_canonical,
                "state_canonical": state_canonical,
                "state_code": state_code,
                "zone": zone,
                "owner_canonical": owner_canonical,
                "team": team,
                "created_month": created_month,
                "created_dayofweek": created_dayofweek,
                "created_hour": created_hour,
                TARGET_COLUMN: target_val,
                "raw_created_on": raw_dt or "",
            }

            if split_tag == "train":
                train_rows.append(feature_dict)
            elif split_tag == "val":
                val_rows.append(feature_dict)
            else:
                test_rows.append(feature_dict)

        df_train = pd.DataFrame(train_rows)
        df_val = pd.DataFrame(val_rows)
        df_test = pd.DataFrame(test_rows)

        # Validate zero target leakage across all splits
        for df, name in [(df_train, "train"), (df_val, "val"), (df_test, "test")]:
            validate_no_leakage(list(df.columns))

        # Check entity de-duplication
        train_ids = set(df_train["id"])
        val_ids = set(df_val["id"])
        test_ids = set(df_test["id"])

        assert len(train_ids.intersection(val_ids)) == 0, "Overlap found between Train and Val IDs!"
        assert len(train_ids.intersection(test_ids)) == 0, "Overlap found between Train and Test IDs!"
        assert len(val_ids.intersection(test_ids)) == 0, "Overlap found between Val and Test IDs!"

        # Persist parquet datasets
        train_path = os.path.join(self.data_dir, "ml_train_dataset.parquet")
        val_path = os.path.join(self.data_dir, "ml_validation_dataset.parquet")
        test_path = os.path.join(self.data_dir, "ml_test_dataset.parquet")

        df_train.to_parquet(train_path, index=False)
        df_val.to_parquet(val_path, index=False)
        df_test.to_parquet(test_path, index=False)

        metrics = {
            "train": {
                "count": len(df_train),
                "admitted": int((df_train[TARGET_COLUMN] == 1).sum()),
                "not_admitted": int((df_train[TARGET_COLUMN] == 0).sum()),
                "path": train_path,
            },
            "val": {
                "count": len(df_val),
                "admitted": int((df_val[TARGET_COLUMN] == 1).sum()),
                "not_admitted": int((df_val[TARGET_COLUMN] == 0).sum()),
                "path": val_path,
            },
            "test": {
                "count": len(df_test),
                "admitted": int((df_test[TARGET_COLUMN] == 1).sum()),
                "not_admitted": int((df_test[TARGET_COLUMN] == 0).sum()),
                "path": test_path,
            },
        }

        logger.info(f"Temporal splitting complete. Metrics: {metrics}")
        return metrics


def load_temporal_splits(data_dir: str = DEFAULT_DATA_DIR) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load persisted train, validation, and test datasets."""
    train_path = os.path.join(data_dir, "ml_train_dataset.parquet")
    val_path = os.path.join(data_dir, "ml_validation_dataset.parquet")
    test_path = os.path.join(data_dir, "ml_test_dataset.parquet")

    df_train = pd.read_parquet(train_path)
    df_val = pd.read_parquet(val_path)
    df_test = pd.read_parquet(test_path)
    return df_train, df_val, df_test
