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
        self._number_id = description["number_id"]
        self._channel = description.get("channel")
        self._attr_name = description["name"]
        self._attr_translation_key = description.get("translation_key")
        self._attr_unique_id = f"{entry.entry_id}_{self._number_id}"
        self._attr_icon = description.get("icon")
        self._attr_native_min_value = description["native_min_value"]
        self._attr_native_max_value = description["native_max_value"]
        self._attr_native_step = description["native_step"]
        self._attr_native_unit_of_measurement = description.get(
            "native_unit_of_measurement"
        )
        self._dynamic_max_id = description.get("dynamic_max_id")
        self._attr_device_info = device_info_for_entry(device, entry)

    @property
    def native_value(self) -> float | None:
        """Return the latest confirmed numeric value."""
        if self._channel is None:
            value = (
                (self.coordinator.data or {}).get("numbers", {}).get(self._number_id)
            )
            return None if value is None else value.get("value")
        values = (self.coordinator.data or {}).get("comparator_outputs", {})
        return values.get(self._channel)

    @property
    def native_max_value(self) -> float:
        """Return a live dependent limit when the equipment defines one."""
        if self._dynamic_max_id is not None:
            dynamic = (
                (self.coordinator.data or {})
                .get("numbers", {})
                .get(self._dynamic_max_id)
            )
            if dynamic is not None:
                return min(self._attr_native_max_value, dynamic["value"])
        return self._attr_native_max_value

    async def async_set_native_value(self, value: float) -> None:
        """Write and publish one confirmed numeric value."""
        if self._channel is None:
            confirmed = await self._device.async_set_number(self._number_id, value)
            self.coordinator.async_apply_confirmed_write(
                ("numbers", self._number_id, "value"),
                confirmed,
            )
            return
        if not float(value).is_integer():
            raise ValueError("TRM-138 C.dr value must be an integer")
        output = int(value)
        await self._device.set_comparator_output(self._channel, output)
        self.coordinator.async_apply_optimistic_write(
            ("comparator_outputs", self._channel),
            output,
        )
