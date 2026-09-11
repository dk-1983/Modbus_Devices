"""Tests for the Daikin RTD-RA interface."""

from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.climate import HVACMode

from custom_components.modbus_devices.equipment.daikin import RTDRA
from custom_components.modbus_devices.modbus_client import SerializedModbusClient


def response(function_code, *, registers=None, address=None, value=None, dev_id=4):
    return SimpleNamespace(
        function_code=function_code,
        registers=registers,
        address=address,
        value=value,
        dev_id=dev_id,
        isError=lambda: False,
    )


class FakeClient:
    def __init__(self):
        self.calls = []
        self.input_responses = [
            response(4, registers=[1, 0x4131, 0xF63C]),
            response(4, registers=[2, 0x0A8C]),
        ]
        self.write_responses = []

    async def read_holding_registers(self, **kwargs):
        self.calls.append(("read_holding_registers", kwargs))
        return response(3, registers=[21, 3, 1, 1, 1])

    async def read_input_registers(self, **kwargs):
        self.calls.append(("read_input_registers", kwargs))
        return self.input_responses.pop(0)

    async def write_register(self, **kwargs):
        self.calls.append(("write_register", kwargs))
        return (
            self.write_responses.pop(0)
            if self.write_responses
            else response(6, address=kwargs["address"], value=kwargs["value"])
        )


@pytest.mark.asyncio
async def test_snapshot_decodes_controls_status_and_signed_temperatures():
    raw = FakeClient()
    device = RTDRA(SerializedModbusClient(raw), 4)

    snapshot = await device.async_get_snapshot()

    assert snapshot["climate"] == {
        "hvac_mode": HVACMode.HEAT,
        "target_temperature": 21,
        "current_temperature": -25.0,
        "fan_mode": "speed_3",
        "swing_mode": "on",
        "diagnostics": {
            "fault_active": True,
            "fault_code": "A1",
            "thermo_state": 2,
            "raw_mode": 1,
        },
    }
    assert snapshot["numeric_sensors"]["coil_inlet_temperature"]["value"] == 27.0
    assert raw.calls == [
        ("read_holding_registers", {"address": 1, "count": 5, "device_id": 4}),
        ("read_input_registers", {"address": 121, "count": 3, "device_id": 4}),
        ("read_input_registers", {"address": 130, "count": 2, "device_id": 4}),
    ]


@pytest.mark.asyncio
async def test_mode_write_uses_documented_registers():
    raw = FakeClient()
    device = RTDRA(SerializedModbusClient(raw), 4)

    assert await device.async_set_hvac_mode(HVACMode.COOL) == {
        "hvac_mode": HVACMode.COOL
    }
    assert raw.calls == [
        ("write_register", {"address": 3, "value": 3, "device_id": 4}),
        ("write_register", {"address": 5, "value": 1, "device_id": 4}),
    ]


@pytest.mark.asyncio
async def test_wrong_device_write_echo_fails():
    raw = FakeClient()
    raw.write_responses = [response(6, address=2, value=5, dev_id=99)]
    device = RTDRA(SerializedModbusClient(raw), 4)

    with pytest.raises(ModbusException, match="Wrong Modbus device id"):
        await device.async_set_fan_mode("speed_5")
