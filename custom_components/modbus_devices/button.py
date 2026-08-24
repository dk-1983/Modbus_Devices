"""Support for Modbus Devices command buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up documented finite Modbus command buttons."""
    runtime = entry.runtime_data
    device = runtime.device
    coordinator = runtime.coordinator
    description_reader = getattr(device, "get_button_descriptions", None)
    descriptions = description_reader() if callable(description_reader) else []
    async_add_entities(
        ModBusCommandButtonEntity(coordinator, device, entry, description)
        for description in descriptions
    )


class ModBusCommandButtonEntity(CoordinatorEntity, ButtonEntity):
    """A finite device command whose result is confirmed by normal polling."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, device, entry: ConfigEntry, description) -> None:
        super().__init__(coordinator)
        self._device = device
        self._command = description["command"]
        self._attr_name = description["name"]
        self._attr_entity_category = description.get("entity_category")
        identity = getattr(device, "attr_unique_id_prefix", None) or entry.entry_id
        self._attr_unique_id = f"{identity}_{description['button_id']}"
        device_identifier = (
            getattr(device, "attr_device_identifier", None) or entry.entry_id
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(Config.DOMAIN, device_identifier)},
            manufacturer=device.attr_manufactures_name,
            model=device.attr_model_name,
            name=device.attr_description,
            hw_version=None
            if device.attr_hardware_version is None
            else str(device.attr_hardware_version),
            sw_version=None
            if device.attr_software_version is None
            else str(device.attr_software_version),
            serial_number=device.attr_serial_number,
            via_device=via_device_for_entry(entry),
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        """Send one validated command without optimistic status or readback."""
        await self._device.async_send_command(self._command)
