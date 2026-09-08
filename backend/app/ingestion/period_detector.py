"""
Period detection service.

Detects the academic period (e.g. "2025-26") from available signals:
  1. Filename patterns
  2. Column header names in staging data
  3. Data values in the first few rows of staging.records

Returns a PeriodDetectionResult with confidence score and detection method.
The upload flow uses this to either auto-confirm (high confidence)
or ask the user to select/confirm the period (low confidence).
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PeriodDetectionResult:
    """Result of period and campus detection for an uploaded file."""

    academic_year: Optional[int]       # Reporting year, e.g. 2026
    campus_name: Optional[str]         # Campus, e.g. "Mohali" or "Unnao"
    period_start_year: Optional[int]   # PY year, e.g. 2025
    period_end_year: Optional[int]     # CY year, e.g. 2026
    academic_label: Optional[str]      # e.g. "2026" or "2025-26"
    confidence: float                  # 0.0 = unknown, 1.0 = certain
    detection_method: str              # "filename" | "column_header" | "data_value" | "none"

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "academic_year": self.academic_year,
            "campus_name": self.campus_name,
            "period_start_year": self.period_start_year,
            "period_end_year": self.period_end_year,
            "academic_label": self.academic_label,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
        }


# ---------------------------------------------------------------------------
# Label & Campus utilities
# ---------------------------------------------------------------------------

def _detect_campus_from_str(s: str) -> Optional[str]:
    """Detect campus name from text (Mohali, Unnao, etc.)."""
    if not s:
        return None
    s_lower = str(s).lower()
    if "mohali" in s_lower:
        return "Mohali"
    if "unnao" in s_lower:
        return "Unnao"
    return None


def _make_label(start_year: int, end_year: int) -> str:
    """Convert start/end years into single reporting year or legacy label."""
    return str(end_year)


def _parse_years_from_label(label: str) -> tuple[int, int] | None:
    """Parse '2026' or '2025-26' or '2025-2026' into (2025, 2026)."""
    if not label:
        return None
    s = label.strip()
    # Single 4-digit year: e.g. "2026"
    if re.match(r"^(20\d{2})$", s):
        cy = int(s)
        return cy - 1, cy
    # Full four-digit range: 2025-2026
    m = re.match(r"^(20\d{2})-(20\d{2})$", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Short range: 2025-26
    m = re.match(r"^(20\d{2})-(\d{2})$", s)
    if m:
        start = int(m.group(1))
        end_suffix = int(m.group(2))
        end = (start // 100) * 100 + end_suffix
        if end <= start:
            end += 100
        return start, end
    return None


# ---------------------------------------------------------------------------
# Signal extractors
# ---------------------------------------------------------------------------

def _detect_from_filename(filename: str) -> PeriodDetectionResult | None:
    """Try to extract academic year and campus from the filename."""
    if not filename:
        return None

    campus = _detect_campus_from_str(filename)

    # Check full range first: 2023-2024 or 2023_2024
    m_range_full = re.search(r"(?<![0-9])(20\d{2})[-_](20\d{2})(?![0-9])", filename)
    if m_range_full:
        start = int(m_range_full.group(1))
        end = int(m_range_full.group(2))
        return PeriodDetectionResult(
            academic_year=end,
            campus_name=campus,
            period_start_year=start,
            period_end_year=end,
            academic_label=str(end),
            confidence=0.95,
            detection_method="filename",
        )

    # Check short range: 2025-26 or 2025_26
    m_range = re.search(r"(?<![0-9])(20\d{2})[-_](\d{2})(?![0-9])", filename)
    if m_range:
        start = int(m_range.group(1))
        end_suffix = int(m_range.group(2))
        end = (start // 100) * 100 + end_suffix
        if end <= start:
            end += 100
        return PeriodDetectionResult(
            academic_year=end,
            campus_name=campus,
            period_start_year=start,
            period_end_year=end,
            academic_label=str(end),
            confidence=0.95,
            detection_method="filename",
        )

    # Single 4-digit year: 2026
    m = re.search(r"(?<![0-9])(20\d{2})(?![0-9])", filename)
    if m:
        cy = int(m.group(1))
        py = cy - 1
        return PeriodDetectionResult(
            academic_year=cy,
            campus_name=campus,
            period_start_year=py,
            period_end_year=cy,
            academic_label=str(cy),
            confidence=0.95,
            detection_method="filename",
        )

    return None


def _detect_from_staging_headers(db: Session, dataset_id: Any) -> PeriodDetectionResult | None:
    """
    Scan staging.records column names (JSON keys) for year patterns.
    E.g. column "CY Leads 2026" or "Admissions 2025-26".
    """
    try:
        rows = db.execute(
            text("SELECT raw_data FROM staging.records WHERE dataset_id = :ds LIMIT 5"),
            {"ds": str(dataset_id)},
        ).mappings().all()

        for row in rows:
            raw = row.get("raw_data") or {}
            campus = None
            for key in raw.keys():
                if not campus:
                    campus = _detect_campus_from_str(str(key))
                # Single or range year in column name
                m = re.search(r"\b(20\d{2})\b", str(key))
                if m:
                    cy = int(m.group(1))
                    return PeriodDetectionResult(
                        academic_year=cy,
                        campus_name=campus,
                        period_start_year=cy - 1,
                        period_end_year=cy,
                        academic_label=str(cy),
                        confidence=0.8,
                        detection_method="column_header",
                    )
    except Exception as exc:
        logger.warning("Period detection (column headers) failed: %s", exc)

    return None


def _detect_from_staging_values(db: Session, dataset_id: Any) -> PeriodDetectionResult | None:
    """
    Scan the actual data values in staging.records for year patterns.
    E.g. a date value "2026-01-15" or a text value "2025".
    """
    try:
        rows = db.execute(
            text("SELECT raw_data FROM staging.records WHERE dataset_id = :ds LIMIT 20"),
            {"ds": str(dataset_id)},
        ).mappings().all()

        year_counts: dict[int, int] = {}
        campus = None
        for row in rows:
            raw = row.get("raw_data") or {}
            for v in raw.values():
                if not campus:
                    campus = _detect_campus_from_str(str(v))
                m = re.search(r"\b(20\d{2})\b", str(v))
                if m:
                    yr = int(m.group(1))
                    year_counts[yr] = year_counts.get(yr, 0) + 1

        if year_counts:
            cy = max(year_counts, key=lambda y: year_counts[y])
            return PeriodDetectionResult(
                academic_year=cy,
                campus_name=campus,
                period_start_year=cy - 1,
                period_end_year=cy,
                academic_label=str(cy),
                confidence=0.55,
                detection_method="data_value",
            )
    except Exception as exc:
        logger.warning("Period detection (data values) failed: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_period(
    filename: str,
    db: Session | None = None,
    dataset_id: Any = None,
) -> PeriodDetectionResult:
    """
    Attempt to detect the academic period for an uploaded file.

    Priority:
      1. Filename (highest confidence, no DB needed)
      2. Staging column headers (requires staged data)
      3. Staging data values (lowest automated confidence)
      4. Return unknown if all signals fail
    """
    # 1. Filename
    result = _detect_from_filename(filename)
    if result and result.is_confident:
        logger.info(
            "Period detected from filename '%s': year=%s, campus=%s (confidence=%.2f)",
            filename, result.academic_year, result.campus_name, result.confidence,
        )
        return result

    # 2. Staging column headers (if DB available)
    if db is not None and dataset_id is not None:
        header_result = _detect_from_staging_headers(db, dataset_id)
        if header_result and header_result.confidence > (result.confidence if result else 0):
            result = header_result

    # 3. Staging data values (if DB available)
    if db is not None and dataset_id is not None:
        value_result = _detect_from_staging_values(db, dataset_id)
        if value_result and value_result.confidence > (result.confidence if result else 0):
            result = value_result

    if result:
        logger.info(
            "Period detected via '%s' for dataset %s: year=%s, campus=%s (confidence=%.2f)",
            result.detection_method, dataset_id, result.academic_year, result.campus_name, result.confidence,
        )
        return result

    # 4. Unknown
    logger.info("Period could not be detected for '%s'", filename)
    return PeriodDetectionResult(
        academic_year=None,
        campus_name=None,
        period_start_year=None,
        period_end_year=None,
        academic_label=None,
        confidence=0.0,
        detection_method="none",
    )


def build_period_label(start_year: int, end_year: int) -> str:
    """Canonical label builder exposed for use in other modules."""
    return _make_label(start_year, end_year)


def parse_label(label: str) -> tuple[int, int] | None:
    """Parse a user-supplied period label into (start_year, end_year) or None."""
    return _parse_years_from_label(label)


def available_period_labels(db: Session | None = None, n: int = 20) -> list[str]:
    """
    Return distinct academic period labels that ACTUALLY exist in system.datasets in DB.
    Does NOT include fake/un-uploaded periods.
    """
    if db is not None:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT DISTINCT academic_label
                    FROM system.datasets
                    WHERE academic_label IS NOT NULL
                    ORDER BY academic_label DESC
                    LIMIT :limit
                    """
                ),
                {"limit": n},
            ).mappings().all()
            return [r["academic_label"] for r in rows if r["academic_label"]]
        except Exception as exc:
            logger.warning("Failed to fetch available periods from DB: %s", exc)

    return []


