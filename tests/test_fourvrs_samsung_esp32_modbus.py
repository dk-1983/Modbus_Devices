"""Protocol tests for the 4VRS Samsung-ESP32-Modbus profile."""

from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.climate import HVACMode
from homeassistant.const import Platform

from custom_components.modbus_devices.equipment.fourvrs import SamsungESP32Modbus
from custom_components.modbus_devices.modbus_client import SerializedModbusClient


def response(function_code, *, registers=None, address=None, value=None, count=None):
    return SimpleNamespace(
        function_code=function_code,
        registers=registers,
        address=address,
        value=value,
        count=count,
        dev_id=9,
        isError=lambda: False,
    )


class Client:
    def __init__(self):
        self.calls = []
        self.words = {
            **{2450 + index: index for index in range(25)},
            50: 7,
            51: 0xFFFF,
            52: 1,
            53: 1,
            58: 240,
            59: 0xFFCE,
            2475: 3,
            2476: 0x5678,
            2477: 0x1234,
            2478: 2,
            2479: 0x000F,
            2480: 1,
            2481: 0,
            2482: 255,
            2483: 25,
            2484: 3,
            2485: 2,
            2486: 5,
            2487: 0,
        }
        self.results = []

    async def read_holding_registers(self, **kwargs):
        self.calls.append(("read_holding_registers", kwargs))
        address = kwargs["address"]
        count = kwargs["count"]
        if address == 2478 and count == 1 and self.results:
            return response(3, registers=[self.results.pop(0)])
        for index in range(25):
            base = 2500 + 18 * index
            if address == base + 17 and count == 1:
                return response(3, registers=[index + 1])
            if address == base and count == 17:
                return response(3, registers=[1, index << 8, *([0] * 15)])
        return response(3, registers=[self.words[address + i] for i in range(count)])

    async def write_register(self, **kwargs):
        self.calls.append(("write_register", kwargs))
        self.words[kwargs["address"]] = kwargs["value"]
        return response(6, address=kwargs["address"], value=kwargs["value"])

    async def write_registers(self, **kwargs):
        self.calls.append(("write_registers", kwargs))
        for offset, value in enumerate(kwargs["values"]):
            self.words[kwargs["address"] + offset] = value
        return response(16, address=kwargs["address"], count=len(kwargs["values"]))


async def completed():
    return None


@pytest.mark.asyncio
async def test_snapshot_uses_zero_based_independent_ranges_and_signed_temperature():
    raw = Client()
    device = SamsungESP32Modbus(SerializedModbusClient(raw), 9)

    snapshot = await device.async_get_snapshot()

    assert device.equipment_model == "Samsung-ESP32-Modbus"
    assert device.attr_platforms == [
        Platform.CLIMATE,
        Platform.SWITCH,
        Platform.SELECT,
        Platform.NUMBER,
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
    ]
    assert snapshot["climate"] == {
        "hvac_mode": HVACMode.COOL,
        "target_temperature": 24.0,
        "current_temperature": -5.0,
        "fan_mode": "turbo",
        "swing_mode": "both",
        "preset_mode": "sleep",
        "diagnostics": {
            "fresh_core": True,
            "raw_link_state": 7,
            "raw_unit_type": 0xFFFF,
            "raw_power": 1,
            "raw_mode": 1,
            "raw_fan": 5,
        },
    }
    assert snapshot["numeric_sensors"]["core_status_count"]["value"] == 0x12345678
    assert snapshot["binary_sensors"] == {
        "core_fresh": {"state": True},
        "rtu_enabled": {"state": True},
        "tcp_enabled": {"state": True},
        "uart_tx_enabled": {"state": True},
    }
    assert [call[1]["address"] for call in raw.calls] == [
        2475,
        2517,
        2500,
        2535,
        2518,
        2553,
        2536,
        2571,
        2554,
        2589,
        2572,
        50,
        58,
        2486,
        2484,
        2485,
        2487,
    ]
    assert snapshot["state_sensors"]["extended_raw_0"]["state"] == "00"
    assert snapshot["state_sensors"]["extended_raw_5"]["state"] is None
    assert snapshot["numeric_sensors"]["extended_age_0"]["value"] == 1


@pytest.mark.asyncio
async def test_extended_catalog_is_polled_five_items_per_snapshot(monkeypatch):
    raw = Client()
    device = SamsungESP32Modbus(SerializedModbusClient(raw), 9)
    monkeypatch.setattr(
        "custom_components.modbus_devices.equipment.fourvrs.asyncio.sleep",
        lambda _delay: completed(),
    )

    await device.async_get_snapshot()
    raw.calls.clear()
    snapshot = await device.async_get_snapshot()

    assert [call[1]["address"] for call in raw.calls[1:11]] == [
        2607,
        2590,
        2625,
        2608,
        2643,
        2626,
        2661,
        2644,
        2679,
        2662,
    ]
    assert snapshot["state_sensors"]["extended_raw_5"]["state"] == "05"


@pytest.mark.asyncio
async def test_mode_from_off_uses_one_fc16_and_requires_new_pending_result(monkeypatch):
    raw = Client()
    raw.results = [2, 1, 2]
    device = SamsungESP32Modbus(SerializedModbusClient(raw), 9)
    monkeypatch.setattr(
        "custom_components.modbus_devices.equipment.fourvrs.asyncio.sleep",
        lambda _delay: completed(),
    )

    assert await device.async_set_hvac_mode(HVACMode.HEAT) == {
        "hvac_mode": HVACMode.HEAT
    }
    assert raw.calls[0] == (
        "write_registers",
        {"address": 52, "values": [1, 4], "device_id": 9},
    )
    assert [item[0] for item in raw.calls].count("write_registers") == 1
    assert raw.calls[-1] == (
        "read_holding_registers",
        {"address": 52, "count": 2, "device_id": 9},
    )


@pytest.mark.asyncio
async def test_target_temperature_uses_x10_and_rejects_invalid_steps(monkeypatch):
    raw = Client()
    raw.results = [1, 2]
    device = SamsungESP32Modbus(SerializedModbusClient(raw), 9)
    monkeypatch.setattr(
        "custom_components.modbus_devices.equipment.fourvrs.asyncio.sleep",
        lambda _delay: completed(),
    )

    assert await device.async_set_target_temperature(24) == 24.0
    assert raw.calls[0] == (
        "write_register",
        {"address": 58, "value": 240, "device_id": 9},
    )
    for invalid in (15, 31, 24.5, True):
        with pytest.raises(ValueError, match="target temperature"):
            await device.async_set_target_temperature(invalid)


def test_project_link_and_documented_protocol_versions_are_device_metadata():
    device = SamsungESP32Modbus(None, 1)

    assert device.attr_device_metadata == {
        "project": "https://github.com/dk-1983/Samsung-ESP32-MQTT-Modbus",
        "register_map_version": "0.3.0",
        "protocol": "Modbus RTU or Modbus TCP",
        "tested_firmware": "0.4.2",
    }
    assert device.attr_software_version is None


@pytest.mark.asyncio
async def test_confirmation_never_accepts_stale_confirmed_without_pending(monkeypatch):
    raw = Client()
    raw.results = [2, 2, 2]
    device = SamsungESP32Modbus(SerializedModbusClient(raw), 9)
    device.COMMAND_CONFIRM_TIMEOUT = 0
    monkeypatch.setattr(
        "custom_components.modbus_devices.equipment.fourvrs.asyncio.sleep",
        lambda _delay: completed(),
    )

    with pytest.raises(ModbusException, match="confirmation timed out"):
        await device.async_set_fan_mode("turbo")
