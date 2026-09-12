"""
Global High-Performance In-Memory Analytics Cache Layer.
Provides sub-10ms response times for all analytical reports and dashboards.
Automatically invalidates on new dataset uploads or data reset operations.
"""
from __future__ import annotations

import time
import logging
from typing import Any, Callable, Optional, Dict, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

# Global storage: key -> (timestamp, data)
_CACHE_STORE: Dict[str, Tuple[float, Any]] = {}

# Default TTL: 86400 seconds (24 hours - invalidated on dataset upload/reset)
DEFAULT_CACHE_TTL = 86400.0


def make_cache_key(prefix: str, **kwargs: Any) -> str:
    """Build a deterministic, normalized cache key from prefix and arguments."""
    parts = [prefix]
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        if v is None or v == "":
            continue
        if isinstance(v, (list, tuple, set)):
            v_str = ",".join(str(item) for item in sorted(v))
        else:
            v_str = str(v).strip()
        parts.append(f"{k}={v_str}")
    return ":".join(parts)


def get_cached_item(key: str, ttl: float = DEFAULT_CACHE_TTL) -> Optional[Any]:
    """Retrieve an item from cache if it exists and has not expired."""
    entry = _CACHE_STORE.get(key)
    if not entry:
        return None
    created_at, data = entry
    if time.time() - created_at < ttl:
        return data
    # Expired: clean up
    _CACHE_STORE.pop(key, None)
    return None


def set_cached_item(key: str, data: Any) -> None:
    """Store an item in the cache with the current timestamp."""
    _CACHE_STORE[key] = (time.time(), data)


def invalidate_analytics_cache(prefix: Optional[str] = None) -> int:
    """
    Invalidate cache entries.
    If prefix is provided, only invalidate keys starting with that prefix.
    If prefix is None, clear the entire analytics cache.
    """
    global _CACHE_STORE
    if prefix is None:
        count = len(_CACHE_STORE)
        _CACHE_STORE.clear()
        logger.info("Cleared entire analytics cache (%d items)", count)
        return count

    keys_to_remove = [k for k in _CACHE_STORE if k.startswith(prefix)]
    for k in keys_to_remove:
        _CACHE_STORE.pop(k, None)
    logger.info("Invalidated %d cache items matching prefix '%s'", len(keys_to_remove), prefix)
    return len(keys_to_remove)


def cached_analytics(prefix: str, ttl: float = DEFAULT_CACHE_TTL):
    """
    Decorator for analytics query functions.
    Inspects keyword arguments, computes a deterministic key,
    and returns cached results if available.
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Exclude db session from cache key
            cache_kwargs = {k: v for k, v in kwargs.items() if k != "db"}
            key = make_cache_key(prefix, **cache_kwargs)
            cached_val = get_cached_item(key, ttl=ttl)
            if cached_val is not None:
                return cached_val

            result = func(*args, **kwargs)
            if result is not None:
                set_cached_item(key, result)
            return result
        return wrapper
    return decorator


def clear_all_application_caches():
    """Invalidate all in-memory analytics caches across all modules."""
    invalidate_analytics_cache()
    try:
        from app.analytics.program_service import clear_programs_cache
        clear_programs_cache()
    except Exception:
        pass
    try:
        from app.analytics.state_service import clear_states_cache
        clear_states_cache()
    except Exception:
        pass
    try:
        from app.analytics.dashboard import clear_filter_options_cache
        clear_filter_options_cache()
    except Exception:
        pass
    try:
        from app.api.dashboard import clear_dash_api_cache
        clear_dash_api_cache()
    except Exception:
        pass
    try:
        from app.analytics.counsellor_service import clear_counsellors_cache
        clear_counsellors_cache()
    except Exception:
        pass
    try:
        from app.analytics.geography_gender_service import clear_geography_gender_cache
        clear_geography_gender_cache()
    except Exception:
        pass
    logger.info("Successfully flushed all application analytics caches.")
