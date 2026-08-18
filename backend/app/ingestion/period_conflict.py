"""
Period conflict and version protection.

When a user uploads a new file, this module checks whether data for the
detected academic period already exists.  It enforces the rule:

  "Data for YYYY-YY already exists — do not silently merge."

Provides three actions the user (via the UI) can choose:
  - cancel       : abort the upload
  - replace      : deactivate old dataset, activate new one
  - new_version  : keep old dataset, new one becomes active version

Only ONE version per academic_label can be is_period_active=TRUE at a time.
"""
from __future__ import annotations

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
class ExistingPeriodInfo:
    dataset_id: str
    original_filename: str
    upload_version: int
    is_period_active: bool
    created_at: str


@dataclass
class ConflictResult:
    """Returned when a period conflict is detected."""
    has_conflict: bool
    academic_label: str
    existing_dataset: Optional[ExistingPeriodInfo]
    next_version: int                  # version number the new upload would receive
    allowed_actions: list[str]         # ["cancel", "replace", "new_version"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_conflict": self.has_conflict,
            "academic_label": self.academic_label,
            "existing_dataset": {
                "dataset_id": self.existing_dataset.dataset_id,
                "original_filename": self.existing_dataset.original_filename,
                "upload_version": self.existing_dataset.upload_version,
                "is_period_active": self.existing_dataset.is_period_active,
                "created_at": self.existing_dataset.created_at,
            } if self.existing_dataset else None,
            "next_version": self.next_version,
            "allowed_actions": self.allowed_actions,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_session_overlap(
    db: Session,
    academic_label: str,
    ignore_dataset_id: Optional[str] = None,
) -> tuple[bool, Optional[dict[str, Any]]]:
    """
    Check if a candidate academic_label (e.g. '2024-25') overlaps year ranges
    with any existing dataset that has a DIFFERENT academic_label (e.g. '2025-26').

    Returns (has_overlap, conflicting_dataset_dict).
    """
    from app.ingestion.period_detector import parse_label

    parsed = parse_label(academic_label)
    if not parsed:
        return False, None

    cand_start, cand_end = parsed
    cand_years = set(range(cand_start, cand_end + 1))

    # Query all existing datasets with period start/end years
    rows = db.execute(
        text(
            """
            SELECT id, original_filename, academic_label, period_start_year, period_end_year, upload_version
            FROM system.datasets
            WHERE period_start_year IS NOT NULL AND period_end_year IS NOT NULL
            """
        )
    ).mappings().all()

    for r in rows:
        ds_id = str(r["id"])
        if ignore_dataset_id and ds_id == str(ignore_dataset_id):
            continue

        ex_label = (r["academic_label"] or "").strip()
        # Same exact session is versioning/replacement, not an overlap conflict
        if ex_label.lower() == academic_label.strip().lower():
            continue

        ex_start = int(r["period_start_year"])
        ex_end = int(r["period_end_year"])
        ex_years = set(range(ex_start, ex_end + 1))

        if cand_years & ex_years:
            return True, {
                "dataset_id": ds_id,
                "academic_label": ex_label,
                "original_filename": r["original_filename"] or "",
                "overlapping_years": sorted(list(cand_years & ex_years)),
            }

    return False, None


def check_period_conflict(
    db: Session,
    academic_label: str,
) -> ConflictResult:
    """
    Check whether data already exists for the given academic_label.

    Returns a ConflictResult.  If has_conflict=False, the upload can
    proceed immediately as version 1.
    """
    rows = db.execute(
        text(
            """
            SELECT id, original_filename, upload_version, is_period_active, created_at
            FROM system.datasets
            WHERE academic_label = :label
            ORDER BY upload_version DESC
            """
        ),
        {"label": academic_label},
    ).mappings().all()

    if not rows:
        return ConflictResult(
            has_conflict=False,
            academic_label=academic_label,
            existing_dataset=None,
            next_version=1,
            allowed_actions=[],
        )

    # Find the active version to surface to the user
    active_row = next((r for r in rows if r["is_period_active"]), rows[0])
    existing = ExistingPeriodInfo(
        dataset_id=str(active_row["id"]),
        original_filename=active_row["original_filename"] or "",
        upload_version=int(active_row["upload_version"] or 1),
        is_period_active=bool(active_row["is_period_active"]),
        created_at=str(active_row["created_at"]),
    )
    next_version = int(rows[0]["upload_version"] or 1) + 1

    return ConflictResult(
        has_conflict=True,
        academic_label=academic_label,
        existing_dataset=existing,
        next_version=next_version,
        allowed_actions=["cancel", "replace", "new_version"],
    )


def apply_conflict_action(
    db: Session,
    new_dataset_id: Any,
    academic_label: str,
    action: str,
    next_version: int,
) -> None:
    """
    Apply the user's chosen conflict resolution action.

    Actions:
      - "cancel"      : No-op from this function (caller deletes new dataset).
      - "replace"     : Deactivate all existing versions, activate new dataset.
      - "new_version" : Keep existing versions, activate new dataset as latest version.

    In all non-cancel cases the new dataset inherits the period metadata.
    """
    if action == "cancel":
        # Caller is responsible for deleting the partially-created dataset
        return

    if action not in ("replace", "new_version"):
        raise ValueError(f"Unknown conflict action: {action!r}")

    # For both "replace" and "new_version":
    # Deactivate is_period_active on all existing versions of this period
    db.execute(
        text(
            """
            UPDATE system.datasets
            SET is_period_active = FALSE
            WHERE academic_label = :label
              AND id != :new_id
            """
        ),
        {"label": academic_label, "new_id": str(new_dataset_id)},
    )

    # If "replace", also deactivate the old global is_active flag
    if action == "replace":
        db.execute(
            text(
                """
                UPDATE system.datasets
                SET is_active = FALSE
                WHERE academic_label = :label
                  AND id != :new_id
                """
            ),
            {"label": academic_label, "new_id": str(new_dataset_id)},
        )

    # Activate the new dataset for this period
    db.execute(
        text(
            """
            UPDATE system.datasets
            SET
                is_period_active = TRUE,
                upload_version   = :version
            WHERE id = :new_id
            """
        ),
        {"version": next_version, "new_id": str(new_dataset_id)},
    )
    logger.info(
        "Conflict resolved via '%s' for period '%s': new dataset_id=%s version=%d",
        action, academic_label, new_dataset_id, next_version,
    )
