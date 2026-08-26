"""Build dynamic native Lovelace cards from Home Assistant registries."""

from dataclasses import dataclass
from typing import Any

from custom_components.modbus_devices.const import Config

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .profile import (
    DevicePresentation,
    PresentationIdentity,
    PresentationProfile,
    PresentationRole,
    PresentationSection,
)
from .registry import DevicePresentationRegistry


@dataclass(frozen=True, slots=True)
class _Candidate:
    entry: Any
    semantic_key: str
    section: PresentationSection
    role_index: int | None


def _device_identifier(device) -> str | None:
    identifiers = sorted(
        identifier
        for domain, identifier in device.identifiers
        if domain == Config.DOMAIN
    )
    return identifiers[0] if identifiers else None


def _semantic_key(unique_id: str, device_identifier: str) -> str:
    prefix = f"{device_identifier}_"
    return unique_id.removeprefix(prefix)


def _entry_category(entry) -> EntityCategory | None:
    category = getattr(entry, "entity_category", None)
    if category is None or isinstance(category, EntityCategory):
        return category
    try:
        return EntityCategory(category)
    except ValueError:
        return None


def _matching_role(
    profile: PresentationProfile,
    semantic_key: str,
    entity_domain: str,
    unique_id: str,
) -> tuple[int, PresentationRole] | None:
    for index, role in enumerate(profile.roles):
        key_matches = role.key == semantic_key or (
            role.match_unique_id_suffix and unique_id.endswith(f"_{role.key}")
        )
        if key_matches and (
            role.entity_domain is None or role.entity_domain == entity_domain
        ):
            return index, role
    return None


def _candidate(
    profile: PresentationProfile,
    entry,
    device_identifier: str,
) -> _Candidate | None:
    if getattr(entry, "disabled_by", None) is not None:
        return None
    semantic_key = _semantic_key(entry.unique_id, device_identifier)
    matched = _matching_role(profile, semantic_key, entry.domain, entry.unique_id)
    if matched is not None:
        role_index, role = matched
        return _Candidate(entry, semantic_key, role.section, role_index)
    if not profile.include_unknown:
        return None
    category = _entry_category(entry)
    if category is EntityCategory.CONFIG and not profile.include_config:
        return None
    if category is EntityCategory.DIAGNOSTIC:
        if not profile.include_diagnostic:
            return None
        section = PresentationSection.DIAGNOSTIC
    else:
        section = PresentationSection.PRIMARY
    return _Candidate(entry, semantic_key, section, None)


def _sort_key(candidate: _Candidate) -> tuple:
    section = 0 if candidate.section is PresentationSection.PRIMARY else 1
    known = 0 if candidate.role_index is not None else 1
    order = candidate.role_index if candidate.role_index is not None else 0
    return (
        section,
        known,
        order,
        candidate.entry.domain,
        candidate.semantic_key,
        candidate.entry.unique_id,
        candidate.entry.entity_id,
    )


def _entity_row(hass, entry) -> dict[str, str]:
    """Build a native row using Home Assistant's registry-relative name."""
    row = {"entity": entry.entity_id}
    if relative_name := er.async_get_unprefixed_name(hass, entry):
        row["name"] = relative_name
    return row


def _config_entry_identity(hass, device) -> PresentationIdentity:
    entry_ids = sorted(device.config_entries)
    if device.primary_config_entry in device.config_entries:
        entry_ids.remove(device.primary_config_entry)
        entry_ids.insert(0, device.primary_config_entry)
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != Config.DOMAIN:
            continue
        options = entry.options or entry.data
        return PresentationIdentity(
            options.get(Config.CONF_MANUFACTURER),
            options.get(Config.CONF_DEVICE_CLASS),
            device.model,
        )
    return PresentationIdentity(device.manufacturer, None, device.model)


async def async_build_device_card(
    hass,
    device_id: str,
    *,
    profiles: DevicePresentationRegistry | None = None,
) -> DevicePresentation | None:
    """Build one current native card without touching dashboard storage or runtime."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None or (device_identifier := _device_identifier(device)) is None:
        return None

    if profiles is None:
        from . import DEFAULT_REGISTRY  # noqa: PLC0415

        profiles = DEFAULT_REGISTRY
    profile = profiles.resolve(_config_entry_identity(hass, device))
    entries = er.async_entries_for_device(er.async_get(hass), device_id)
    candidates = [
        candidate
        for entry in entries
        if (candidate := _candidate(profile, entry, device_identifier)) is not None
    ]
    if not candidates:
        return None

    candidates.sort(key=_sort_key)
    title = device.name_by_user or device.name or device.model or device.id
    return DevicePresentation(
        device_id=device.id,
        area_id=device.area_id,
        profile_id=profile.profile_id,
        card={
            "type": profile.card_type,
            "title": title,
            "show_header_toggle": False,
            "entities": [
                _entity_row(hass, candidate.entry) for candidate in candidates
            ],
        },
    )
