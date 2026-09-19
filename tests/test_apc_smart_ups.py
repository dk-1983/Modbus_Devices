"""Tests for read-only APC Smart-UPS monitoring."""

from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, Platform, UnitOfElectricPotential

from custom_components.modbus_devices.equipment.apc import SmartUPS3000RMXL


def response(function_code=3, *, registers=None, error=False):
    return SimpleNamespace(
        function_code=function_code,
        registers=registers,
        dev_id=1,
        isError=lambda: error,
    )


class Client:
    def __init__(self, status=0x0008, voltage=214):
        self.calls = []
        self.responses = {
            0x0003: response(registers=[status]),
            0x0005: response(registers=[100, 45, 55, 16, 4, 0, 1, 33, 220, 213]),
            0x0011: response(registers=[voltage, 50]),
        }

    async def read_holding_registers(self, **kwargs):
        self.calls.append(kwargs)
        value = self.responses[kwargs["address"]]
        if isinstance(value, BaseException):
            raise value
        return value


@pytest.mark.asyncio
async def test_snapshot_uses_three_field_verified_fc03_reads():
    client = Client()
    snapshot = await SmartUPS3000RMXL(client, 1).async_get_snapshot()

    assert client.calls == [
        {"address": 0x0003, "count": 1, "device_id": 1},
        {"address": 0x0005, "count": 10, "device_id": 1},
        {"address": 0x0011, "count": 2, "device_id": 1},
    ]
    assert snapshot == {
        "binary_sensors": {
            "online": {
                "state": True,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
            "on_battery": {
                "state": False,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
            "low_battery": {
                "state": False,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
            "replace_battery": {
                "state": False,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
            "overload": {
                "state": False,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
            "battery_calibration": {
                "state": False,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
            "avr_boost": {
                "state": False,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
            "avr_trim": {
                "state": False,
                "primary_code": 0x0008,
                "expanded_codes": [],
            },
        },
        "numeric_sensors": {
            "battery_charge": {
                "value": 100,
                "raw_register": 100,
                "register_address": 0x0005,
                "parameter_kind": "apc_uint16",
            },
            "runtime_remaining": {
                "value": 45,
                "raw_register": 45,
                "register_address": 0x0006,
                "parameter_kind": "apc_uint16",
            },
            "battery_voltage": {
                "value": 55,
                "raw_register": 55,
                "register_address": 0x0007,
                "parameter_kind": "apc_uint16",
            },
            "internal_temperature": {
                "value": 16,
                "raw_register": 16,
                "register_address": 0x0008,
                "parameter_kind": "apc_uint16",
            },
            "battery_pack_count": {
                "value": 1,
                "raw_register": 1,
                "register_address": 0x000B,
                "parameter_kind": "apc_uint16",
            },
            "output_load": {
                "value": 33,
                "raw_register": 33,
                "register_address": 0x000C,
                "parameter_kind": "apc_uint16",
            },
            "output_voltage": {
                "value": 213,
                "raw_register": 213,
                "register_address": 0x000E,
                "parameter_kind": "apc_uint16",
            },
            "input_voltage": {
                "value": 214,
                "raw_register": 214,
                "register_address": 0x0011,
                "parameter_kind": "apc_uint16",
            },
            "input_frequency": {
                "value": 50,
                "raw_register": 50,
                "register_address": 0x0012,
                "parameter_kind": "apc_uint16",
            },
            "status_word_3": {
                "value": 0x0008,
                "raw_register": 0x0008,
                "register_address": 0x0003,
                "parameter_kind": "apc_status_word",
            },
        },
    }


@pytest.mark.parametrize(
    ("status", "online", "on_battery"),
    [
        (0x0000, False, False),
        (0x0008, True, False),
        (0x0010, False, True),
        (0x0018, True, True),
    ],
)
@pytest.mark.asyncio
async def test_status_bits_are_decoded_independently(status, online, on_battery):
    snapshot = await SmartUPS3000RMXL(Client(status=status), 1).async_get_snapshot()
    assert snapshot["binary_sensors"]["online"]["state"] is online
    assert snapshot["binary_sensors"]["on_battery"]["state"] is on_battery
    assert snapshot["numeric_sensors"]["status_word_3"]["value"] == status


@pytest.mark.parametrize(
    ("sensor_id", "bit"),
    [
        ("battery_calibration", 0),
        ("avr_trim", 1),
        ("avr_boost", 2),
        ("online", 3),
        ("on_battery", 4),
        ("overload", 5),
        ("low_battery", 6),
        ("replace_battery", 7),
    ],
)
@pytest.mark.asyncio
async def test_every_documented_status_word_3_bit_is_lossless(sensor_id, bit):
    status = 1 << bit
    snapshot = await SmartUPS3000RMXL(Client(status=status), 1).async_get_snapshot()

    states = snapshot["binary_sensors"]
    assert states[sensor_id]["state"] is True
    assert states[sensor_id]["primary_code"] == status
    assert sum(item["state"] for item in states.values()) == 1


@pytest.mark.asyncio
async def test_zero_voltage_is_a_valid_measurement():
    snapshot = await SmartUPS3000RMXL(Client(voltage=0), 1).async_get_snapshot()
    assert snapshot["numeric_sensors"]["input_voltage"]["value"] == 0


@pytest.mark.asyncio
async def test_short_primary_measurement_block_is_rejected():
    client = Client()
    client.responses[0x0005] = response(registers=[100] * 9)

    with pytest.raises(ModbusException, match="Short Modbus response"):
        await SmartUPS3000RMXL(client, 1).async_get_snapshot()

    assert client.calls == [
        {"address": 0x0003, "count": 1, "device_id": 1},
        {"address": 0x0005, "count": 10, "device_id": 1},
    ]


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        object(),
        response(error=True, registers=[0x0008]),
        response(4, registers=[0x0008]),
        response(registers=[]),
        response(registers=[0x0008, 0]),
        response(registers=[True]),
        response(registers=[0x10000]),
    ],
)
@pytest.mark.asyncio
async def test_strict_fc03_response_validation(invalid):
    client = Client()
    client.responses[0x0003] = invalid
    with pytest.raises(ModbusException):
        await SmartUPS3000RMXL(client, 1).async_get_snapshot()
    assert client.calls == [{"address": 0x0003, "count": 1, "device_id": 1}]


@pytest.mark.asyncio
async def test_transport_timeout_propagates_without_default_values():
    client = Client()
    client.responses[0x0003] = TimeoutError("UPS response timeout")
    with pytest.raises(TimeoutError, match="UPS response timeout"):
        await SmartUPS3000RMXL(client, 1).async_get_snapshot()


@pytest.mark.asyncio
async def test_initialization_is_read_only_and_does_not_poll():
    client = Client()
    device = SmartUPS3000RMXL(client, 1)
    assert await device.data_init() is True
    assert client.calls == []
    assert not hasattr(device, "write_register")
    assert not hasattr(device, "write_coil")
    assert not hasattr(device, "get_button_descriptions")
    assert set(device.attr_platforms) == {Platform.SENSOR, Platform.BINARY_SENSOR}


def test_entity_descriptions_match_home_assistant_semantics():
    binary = {
        item["sensor_id"]: item
        for item in SmartUPS3000RMXL(None, 1).get_binary_sensor_descriptions()
    }
    numeric = {
        item["sensor_id"]: item
        for item in SmartUPS3000RMXL(None, 1).get_numeric_sensor_descriptions()
    }
    assert binary["online"]["device_class"] is BinarySensorDeviceClass.POWER
    assert binary["on_battery"]["device_class"] is BinarySensorDeviceClass.PROBLEM
    assert binary["low_battery"]["device_class"] is BinarySensorDeviceClass.BATTERY
    assert binary["replace_battery"]["device_class"] is BinarySensorDeviceClass.PROBLEM
    assert binary["overload"]["device_class"] is BinarySensorDeviceClass.PROBLEM
    assert (
        binary["battery_calibration"]["device_class"] is BinarySensorDeviceClass.RUNNING
    )
    assert binary["battery_calibration"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert binary["avr_boost"]["device_class"] is None
    assert binary["avr_trim"]["device_class"] is None
    assert numeric["input_voltage"] == {
        "sensor_id": "input_voltage",
        "name": "Input voltage",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "precision": 0,
    }
    assert numeric["status_word_3"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert numeric["status_word_3"]["state_class"] is None
    assert numeric["status_word_3"]["unit"] is None
    assert numeric["battery_charge"]["device_class"] is SensorDeviceClass.BATTERY
    assert numeric["runtime_remaining"]["device_class"] is SensorDeviceClass.DURATION
    assert numeric["battery_voltage"]["device_class"] is SensorDeviceClass.VOLTAGE
    assert (
        numeric["internal_temperature"]["device_class"] is SensorDeviceClass.TEMPERATURE
    )
    assert numeric["battery_pack_count"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert numeric["battery_pack_count"]["icon"] == "mdi:battery-outline"
    assert numeric["output_load"]["unit"] == "%"
    assert numeric["output_voltage"]["device_class"] is SensorDeviceClass.VOLTAGE
    assert numeric["input_frequency"]["device_class"] is SensorDeviceClass.FREQUENCY
