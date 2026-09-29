"""Lifecycle helpers for cached S2000-PP configuration tables."""

from __future__ import annotations

S2000_PP_CONFIGURATION_CACHE_KEYS = (
    "s2000_pp_configuration_cache",
    "s2000_pp_mapping_reconciliation_cache",
)


def invalidate_s2000_pp_configuration_caches(
    domain_data: dict,
    gateway_id: str,
) -> None:
    """Invalidate every configuration view held for one S2000-PP gateway."""
    for cache_key in S2000_PP_CONFIGURATION_CACHE_KEYS:
        cache = domain_data.get(cache_key)
        invalidate = getattr(cache, "invalidate", None)
        if callable(invalidate):
            invalidate(gateway_id)
