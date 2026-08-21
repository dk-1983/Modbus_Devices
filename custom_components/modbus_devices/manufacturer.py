"""Canonical manufacturer names and legacy compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .const import Config


@dataclass(frozen=True, slots=True)
class Manufacturer:
    """Explicit manufacturer registry entry."""

    canonical_name: str
    module_name: str
    legacy_names: frozenset[str] = frozenset()


MANUFACTURERS: tuple[Manufacturer, ...] = (
    Manufacturer("Bolid", "bolid", frozenset({"bolid"})),
    Manufacturer("Dyna Drive", "dyna_drive"),
    Manufacturer(
        "Owen",
        "owen",
        frozenset({"Oven", "OWEN", "OVEN", "oven", "owen"}),
    ),
)

_BY_NAME = {
    name: manufacturer
    for manufacturer in MANUFACTURERS
    for name in {manufacturer.canonical_name, *manufacturer.legacy_names}
}


def resolve_manufacturer(value: str) -> Manufacturer:
    """Resolve a canonical or explicitly supported legacy manufacturer value."""
    try:
        return _BY_NAME[value.strip()]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"Unsupported manufacturer: {value!r}") from exc


def canonical_manufacturer_name(value: str) -> str:
    """Return the explicitly registered canonical manufacturer name."""
    return resolve_manufacturer(value).canonical_name


def manufacturer_module_name(value: str) -> str:
    """Return the equipment module for a manufacturer value."""
    return resolve_manufacturer(value).module_name


def canonicalize_manufacturer_options(
    options: Mapping[str, Any],
) -> dict[str, Any]:
    """Copy config options with a canonical persisted manufacturer value."""
    normalized = dict(options)
    manufacturer = normalized.get(Config.CONF_MANUFACTURER)
    if manufacturer:
        normalized[Config.CONF_MANUFACTURER] = canonical_manufacturer_name(
            manufacturer
        )
    return normalized


def canonicalize_manufacturer_unique_id(unique_id: str) -> str:
    """Canonicalize legacy manufacturer tokens for identity comparison only."""
    canonical = unique_id
    for legacy_name in resolve_manufacturer("Owen").legacy_names:
        canonical = canonical.replace(f"_{legacy_name}_", "_Owen_")
    return canonical
