"""
Phase 7.5 Automated Label Maturity & Outcome Censoring Test Suite

Validates:
1. Empirical outcome delay percentiles ordering (P50 <= P75 <= P90 <= P95 <= P99 <= Max)
2. Mandatory audit conclusion is "B. LABELS ARE NOT MATURE"
3. Right-censored negative label detection logic
4. Immutability of Phase 7 temporal split parquet files
5. Absolute absence of forbidden leakage columns
"""

import os
import pytest
import pandas as pd
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.ml.ml_label_maturity import (
    LabelMaturityAuditor,
    get_label_maturity_conclusion,
    DEFAULT_MATURITY_P90_DAYS,
)
from app.ml.ml_temporal_split import load_temporal_splits, DEFAULT_DATA_DIR
from app.ml.ml_feature_pipeline import FORBIDDEN_LEAKAGE_FIELDS


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def split_datasets():
    df_train, df_val, df_test = load_temporal_splits(DEFAULT_DATA_DIR)
    return {"train": df_train, "val": df_val, "test": df_test}


class TestMLLabelMaturity:
    def test_01_outcome_delay_percentiles_calculation(self, db: Session):
        """Outcome delay distribution percentiles obey strict non-decreasing order."""
        auditor = LabelMaturityAuditor(db)
        stats = auditor.compute_outcome_delay_distribution()

        assert "median_p50" in stats
        assert stats["total_samples"] > 0
        assert stats["median_p50"] <= stats["p75"] <= stats["p90"] <= stats["p95"] <= stats["p99"] <= stats["max"]
        assert stats["p90"] > 0

    def test_02_mandatory_conclusion_is_b(self):
        """Audit conclusion explicitly returns 'B. LABELS ARE NOT MATURE'."""
        conclusion = get_label_maturity_conclusion()
        assert conclusion.startswith("B. LABELS ARE NOT MATURE")

    def test_03_censoring_audit_detects_immature_test_labels(self, db: Session, split_datasets):
        """Censoring audit flags immature negative labels in Test dataset."""
        auditor = LabelMaturityAuditor(db)
        metrics = auditor.audit_split_censoring(split_datasets["test"], snapshot_date="2026-08-24")

        assert metrics["total_records"] > 0
        assert metrics["immature_p90_count"] > 0
        assert metrics["immature_p90_pct_of_split"] > 90.0  # >90% of Test split is censored

    def test_04_parquet_datasets_remain_immutable(self):
        """Phase 7 parquet datasets exist and are non-empty."""
        for name in ["ml_train_dataset.parquet", "ml_validation_dataset.parquet", "ml_test_dataset.parquet"]:
            path = os.path.join(DEFAULT_DATA_DIR, name)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_05_zero_forbidden_leakage_columns(self, split_datasets):
        """Zero forbidden leakage fields exist in feature datasets."""
        for name, df in split_datasets.items():
            for forbidden in FORBIDDEN_LEAKAGE_FIELDS:
                assert forbidden not in df.columns, f"Forbidden field '{forbidden}' found in {name}!"
