"""
Phase 12: Graph Dimension Canonicalization Engine

Provides authoritative key resolution and normalization for graph nodes and relationships.
Enforces:
1. Lead ID: enquiry_id (uppercase trimmed)
2. Owner: Uses employee_id as canonical key when available; owner name retained as display property.
3. Location/State: Resolves international states/countries to INTERNATIONAL (state_code: "INT").
4. Strict casing/whitespace deduplication across all dimensions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.normalization.dimension_resolver import (
    StateResolver,
    SourceResolver,
    EmployeeResolver,
    ProgramResolver,
)


INTERNATIONAL_INDICATORS = {
    "international", "abroad", "foreign", "nepal", "bhutan", "bangladesh",
    "sri lanka", "uae", "dubai", "usa", "uk", "canada", "australia", "nri", "overseas"
}


class GraphCanonicalizer:
    def __init__(self, db: Optional[Session] = None):
        self.state_resolver = StateResolver(db) if db else None
        self.source_resolver = SourceResolver(db) if db else None
        self.employee_resolver = EmployeeResolver(db) if db else None
        self.program_resolver = ProgramResolver(db) if db else None

    @staticmethod
    def canonicalize_lead_id(raw_id: Optional[str]) -> str:
        """Enforce canonical lead identifier (enquiry_id)."""
        if not raw_id or not str(raw_id).strip():
            raise ValueError("Invalid lead identifier: enquiry_id cannot be null or empty")
        return str(raw_id).strip().upper()

    def canonicalize_state(self, raw_state: Optional[str], country: Optional[str] = None) -> Dict[str, Any]:
        """
        Resolves raw state & country values to canonical State entity properties.
        Explicitly routes all international locations to state_code: "INT", canonical_name: "INTERNATIONAL".
        """
        combined = f"{raw_state or ''} {country or ''}".strip().lower()

        # Check explicit international indicator
        if any(indicator in combined for indicator in INTERNATIONAL_INDICATORS):
            return {
                "state_code": "INT",
                "state_name": "INTERNATIONAL",
                "zone": "INTERNATIONAL",
                "is_international": True,
            }

        if self.state_resolver and raw_state:
            res = self.state_resolver.resolve(raw_state)
            if res.resolution_status == "RESOLVED" and res.canonical_value:
                return {
                    "state_code": res.extra.get("state_code") or res.canonical_value.upper()[:3],
                    "state_name": res.canonical_value,
                    "zone": res.extra.get("zone") or "UNKNOWN",
                    "is_international": False,
                }

        # Fallback normalization for unmapped domestic state strings
        clean_name = (raw_state or "UNKNOWN").strip().title()
        clean_code = re.sub(r"[^A-Z]", "", clean_name.upper())[:3] or "UNK"
        return {
            "state_code": clean_code,
            "state_name": clean_name,
            "zone": "UNKNOWN",
            "is_international": False,
        }

    def canonicalize_owner(
        self,
        raw_owner: Optional[str],
        raw_employee_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolves Owner entity.
        Prefers stable employee_id as canonical key. Retains display_name separately.
        """
        emp_id = (raw_employee_id or "").strip()
        display_name = (raw_owner or "Unassigned Owner").strip()

        if self.employee_resolver and raw_owner:
            res = self.employee_resolver.resolve(raw_owner)
            if res.resolution_status == "RESOLVED" and res.canonical_value:
                display_name = res.canonical_value
                extra = res.extra or {}
                if not emp_id and "employee_id" in extra:
                    emp_id = str(extra["employee_id"]).strip()

        # If no explicit employee_id, slugify the display name into a deterministic fallback key
        if not emp_id:
            emp_id = f"emp_{re.sub(r'[^a-z0-9]', '_', display_name.lower())}"

        return {
            "employee_id": emp_id.lower(),
            "employee_name": display_name,
            "display_name": display_name,
        }

    def canonicalize_source(self, raw_source: Optional[str]) -> Dict[str, Any]:
        """Resolves Source entity into canonical key and display attributes."""
        source_name = (raw_source or "Direct / Unknown").strip()
        source_key = re.sub(r"[^a-z0-9]", "_", source_name.lower())
        main_source = source_name

        if self.source_resolver and raw_source:
            res = self.source_resolver.resolve(raw_source)
            if res.resolution_status == "RESOLVED" and res.canonical_value:
                source_name = res.canonical_value
                main_source = res.extra.get("main_source") or source_name
                source_key = re.sub(r"[^a-z0-9]", "_", source_name.lower())

        return {
            "source_key": source_key,
            "source_name": source_name,
            "main_source": main_source,
        }

    def canonicalize_program(self, raw_program: Optional[str], program_code: Optional[str] = None) -> Dict[str, Any]:
        """Resolves Program entity into canonical program_code key and display attributes."""
        code = (program_code or "").strip().upper()
        p_name = (raw_program or "General Program").strip()

        if self.program_resolver and raw_program:
            res = self.program_resolver.resolve(raw_program)
            if res.resolution_status == "RESOLVED":
                p_name = res.canonical_value or p_name
                if not code and res.extra.get("program_code"):
                    code = str(res.extra["program_code"]).strip().upper()

        if not code:
            code = f"PROG_{re.sub(r'[^A-Z0-9]', '', p_name.upper())[:10]}"

        return {
            "program_code": code,
            "program_name": p_name,
        }

    @staticmethod
    def canonicalize_campus(raw_campus: Optional[str]) -> Dict[str, Any]:
        """Resolves Campus entity into canonical campus_id slug and display name."""
        campus_name = (raw_campus or "Main Campus").strip().title()
        campus_id = re.sub(r"[^a-z0-9]", "_", campus_name.lower())
        return {
            "campus_id": campus_id,
            "campus_name": campus_name,
        }
