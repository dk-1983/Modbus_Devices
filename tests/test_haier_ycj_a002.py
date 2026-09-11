"""Tests for the Haier YCJ-A002 interface."""

from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.climate import HVACMode

from custom_components.modbus_devices.equipment.haier import YCJA002
from custom_components.modbus_devices.modbus_client import SerializedModbusClient


def response(function_code, *, registers=None, bits=None, address=None, value=None):
    return SimpleNamespace(
        function_code=function_code,
        registers=registers,
        bits=bits,
        address=address,
        value=value,
        dev_id=7,
        isError=lambda: False,
    )


class FakeClient:
    def __init__(self):
        self.calls = []
        self.write_responses = []

    async def read_coils(self, **kwargs):
        self.calls.append(("read_coils", kwargs))
        return response(1, bits=[True])

    async def read_holding_registers(self, **kwargs):
        self.calls.append(("read_holding_registers", kwargs))
        return response(3, registers=[23, 1, 4, 1])

    async def read_input_registers(self, **kwargs):
        self.calls.append(("read_input_registers", kwargs))
        return response(4, registers=[24, 0, 0])

    async def write_register(self, **kwargs):
        self.calls.append(("write_register", kwargs))
        return (
            self.write_responses.pop(0)
            if self.write_responses
            else response(6, address=kwargs["address"], value=kwargs["value"])
        )

    async def write_coil(self, **kwargs):
        self.calls.append(("write_coil", kwargs))
        return (
            self.write_responses.pop(0)
            if self.write_responses
            else response(5, address=kwargs["address"], value=kwargs["value"])
        )


@pytest.mark.asyncio
async def test_snapshot_uses_documented_register_map():
    raw = FakeClient()
    device = YCJA002(SerializedModbusClient(raw), 7)

    snapshot = await device.async_get_snapshot()

    assert snapshot["climate"] == {
        "hvac_mode": HVACMode.COOL,
        "target_temperature": 23,
        "current_temperature": 24,
        "fan_mode": "auto",
        "swing_mode": None,
        "diagnostics": {
            "fault_code": 0,
            "lock_state": 1,
            "compatibility_unit_number": 0,
            "raw_mode": 1,
            "raw_fan": 4,
        },
    }
    assert raw.calls == [
        ("read_coils", {"address": 0, "count": 1, "device_id": 7}),
        ("read_holding_registers", {"address": 0, "count": 4, "device_id": 7}),
        ("read_input_registers", {"address": 0, "count": 3, "device_id": 7}),
    ]


@pytest.mark.asyncio
async def test_mode_write_uses_strict_fc06_then_fc05():
    raw = FakeClient()
    device = YCJA002(SerializedModbusClient(raw), 7)

    assert await device.async_set_hvac_mode(HVACMode.HEAT) == {
        "hvac_mode": HVACMode.HEAT
    }
    assert raw.calls == [
        ("write_register", {"address": 1, "value": 2, "device_id": 7}),
        ("write_coil", {"address": 0, "value": True, "device_id": 7}),
    ]


@pytest.mark.asyncio
async def test_wrong_write_echo_fails():
    raw = FakeClient()
    raw.write_responses = [response(6, address=99, value=25)]
    device = YCJA002(SerializedModbusClient(raw), 7)

    with pytest.raises(ModbusException, match="Wrong FC06 address"):
        await device.async_set_target_temperature(25)
