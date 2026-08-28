"""Shared Home Assistant device metadata helpers."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import Config


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
    device_identifier = (
        identifier
        or getattr(device, "attr_device_identifier", None)
        or entry.entry_id
    )
    return DeviceInfo(
        identifiers={(Config.DOMAIN, device_identifier)},
        manufacturer=device.attr_manufactures_name,
        model=device.attr_model_name,
        name=device.attr_description,
        hw_version=(
            None
            if device.attr_hardware_version is None
            else str(device.attr_hardware_version)
        ),
        sw_version=(
            None
            if device.attr_software_version is None
            else str(device.attr_software_version)
        ),
        serial_number=device.attr_serial_number,
        via_device=via_device_for_entry(entry),
    )
