"""Support for Modbus Devices Switches."""

from __future__ import annotations

import logging

from pymodbus.exceptions import ConnectionException

from homeassistant.components.switch import SwitchEntity
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
    """Set up Modbus switch entities."""

    data = hass.data[Config.DOMAIN][entry.entry_id]

    device = data["device"]
    coordinator = data["coordinator"]

    entities = []

    outputs = await device.get_outputs()

    for output in outputs:
        entities.append(
            ModBusSwitchEntity(
                coordinator=coordinator,
                device=device,
                entry=entry,
                output=output,
            )
        )

    async_add_entities(entities)


class ModBusSwitchEntity(
    CoordinatorEntity,
    SwitchEntity,
):
    """Representation of Modbus switch."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        device,
        entry: ConfigEntry,
        output: dict,
    ) -> None:
        """Initialize switch."""

        super().__init__(coordinator)

        self._device = device
        self._entry = entry
        self._output = output

        self._output_number = output["out_number"]

        self._attr_name = (
            f"{output['out_type']} "
            f"{output['out_number_view']}"
        )

        self._attr_unique_id = (
            f"{entry.entry_id}_"
            f"{self._output_number}"
        )

        self._attr_device_class = output["device_class"]

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
    def current_output(self) -> dict | None:
        """Return current output data from coordinator."""

        outputs = self.coordinator.data.get("outputs", {})

        return outputs.get(self._output_number)

    @property
    def is_on(self) -> bool:
        """Return switch state."""

        output = self.current_output

        if output is None:
            return False

        return output["state"]

    @property
    def icon(self) -> str | None:
        """Return entity icon."""

        output = self.current_output

        if output is None:
            return None

        if output["state"]:
            return output["icon_on"]

        return output["icon_off"]

    async def async_turn_on(self, **kwargs) -> None:
        """Turn switch on."""

        try:
            await self._device.set_output(
                self._output_number,
                True,
            )

            await self.coordinator.async_request_refresh()

        except ConnectionException as exc:
            _LOGGER.error(
                "Failed to turn ON output %s: %s",
                self._output_number,
                exc,
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn switch off."""

        try:
            await self._device.set_output(
                self._output_number,
                False,
            )

            await self.coordinator.async_request_refresh()

        except ConnectionException as exc:
            _LOGGER.error(
                "Failed to turn OFF output %s: %s",
                self._output_number,
                exc,
            )
