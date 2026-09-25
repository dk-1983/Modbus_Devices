"""Writable time controls for Modbus Devices."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
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
    """Set up writable Modbus time entities."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    device = coordinator.device
    description_reader = getattr(device, "get_time_descriptions", None)
    if not callable(description_reader):
        async_add_entities([])
        return
    async_add_entities(
        ModBusTimeEntity(coordinator, device, entry, description)
        for description in description_reader()
    )


class ModBusTimeEntity(CoordinatorEntity, TimeEntity):
    """Representation of one readback-confirmed Modbus time parameter."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._device = device
        self._time_id = description["time_id"]
        translation_key = description.get("translation_key")
        if translation_key:
            self._attr_translation_key = translation_key
        else:
            self._attr_name = description["name"]
        self._attr_icon = description.get("icon")
        self._attr_entity_category = description.get("entity_category")
        self._attr_unique_id = f"{entry.entry_id}_{self._time_id}"
        self._attr_device_info = device_info_for_entry(device, entry)

    @property
    def native_value(self) -> time | None:
        """Return the latest confirmed time value."""
        current = (self.coordinator.data or {}).get("times", {}).get(self._time_id)
        return None if current is None else current.get("value")

    async def async_set_value(self, value: time) -> None:
        """Write and publish one confirmed time value."""
        confirmed = await self._device.async_set_time(self._time_id, value)
        self.coordinator.async_apply_confirmed_write(
            ("times", self._time_id, "value"),
            confirmed,
        )
