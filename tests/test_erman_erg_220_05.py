"""Document-derived tests for the ERMAN ER-G-220-05 drive."""

from datetime import time, timedelta
import logging
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
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.equipment import (
    get_class,
    get_equipment_display_name,
)
from custom_components.modbus_devices.equipment.erman import (
    ERG22005,
    NUMBER_PARAMETERS,
    RUNTIME_BASE_ADDRESS,
    RUNTIME_REGISTER_COUNT,
    SELECT_PARAMETERS,
    TIME_PARAMETERS,
    WEEKDAY_PARAMETERS,
)
from custom_components.modbus_devices.number import ModBusNumberEntity
from custom_components.modbus_devices.select import ModBusSelectEntity
from custom_components.modbus_devices.sensor import (
    ModBusNumericSensorEntity,
    ModBusStateSensorEntity,
)
from custom_components.modbus_devices.switch import ModBusDescribedSwitchEntity
from custom_components.modbus_devices.time import ModBusTimeEntity


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
        self.settings = {
            **{
                item.address: round(item.minimum / item.scale)
                for item in NUMBER_PARAMETERS
            },
            **{item.address: 0 for item in SELECT_PARAMETERS},
            **(output_functions or {1118: 4, 1120: 4}),
        }
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
            [
                self.settings.get(kwargs["address"] + offset, 0)
                for offset in range(kwargs["count"])
            ],
            function_code=3,
            dev_id=kwargs["device_id"],
        )

    async def write_register(self, **kwargs):
        self.write_calls.append(kwargs)
        self.settings[kwargs["address"]] = kwargs["value"]
        return Response(
            function_code=6,
            address=kwargs["address"],
            value=kwargs["value"],
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
        Platform.NUMBER,
        Platform.SELECT,
        Platform.TIME,
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


def test_configuration_descriptions_cover_safe_protocol_parameters():
    device = ERG22005(None, 1)
    numbers = {item["number_id"]: item for item in device.get_number_descriptions()}
    selects = {item["select_id"]: item for item in device.get_select_descriptions()}

    assert len(numbers) == 25
    assert numbers["p109"]["native_step"] == 0.01
    assert numbers["p109"]["dynamic_max_id"] == "p006"
    assert numbers["p106"]["native_step"] == 0.1
    assert numbers["p133"]["native_max_value"] == 600
    assert len(selects) == 12
    assert selects["p100"]["options"][-1] == "analog_input_frequency"
    assert selects["p118"]["options"][-1] == "time_relay"
    assert "p122" not in numbers
    assert "p123" not in selects

    times = {item["time_id"]: item for item in device.get_time_descriptions()}
    switches = {item["switch_id"]: item for item in device.get_switch_descriptions()}
    assert set(times) == {"p132", "p135"}
    assert times["p132"]["translation_key"] == "erman_p132"
    assert "p134_monday" in switches
    assert "p137_sunday" in switches
    assert switches["p134_monday"]["translation_key"] == "erman_p134_monday"


def test_configuration_coverage_has_only_intentional_non_schedule_gaps():
    implemented = {
        *(item.parameter for item in NUMBER_PARAMETERS),
        *(item.parameter for item in SELECT_PARAMETERS),
        *(item.parameter for item in TIME_PARAMETERS),
        *(item.parameter for item in WEEKDAY_PARAMETERS),
    }
    documented = {
        "p001",
        "p002",
        "p003",
        "p004",
        "p005",
        "p006",
        "p008",
        *(f"p{number}" for number in range(100, 138)),
    }

    assert documented - implemented == {"p122", "p123", "p127", "p128"}


@pytest.mark.asyncio
async def test_scaled_number_write_is_serialized_and_readback_confirmed():
    client = Client(Response(RUNTIME_VECTOR, dev_id=7))
    client.settings[1006] = 600
    device = ERG22005(client, 7)

    confirmed = await device.async_set_number("p109", 1.25)

    assert confirmed == 1.25
    assert client.logical_operations == 1
    assert client.write_calls == [{"address": 1109, "value": 125, "device_id": 7}]
    assert client.holding_calls[0] == {"address": 1006, "count": 1, "device_id": 7}
    assert client.holding_calls[-1] == {"address": 1109, "count": 1, "device_id": 7}


@pytest.mark.asyncio
async def test_dynamic_limit_and_decimal_step_are_enforced_before_write():
    client = Client(Response(RUNTIME_VECTOR, dev_id=1))
    client.settings[1006] = 300
    device = ERG22005(client, 1)

    with pytest.raises(ValueError, match="P109 must be 0..3.0"):
        await device.async_set_number("p109", 3.01)
    with pytest.raises(ValueError, match="P106 must use step 0.1"):
        await device.async_set_number("p106", 12.34)
    assert client.write_calls == []


@pytest.mark.asyncio
async def test_lowering_p102_clamps_p101_first_and_confirms_both_writes(caplog):
    client = Client(Response(RUNTIME_VECTOR, dev_id=1))
    client.settings[1101] = 500
    client.settings[1102] = 500
    device = ERG22005(client, 1)

    with caplog.at_level(
        logging.INFO,
        logger="custom_components.modbus_devices.equipment.erman",
    ):
        confirmed = await device.async_set_number("p102", 45.0)

    assert confirmed == 45.0
    assert client.logical_operations == 1
    assert client.write_calls == [
        {"address": 1101, "value": 450, "device_id": 1},
        {"address": 1102, "value": 450, "device_id": 1},
    ]
    assert client.settings[1101] == 450
    assert client.settings[1102] == 450
    assert "ERMAN dependent clamp" in caplog.text
    assert "parameter=P101 raw_value=450" in caplog.text
    assert "parameter=P102 raw_value=450" in caplog.text


@pytest.mark.asyncio
async def test_p102_does_not_change_p101_when_it_is_already_within_limit():
    client = Client(Response(RUNTIME_VECTOR, dev_id=1))
    client.settings[1101] = 400
    client.settings[1102] = 500

    confirmed = await ERG22005(client, 1).async_set_number("p102", 45.0)

    assert confirmed == 45.0
    assert client.write_calls == [{"address": 1102, "value": 450, "device_id": 1}]
    assert client.settings[1101] == 400


@pytest.mark.asyncio
async def test_failed_p101_clamp_leaves_p102_untouched():
    client = Client(Response(RUNTIME_VECTOR, dev_id=1))
    client.settings[1101] = 500
    client.settings[1102] = 500

    async def reject_p101(**kwargs):
        client.write_calls.append(kwargs)
        return Response(
            function_code=6,
            address=kwargs["address"],
            value=449,
            dev_id=kwargs["device_id"],
        )

    client.write_register = reject_p101

    with pytest.raises(ModbusException, match="Wrong FC06 value echo"):
        await ERG22005(client, 1).async_set_number("p102", 45.0)

    assert client.write_calls == [{"address": 1101, "value": 450, "device_id": 1}]
    assert client.settings[1102] == 500


@pytest.mark.asyncio
async def test_p006_write_never_rewrites_dependent_pressure_parameters():
    client = Client(Response(RUNTIME_VECTOR, dev_id=1))
    dependent_addresses = (1001, 1005, 1109, 1111, 1113, 1115, 1116)
    before = {address: client.settings[address] for address in dependent_addresses}

    confirmed = await ERG22005(client, 1).async_set_number("p006", 10.0)

    assert confirmed == 10.0
    assert client.write_calls == [{"address": 1006, "value": 1000, "device_id": 1}]
    assert {
        address: client.settings[address] for address in dependent_addresses
    } == before


@pytest.mark.asyncio
async def test_select_write_uses_documented_code_and_exact_readback():
    client = Client(Response(RUNTIME_VECTOR, dev_id=4))
    device = ERG22005(client, 4)

    confirmed = await device.async_set_select("p117", "rs485")

    assert confirmed == "rs485"
    assert client.write_calls == [{"address": 1117, "value": 2, "device_id": 4}]


@pytest.mark.asyncio
async def test_schedule_time_write_uses_decimal_hhmm_and_exact_readback():
    client = Client(Response(RUNTIME_VECTOR, dev_id=4))
    device = ERG22005(client, 4)

    confirmed = await device.async_set_time("p132", time(7, 5))

    assert confirmed == time(7, 5)
    assert client.logical_operations == 1
    assert client.write_calls == [{"address": 1132, "value": 705, "device_id": 4}]
    assert client.holding_calls[-1] == {
        "address": 1132,
        "count": 1,
        "device_id": 4,
    }


@pytest.mark.asyncio
async def test_schedule_time_rejects_seconds_and_unknown_parameter_without_io():
    client = Client(Response(RUNTIME_VECTOR, dev_id=4))
    device = ERG22005(client, 4)

    with pytest.raises(ValueError, match="minute precision"):
        await device.async_set_time("p132", time(7, 5, 1))
    with pytest.raises(ValueError, match="Unknown ER-G-220-05 time"):
        await device.async_set_time("p999", time(7, 5))

    assert client.write_calls == []


def test_schedule_time_decoder_rejects_invalid_hhmm_without_losing_snapshot():
    assert ERG22005._decode_hhmm(0) == time(0, 0)
    assert ERG22005._decode_hhmm(2359) == time(23, 59)
    assert ERG22005._decode_hhmm(1260) is None
    assert ERG22005._decode_hhmm(2400) is None


@pytest.mark.asyncio
async def test_weekday_switch_preserves_every_other_mask_bit():
    client = Client(Response(RUNTIME_VECTOR, dev_id=4))
    client.settings[1134] = 0x8000 | (1 << 0) | (1 << 6)
    device = ERG22005(client, 4)

    confirmed = await device.async_set_switch("p134_wednesday", True)

    assert confirmed is True
    assert client.logical_operations == 1
    assert client.write_calls == [
        {
            "address": 1134,
            "value": 0x8000 | (1 << 0) | (1 << 2) | (1 << 6),
            "device_id": 4,
        }
    ]
    assert client.settings[1134] & 0x8000
    assert client.settings[1134] & (1 << 0)
    assert client.settings[1134] & (1 << 2)
    assert client.settings[1134] & (1 << 6)


@pytest.mark.asyncio
async def test_weekday_switch_skips_write_when_bit_already_matches():
    client = Client(Response(RUNTIME_VECTOR, dev_id=4))
    client.settings[1137] = 1 << 6

    confirmed = await ERG22005(client, 4).async_set_switch("p137_sunday", True)

    assert confirmed is True
    assert client.logical_operations == 1
    assert client.write_calls == []


@pytest.mark.asyncio
async def test_settings_are_grouped_and_cached_between_fast_runtime_polls():
    client = Client(Response(RUNTIME_VECTOR, dev_id=5))
    client.settings[1006] = 600
    client.settings[1109] = 125
    client.settings[1132] = 730
    client.settings[1134] = (1 << 0) | (1 << 4)
    client.settings[1135] = 2215
    client.settings[1137] = 1 << 6
    device = ERG22005(client, 5)

    first = await device.async_get_snapshot()
    second = await device.async_get_snapshot()

    assert first["numbers"]["p006"]["value"] == 6.0
    assert first["numbers"]["p109"]["value"] == 1.25
    assert second["numbers"] == first["numbers"]
    assert first["times"]["p132"]["value"] == time(7, 30)
    assert first["times"]["p135"]["value"] == time(22, 15)
    assert first["switches"]["p134_monday"]["state"] is True
    assert first["switches"]["p134_friday"]["state"] is True
    assert first["switches"]["p134_tuesday"]["state"] is False
    assert first["switches"]["p137_sunday"]["state"] is True
    setting_reads = [
        call for call in client.holding_calls if call["address"] in (1001, 1100)
    ]
    assert setting_reads == [
        {"address": 1001, "count": 8, "device_id": 5},
        {"address": 1100, "count": 38, "device_id": 5},
    ]


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
    assert snapshot["switches"]["output_y1"] == {"state": False}
    assert snapshot["switches"]["output_y2"] == {"state": False}
    assert snapshot["switches"]["p134_monday"]["state"] is False
    assert snapshot["switches"]["p137_sunday"]["state"] is False


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
    caplog,
):
    client = Client(Response(RUNTIME_VECTOR))
    device = ERG22005(client, 3)
    description = next(
        item
        for item in device.get_button_descriptions()
        if item["button_id"] == button_id
    )

    assert description["translation_key"] == translation_key
    with caplog.at_level(
        logging.INFO,
        logger="custom_components.modbus_devices.equipment.erman",
    ):
        await device.async_send_command(description["command"])

    assert client.write_calls == [{"address": address, "value": True, "device_id": 3}]
    assert f"address={address}" in caplog.text
    assert "ERMAN FC05 command requested" in caplog.text
    assert "ERMAN FC05 command confirmed" in caplog.text


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


@pytest.mark.asyncio
async def test_generic_number_and_select_entities_publish_confirmed_settings():
    client = Client(Response(RUNTIME_VECTOR))
    client.settings[1006] = 600
    client.settings[1109] = 125
    device = ERG22005(client, 6)
    device.attr_device_identifier = "stable-erman-device"
    device.attr_unique_id_prefix = "stable-erman-device"
    coordinator = SimpleNamespace(
        data={
            "numbers": {
                "p006": {"value": 6.0},
                "p109": {"value": 1.25},
            },
            "selects": {"p117": {"state": "control_panel"}},
        },
        device=device,
        last_update_success=True,
    )
    patches = []

    def apply(path, value):
        patches.append((path, value))
        coordinator.data[path[0]][path[1]][path[2]] = value

    coordinator.async_apply_confirmed_write = apply
    entry = SimpleNamespace(entry_id="erg")
    number = ModBusNumberEntity(
        coordinator,
        device,
        entry,
        next(
            item
            for item in device.get_number_descriptions()
            if item["number_id"] == "p109"
        ),
    )
    select = ModBusSelectEntity(
        coordinator,
        device,
        entry,
        next(
            item
            for item in device.get_select_descriptions()
            if item["select_id"] == "p117"
        ),
    )

    assert number.native_value == 1.25
    assert number.device_info["identifiers"] == {(Config.DOMAIN, "stable-erman-device")}
    assert number.device_info["identifiers"] == select.device_info["identifiers"]
    assert number.native_max_value == 6.0
    assert number.translation_key == "erman_p109"
    assert "_attr_name" not in vars(number)
    assert select.current_option == "control_panel"
    assert select.translation_key == "erman_p117"
    assert "_attr_name" not in vars(select)

    await number.async_set_native_value(1.5)
    await select.async_select_option("rs485")

    assert patches == [
        (("numbers", "p109", "value"), 1.5),
        (("selects", "p117", "state"), "rs485"),
    ]


@pytest.mark.asyncio
async def test_generic_time_entity_publishes_confirmed_schedule_value():
    client = Client(Response(RUNTIME_VECTOR, dev_id=1))
    device = ERG22005(client, 1)
    coordinator = SimpleNamespace(
        data={"times": {"p132": {"value": time(6, 30)}}},
        device=device,
        last_update_success=True,
    )
    patches = []

    def apply(path, value):
        patches.append((path, value))
        coordinator.data[path[0]][path[1]][path[2]] = value

    coordinator.async_apply_confirmed_write = apply
    entry = SimpleNamespace(entry_id="erg")
    description = next(
        item for item in device.get_time_descriptions() if item["time_id"] == "p132"
    )
    entity = ModBusTimeEntity(coordinator, device, entry, description)

    assert entity.native_value == time(6, 30)
    assert entity.translation_key == "erman_p132"
    await entity.async_set_value(time(7, 45))

    assert entity.native_value == time(7, 45)
    assert patches == [(("times", "p132", "value"), time(7, 45))]
