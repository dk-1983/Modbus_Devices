"""Tests for the Samsung MIM-B19N/MIM-B19NT profile."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.climate import HVACMode

from custom_components.modbus_devices.equipment.samsung import MIMB19N
from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.modbus_client import SerializedModbusClient


def response(function_code, *, registers=None, address=None, value=None, dev_id=7):
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
        self.write_responses = []

    async def read_input_registers(self, **kwargs):
        self.calls.append(("read_input_registers", kwargs))
        if kwargs["address"] == 0:
            return response(4, registers=[0, 0, 0])
        registers = [0] * 31
        registers[0] = 0x0007
        registers[1] = 1
        registers[2] = 1
        registers[3] = 1
        registers[4] = 2
        registers[5] = 1
        registers[8] = 235
        registers[9] = 247
        return response(4, registers=registers)

    async def write_register(self, **kwargs):
        self.calls.append(("write_register", kwargs))
        if self.write_responses:
            return self.write_responses.pop(0)
        return response(6, address=kwargs["address"], value=kwargs["value"])


@pytest.mark.asyncio
async def test_snapshot_uses_selected_samsung_unit_block():
    raw = FakeClient()
    device = MIMB19N(SerializedModbusClient(raw), 7)
    device.configure_subdevice_address(2)

    snapshot = await device.async_get_snapshot()

    assert raw.calls == [
        ("read_input_registers", {"address": 0, "count": 3, "device_id": 7}),
        ("read_input_registers", {"address": 150, "count": 31, "device_id": 7}),
    ]
    assert snapshot["climate"]["hvac_mode"] is HVACMode.COOL
    assert snapshot["climate"]["target_temperature"] == 23.5
    assert snapshot["climate"]["current_temperature"] == 24.7
    assert snapshot["climate"]["fan_mode"] == "medium"
    assert snapshot["climate"]["swing_mode"] == "vertical"
    assert snapshot["binary_sensors"]["unit_link"]["state"] is True


@pytest.mark.asyncio
async def test_disconnected_unit_keeps_diagnostics_but_hides_climate_state():
    raw = FakeClient()

    async def disconnected(**kwargs):
        raw.calls.append(("read_input_registers", kwargs))
        count = kwargs["count"]
        return response(4, registers=[0] * count)

    raw.read_input_registers = disconnected
    device = MIMB19N(SerializedModbusClient(raw), 7)

    snapshot = await device.async_get_snapshot()

    assert snapshot["climate"]["hvac_mode"] is None
    assert snapshot["climate"]["current_temperature"] is None
    assert snapshot["binary_sensors"]["unit_link"]["state"] is False
    assert snapshot["numeric_sensors"]["gateway_error_code"]["value"] == 0


@pytest.mark.asyncio
async def test_controls_write_documented_registers_for_selected_unit():
    raw = FakeClient()
    device = MIMB19N(SerializedModbusClient(raw), 7)
    device.configure_subdevice_address(3)

    assert await device.async_set_hvac_mode(HVACMode.HEAT) == {
        "hvac_mode": HVACMode.HEAT
    }
    assert await device.async_set_target_temperature(21.5) == 21.5
    assert await device.async_set_fan_mode("high") == "high"
    assert await device.async_set_swing_mode("off") == "off"

    assert raw.calls == [
        ("write_register", {"address": 203, "value": 4, "device_id": 7}),
        ("write_register", {"address": 202, "value": 1, "device_id": 7}),
        ("write_register", {"address": 208, "value": 215, "device_id": 7}),
        ("write_register", {"address": 204, "value": 3, "device_id": 7}),
        ("write_register", {"address": 205, "value": 0, "device_id": 7}),
    ]


def test_rejects_invalid_unit_and_control_values():
    device = MIMB19N(None, 7)
    with pytest.raises(ValueError, match="0..47"):
        device.configure_subdevice_address(48)


@pytest.mark.asyncio
async def test_wrong_fc06_echo_is_rejected():
    raw = FakeClient()
    raw.write_responses = [response(6, address=999, value=220)]
    device = MIMB19N(SerializedModbusClient(raw), 7)

    with pytest.raises(ModbusException, match="Wrong FC06 address"):
        await device.async_set_target_temperature(22)


@pytest.mark.asyncio
async def test_config_flow_collects_separate_samsung_unit_address():
    async def executor(target, *args):
        return target(*args)

    flow = ModbusDevicesConfigFlow()
    flow.hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(async_entries=lambda _: []),
        async_add_executor_job=executor,
    )
    flow._selected_manufacturer = "Samsung"
    flow._selected_category = "climate_control"
    flow._manufacturer_devices = ["MIMB19N"]
    flow._data = {Config.CONF_MODBUS_MODE: Config.MODBUS_RTU_OVER_TCP}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()

    result = await flow.async_step_device({Config.CONF_DEVICE_CLASS: "MIMB19N"})
    assert result["step_id"] == "subdevice_address"

    result = await flow.async_step_subdevice_address(
        {Config.CONF_SUBDEVICE_ADDRESS: 12}
    )
    assert result["step_id"] == "rtu_over_tcp"
    assert flow._data[Config.CONF_SUBDEVICE_ADDRESS] == 12

    result = await flow._async_connection_ready("endpoint")
    flow.async_set_unique_id.assert_awaited_once_with("endpoint:subdevice:12")
    assert result["title"] == "Samsung MIMB19N unit 12"
