"""
Tests for the period detection service.
Covers: filename patterns, low-confidence fallback, unknown period handling.
"""
import pytest
from app.ingestion.period_detector import detect_period, build_period_label, parse_label, available_period_labels


class TestFilenameDetection:
    """Period detection from filenames."""

    def test_detect_yyyy_yy_hyphen(self):
        result = detect_period("Admissions_2025-26.xlsx")
        assert result.academic_label == "2025-26"
        assert result.period_start_year == 2025
        assert result.period_end_year == 2026
        assert result.confidence >= 0.9
        assert result.detection_method == "filename"

    def test_detect_yyyy_yy_underscore(self):
        result = detect_period("Data_2024_25.xlsx")
        assert result.academic_label == "2024-25"
        assert result.period_start_year == 2024
        assert result.period_end_year == 2025

    def test_detect_yyyy_yyyy_full(self):
        result = detect_period("Report_2023-2024.csv")
        assert result.academic_label == "2023-24"
        assert result.period_start_year == 2023
        assert result.period_end_year == 2024

    def test_detect_single_year(self):
        result = detect_period("Admissions_2026.xlsx")
        assert result.academic_label == "2025-26"
        assert result.period_start_year == 2025
        assert result.period_end_year == 2026
        assert result.confidence < 0.9  # lower confidence for single year

    def test_detect_data_dump_no_year(self):
        result = detect_period("Data - Dump.xlsx")
        # No year in filename — should return low/no confidence
        assert result.confidence <= 0.6
        # Either unknown or low-confidence single year guess
        assert result.detection_method in ("filename", "none")

    def test_unknown_filename(self):
        result = detect_period("report.csv")
        assert result.academic_label is None or result.confidence < 0.7
        # Should not be confident
        assert not result.is_confident or result.academic_label is None

    def test_production_data_no_year(self):
        result = detect_period("Production_Data.csv")
        # No explicit year — confidence must be low
        assert result.confidence < 0.9

    def test_no_hardcoded_years_in_result(self):
        """Detected years must come from the filename, not from code constants."""
        result = detect_period("Academic_2022-23.xlsx")
        # Result must reflect the filename year, not any hardcoded year
        assert result.period_start_year == 2022
        assert result.period_end_year == 2023
        assert result.academic_label == "2022-23"

    def test_detect_very_old_year(self):
        result = detect_period("Admissions_2020-21.xlsx")
        assert result.academic_label == "2020-21"
        assert result.period_start_year == 2020
        assert result.period_end_year == 2021

    def test_detect_future_year(self):
        result = detect_period("Projections_2027-28.xlsx")
        assert result.academic_label == "2027-28"
        assert result.period_start_year == 2027
        assert result.period_end_year == 2028


class TestLabelUtilities:
    """Label builder and parser."""

    def test_build_label(self):
        assert build_period_label(2025, 2026) == "2025-26"
        assert build_period_label(2022, 2023) == "2022-23"
        assert build_period_label(2019, 2020) == "2019-20"

    def test_parse_label_short(self):
        result = parse_label("2025-26")
        assert result == (2025, 2026)

    def test_parse_label_full(self):
        result = parse_label("2025-2026")
        assert result == (2025, 2026)

    def test_parse_label_invalid(self):
        assert parse_label("invalid") is None
        assert parse_label("2025") is None
        assert parse_label("") is None

    def test_available_period_labels_no_hardcoded_years(self):
        """Labels should be dynamically retrieved from DB, returning empty when no DB or no datasets exist."""
        labels = available_period_labels(n=5)
        # Without DB, returns empty list (no fake periods generated)
        assert isinstance(labels, list)
        assert len(labels) == 0


class TestPeriodDetectionResult:
    def test_is_confident_threshold(self):
        result = detect_period("Data_2025-26.xlsx")
        assert result.is_confident  # >= 0.7

    def test_not_confident_for_unknown(self):
        result = detect_period("report.csv")
        # For a filename with no year, confidence should be 0 or very low
        assert result.confidence < 0.7 or result.academic_label is None

    def test_to_dict_keys(self):
        result = detect_period("Test_2024-25.xlsx")
        d = result.to_dict()
        assert "period_start_year" in d
        assert "period_end_year" in d
        assert "academic_label" in d
        assert "confidence" in d
        assert "detection_method" in d
