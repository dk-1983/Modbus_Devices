"""Support for Modbus Devices Switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import Config
from .device_info import via_device_for_entry
from .runtime import ModbusDevicesConfigEntry

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Modbus switch entities."""

    runtime = entry.runtime_data
    device = runtime.device
    coordinator = runtime.coordinator

    entities = []

    description_reader = getattr(device, "get_output_descriptions", None)
    outputs = (
        description_reader()
        if callable(description_reader)
        else (coordinator.data or {}).get("outputs", {}).values()
    )

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

        identity = getattr(device, "attr_unique_id_prefix", None)
        self._attr_unique_id = (
            f"{identity}_output_{self._output_number}"
            if identity
            else f"{entry.entry_id}_{self._output_number}"
        )

        self._attr_device_class = output["device_class"]

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
            via_device=via_device_for_entry(entry),
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

    @property
    def extra_state_attributes(self) -> dict:
        """Expose static passport metadata without creating runtime entities."""
        return {
            **dict(getattr(self._device, "attr_device_metadata", {})),
            "high_speed": bool(self._output.get("high_speed", False)),
            "modbus_address": self._output.get("address"),
            "modbus_data_area": self._output.get("data_type"),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Turn switch on."""
        await self._device.set_output(
            self._output_number,
            True,
        )
        self.coordinator.async_apply_optimistic_write(
            ("outputs", self._output_number, "state"),
            True,
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn switch off."""
        await self._device.set_output(
            self._output_number,
            False,
        )
        self.coordinator.async_apply_optimistic_write(
            ("outputs", self._output_number, "state"),
            False,
        )
