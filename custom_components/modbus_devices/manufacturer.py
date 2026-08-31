"""Canonical manufacturer registry and internal module resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .const import Config


@dataclass(frozen=True, slots=True)
class Manufacturer:
    """Explicit manufacturer registry entry."""

    canonical_name: str
    module_name: str


MANUFACTURERS: tuple[Manufacturer, ...] = (
    Manufacturer("Bolid", "bolid"),
    Manufacturer("Dyna Drive", "dyna_drive"),
    Manufacturer("Owen", "owen"),
    Manufacturer("Zuked", "zuked"),
)

_BY_NAME = {manufacturer.canonical_name: manufacturer for manufacturer in MANUFACTURERS}
_BY_MODULE_NAME = {
    manufacturer.module_name: manufacturer for manufacturer in MANUFACTURERS
}


def resolve_manufacturer(value: str) -> Manufacturer:
    """Resolve a canonical or explicitly supported legacy manufacturer value."""
    try:
        return _BY_NAME[value]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"Unsupported manufacturer: {value!r}") from exc


def canonical_manufacturer_name(value: str) -> str:
    """Return the explicitly registered canonical manufacturer name."""
    return resolve_manufacturer(value).canonical_name


def manufacturer_module_name(value: str) -> str:
    """Return a module for a manufacturer value or exact internal module key."""
    if value in _BY_MODULE_NAME:
        return value
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
