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
    """
    Database-driven source resolution engine using organization.source_master.
    Preserves canonical hierarchy:
      Lead Type -> Main Source -> Source Cluster -> Report Source -> Source
    Safeguards:
      - NNEXT is strictly distinct from Nxt - OTHER and nNext.
      - Never collapses distinct business concepts via case folding.
      - Supports composite evidence (Source + SourceMedium + Origin).
      - Handles blank/missing fields gracefully without discarding evidence.
    """

    def __init__(self, db: Optional[Session] = None):
        self._exact_sources: Dict[str, dict] = {}
        self._lower_sources: Dict[str, List[dict]] = {}
        self._clusters: Dict[str, List[dict]] = {}
        self._report_sources: Dict[str, List[dict]] = {}
        self._main_sources: Dict[str, List[dict]] = {}
        self._all_records: List[dict] = []
        self._load(db)

    def _load(self, db: Optional[Session] = None) -> None:
        rows = []
        if db is not None:
            try:
                rows = db.execute(text(
                    "SELECT source, main_source, source_cluster, report_source, lead_type "
                    "FROM organization.source_master"
                )).mappings().all()
            except Exception as e:
                logger.warning("Could not load from organization.source_master, falling back to seeds: %s", e)
                rows = []

        if not rows:
            try:
                from app.database.seeds.dimension_seed_data import SOURCES
                rows = SOURCES
            except Exception as e:
                logger.error("Could not load fallback SOURCES: %s", e)
                rows = []

        for r in rows:
            entry = {
                "source": r.get("source") or "",
                "main_source": r.get("main_source") or "",
                "source_cluster": r.get("source_cluster") or "",
                "report_source": r.get("report_source") or "",
                "lead_type": r.get("lead_type") or "",
            }
            self._all_records.append(entry)

            src = entry["source"].strip()
            if src:
                self._exact_sources[src] = entry
                self._lower_sources.setdefault(src.lower(), []).append(entry)

            sc = entry["source_cluster"].strip().upper()
            if sc:
                self._clusters.setdefault(sc, []).append(entry)

            rs = entry["report_source"].strip().lower()
            if rs:
                self._report_sources.setdefault(rs, []).append(entry)

            ms = entry["main_source"].strip().lower()
            if ms:
                self._main_sources.setdefault(ms, []).append(entry)

    def resolve(
        self,
        raw_source: Optional[str],
        raw_source_medium: Optional[str] = None,
        raw_origin: Optional[str] = None,
    ) -> DimensionResolution:
        raw_s = (raw_source or "").strip()
        raw_sm = (raw_source_medium or "").strip()
        raw_o = (raw_origin or "").strip()

        base_extra = {
            "raw_source": raw_s,
            "raw_source_medium": raw_sm,
            "raw_origin": raw_o,
            "resolved_lead_type": None,
            "resolved_main_source": None,
            "resolved_source_cluster": None,
            "resolved_report_source": None,
            "resolved_source": None,
            "confidence": "NONE",
            "resolution_reason": "",
        }

        if not raw_s and not raw_sm and not raw_o:
            extra = dict(base_extra)
            extra["resolution_reason"] = "All source fields are empty"
            return DimensionResolution(
                raw_value="",
                canonical_value=None,
                resolution_method="EMPTY",
                resolution_status="UNRESOLVED",
                extra=extra,
            )

        def _make_res(
            canonical: Optional[str],
            method: str,
            status: str,
            lead_type: Optional[str],
            main_source: Optional[str],
            source_cluster: Optional[str],
            report_source: Optional[str],
            confidence: str,
            reason: str,
        ) -> DimensionResolution:
            extra = dict(base_extra)
            extra.update({
                "resolved_lead_type": lead_type,
                "resolved_main_source": main_source,
                "resolved_source_cluster": source_cluster,
                "resolved_report_source": report_source,
                "resolved_source": canonical,
                # Also keep legacy shorthand keys for backward compatibility
                "lead_type": lead_type,
                "main_source": main_source,
                "source_cluster": source_cluster,
                "report_source": report_source,
                "confidence": confidence,
                "resolution_reason": reason,
            })
            return DimensionResolution(
                raw_value=raw_s or raw_sm or raw_o,
                canonical_value=canonical,
                resolution_method=method,
                resolution_status=status,
                extra=extra,
            )

        # -------------------------------------------------------------
        # 1. Composite Match (Source + SourceMedium)
        # -------------------------------------------------------------
        if raw_s and raw_sm:
            norm_sm = raw_sm.upper()
            alias_map = {
                "GPMAX": "PMAX",
                "GDG": "GDC",
                "MWCON": "FB",
            }
            cluster_target = alias_map.get(norm_sm, norm_sm)

            # Agency nNext handling with SourceMedium channel evidence
            if raw_s.lower() == "nnext" and raw_s != "NNEXT":
                cluster_val = "Nxt - OTHER"
                rep_src = "Others"
                sm_l = raw_sm.lower()
                if "gsn" in sm_l:
                    cluster_val = "GSN"
                    rep_src = "Google"
                elif "gdn" in sm_l:
                    cluster_val = "GDN"
                    rep_src = "Google"
                elif "pmax" in sm_l:
                    cluster_val = "PMAX"
                    rep_src = "Google"
                elif any(k in sm_l for k in ("fb", "mwcon", "mreach", "mvideo", "mlg")):
                    cluster_val = "FB"
                    rep_src = "Facebook"
                elif "gdc" in sm_l or "gdg" in sm_l:
                    cluster_val = "GDC"
                    rep_src = "Google"
                elif "yt" in sm_l:
                    cluster_val = "YT"
                    rep_src = "Youtube"

                return _make_res(
                    canonical="nNext",
                    method="COMPOSITE",
                    status="RESOLVED",
                    lead_type="In House",
                    main_source="nNext",
                    source_cluster=cluster_val,
                    report_source=rep_src,
                    confidence="HIGH",
                    reason=f"Resolved digital marketing agency nNext via SourceMedium channel '{raw_sm}'",
                )

            candidates = []
            for s in self._all_records:
                rs = s["report_source"].lower()
                sc = s["source_cluster"].upper()
                src = s["source"].lower()

                src_match = (
                    rs == raw_s.lower()
                    or src == raw_s.lower()
                    or (raw_s.lower() == "meta" and rs == "facebook")
                )
                cluster_match = (
                    sc == cluster_target
                    or cluster_target in sc
                    or raw_sm.lower() in src
                )
                if src_match and cluster_match:
                    candidates.append(s)

            if candidates:
                c = candidates[0]
                cluster_val = cluster_target if cluster_target in ("GSN", "GDN", "PMAX", "FB", "GDC") else c["source_cluster"]
                return _make_res(
                    canonical=c["source"],
                    method="COMPOSITE",
                    status="RESOLVED",
                    lead_type=c["lead_type"],
                    main_source=c["main_source"],
                    source_cluster=cluster_val,
                    report_source=c["report_source"],
                    confidence="HIGH",
                    reason=f"Matched via Source ({raw_s}) + SourceMedium ({raw_sm})",
                )

        # -------------------------------------------------------------
        # 2. Exact Case-Sensitive Match on Source
        # -------------------------------------------------------------
        if raw_s and raw_s in self._exact_sources:
            entry = self._exact_sources[raw_s]
            return _make_res(
                canonical=entry["source"],
                method="EXACT",
                status="RESOLVED",
                lead_type=entry["lead_type"],
                main_source=entry["main_source"],
                source_cluster=entry["source_cluster"],
                report_source=entry["report_source"],
                confidence="HIGH",
                reason=f"Exact case-sensitive match on source '{raw_s}'",
            )

        # -------------------------------------------------------------
        # 3. Agency Direct / Distinct NNEXT Guard (when SourceMedium is missing)
        # -------------------------------------------------------------
        if raw_s.lower() == "nnext" and raw_s != "NNEXT":
            return _make_res(
                canonical="nNext",
                method="COMPOSITE",
                status="RESOLVED",
                lead_type="In House",
                main_source="nNext",
                source_cluster="Nxt - OTHER",
                report_source="Others",
                confidence="HIGH",
                reason="Identified as digital marketing agency nNext (distinct from source NNEXT)",
            )

        # -------------------------------------------------------------
        # 4. Exact Case-Insensitive Match on Source
        # -------------------------------------------------------------
        lower_s = raw_s.lower()
        if lower_s in self._lower_sources:
            entries = self._lower_sources[lower_s]
            distinct_ms = {e["main_source"] for e in entries}
            distinct_lt = {e["lead_type"] for e in entries}
            distinct_sc = {e["source_cluster"] for e in entries}
            if len(distinct_ms) > 1 or len(distinct_lt) > 1 or len(distinct_sc) > 1:
                return _make_res(
                    canonical=entries[0]["source"],
                    method="AMBIGUOUS",
                    status="AMBIGUOUS",
                    lead_type=entries[0]["lead_type"],
                    main_source=entries[0]["main_source"],
                    source_cluster=entries[0]["source_cluster"],
                    report_source=entries[0]["report_source"],
                    confidence="LOW",
                    reason=f"Multiple ambiguous dimension entries for '{raw_s}'",
                )

            entry = entries[0]
            return _make_res(
                canonical=entry["source"],
                method="EXACT_CASE_INSENSITIVE",
                status="RESOLVED",
                lead_type=entry["lead_type"],
                main_source=entry["main_source"],
                source_cluster=entry["source_cluster"],
                report_source=entry["report_source"],
                confidence="HIGH",
                reason=f"Case-insensitive match on source '{raw_s}'",
            )

        # -------------------------------------------------------------
        # 5. Missing Source Fallback (SourceMedium only)
        # -------------------------------------------------------------
        if not raw_s and raw_sm:
            norm_sm = raw_sm.upper()
            if norm_sm in self._clusters:
                c_entries = self._clusters[norm_sm]
                distinct_ms = {e["main_source"] for e in c_entries}
                distinct_lt = {e["lead_type"] for e in c_entries}
                if len(distinct_ms) > 1 or len(distinct_lt) > 1:
                    return _make_res(
                        canonical=c_entries[0]["source"],
                        method="AMBIGUOUS",
                        status="AMBIGUOUS",
                        lead_type=c_entries[0]["lead_type"],
                        main_source=c_entries[0]["main_source"],
                        source_cluster=c_entries[0]["source_cluster"],
                        report_source=c_entries[0]["report_source"],
                        confidence="LOW",
                        reason=f"Ambiguous SourceMedium '{raw_sm}' maps to multiple dimension rows",
                    )
                c = c_entries[0]
                return _make_res(
                    canonical=c["source"],
                    method="FALLBACK",
                    status="RESOLVED",
                    lead_type=c["lead_type"],
                    main_source=c["main_source"],
                    source_cluster=c["source_cluster"],
                    report_source=c["report_source"],
                    confidence="MEDIUM",
                    reason=f"Resolved unambiguously from SourceMedium evidence '{raw_sm}'",
                )

        # -------------------------------------------------------------
        # 6. UNMAPPED
        # -------------------------------------------------------------
        return _make_res(
            canonical=None,
            method="UNMAPPED",
            status="UNRESOLVED",
            lead_type=None,
            main_source=None,
            source_cluster=None,
            report_source=None,
            confidence="NONE",
            reason=f"No master dimension entry matches source='{raw_s}', medium='{raw_sm}', origin='{raw_o}'",
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
