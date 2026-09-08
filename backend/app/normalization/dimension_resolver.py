"""
Phase 2-4 — Centralized Dimension Resolver

Resolves raw dimension values (state, source, employee, program) against
organization master tables. Produces audit-trail metadata for every resolution.

Rules:
  - Never invents values; only uses approved master data.
  - Preserves raw_value alongside canonical_value.
  - UNRESOLVED items are flagged, never silently dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class DimensionResolution:
    raw_value: str
    canonical_value: Optional[str]
    resolution_method: str   # EXACT_NAME | STATE_CODE | CITY_ALIAS | UNRESOLVED
    resolution_status: str   # RESOLVED | UNRESOLVED
    extra: Dict[str, Any]    # state_code, zone, team, etc.

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# State Resolver
# ---------------------------------------------------------------------------

class StateResolver:
    """
    Resolves raw state values using organization.state_master.

    Resolution order:
      1. Exact state_name match (case-insensitive, trimmed)
      2. State_code match
      3. The state_master already contains approved city-to-state aliases
         (e.g., MUMBAI→MH, Mohali→PB via Punjab entry)
      4. UNRESOLVED
    """

    def __init__(self, db: Session):
        self._by_name: Dict[str, dict] = {}
        self._by_code: Dict[str, dict] = {}
        self._load(db)

    def _load(self, db: Session) -> None:
        rows = db.execute(text(
            "SELECT state_name, state_code, zone FROM organization.state_master"
        )).mappings().all()
        for r in rows:
            name = (r["state_name"] or "").strip().lower()
            code = (r["state_code"] or "").strip().upper()
            entry = {
                "state_name": r["state_name"],
                "state_code": r["state_code"],
                "zone": r["zone"],
            }
            if name:
                self._by_name[name] = entry
            if code:
                self._by_code[code] = entry

    def resolve(self, raw_state: Optional[str]) -> DimensionResolution:
        if not raw_state or not raw_state.strip():
            return DimensionResolution(
                raw_value=raw_state or "",
                canonical_value=None,
                resolution_method="EMPTY",
                resolution_status="UNRESOLVED",
                extra={"state_code": None, "zone": None},
            )

        normalized = raw_state.strip().lower()

        # 1. Exact state_name match
        if normalized in self._by_name:
            entry = self._by_name[normalized]
            return DimensionResolution(
                raw_value=raw_state,
                canonical_value=entry["state_name"],
                resolution_method="EXACT_NAME",
                resolution_status="RESOLVED",
                extra={"state_code": entry["state_code"], "zone": entry["zone"]},
            )

        # 2. State_code match
        upper = raw_state.strip().upper()
        if upper in self._by_code:
            entry = self._by_code[upper]
            return DimensionResolution(
                raw_value=raw_state,
                canonical_value=entry["state_name"],
                resolution_method="STATE_CODE",
                resolution_status="RESOLVED",
                extra={"state_code": entry["state_code"], "zone": entry["zone"]},
            )

        # 3. UNRESOLVED
        return DimensionResolution(
            raw_value=raw_state,
            canonical_value=None,
            resolution_method="UNRESOLVED",
            resolution_status="UNRESOLVED",
            extra={"state_code": None, "zone": None},
        )


# ---------------------------------------------------------------------------
# Source Resolver
# ---------------------------------------------------------------------------

class SourceResolver:
    """Resolves raw source values using organization.source_master."""

    def __init__(self, db: Session):
        self._by_source: Dict[str, dict] = {}
        self._load(db)

    def _load(self, db: Session) -> None:
        rows = db.execute(text(
            "SELECT source, main_source, source_cluster, report_source "
            "FROM organization.source_master"
        )).mappings().all()
        for r in rows:
            key = (r["source"] or "").strip().lower()
            if key:
                self._by_source[key] = {
                    "source": r["source"],
                    "main_source": r["main_source"],
                    "source_cluster": r["source_cluster"],
                    "report_source": r["report_source"],
                }

    def resolve(self, raw_source: Optional[str]) -> DimensionResolution:
        if not raw_source or not raw_source.strip():
            return DimensionResolution(
                raw_value=raw_source or "",
                canonical_value=None,
                resolution_method="EMPTY",
                resolution_status="UNRESOLVED",
                extra={},
            )

        normalized = raw_source.strip().lower()
        if normalized in self._by_source:
            entry = self._by_source[normalized]
            return DimensionResolution(
                raw_value=raw_source,
                canonical_value=entry["source"],
                resolution_method="EXACT_MATCH",
                resolution_status="RESOLVED",
                extra={
                    "main_source": entry["main_source"],
                    "source_cluster": entry["source_cluster"],
                    "report_source": entry["report_source"],
                },
            )

        return DimensionResolution(
            raw_value=raw_source,
            canonical_value=None,
            resolution_method="UNRESOLVED",
            resolution_status="UNRESOLVED",
            extra={},
        )


# ---------------------------------------------------------------------------
# Employee Resolver
# ---------------------------------------------------------------------------

class EmployeeResolver:
    """Resolves raw owner/employee names using organization.employee_master."""

    def __init__(self, db: Session):
        self._by_name: Dict[str, dict] = {}
        self._load(db)

    def _load(self, db: Session) -> None:
        rows = db.execute(text(
            "SELECT employee_name, office, state, zone, status, team "
            "FROM organization.employee_master"
        )).mappings().all()
        for r in rows:
            key = (r["employee_name"] or "").strip().lower()
            if key:
                self._by_name[key] = {
                    "employee_name": r["employee_name"],
                    "office": r["office"],
                    "state": r["state"],
                    "zone": r["zone"],
                    "status": r["status"],
                    "team": r["team"],
                }

    def resolve(self, raw_owner: Optional[str]) -> DimensionResolution:
        if not raw_owner or not raw_owner.strip():
            return DimensionResolution(
                raw_value=raw_owner or "",
                canonical_value=None,
                resolution_method="EMPTY",
                resolution_status="UNRESOLVED",
                extra={},
            )

        normalized = raw_owner.strip().lower()
        if normalized in self._by_name:
            entry = self._by_name[normalized]
            return DimensionResolution(
                raw_value=raw_owner,
                canonical_value=entry["employee_name"],
                resolution_method="EXACT_MATCH",
                resolution_status="RESOLVED",
                extra={
                    "team": entry["team"],
                    "zone": entry["zone"],
                    "office": entry["office"],
                    "status": entry["status"],
                },
            )

        return DimensionResolution(
            raw_value=raw_owner,
            canonical_value=None,
            resolution_method="UNRESOLVED",
            resolution_status="UNRESOLVED",
            extra={},
        )


# ---------------------------------------------------------------------------
# Program Resolver
# ---------------------------------------------------------------------------

class ProgramResolver:
    """Resolves raw program names using organization.course_master."""

    def __init__(self, db: Session):
        self._by_short: Dict[str, dict] = {}
        self._by_full: Dict[str, dict] = {}
        self._load(db)

    def _load(self, db: Session) -> None:
        rows = db.execute(text(
            "SELECT program_name, program_name_short, program_code, "
            "course_cluster, degree_type, program_group, program_campus "
            "FROM organization.course_master"
        )).mappings().all()
        for r in rows:
            entry = {
                "program_name": r["program_name"],
                "program_name_short": r["program_name_short"],
                "program_code": r["program_code"],
                "course_cluster": r["course_cluster"],
                "degree_type": r["degree_type"],
                "program_group": r["program_group"],
                "program_campus": r["program_campus"],
            }
            short_key = (r["program_name_short"] or "").strip().lower()
            full_key = (r["program_name"] or "").strip().lower()
            if short_key:
                self._by_short[short_key] = entry
            if full_key:
                self._by_full[full_key] = entry

    def resolve(self, raw_program: Optional[str]) -> DimensionResolution:
        if not raw_program or not raw_program.strip():
            return DimensionResolution(
                raw_value=raw_program or "",
                canonical_value=None,
                resolution_method="EMPTY",
                resolution_status="UNRESOLVED",
                extra={},
            )

        normalized = raw_program.strip().lower()

        # 1. Match by program_name_short
        if normalized in self._by_short:
            entry = self._by_short[normalized]
            return DimensionResolution(
                raw_value=raw_program,
                canonical_value=entry["program_name_short"],
                resolution_method="SHORT_NAME_MATCH",
                resolution_status="RESOLVED",
                extra={
                    "program_code": entry["program_code"],
                    "course_cluster": entry["course_cluster"],
                    "degree_type": entry["degree_type"],
                    "program_campus": entry["program_campus"],
                },
            )

        # 2. Match by full program_name
        if normalized in self._by_full:
            entry = self._by_full[normalized]
            return DimensionResolution(
                raw_value=raw_program,
                canonical_value=entry["program_name"],
                resolution_method="FULL_NAME_MATCH",
                resolution_status="RESOLVED",
                extra={
                    "program_code": entry["program_code"],
                    "course_cluster": entry["course_cluster"],
                    "degree_type": entry["degree_type"],
                    "program_campus": entry["program_campus"],
                },
            )

        return DimensionResolution(
            raw_value=raw_program,
            canonical_value=None,
            resolution_method="UNRESOLVED",
            resolution_status="UNRESOLVED",
            extra={},
        )


# ---------------------------------------------------------------------------
# Composite Resolver (convenience)
# ---------------------------------------------------------------------------

class DimensionResolverSuite:
    """Initializes all dimension resolvers from master tables."""

    def __init__(self, db: Session):
        self.state = StateResolver(db)
        self.source = SourceResolver(db)
        self.employee = EmployeeResolver(db)
        self.program = ProgramResolver(db)
