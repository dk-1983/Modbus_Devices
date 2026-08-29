"""Shared Home Assistant device metadata helpers."""

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import Config


def _metadata_text(value: object) -> str | None:
    """Return a native DeviceInfo value without inventing placeholders."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True, slots=True)
class EquipmentMetadata:
    """Optional protocol-derived metadata shared by one physical device."""

    model_id: str | None = None
    sw_version: str | None = None
    hw_version: str | None = None
    serial_number: str | None = None

    @classmethod
    def from_device(cls, device: Any) -> "EquipmentMetadata":
        """Normalize cached equipment attributes for Home Assistant DeviceInfo."""
        model_id = getattr(device, "attr_model_id", None)
        if model_id is None:
            model_id = getattr(device, "attr_device_type", None)
        return cls(
            model_id=_metadata_text(model_id),
            sw_version=_metadata_text(
                getattr(device, "attr_software_version", None)
            ),
            hw_version=_metadata_text(
                getattr(device, "attr_hardware_version", None)
            ),
            serial_number=_metadata_text(
                getattr(device, "attr_serial_number", None)
            ),
        )


def via_device_for_entry(entry: ConfigEntry) -> tuple[str, str] | None:
    """Return the persisted S2000-PP parent identity for a downstream entry."""
    options = getattr(entry, "options", None) or getattr(entry, "data", {})
    gateway_entry_id = options.get(Config.CONF_GATEWAY_ENTRY_ID)
    if not isinstance(gateway_entry_id, str) or not gateway_entry_id:
        return None
    return (Config.DOMAIN, gateway_entry_id)


def device_info_for_entry(
    device,
    entry: ConfigEntry,
    *,
    identifier: str | None = None,
) -> DeviceInfo:
    """Build stable Home Assistant device metadata for one equipment instance."""
    metadata = EquipmentMetadata.from_device(device)
    device_identifier = (
        identifier
        or getattr(device, "attr_device_identifier", None)
        or entry.entry_id
    )
    return DeviceInfo(
        identifiers={(Config.DOMAIN, device_identifier)},
        manufacturer=device.attr_manufactures_name,
        model=device.attr_model_name,
        model_id=metadata.model_id,
        name=device.attr_description,
        hw_version=metadata.hw_version,
        sw_version=metadata.sw_version,
        serial_number=metadata.serial_number,
        via_device=via_device_for_entry(entry),
    )
