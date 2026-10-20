"""
Lead Type Resolver Engine

Dynamically resolves lead sources into canonical lead type categories
using organization.source_master as the authoritative source.
Eliminates hardcoded keyword sets.
"""

from typing import Optional, Set
from sqlalchemy.orm import Session

# Deprecated compatibility sets (kept empty/for interface compatibility)
IN_HOUSE_KEYWORDS: Set[str] = set()
OUT_SOURCED_KEYWORDS: Set[str] = set()

_SOURCE_LEAD_TYPE_CACHE: dict[str, str] = {}
_RESOLVER_INSTANCE = None


def _get_resolver(db: Optional[Session] = None):
    global _RESOLVER_INSTANCE
    if _RESOLVER_INSTANCE is None or db is not None:
        from app.normalization.dimension_resolver import SourceResolver
        _RESOLVER_INSTANCE = SourceResolver(db)
    return _RESOLVER_INSTANCE


def resolve_lead_type(source: Optional[str], db: Optional[Session] = None) -> str:
    """
    Resolve lead source into canonical lead type category dynamically.
    Uses organization.source_master via SourceResolver.
    Returns uppercase canonical category: 'IN HOUSE', 'OUT SOURCED', or 'OTHERS'.
    """
    if not source or not isinstance(source, str):
        return "OTHERS"

    cleaned = source.strip()
    if not cleaned:
        return "OTHERS"

    lower_key = cleaned.lower()
    if lower_key in _SOURCE_LEAD_TYPE_CACHE:
        return _SOURCE_LEAD_TYPE_CACHE[lower_key]

    resolver = _get_resolver(db)
    res = resolver.resolve(cleaned)
    lt = res.extra.get("lead_type")
    if lt and lt.strip():
        val = lt.strip().upper()
        _SOURCE_LEAD_TYPE_CACHE[lower_key] = val
        return val

    # If unmapped, default to OTHERS
    _SOURCE_LEAD_TYPE_CACHE[lower_key] = "OTHERS"
    return "OTHERS"

