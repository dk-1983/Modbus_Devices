"""Writable numeric controls for Modbus Devices."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up writable Modbus number entities."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    device = coordinator.device
    description_reader = getattr(device, "get_number_descriptions", None)
    if not callable(description_reader):
        async_add_entities([])
        return

    async_add_entities(
        ModBusNumberEntity(coordinator, device, entry, description)
        for description in description_reader()
    )


class ModBusNumberEntity(CoordinatorEntity, NumberEntity):
    """Representation of one writable numeric Modbus parameter."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._device = device
        self._channel = description["channel"]
        self._attr_name = description["name"]
        self._attr_unique_id = f"{entry.entry_id}_{description['number_id']}"
        self._attr_icon = description.get("icon")
        self._attr_native_min_value = description["native_min_value"]
        self._attr_native_max_value = description["native_max_value"]
        self._attr_native_step = description["native_step"]
        self._attr_device_info = device_info_for_entry(
            device,
            entry,
            identifier=entry.entry_id,
        )

    @property
    def native_value(self) -> int | None:
        """Return the last FC03-confirmed C.dr value."""
        values = (self.coordinator.data or {}).get("comparator_outputs", {})
        return values.get(self._channel)

    async def async_set_native_value(self, value: float) -> None:
        """Write one integral C.dr value and publish only confirmed success."""
        if not float(value).is_integer():
            raise ValueError("TRM-138 C.dr value must be an integer")
        output = int(value)
        await self._device.set_comparator_output(self._channel, output)
        self.coordinator.async_apply_optimistic_write(
            ("comparator_outputs", self._channel),
            output,
        )
