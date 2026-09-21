"""Writable enumerated controls for Modbus Devices."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Set up enumerated Modbus controls."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    device = coordinator.device
    description_reader = getattr(device, "get_select_descriptions", None)
    if not callable(description_reader):
        async_add_entities([])
        return

    async_add_entities(
        ModBusSelectEntity(coordinator, device, entry, description)
        for description in description_reader()
    )


class ModBusSelectEntity(CoordinatorEntity, SelectEntity):
    """Representation of one readback-confirmed enumerated parameter."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._device = device
        self._select_id = description["select_id"]
        self._attr_name = description["name"]
        self._attr_options = list(description["options"])
        self._attr_icon = description.get("icon")
        self._attr_entity_category = description.get("entity_category")
        self._attr_unique_id = f"{entry.entry_id}_{self._select_id}"
        self._attr_device_info = device_info_for_entry(device, entry)

    @property
    def current_option(self) -> str | None:
        current = (self.coordinator.data or {}).get("selects", {}).get(self._select_id)
        return None if current is None else current.get("state")

    async def async_select_option(self, option: str) -> None:
        confirmed = await self._device.async_set_select(self._select_id, option)
        self.coordinator.async_apply_confirmed_write(
            ("selects", self._select_id, "state"),
            confirmed,
        )
