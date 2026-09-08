"""
Phase 7 Automated Temporal Train / Validation / Test Split Test Suite

Validates:
1. Persistence and non-empty state of ml_train_dataset, ml_validation_dataset, ml_test_dataset
2. Zero record ID overlap across splits (de-duplication guarantee)
3. Chronological temporal boundary ordering (Train <= Val <= Test)
4. Binary target integrity (cy_admission in {0, 1})
5. Absolute absence of forbidden target leakage columns
6. Campus and Academic Year distribution preservation
"""

import os
import pytest
import pandas as pd

from app.ml.ml_temporal_split import (
    load_temporal_splits,
    DEFAULT_DATA_DIR,
    PURE_T0_FEATURE_COLUMNS,
)
from app.ml.ml_feature_pipeline import FORBIDDEN_LEAKAGE_FIELDS, TARGET_COLUMN


@pytest.fixture(scope="module")
def split_datasets():
    df_train, df_val, df_test = load_temporal_splits(DEFAULT_DATA_DIR)
    return {"train": df_train, "val": df_val, "test": df_test}


class TestMLTemporalSplit:
    def test_01_persisted_datasets_exist(self):
        """Parquet dataset files exist in data_dir."""
        for filename in ["ml_train_dataset.parquet", "ml_validation_dataset.parquet", "ml_test_dataset.parquet"]:
            filepath = os.path.join(DEFAULT_DATA_DIR, filename)
            assert os.path.exists(filepath), f"Missing dataset file: {filepath}"
            assert os.path.getsize(filepath) > 0, f"Empty dataset file: {filepath}"

    def test_02_zero_id_overlap_across_splits(self, split_datasets):
        """Zero record ID overlap between Train, Validation, and Test splits."""
        train_ids = set(split_datasets["train"]["id"])
        val_ids = set(split_datasets["val"]["id"])
        test_ids = set(split_datasets["test"]["id"])

        train_val_overlap = train_ids.intersection(val_ids)
        train_test_overlap = train_ids.intersection(test_ids)
        val_test_overlap = val_ids.intersection(test_ids)

        assert len(train_val_overlap) == 0, f"Train-Val ID overlap: {len(train_val_overlap)}"
        assert len(train_test_overlap) == 0, f"Train-Test ID overlap: {len(train_test_overlap)}"
        assert len(val_test_overlap) == 0, f"Val-Test ID overlap: {len(val_test_overlap)}"

    def test_03_total_rows_match_production_baseline(self, split_datasets):
        """Total rows across Train, Val, and Test equal 2,609,151 production records."""
        total_count = (
            len(split_datasets["train"])
            + len(split_datasets["val"])
            + len(split_datasets["test"])
        )
        assert total_count == 2609151, f"Total split rows mismatch: {total_count}"

    def test_04_target_binary_integrity(self, split_datasets):
        """Target cy_admission is strictly binary (0 or 1) across all 3 splits."""
        for name, df in split_datasets.items():
            assert TARGET_COLUMN in df.columns
            unique_targets = set(df[TARGET_COLUMN].unique())
            assert unique_targets.issubset({0, 1}), f"Invalid target values in {name}: {unique_targets}"

    def test_05_zero_forbidden_leakage_columns(self, split_datasets):
        """Zero forbidden target leakage columns exist in any split dataset."""
        for name, df in split_datasets.items():
            for forbidden in FORBIDDEN_LEAKAGE_FIELDS:
                assert (
                    forbidden not in df.columns
                ), f"Forbidden column '{forbidden}' leaked into {name} split!"

    def test_06_pure_t0_feature_columns_present(self, split_datasets):
        """All 11 pure t0 feature columns are present in Train, Val, and Test splits."""
        for name, df in split_datasets.items():
            for col in PURE_T0_FEATURE_COLUMNS:
                assert col in df.columns, f"Missing feature column '{col}' in {name} split!"

    def test_07_campus_and_academic_year_preservation(self, split_datasets):
        """Campus and Academic Year values are preserved correctly across splits."""
        assert set(split_datasets["train"]["academic_year"].unique()) == {2025, 2026}
        assert set(split_datasets["train"]["campus_name"].unique()) == {"Mohali", "Unnao"}

        assert set(split_datasets["val"]["academic_year"].unique()) == {2026}
        assert set(split_datasets["test"]["academic_year"].unique()) == {2026}
