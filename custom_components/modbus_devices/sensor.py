"""Support for Modbus Devices Sensors."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import Config

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Modbus sensor entities."""

    data = hass.data[Config.DOMAIN][entry.entry_id]

    device = data["device"]
    coordinator = data["coordinator"]

    entities = []

    channel_reader = getattr(device, "get_chanels", None)
    channels = await channel_reader() if callable(channel_reader) else []

    for channel in channels:
        entities.append(
            ModBusSensorEntity(
                coordinator=coordinator,
                device=device,
                entry=entry,
                channel=channel,
            )
        )

    description_reader = getattr(device, "get_state_sensor_descriptions", None)
    if callable(description_reader):
        for description in description_reader():
            entities.append(
                ModBusStateSensorEntity(
                    coordinator=coordinator,
                    device=device,
                    entry=entry,
                    description=description,
                )
            )

    numeric_reader = getattr(device, "get_numeric_sensor_descriptions", None)
    if callable(numeric_reader):
        for description in numeric_reader():
            entities.append(
                ModBusNumericSensorEntity(
                    coordinator=coordinator,
                    device=device,
                    entry=entry,
                    description=description,
                )
            )

    async_add_entities(entities)


class ModBusSensorEntity(
    CoordinatorEntity,
    SensorEntity,
):
    """Representation of Modbus sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        device,
        entry: ConfigEntry,
        channel: dict,
    ) -> None:
        """Initialize sensor."""

        super().__init__(coordinator)

        self._device = device
        self._entry = entry
        self._channel = channel

        self._channel_number = channel["chanel_number"]

        self._attr_name = (
            f"{channel['chanel_type']} "
            f"{channel['chanel_number_view']}"
        )

        self._attr_unique_id = (
            f"{self._entry.entry_id}_"
            f"{self._channel_number}"
        )

        self._attr_device_class = channel["device_class"]

        self._attr_state_class = channel["state_class"]

        self._attr_native_unit_of_measurement = (
            channel["unit_of_temperature_c"]
        )

        self._attr_device_info = DeviceInfo(
            identifiers={
                (Config.DOMAIN, self._entry.entry_id),
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
    def available(self) -> bool:
        """Return entity availability."""

        return self.coordinator.last_update_success

    @property
    def current_channel(self) -> dict | None:
        """Return current channel data from coordinator."""

        channels = self.coordinator.data.get("chanels", {})

        return channels.get(self._channel_number)

    @property
    def native_value(self):
        """Return sensor value."""

        channel = self.current_channel

        if channel is None:
            return None

        value = channel.get("value")

        if not value or len(value) < 2:
            return None

        precision = value[0]

        return value[1] / (10**precision)

    @property
    def suggested_display_precision(self) -> int:
        """Return display precision."""

        channel = self.current_channel

        if channel is None:
            return 0

        value = channel.get("value")

        if not value:
            return 0

        return value[0]


class ModBusStateSensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a lossless multi-state gateway object."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._sensor_id = description["sensor_id"]
        self._attr_name = description["name"]
        self._attr_device_class = description.get("device_class")
        self._attr_icon = description.get("icon")
        self._attr_entity_category = description.get("entity_category")
        identity = getattr(device, "attr_unique_id_prefix", None) or entry.entry_id
        self._attr_unique_id = f"{identity}_{self._sensor_id}"
        device_identifier = (
            getattr(device, "attr_device_identifier", None) or entry.entry_id
        )
        self._attr_device_info = DeviceInfo(
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
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def _current(self) -> dict | None:
        data = self.coordinator.data or {}
        return data.get("state_sensors", {}).get(self._sensor_id)

    @property
    def native_value(self) -> str | None:
        current = self._current
        return None if current is None else current["state"]

    @property
    def extra_state_attributes(self) -> dict:
        current = self._current
        metadata = dict(getattr(self.coordinator.device, "attr_device_metadata", {}))
        if current is None:
            return metadata
        return {
            **metadata,
            "primary_code": current["primary_code"],
            "expanded_codes": current["expanded_codes"],
            "expanded_states": current["expanded_states"],
        }


class ModBusNumericSensorEntity(CoordinatorEntity, SensorEntity):
    """Representation of a documented S2000-PP physical numeric value."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._sensor_id = description["sensor_id"]
        self._attr_name = description["name"]
        self._attr_device_class = description["device_class"]
        self._attr_state_class = description["state_class"]
        self._attr_native_unit_of_measurement = description["unit"]
        self._attr_suggested_display_precision = description["precision"]
        self._attr_entity_category = description.get("entity_category")
        identity = getattr(device, "attr_unique_id_prefix", None) or entry.entry_id
        self._attr_unique_id = f"{identity}_{self._sensor_id}"
        device_identifier = (
            getattr(device, "attr_device_identifier", None) or entry.entry_id
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(Config.DOMAIN, device_identifier)},
            manufacturer=device.attr_manufactures_name,
            model=device.attr_model_name,
            name=device.attr_description,
            hw_version=(None if device.attr_hardware_version is None else str(device.attr_hardware_version)),
            sw_version=(None if device.attr_software_version is None else str(device.attr_software_version)),
            serial_number=device.attr_serial_number,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def _current(self) -> dict | None:
        return (self.coordinator.data or {}).get("numeric_sensors", {}).get(
            self._sensor_id
        )

    @property
    def native_value(self) -> float | None:
        current = self._current
        return None if current is None else current["value"]

    @property
    def extra_state_attributes(self) -> dict:
        current = self._current
        metadata = dict(getattr(self.coordinator.device, "attr_device_metadata", {}))
        if current is None:
            return metadata
        return {
            **metadata,
            **{
                key: current[key]
                for key in ("raw_register", "raw_count", "register_address", "parameter_kind")
                if key in current
            },
        }
