"""
Phase 6 Automated ML Feature Engineering & Target Leakage Test Suite

Validates:
1. Binary prediction target integrity (cy_admission in {0, 1})
2. Absolute absence of forbidden target leakage columns
3. Dimension resolution & missingness handling for State, Source, Owner
4. Feature schema completeness across all 4 production datasets
"""

import pytest
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.ml.ml_feature_pipeline import (
    MLFeaturePipeline,
    validate_no_leakage,
    FORBIDDEN_LEAKAGE_FIELDS,
    ACCEPTED_FEATURE_COLUMNS,
    TARGET_COLUMN,
)


@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestMLFeaturePipeline:
    def test_01_validate_no_leakage_detector(self):
        """validate_no_leakage raises ValueError when forbidden leakage columns are present."""
        clean_cols = ["campus_name", "academic_year", "source_canonical", "cy_admission"]
        validate_no_leakage(clean_cols)  # Should pass cleanly

        for forbidden in FORBIDDEN_LEAKAGE_FIELDS:
            dirty_cols = clean_cols + [forbidden]
            with pytest.raises(ValueError, match="TARGET LEAKAGE DETECTED"):
                validate_no_leakage(dirty_cols)

    def test_02_target_binary_integrity(self, db: Session):
        """Target variable cy_admission is strictly binary (0 or 1) with no nulls."""
        pipeline = MLFeaturePipeline(db)
        df = pipeline.extract_features(limit=5000)

        assert TARGET_COLUMN in df.columns
        unique_targets = set(df[TARGET_COLUMN].unique())
        assert unique_targets.issubset({0, 1}), f"Invalid target values: {unique_targets}"
        assert df[TARGET_COLUMN].isnull().sum() == 0

    def test_03_accepted_feature_columns_present(self, db: Session):
        """All 12 accepted feature columns are present in extracted DataFrame."""
        pipeline = MLFeaturePipeline(db)
        df = pipeline.extract_features(limit=1000)

        for col in ACCEPTED_FEATURE_COLUMNS:
            assert col in df.columns, f"Missing feature column: {col}"

    def test_04_no_forbidden_columns_in_extracted_features(self, db: Session):
        """Extracted DataFrame contains ZERO forbidden leakage fields."""
        pipeline = MLFeaturePipeline(db)
        df = pipeline.extract_features(limit=1000)

        for forbidden in FORBIDDEN_LEAKAGE_FIELDS:
            assert forbidden not in df.columns, f"Forbidden column leaked into features: {forbidden}"

    def test_05_dimension_missingness_handling(self, db: Session):
        """Null dimensions fall back to explicitly typed UNMAPPED string placeholders."""
        pipeline = MLFeaturePipeline(db)
        df = pipeline.extract_features(limit=2000)

        for col in ["state_canonical", "source_canonical", "owner_canonical", "campus_name", "zone", "team"]:
            assert df[col].isnull().sum() == 0, f"Nulls found in {col} (must use UNMAPPED placeholder)"

    def test_06_temporal_features_valid_range(self, db: Session):
        """Derived temporal features have valid numeric bounds."""
        pipeline = MLFeaturePipeline(db)
        df = pipeline.extract_features(limit=2000)

        assert df["created_month"].between(1, 12).all(), "Invalid created_month"
        assert df["created_dayofweek"].between(0, 6).all(), "Invalid created_dayofweek"
        assert df["created_hour"].between(0, 23).all(), "Invalid created_hour"

    def test_07_extract_features_all_datasets(self, db: Session):
        """Extraction works cleanly for all 4 production dataset IDs."""
        datasets = db.execute(text(
            "SELECT id, campus_name, academic_year FROM system.datasets WHERE is_analytics_enabled = TRUE"
        )).mappings().all()

        assert len(datasets) == 4
        pipeline = MLFeaturePipeline(db)

        for ds in datasets:
            df = pipeline.extract_features(dataset_id=str(ds["id"]), limit=100)
            assert len(df) == 100
            assert set(df["academic_year"]) == {ds["academic_year"]}
            assert set(df["campus_name"]) == {ds["campus_name"]}
