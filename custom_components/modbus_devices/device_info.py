"""Shared Home Assistant device metadata helpers."""

from homeassistant.config_entries import ConfigEntry

from .const import Config


def via_device_for_entry(entry: ConfigEntry) -> tuple[str, str] | None:
    """Return the persisted S2000-PP parent identity for a downstream entry."""
    options = getattr(entry, "options", None) or getattr(entry, "data", {})
    gateway_entry_id = options.get(Config.CONF_GATEWAY_ENTRY_ID)
    if not isinstance(gateway_entry_id, str) or not gateway_entry_id:
        return None
    return (Config.DOMAIN, gateway_entry_id)
