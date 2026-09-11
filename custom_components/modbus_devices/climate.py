"""Climate entities for Modbus HVAC interfaces."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
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
    """Set up a Modbus climate entity."""
    runtime = entry.runtime_data
    device = runtime.coordinator.device
    if not callable(getattr(device, "get_climate_description", None)):
        return
    async_add_entities([ModbusClimateEntity(runtime.coordinator, device, entry)])


class ModbusClimateEntity(CoordinatorEntity, ClimateEntity):
    """Represent one Modbus HVAC controller."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, device, entry) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._device = device
        description = device.get_climate_description()
        self._attr_unique_id = f"{entry.entry_id}_climate"
        self._attr_device_info = device_info_for_entry(device, entry)
        self._attr_hvac_modes = description["hvac_modes"]
        self._attr_fan_modes = description["fan_modes"]
        self._attr_min_temp = description["min_temp"]
        self._attr_max_temp = description["max_temp"]
        self._attr_target_temperature_step = description.get("temperature_step", 1)
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if description.get("swing_modes"):
            self._attr_swing_modes = description["swing_modes"]
            features |= ClimateEntityFeature.SWING_MODE
        self._attr_supported_features = features

    @property
    def _current(self) -> dict[str, Any]:
        """Return the current climate snapshot."""
        return (self.coordinator.data or {}).get("climate", {})

    @property
    def hvac_mode(self) -> HVACMode | None:
        return self._current.get("hvac_mode")

    @property
    def target_temperature(self) -> float | None:
        return self._current.get("target_temperature")

    @property
    def current_temperature(self) -> float | None:
        return self._current.get("current_temperature")

    @property
    def fan_mode(self) -> str | None:
        return self._current.get("fan_mode")

    @property
    def swing_mode(self) -> str | None:
        return self._current.get("swing_mode")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose raw protocol diagnostics without creating control entities."""
        return dict(self._current.get("diagnostics", {}))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the operating mode."""
        patch = await self._device.async_set_hvac_mode(hvac_mode)
        for key, value in patch.items():
            self.coordinator.async_apply_optimistic_write(("climate", key), value)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        value = await self._device.async_set_target_temperature(temperature)
        self.coordinator.async_apply_optimistic_write(
            ("climate", "target_temperature"), value
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        value = await self._device.async_set_fan_mode(fan_mode)
        self.coordinator.async_apply_optimistic_write(("climate", "fan_mode"), value)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the louvre mode."""
        value = await self._device.async_set_swing_mode(swing_mode)
        self.coordinator.async_apply_optimistic_write(("climate", "swing_mode"), value)
