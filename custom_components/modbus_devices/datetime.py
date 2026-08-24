"""Support for Modbus Devices DateTime entities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from pymodbus.exceptions import ConnectionException

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import Config
from .device_info import via_device_for_entry
from .runtime import ModbusDevicesConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Modbus datetime entities."""

    runtime = entry.runtime_data
    device = runtime.device
    coordinator = runtime.coordinator

    entities = []

    for number in device.attr_clock_iter:
        entities.append(
            ModBusDevicesDateTime(
                coordinator=coordinator,
                device=device,
                entry=entry,
                number=number,
            )
        )

    async_add_entities(entities)


class ModBusDevicesDateTime(
    CoordinatorEntity,
    DateTimeEntity,
):
    """Representation of Modbus datetime."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        device,
        entry: ConfigEntry,
        number: int,
    ) -> None:
        """Initialize datetime entity."""

        super().__init__(coordinator)

        self._device = device
        self._entry = entry
        self._number = number

        self._attr_name = (
            f"{device.attr_description} clock"
        )

        self._attr_unique_id = (
            f"{entry.entry_id}_clock_{number}"
        )

        self._attr_device_info = DeviceInfo(
            identifiers={
                (Config.DOMAIN, entry.entry_id),
            },
            manufacturer=device.attr_manufactures_name,
            model=device.attr_model_name,
            name=device.attr_description,
            hw_version=str(device.attr_hardware_version),
            sw_version=str(device.attr_software_version),
            serial_number=device.attr_serial_number,
            via_device=via_device_for_entry(entry),
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""

        return self.coordinator.last_update_success

    @property
    def native_value(self) -> datetime | None:
        """Return datetime value."""

        controller_time = self.coordinator.data.get("time")

        if controller_time is None:
            return None

        return controller_time + timedelta(
            hours=Config.TIME_DELTA
        )

    async def async_set_value(
        self,
        value: datetime,
    ) -> None:
        """Set datetime manually."""

        try:
            await self._device.set_time(value)
            self.coordinator.async_apply_optimistic_write(
                ("time",),
                value - timedelta(hours=Config.TIME_DELTA),
            )

            _LOGGER.info(
                "Controller time updated: %s",
                value,
            )

        except ConnectionException as exc:
            _LOGGER.error(
                "Failed to update controller time: %s",
                exc,
            )
            raise
