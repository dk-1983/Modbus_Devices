"""Document-derived tests for the ERMAN ER-G-220-05 drive."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform

from custom_components.modbus_devices.button import ModBusCommandButtonEntity
from custom_components.modbus_devices.coordinator import (
    DEFAULT_SCAN_INTERVAL,
    MINIMUM_SCAN_INTERVAL,
    get_poll_interval,
)
from custom_components.modbus_devices.equipment.equipment import (
    get_class,
    get_equipment_display_name,
)
from custom_components.modbus_devices.equipment.erman import (
    ERG22005,
    RUNTIME_BASE_ADDRESS,
    RUNTIME_REGISTER_COUNT,
)
from custom_components.modbus_devices.sensor import (
    ModBusNumericSensorEntity,
    ModBusStateSensorEntity,
)
from custom_components.modbus_devices.switch import ModBusDescribedSwitchEntity


class Response:
    """Minimal pymodbus-compatible response."""

    def __init__(
        self,
        registers=None,
        *,
        function_code=4,
        error=False,
        dev_id=None,
        bits=None,
        address=None,
        value=None,
    ):
        self.registers = registers
        self.function_code = function_code
        self.error = error
        self.dev_id = dev_id
        self.bits = bits
        self.address = address
        self.value = value

    def isError(self):
        return self.error


class Client:
    """Capture one exact FC04 runtime request."""

    def __init__(
        self,
        response,
        *,
        output_states=None,
        output_functions=None,
    ):
        self.response = response
        self.calls = []
        self.output_states = output_states or [False, False]
        self.output_functions = output_functions or {1118: 4, 1120: 4}
        self.coil_calls = []
        self.holding_calls = []
        self.write_calls = []
        self.logical_operations = 0

    async def read_input_registers(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    async def read_coils(self, **kwargs):
        self.coil_calls.append(kwargs)
        start = kwargs["address"] - 13
        return Response(
            function_code=1,
            bits=self.output_states[start : start + kwargs["count"]],
            dev_id=kwargs["device_id"],
        )

    async def read_holding_registers(self, **kwargs):
        self.holding_calls.append(kwargs)
        return Response(
            [self.output_functions[kwargs["address"]]],
            function_code=3,
            dev_id=kwargs["device_id"],
        )

    async def write_coil(self, **kwargs):
        self.write_calls.append(kwargs)
        if kwargs["address"] in (13, 14):
            self.output_states[kwargs["address"] - 13] = kwargs["value"]
        return Response(
            function_code=5,
            address=kwargs["address"],
            value=kwargs["value"],
            dev_id=kwargs["device_id"],
        )

    async def async_execute_serialized(self, operation):
        self.logical_operations += 1
        return await operation(self)


RUNTIME_VECTOR = [
    503,
    127,
    223,
    41,
    8,
    0,
    245,
    125,
    37,
    82,
]


def test_registry_and_metadata_are_canonical_and_mark_hardware_status():
    assert get_class("ERMAN", "ERG22005") is ERG22005
    assert get_equipment_display_name("ERMAN", "ERG22005") == "ER-G-220-05"

    device = ERG22005(None, 1)
    assert device.attr_manufactures_name == "ERMAN"
    assert device.attr_model_name == "ER-G-220-05"
    assert device.attr_platforms == [
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.SWITCH,
    ]
    assert device.attr_device_metadata["documented_software_version"] == "01.25"
    assert device.attr_device_metadata["writes"] == (
        "documented FC05 commands exposed; hardware feedback pending"
    )
    assert device.attr_poll_interval == timedelta(seconds=1)
    assert get_poll_interval(device) == timedelta(seconds=1)


def test_poll_interval_defaults_to_five_seconds_and_cannot_exceed_one_hertz():
    assert get_poll_interval(SimpleNamespace()) == DEFAULT_SCAN_INTERVAL
    assert (
        get_poll_interval(
            SimpleNamespace(attr_poll_interval=timedelta(milliseconds=100))
        )
        == MINIMUM_SCAN_INTERVAL
    )

    with pytest.raises(ValueError, match="positive timedelta"):
        get_poll_interval(SimpleNamespace(attr_poll_interval=0.5))


def test_runtime_description_set_matches_documented_engineering_values():
    descriptions = {
        item["sensor_id"]: item for item in ERG22005.get_numeric_sensor_descriptions()
    }

    assert set(descriptions) == {
        "output_frequency",
        "motor_current",
        "input_voltage",
        "drive_temperature",
        "current_pressure",
        "analog_input_1",
        "analog_input_2",
    }
    assert descriptions["output_frequency"]["unit"] == "Hz"
    assert descriptions["motor_current"]["unit"] == "A"
    assert descriptions["input_voltage"]["unit"] == "V"
    assert descriptions["drive_temperature"]["unit"] == "°C"
    assert descriptions["current_pressure"]["unit"] == "atm"
    assert descriptions["current_pressure"]["precision"] == 2


def test_decode_runtime_applies_documented_scales_and_states_losslessly():
    snapshot = ERG22005.decode_runtime(RUNTIME_VECTOR)
    numeric = snapshot["numeric_sensors"]
    states = snapshot["state_sensors"]

    assert numeric["output_frequency"]["value"] == 50.3
    assert numeric["motor_current"]["value"] == 12.7
    assert numeric["input_voltage"]["value"] == 223
    assert numeric["drive_temperature"]["value"] == 41
    assert numeric["current_pressure"]["value"] == 2.45
    assert numeric["analog_input_1"]["value"] == 37
    assert numeric["analog_input_2"]["value"] == 82
    assert numeric["current_pressure"]["register_address"] == 2006

    assert states["drive_state"] == {
        "state": "running_at_set_frequency",
        "primary_code": 8,
        "expanded_codes": [],
        "expanded_states": [],
    }
    assert states["fault_code"]["state"] == "no_fault"
    assert states["software_version"]["state"] == "01.25"
    assert states["software_version"]["primary_code"] == 125


def test_software_version_uses_documented_decimal_mmyy_encoding():
    assert ERG22005.decode_software_version(0x01AA) == "04.26"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "no_fault"),
        (1, "reserved_fault_1"),
        (3, "reserved_fault_3"),
        (4, "err1"),
        (15, "e_u5"),
        (28, "e_cf"),
        (99, "unknown_fault_99"),
    ],
)
def test_fault_decoder_preserves_reserved_and_unknown_codes(code, expected):
    assert ERG22005.decode_fault(code) == expected


def test_unknown_drive_state_and_nonstandard_software_word_are_preserved():
    registers = list(RUNTIME_VECTOR)
    registers[4] = 77
    registers[7] = 0xFFFF

    states = ERG22005.decode_runtime(registers)["state_sensors"]

    assert states["drive_state"]["state"] == "unknown_state_77"
    assert states["drive_state"]["primary_code"] == 77
    assert states["software_version"]["state"] == "raw_0xFFFF"


@pytest.mark.parametrize(
    "registers",
    [
        RUNTIME_VECTOR[:-1],
        RUNTIME_VECTOR + [0],
        [*RUNTIME_VECTOR[:-1], -1],
        [*RUNTIME_VECTOR[:-1], 0x10000],
        [*RUNTIME_VECTOR[:-1], True],
    ],
)
def test_decoder_rejects_malformed_runtime_blocks(registers):
    with pytest.raises(ValueError, match="ten unsigned 16-bit"):
        ERG22005.decode_runtime(registers)


@pytest.mark.asyncio
async def test_snapshot_uses_one_exact_fc04_request_and_device_identity():
    client = Client(Response(RUNTIME_VECTOR, dev_id=7))

    snapshot = await ERG22005(client, 7).async_get_snapshot()

    assert client.calls == [
        {
            "address": RUNTIME_BASE_ADDRESS,
            "count": RUNTIME_REGISTER_COUNT,
            "device_id": 7,
        }
    ]
    assert (
        snapshot["numeric_sensors"]
        == ERG22005.decode_runtime(RUNTIME_VECTOR)["numeric_sensors"]
    )
    assert (
        snapshot["state_sensors"]
        == ERG22005.decode_runtime(RUNTIME_VECTOR)["state_sensors"]
    )
    assert snapshot["switches"] == {
        "output_y1": {"state": False},
        "output_y2": {"state": False},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        Response(RUNTIME_VECTOR[:-1], dev_id=7),
        Response(RUNTIME_VECTOR, function_code=3, dev_id=7),
        Response(RUNTIME_VECTOR, error=True, dev_id=7),
        Response(RUNTIME_VECTOR, dev_id=8),
        None,
    ],
)
async def test_snapshot_rejects_short_wrong_function_error_identity_and_empty(response):
    with pytest.raises(ModbusException):
        await ERG22005(Client(response), 7).async_get_snapshot()


def test_generic_sensor_entities_publish_decoded_values_and_evidence():
    device = ERG22005(None, 1)
    snapshot = device.decode_runtime(RUNTIME_VECTOR)
    coordinator = SimpleNamespace(
        data=snapshot,
        device=device,
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="erg")

    numeric_description = next(
        item
        for item in device.get_numeric_sensor_descriptions()
        if item["sensor_id"] == "current_pressure"
    )
    numeric = ModBusNumericSensorEntity(
        coordinator,
        device,
        entry,
        numeric_description,
    )
    assert numeric.native_value == 2.45
    assert numeric.translation_key == "erman_current_pressure"
    assert numeric.native_unit_of_measurement == "atm"
    assert numeric.extra_state_attributes["raw_register"] == 245
    assert numeric.extra_state_attributes["register_address"] == 2006

    state_description = next(
        item
        for item in device.get_state_sensor_descriptions()
        if item["sensor_id"] == "fault_code"
    )
    state = ModBusStateSensorEntity(
        coordinator,
        device,
        entry,
        state_description,
    )
    assert state.native_value == "no_fault"
    assert state.translation_key == "erman_fault_code"
    assert "e_er" in state.options
    assert state.extra_state_attributes["primary_code"] == 0


@pytest.mark.parametrize(
    ("button_id", "translation_key", "address"),
    [
        ("start", "erman_start", 0),
        ("stop", "erman_stop", 1),
        ("emergency_stop", "erman_emergency_stop", 2),
        ("save_parameters", "erman_save_parameters", 5),
        ("load_parameters", "erman_load_parameters", 7),
        ("reset_fault", "erman_reset_fault", 9),
    ],
)
@pytest.mark.asyncio
async def test_documented_command_buttons_use_only_non_reserved_fc05_addresses(
    button_id,
    translation_key,
    address,
):
    client = Client(Response(RUNTIME_VECTOR))
    device = ERG22005(client, 3)
    description = next(
        item
        for item in device.get_button_descriptions()
        if item["button_id"] == button_id
    )

    assert description["translation_key"] == translation_key
    await device.async_send_command(description["command"])

    assert client.write_calls == [{"address": address, "value": True, "device_id": 3}]


@pytest.mark.asyncio
async def test_unsupported_command_is_rejected_without_io():
    client = Client(Response(RUNTIME_VECTOR))

    with pytest.raises(ValueError, match="Unsupported ER-G-220-05 command"):
        await ERG22005(client, 1).async_send_command(3)

    assert client.write_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        Response(function_code=5, address=1, value=True, dev_id=3),
        Response(function_code=5, address=0, value=False, dev_id=3),
        Response(function_code=1, address=0, value=True, dev_id=3),
        Response(function_code=5, address=0, value=True, dev_id=4),
        Response(function_code=5, address=0, value=True, dev_id=3, error=True),
    ],
)
async def test_command_rejects_invalid_fc05_echo(response):
    client = Client(Response(RUNTIME_VECTOR))

    async def write_coil(**kwargs):
        client.write_calls.append(kwargs)
        return response

    client.write_coil = write_coil

    with pytest.raises(ModbusException):
        await ERG22005(client, 3).async_send_command(0)


@pytest.mark.asyncio
async def test_y1_write_checks_p118_and_confirms_exact_fc01_readback():
    client = Client(Response(RUNTIME_VECTOR))
    device = ERG22005(client, 6)

    confirmed = await device.async_set_switch("output_y1", True)

    assert confirmed is True
    assert client.logical_operations == 1
    assert client.holding_calls == [{"address": 1118, "count": 1, "device_id": 6}]
    assert client.write_calls == [{"address": 13, "value": True, "device_id": 6}]
    assert client.coil_calls == [{"address": 13, "count": 1, "device_id": 6}]


@pytest.mark.asyncio
async def test_y2_write_is_rejected_when_p120_is_not_manual_mode():
    client = Client(
        Response(RUNTIME_VECTOR),
        output_functions={1118: 4, 1120: 3},
    )

    with pytest.raises(ModbusException, match=r"P120 must equal 4, got 3"):
        await ERG22005(client, 6).async_set_switch("output_y2", True)

    assert client.logical_operations == 1
    assert client.write_calls == []
    assert client.coil_calls == []


@pytest.mark.asyncio
async def test_y1_readback_mismatch_remains_failure():
    client = Client(Response(RUNTIME_VECTOR))

    async def write_coil(**kwargs):
        client.write_calls.append(kwargs)
        return Response(
            function_code=5,
            address=kwargs["address"],
            value=kwargs["value"],
            dev_id=kwargs["device_id"],
        )

    client.write_coil = write_coil

    with pytest.raises(ModbusException, match="readback mismatch"):
        await ERG22005(client, 6).async_set_switch("output_y1", True)


@pytest.mark.asyncio
async def test_generic_button_and_switch_entities_use_equipment_contracts():
    client = Client(Response(RUNTIME_VECTOR))
    device = ERG22005(client, 6)
    coordinator = SimpleNamespace(
        data={"switches": {"output_y1": {"state": False}}},
        device=device,
        last_update_success=True,
    )
    patches = []

    def apply(path, value):
        patches.append((path, value))
        coordinator.data[path[0]][path[1]][path[2]] = value

    coordinator.async_apply_confirmed_write = apply
    entry = SimpleNamespace(entry_id="erg")
    button = ModBusCommandButtonEntity(
        coordinator,
        device,
        entry,
        device.get_button_descriptions()[0],
    )
    output = ModBusDescribedSwitchEntity(
        coordinator,
        device,
        entry,
        device.get_switch_descriptions()[0],
    )

    assert button.translation_key == "erman_start"
    assert output.translation_key == "erman_output_y1"

    await button.async_press()
    assert client.write_calls[-1] == {"address": 0, "value": True, "device_id": 6}
    assert output.is_on is False

    await output.async_turn_on()
    assert patches == [(("switches", "output_y1", "state"), True)]
    assert output.is_on is True
