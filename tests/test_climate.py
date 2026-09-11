"""Tests for the shared Modbus climate entity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.climate import HVACMode

from custom_components.modbus_devices.climate import ModbusClimateEntity


def climate_device():
    return SimpleNamespace(
        attr_manufactures_name="Haier",
        attr_model_name="YCJ-A002",
        attr_description="Air-conditioner Modbus interface",
        attr_serial_number=None,
        attr_hardware_version=None,
        attr_software_version=None,
        get_climate_description=lambda: {
            "hvac_modes": [HVACMode.OFF, HVACMode.COOL],
            "fan_modes": ["auto"],
            "min_temp": 16,
            "max_temp": 30,
            "temperature_step": 1,
        },
        async_set_hvac_mode=AsyncMock(return_value={"hvac_mode": HVACMode.COOL}),
        async_set_target_temperature=AsyncMock(return_value=24),
        async_set_fan_mode=AsyncMock(return_value="auto"),
    )


def climate_entity(device):
    coordinator = Mock(last_update_success=True)
    coordinator.data = {"climate": {"hvac_mode": HVACMode.OFF}}
    coordinator.async_apply_optimistic_write = Mock()
    entry = SimpleNamespace(entry_id="haier-1")
    return ModbusClimateEntity(coordinator, device, entry), coordinator


@pytest.mark.asyncio
async def test_climate_updates_only_confirmed_writes():
    device = climate_device()
    entity, coordinator = climate_entity(device)

    await entity.async_set_hvac_mode(HVACMode.COOL)

    coordinator.async_apply_optimistic_write.assert_called_once_with(
        ("climate", "hvac_mode"), HVACMode.COOL
    )


@pytest.mark.asyncio
async def test_climate_does_not_publish_failed_write():
    device = climate_device()
    device.async_set_hvac_mode.side_effect = ModbusException("bad echo")
    entity, coordinator = climate_entity(device)

    with pytest.raises(ModbusException, match="bad echo"):
        await entity.async_set_hvac_mode(HVACMode.COOL)

    coordinator.async_apply_optimistic_write.assert_not_called()
