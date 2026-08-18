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
    """Result of period detection for an uploaded file."""

    period_start_year: Optional[int]   # PY year, e.g. 2025
    period_end_year: Optional[int]     # CY year, e.g. 2026
    academic_label: Optional[str]      # e.g. "2025-26"
    confidence: float                  # 0.0 = unknown, 1.0 = certain
    detection_method: str              # "filename" | "column_header" | "data_value" | "none"

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start_year": self.period_start_year,
            "period_end_year": self.period_end_year,
            "academic_label": self.academic_label,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
        }


# ---------------------------------------------------------------------------
# Label utilities
# ---------------------------------------------------------------------------

def _make_label(start_year: int, end_year: int) -> str:
    """Convert start/end years into the canonical "YYYY-YY" label."""
    return f"{start_year}-{str(end_year)[-2:]}"


def _parse_years_from_label(label: str) -> tuple[int, int] | None:
    """Parse "2025-26" or "2025-2026" into (2025, 2026)."""
    # Full four-digit range: 2025-2026
    m = re.match(r"^(20\d{2})-(20\d{2})$", label.strip())
    if m:
        return int(m.group(1)), int(m.group(2))
    # Short range: 2025-26
    m = re.match(r"^(20\d{2})-(\d{2})$", label.strip())
    if m:
        start = int(m.group(1))
        end_suffix = int(m.group(2))
        end = (start // 100) * 100 + end_suffix
        # Handle century boundary: 2099-00 → 2100
        if end <= start:
            end += 100
        return start, end
    return None


# ---------------------------------------------------------------------------
# Signal extractors
# ---------------------------------------------------------------------------

def _detect_from_filename(filename: str) -> PeriodDetectionResult | None:
    """Try to extract an academic period from the filename."""
    if not filename:
        return None

    # Pattern 1: "2025-26" or "2025_26"
    # Use (?<![0-9]) / (?![0-9]) instead of \b to avoid underscore-boundary issues
    m = re.search(r"(?<![0-9])(20\d{2})[-_](\d{2})(?![0-9])", filename)
    if m:
        start = int(m.group(1))
        end_suffix = int(m.group(2))
        end = (start // 100) * 100 + end_suffix
        if end <= start:
            end += 100
        return PeriodDetectionResult(
            period_start_year=start,
            period_end_year=end,
            academic_label=_make_label(start, end),
            confidence=0.95,
            detection_method="filename",
        )

    # Pattern 2: "2025-2026" or "2025_2026"
    m = re.search(r"(?<![0-9])(20\d{2})[-_](20\d{2})(?![0-9])", filename)
    if m:
        start = int(m.group(1))
        end = int(m.group(2))
        if end == start + 1:
            return PeriodDetectionResult(
                period_start_year=start,
                period_end_year=end,
                academic_label=_make_label(start, end),
                confidence=0.95,
                detection_method="filename",
            )

    # Pattern 3: Single four-digit year — treat as CY
    m = re.search(r"(?<![0-9])(20\d{2})(?![0-9])", filename)
    if m:
        cy = int(m.group(1))
        py = cy - 1
        return PeriodDetectionResult(
            period_start_year=py,
            period_end_year=cy,
            academic_label=_make_label(py, cy),
            confidence=0.6,
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
            for key in raw.keys():
                # Full range in column name
                m = re.search(r"\b(20\d{2})[-_](\d{2})\b", str(key))
                if m:
                    start = int(m.group(1))
                    end_suffix = int(m.group(2))
                    end = (start // 100) * 100 + end_suffix
                    if end <= start:
                        end += 100
                    return PeriodDetectionResult(
                        period_start_year=start,
                        period_end_year=end,
                        academic_label=_make_label(start, end),
                        confidence=0.8,
                        detection_method="column_header",
                    )
                # Single year in column name
                m = re.search(r"\b(20\d{2})\b", str(key))
                if m:
                    cy = int(m.group(1))
                    return PeriodDetectionResult(
                        period_start_year=cy - 1,
                        period_end_year=cy,
                        academic_label=_make_label(cy - 1, cy),
                        confidence=0.65,
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
        for row in rows:
            raw = row.get("raw_data") or {}
            for v in raw.values():
                m = re.search(r"\b(20\d{2})\b", str(v))
                if m:
                    yr = int(m.group(1))
                    year_counts[yr] = year_counts.get(yr, 0) + 1

        if year_counts:
            # Pick most-frequent year as CY
            cy = max(year_counts, key=lambda y: year_counts[y])
            py = cy - 1
            return PeriodDetectionResult(
                period_start_year=py,
                period_end_year=cy,
                academic_label=_make_label(py, cy),
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

    Args:
        filename:   Original uploaded filename.
        db:         SQLAlchemy session (optional; needed for staging signals).
        dataset_id: Dataset UUID (optional; needed for staging signals).

    Returns:
        PeriodDetectionResult — always non-None; check .is_confident and .academic_label.
    """
    # 1. Filename
    result = _detect_from_filename(filename)
    if result and result.is_confident:
        logger.info(
            "Period detected from filename '%s': %s (confidence=%.2f)",
            filename, result.academic_label, result.confidence,
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
            "Period detected via '%s' for dataset %s: %s (confidence=%.2f)",
            result.detection_method, dataset_id, result.academic_label, result.confidence,
        )
        return result

    # 4. Unknown
    logger.info("Period could not be detected for '%s'", filename)
    return PeriodDetectionResult(
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


