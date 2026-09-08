"""
Phase 1 & 2 — Business Status Normalization Registry

Centralized, auditable mapping of CRM ProspectStage values to canonical statuses.
Every mapping includes raw_value, canonical_value, business_meaning, admission_flag,
refunded_flag, confidence, and resolution_status.

Rules:
  - Case and whitespace are normalized before lookup.
  - Unknown statuses are flagged UNMAPPED / REVIEW_REQUIRED (never silently zeroed).
  - Raw values are NEVER modified; only derived canonical fields are produced.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass(frozen=True)
class StatusMapping:
    raw_value: str
    canonical_value: str
    business_meaning: str
    admission_flag: int  # 1 = net enrolled admission
    refunded_flag: int   # 1 = refund processed
    confidence: float    # 1.0 = confirmed business rule
    resolution_status: str  # RESOLVED | REVIEW_REQUIRED

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Canonical ProspectStage Registry
# ---------------------------------------------------------------------------
# Built from inspection of all distinct ProspectStage values observed in
# Mohali 2026 staging data (974,328 CRM records).

PROSPECT_STAGE_REGISTRY: Dict[str, StatusMapping] = {}

_DEFINITIONS: List[tuple] = [
    # (raw_value, canonical, meaning, admission, refunded, confidence, status)
    ("Enrolled",                       "ENROLLED",             "Net enrolled student",              1, 0, 1.0, "RESOLVED"),
    ("Refunded",                       "REFUNDED",             "Enrolled then refunded",            0, 1, 1.0, "RESOLVED"),
    ("Admit in Other College",         "ADMIT_OTHER_COLLEGE",  "Lost to competitor institution",     0, 0, 1.0, "RESOLVED"),
    ("Not Interested",                 "NOT_INTERESTED",       "Declined / expressed disinterest",  0, 0, 1.0, "RESOLVED"),
    ("Not Available",                  "NOT_AVAILABLE",        "Unreachable / no answer",           0, 0, 1.0, "RESOLVED"),
    ("Not Relevant",                   "NOT_RELEVANT",         "Non-target segment",                0, 0, 1.0, "RESOLVED"),
    ("4 - Negative",                   "NEGATIVE",             "Negative disposition call result",  0, 0, 1.0, "RESOLVED"),
    ("Others",                         "OTHERS",               "Uncategorized / miscellaneous",     0, 0, 0.9, "RESOLVED"),
    ("Follow-Up",                      "FOLLOW_UP",            "Active pipeline / scheduled call",  0, 0, 1.0, "RESOLVED"),
    ("Duplicate Lead",                 "DUPLICATE",            "Duplicate CRM record",              0, 0, 1.0, "RESOLVED"),
    ("General Enquiry",                "GENERAL_ENQUIRY",      "Information request only",          0, 0, 1.0, "RESOLVED"),
    ("Not Eligible",                   "NOT_ELIGIBLE",         "Failed eligibility criteria",       0, 0, 1.0, "RESOLVED"),
    ("Interested",                     "INTERESTED",           "Warm lead / expressed interest",    0, 0, 1.0, "RESOLVED"),
    ("New Lead",                       "NEW_LEAD",             "Fresh unprocessed lead",            0, 0, 1.0, "RESOLVED"),
    ("Wrongly Dialed on CU Helpline",  "WRONG_DIAL",           "Data entry error / wrong number",  0, 0, 1.0, "RESOLVED"),
    ("Laptop Scheme",                  "LAPTOP_SCHEME",        "Laptop scheme enquiry",             0, 0, 0.9, "RESOLVED"),
]

for _raw, _canon, _meaning, _adm, _ref, _conf, _status in _DEFINITIONS:
    key = _raw.strip().lower()
    PROSPECT_STAGE_REGISTRY[key] = StatusMapping(
        raw_value=_raw,
        canonical_value=_canon,
        business_meaning=_meaning,
        admission_flag=_adm,
        refunded_flag=_ref,
        confidence=_conf,
        resolution_status=_status,
    )

# Immutable sentinel for unmapped statuses
UNMAPPED_STATUS = StatusMapping(
    raw_value="",
    canonical_value="UNMAPPED",
    business_meaning="Unknown status — requires business review",
    admission_flag=0,
    refunded_flag=0,
    confidence=0.0,
    resolution_status="REVIEW_REQUIRED",
)


def resolve_prospect_stage(raw_value: Optional[str]) -> StatusMapping:
    """
    Resolve a raw ProspectStage value to its canonical status mapping.

    Resolution:
      1. Trim whitespace and normalize case.
      2. Exact lookup in the registry.
      3. If not found → return UNMAPPED sentinel.
    """
    if raw_value is None:
        return UNMAPPED_STATUS
    normalized = raw_value.strip().lower()
    if not normalized:
        return UNMAPPED_STATUS
    return PROSPECT_STAGE_REGISTRY.get(normalized, UNMAPPED_STATUS)


def get_all_mappings() -> List[StatusMapping]:
    """Return all defined status mappings (for documentation / audit)."""
    return list(PROSPECT_STAGE_REGISTRY.values())


def get_unmapped_statuses(raw_values: List[str]) -> List[str]:
    """Return raw values that have no mapping in the registry."""
    unmapped = []
    for rv in raw_values:
        if rv is None:
            unmapped.append("")
            continue
        normalized = rv.strip().lower()
        if not normalized or normalized not in PROSPECT_STAGE_REGISTRY:
            unmapped.append(rv)
    return unmapped


# ---------------------------------------------------------------------------
# CUCET Exam Status Registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CucetStatusMapping:
    raw_value: str
    canonical_value: str
    cucet_flag: int        # 1 = attempted/registered exam
    business_meaning: str
    confidence: float
    resolution_status: str

    def to_dict(self) -> dict:
        return asdict(self)


CUCET_STATUS_REGISTRY: Dict[str, CucetStatusMapping] = {}

_CUCET_DEFINITIONS: List[tuple] = [
    ("Eligible-for-Scholarship",                          "ELIGIBLE_SCHOLARSHIP",       1, "Passed exam with scholarship eligibility",  1.0, "RESOLVED"),
    ("Eligible for Admission but not for Scholarship",    "ELIGIBLE_NO_SCHOLARSHIP",    1, "Passed exam without scholarship",           1.0, "RESOLVED"),
    ("Not-Eligible for Admissions",                       "NOT_ELIGIBLE",               1, "Attempted exam but failed",                 1.0, "RESOLVED"),
    ("No Show",                                           "NO_SHOW",                    0, "Registered but did not appear",             1.0, "RESOLVED"),
    ("Upcoming Exam",                                     "UPCOMING",                   0, "Scheduled but not yet taken",               1.0, "RESOLVED"),
    ("",                                                  "NOT_REGISTERED",             0, "Not registered for CUCET",                  1.0, "RESOLVED"),
]

for _raw, _canon, _flag, _meaning, _conf, _status in _CUCET_DEFINITIONS:
    key = _raw.strip().lower()
    CUCET_STATUS_REGISTRY[key] = CucetStatusMapping(
        raw_value=_raw,
        canonical_value=_canon,
        cucet_flag=_flag,
        business_meaning=_meaning,
        confidence=_conf,
        resolution_status=_status,
    )

UNMAPPED_CUCET = CucetStatusMapping(
    raw_value="",
    canonical_value="UNMAPPED",
    cucet_flag=0,
    business_meaning="Unknown CUCET status — requires review",
    confidence=0.0,
    resolution_status="REVIEW_REQUIRED",
)


def resolve_cucet_status(raw_value: Optional[str]) -> CucetStatusMapping:
    """Resolve a raw mx_CUCET_Exam_Status value."""
    if raw_value is None:
        return CUCET_STATUS_REGISTRY.get("", UNMAPPED_CUCET)
    normalized = raw_value.strip().lower()
    return CUCET_STATUS_REGISTRY.get(normalized, UNMAPPED_CUCET)
