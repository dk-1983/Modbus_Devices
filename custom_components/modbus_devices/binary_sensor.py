"""Support for Modbus Devices binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .coordinator import ModbusDeviceCoordinator
from .device_info import device_info_for_entry
from .runtime import ModbusDevicesConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""

    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    device = coordinator.device

    entities = []

    for input_data in (coordinator.data or {}).get("inputs", {}).values():

        entities.append(
            ModBusBinarySensorEntity(
                coordinator=coordinator,
                device=device,
                entry=entry,
                input_data=input_data,
            )
        )

    description_reader = getattr(device, "get_binary_sensor_descriptions", None)
    if callable(description_reader):
        for description in description_reader():
            entities.append(
                ModBusDescribedBinarySensorEntity(
                    coordinator=coordinator,
                    device=device,
                    entry=entry,
                    description=description,
                )
            )

    async_add_entities(entities)

    _LOGGER.info(
        "Loaded %s binary sensors",
        len(entities),
    )


class ModBusBinarySensorEntity(
    CoordinatorEntity,
    BinarySensorEntity,
):
    """Representation of Modbus binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ModbusDeviceCoordinator,
        device,
        entry: ConfigEntry,
        input_data,
    ) -> None:
        """Initialize entity."""

        super().__init__(coordinator)

        self._device = device
        self._entry = entry
        self._input = input_data

        self._attr_name = (
            f"{input_data['input_type']} "
            f"{input_data['input_number_view']}"
        )

        identity = (
            getattr(device, "attr_unique_id_prefix", None)
            or device.attr_serial_number
            or self._entry.entry_id
        )
        self._attr_unique_id = f"{identity}_input_{input_data['input_number']}"

        self._attr_device_class = input_data["device_class"]

        self._attr_device_info = device_info_for_entry(device, entry)

    @property
    def is_on(self) -> bool | None:
        """Return sensor state."""

        data = self.coordinator.data

        if not data:
            return None

        inputs = data.get("inputs", {})

        input_state = inputs.get(
            self._input["input_number"]
        )

        if input_state is None:
            return None

        return input_state["state"]

    @property
    def extra_state_attributes(self) -> dict:
        """Expose static channel and passport metadata."""
        return {
            **dict(getattr(self._device, "attr_device_metadata", {})),
            "high_speed": bool(self._input.get("high_speed", False)),
            "modbus_address": self._input.get("address"),
            "modbus_data_area": self._input.get("data_type"),
        }

    @property
    def icon(self) -> str | None:
        """Return icon."""

        if self.is_on:
            return self._input["icon_on"]

        return self._input["icon_off"]


class ModBusDescribedBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    """Representation of a semantic binary state derived by equipment."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._sensor_id = description["sensor_id"]
        self._attr_name = description["name"]
        self._attr_device_class = description["device_class"]
        self._attr_entity_category = description.get("entity_category")
        self._attr_icon = description.get("icon")
        identity = getattr(device, "attr_unique_id_prefix", None) or entry.entry_id
        self._attr_unique_id = f"{identity}_{self._sensor_id}"
        self._attr_device_info = device_info_for_entry(device, entry)

    @property
    def is_on(self) -> bool | None:
        """Return the current semantic binary state or unknown."""
        current = (self.coordinator.data or {}).get("binary_sensors", {}).get(
            self._sensor_id
        )
        return None if current is None else current.get("state")

    @property
    def extra_state_attributes(self) -> dict:
        """Expose lossless source-state evidence and device metadata."""
        current = (self.coordinator.data or {}).get("binary_sensors", {}).get(
            self._sensor_id
        )
        metadata = dict(getattr(self.coordinator.device, "attr_device_metadata", {}))
        if current is None:
            return metadata
        return {
            **metadata,
            **{
                key: current[key]
                for key in ("primary_code", "expanded_codes")
                if key in current
            },
        }
