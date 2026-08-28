"""Support for Modbus Devices command buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .device_info import device_info_for_entry
from .runtime import ModbusDevicesConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up documented finite Modbus command buttons."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    device = coordinator.device
    description_reader = getattr(device, "get_button_descriptions", None)
    descriptions = description_reader() if callable(description_reader) else []
    async_add_entities(
        ModBusCommandButtonEntity(coordinator, device, entry, description)
        for description in descriptions
    )


class ModBusCommandButtonEntity(CoordinatorEntity, ButtonEntity):
    """A finite device command whose result is confirmed by normal polling."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._device = device
        self._command = description["command"]
        self._attr_name = description["name"]
        self._attr_entity_category = description.get("entity_category")
        identity = getattr(device, "attr_unique_id_prefix", None) or entry.entry_id
        self._attr_unique_id = f"{identity}_{description['button_id']}"
        self._attr_device_info = device_info_for_entry(device, entry)

    async def async_press(self) -> None:
        """Send one validated command without optimistic status or readback."""
        await self._device.async_send_command(self._command)
