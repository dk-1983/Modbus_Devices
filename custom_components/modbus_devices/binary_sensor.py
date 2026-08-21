"""Support for Modbus Devices binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import Config
from .coordinator import ModbusDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""

    entry_data = hass.data[Config.DOMAIN][entry.entry_id]

    device = entry_data["device"]
    coordinator = entry_data["coordinator"]

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

        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    Config.DOMAIN,
                    getattr(device, "attr_device_identifier", None)
                    or self._entry.entry_id,
                ),
            },
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
        )

    @property
    def is_on(self) -> bool:
        """Return sensor state."""

        data = self.coordinator.data

        if not data:
            return False

        inputs = data.get("inputs", {})

        input_state = inputs.get(
            self._input["input_number"]
        )

        if input_state is None:
            return False

        return input_state["state"]

    @property
    def available(self) -> bool:
        """Return availability."""

        return self.coordinator.last_update_success

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
