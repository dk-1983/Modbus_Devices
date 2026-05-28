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

    channels = await device.get_chanels()

    for channel in channels:
        entities.append(
            ModBusSensorEntity(
                coordinator=coordinator,
                device=device,
                entry=entry,
                channel=channel,
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
            hw_version=str(device.attr_hardware_version),
            sw_version=str(device.attr_software_version),
            serial_number=device.attr_serial_number,
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""

        return self.coordinator.last_update_success

    @property
    def current_channel(self) -> dict | None:
        """Return current channel data from coordinator."""

        channels = self.coordinator.data.get("channels", {})

        return channels.get(self._channel_number)

    @property
    def native_value(self):
        """Return sensor value."""

        channel = self.current_channel

        if channel is None:
            return None

        value = channel["value"]

        precision = value[0]

        return value[1] / (10**precision)

    @property
    def suggested_display_precision(self) -> int:
        """Return display precision."""

        channel = self.current_channel

        if channel is None:
            return 0

        return channel["value"][0]
