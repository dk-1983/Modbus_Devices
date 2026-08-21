"""Regression tests for strict writes before optimistic publication."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.equipment.bolid import M3000BB1020
from custom_components.modbus_devices.switch import ModBusSwitchEntity


class Response:
    def __init__(self, *, function_code=5, address=4096, value=True, error=False):
        self.function_code = function_code
        self.address = address
        self.value = value
        self._error = error

    def isError(self):
        return self._error


class Client:
    def __init__(self, response):
        self.response = response

    async def write_coil(self, **_kwargs):
        return self.response


@pytest.mark.asyncio
async def test_m3000_fc05_echo_is_strict_before_local_state_change():
    device = M3000BB1020(Client(Response(address=4097)), 1)
    with pytest.raises(ModbusException):
        await device.set_output(1, True)
    assert device.attr_out1["state"] is None


@pytest.mark.asyncio
async def test_invalid_write_cannot_increment_coordinator_generation():
    device = M3000BB1020(Client(Response(value=False)), 1)
    coordinator = Mock(last_update_success=True)
    coordinator.data = {"outputs": {1: {"state": False}}}
    coordinator.async_apply_optimistic_write = Mock()
    entry = SimpleNamespace(entry_id="entry-1")
    entity = ModBusSwitchEntity(coordinator, device, entry, device.attr_out1)

    with pytest.raises(ModbusException):
        await entity.async_turn_on()
    coordinator.async_apply_optimistic_write.assert_not_called()
