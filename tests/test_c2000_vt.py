"""Tests for C2000-VT model and mapping."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.modbus_devices.equipment.bolid import C2000VT
from custom_components.modbus_devices.gateway import (
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    DPLSSubIdentity,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPRuntimeReader,
    S2000PPZoneRow,
    S2000PPZoneState,
    decode_s2000_pp_q8_8,
    decode_s2000_pp_zone_state_register,
    manual_zone_mapping,
    resolve_zone_row,
)
from custom_components.modbus_devices.rtu_over_udp import append_modbus_rtu_crc
import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntryError
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import UpdateFailed
import custom_components.modbus_devices as integration
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.coordinator import ModbusDeviceCoordinator


def make_mapping(*objects, base=20, kdl=10, variant="vt"):
    return ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=GatewayContext(GatewayType.S2000_PP, "pp", "tcp:x", 1),
            model="C2000VT",
            orion_address=kdl,
            dpls=DPLSSubIdentity(base, 2),
            metadata=DownstreamDeviceMetadata(variant),
        ),
        source=MappingSource.MANUAL,
        objects=objects,
    )


@pytest.mark.parametrize("variant", ["vt", "vt_01"])
def test_variants_and_service_metadata(variant):
    device = C2000VT(None, 1)
    device.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(20, 1, 6, 0, None),
            manual_zone_mapping(21, 2, 6, 0, None),
            variant=variant,
        )
    )
    assert device.attr_device_metadata["variant"].startswith("С2000-ВТ")
    assert device.attr_serial_number is None
    assert device.attr_software_version is None


def test_base_address_validation():
    with pytest.raises(ValueError):
        DPLSSubIdentity(127, 2)


def test_temperature_humidity_mapping_and_entity_metadata():
    device = C2000VT(None, 1)
    device.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(20, 11, 6, 0, None),
            manual_zone_mapping(21, 12, 6, 0, None),
        )
    )
    descriptions = {item["sensor_id"]: item for item in device.get_numeric_sensor_descriptions()}
    assert descriptions["temperature"]["device_class"] is SensorDeviceClass.TEMPERATURE
    assert descriptions["temperature"]["unit"] == UnitOfTemperature.CELSIUS
    assert descriptions["humidity"]["device_class"] is SensorDeviceClass.HUMIDITY
    assert descriptions["humidity"]["unit"] == PERCENTAGE
    assert {item["sensor_id"] for item in device.get_state_sensor_descriptions()} == {
        "temperature_state", "humidity_state"
    }
    assert all(
        item["entity_category"] is EntityCategory.DIAGNOSTIC
        for item in device.get_state_sensor_descriptions()
    )


@pytest.mark.parametrize(
    ("raw", "states"),
    [
        (0x4EC8, (78, 200)),
        (0x4E00, (78,)),
        (0x004E, (78,)),
        (0x0000, ()),
    ],
)
def test_zone_state_register_contains_two_priority_state_bytes(raw, states):
    assert decode_s2000_pp_zone_state_register(raw) == states


@pytest.mark.asyncio
async def test_real_temperature_state_register_is_decoded_as_priority_bytes():
    class Response:
        def __init__(self, registers, function_code):
            self.registers = registers
            self.function_code = function_code

        def isError(self):
            return False

    class Client:
        async def read_holding_registers(self, *, address, count, device_id):
            assert address == 40000
            assert count == 1
            return Response([0x4EC8], 3)

        async def read_input_registers(self, *, address, count, device_id):
            assert address == 4096
            assert count == 16
            return Response([78, 200, *([0] * 14)], 4)

    state = (
        await S2000PPRuntimeReader(Client(), 1).async_read_zone_states(
            (manual_zone_mapping(20, 1, 6, 0, None),)
        )
    )[1]
    device = C2000VT(None, 1)

    assert 0x4EC8 == 20168
    assert state.primary_register == 20168
    assert state.priority_states == (78, 200)
    assert state.primary_state == 78
    assert device._state_sensor_value(state)["state"] == "temperature_normal"


def test_temperature_and_unknown_state_fallback_are_independent():
    device = C2000VT(None, 1)

    assert decode_s2000_pp_q8_8(0x1480) == 20.5
    assert decode_s2000_pp_q8_8(0xFB80) == -4.5
    assert device._state_sensor_value(
        S2000PPZoneState(1, 254, (254,))
    )["state"] == "unknown_254"


def test_nested_identity_distinguishes_devices():
    first = make_mapping(manual_zone_mapping(20, 1, 6, 0, None), base=20, kdl=10)
    second = make_mapping(manual_zone_mapping(30, 2, 6, 0, None), base=30, kdl=10)
    third = make_mapping(manual_zone_mapping(20, 3, 6, 0, None), base=20, kdl=11)
    assert len({first.identity.stable_id, second.identity.stable_id, third.identity.stable_id}) == 3


def test_wrong_zone_type_or_local_number_rejected():
    with pytest.raises(ValueError):
        C2000VT(None, 1).apply_gateway_mapping(
            make_mapping(manual_zone_mapping(20, 1, 1, 0, None))
        )
    with pytest.raises(ValueError):
        C2000VT(None, 1).apply_gateway_mapping(
            make_mapping(manual_zone_mapping(22, 1, 6, 0, None))
        )


@pytest.mark.parametrize("channel", ["temperature", "humidity"])
def test_partial_legacy_mapping_reproduces_old_one_channel_failure(channel):
    item = (
        manual_zone_mapping(20, 11, 6, 0, None)
        if channel == "temperature"
        else manual_zone_mapping(21, 12, 6, 0, None)
    )

    with pytest.raises(ValueError, match="both temperature and humidity"):
        C2000VT(None, 1).apply_gateway_mapping(make_mapping(item))


def configuration(*rows):
    return S2000PPConfiguration(
        zones=rows,
        relays=(),
        partitions=(),
        unparsed_registers=(),
    )


def test_partial_legacy_mapping_is_repaired_from_unambiguous_live_table():
    partial = make_mapping(manual_zone_mapping(20, 41, 6, 3, None))
    live = configuration(
        S2000PPZoneRow(41, 10, 20, 3, 6),
        S2000PPZoneRow(42, 10, 21, 3, 6),
    )

    repaired = C2000VT.reconcile_gateway_mapping(partial, live)

    assert [item.gateway_object_number for item in repaired.objects] == [41, 42]
    assert repaired.identity == partial.identity
    assert repaired.source is partial.source
    device = C2000VT(None, 1)
    device.apply_gateway_mapping(repaired)
    assert set(device._numeric_mappings) == {"temperature", "humidity"}


@pytest.mark.asyncio
async def test_overlapping_legacy_entries_fail_explicitly_instead_of_duplicating(
    monkeypatch,
):
    first = make_mapping(manual_zone_mapping(20, 41, 6, 3, None))
    overlapping = make_mapping(
        manual_zone_mapping(21, 42, 6, 3, None), base=21
    )
    current_entry = SimpleNamespace(entry_id="temperature", data={}, options={})
    other_entry = SimpleNamespace(
        entry_id="humidity",
        data={},
        options={Config.CONF_GATEWAY_MAPPING: overlapping.to_dict()},
    )
    hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(
            async_entries=lambda _domain: [current_entry, other_entry],
            async_update_entry=Mock(),
        ),
    )

    class Reader:
        def __init__(self, *_args):
            pass

        async def async_read(self):
            return configuration(
                S2000PPZoneRow(41, 10, 20, 3, 6),
                S2000PPZoneRow(42, 10, 21, 3, 6),
            )

    monkeypatch.setattr(integration, "S2000PPConfigurationReader", Reader)

    with pytest.raises(ConfigEntryError, match="duplicate entries"):
        await integration._async_reconcile_gateway_mapping(
            hass, current_entry, {}, C2000VT, object(), first
        )
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize(
    "rows",
    [
        (S2000PPZoneRow(41, 10, 20, 3, 6),),
        (
            S2000PPZoneRow(41, 10, 20, 3, 6),
            S2000PPZoneRow(42, 10, 21, 3, 6),
            S2000PPZoneRow(43, 10, 21, 3, 6),
        ),
        (
            S2000PPZoneRow(41, 10, 20, 3, 6),
            S2000PPZoneRow(42, 10, 22, 3, 6),
        ),
    ],
)
def test_missing_ambiguous_or_non_adjacent_footprint_is_rejected(rows):
    partial = make_mapping(manual_zone_mapping(20, 41, 6, 3, None))

    with pytest.raises(ValueError, match="unambiguous adjacent"):
        C2000VT.reconcile_gateway_mapping(partial, configuration(*rows))


def test_manual_and_automatic_objects_are_equivalent():
    manual = manual_zone_mapping(20, 41, 6, 0, None)
    automatic = resolve_zone_row(S2000PPZoneRow(41, 10, 20, 0, 6), None)
    assert manual == automatic


@pytest.mark.asyncio
async def test_pending_preserves_previous_confirmed_value():
    class Response:
        def __init__(self, registers=None, error=False, code=None, address=None,
                     value=None, function_code=None):
            self.registers = registers
            self._error = error
            self.exception_code = code
            self.address = address
            self.value = value
            self.function_code = function_code

        def isError(self):
            return self._error

    class Client:
        async def write_register(self, **kwargs):
            return Response(
                address=kwargs["address"],
                value=kwargs["value"],
                function_code=6,
            )

        async def read_holding_registers(self, *, address, count, device_id):
            if address == 46328:
                return Response(error=True, code=15)
            return Response(registers=[0] * count, function_code=3)

        async def read_input_registers(self, *, address, count, device_id):
            return Response(registers=[0] * count, function_code=4)

    device = C2000VT(Client(), 1)
    device.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(20, 1, 6, 0, None),
            manual_zone_mapping(21, 2, 6, 0, None),
        )
    )
    device._numeric_values["temperature"] = {
        "value": 23.5,
        "raw_register": 6016,
        "parameter_kind": "temperature",
    }
    snapshot = await device.async_get_snapshot()
    assert snapshot["numeric_sensors"]["temperature"]["value"] == 23.5


class RoundRobinResponse:
    def __init__(self, *, registers=None, exception_code=None, address=None, value=None,
                 function_code=None):
        self.registers = registers
        self.exception_code = exception_code
        self.address = address
        self.value = value
        self.function_code = function_code

    def isError(self):
        return self.exception_code is not None


class RoundRobinClient:
    def __init__(
        self,
        results,
        state_registers=(0x4E00, 0x4800),
        *,
        selector_response="valid",
    ):
        self.results = iter(results)
        self.state_registers = state_registers
        self.selector_response = selector_response
        self.calls = []

    async def write_register(self, *, address, value, device_id):
        self.calls.append(("select", address, value))
        if self.selector_response == "invalid":
            return RoundRobinResponse(
                address=address,
                value=value + 1,
                function_code=6,
            )
        if self.selector_response == "exception":
            return RoundRobinResponse(exception_code=4, function_code=0x86)
        return RoundRobinResponse(address=address, value=value, function_code=6)

    async def read_holding_registers(self, *, address, count, device_id):
        self.calls.append(("holding", address, count))
        if address == 46328:
            result = next(self.results)
            if result == "pending":
                return RoundRobinResponse(exception_code=15)
            if result in {"error", "error3", "error4", "error99"}:
                code = {"error4": 4, "error99": 99}.get(result, 3)
                return RoundRobinResponse(exception_code=code, function_code=0x83)
            if result == "transport":
                raise OSError("numeric transport failed")
            if result == "wrong_function":
                return RoundRobinResponse(registers=[0x1480], function_code=4)
            if result == "malformed":
                return RoundRobinResponse(registers=[], function_code=3)
            return RoundRobinResponse(registers=[result], function_code=3)
        return RoundRobinResponse(
            registers=list(self.state_registers[:count]), function_code=3
        )

    async def read_input_registers(self, *, address, count, device_id):
        self.calls.append(("input", address, count))
        blocks = ([78, *([0] * 15)], [72, *([0] * 15)])
        return RoundRobinResponse(
            registers=[value for block in blocks for value in block][:count],
            function_code=4,
        )


def round_robin_device(client):
    device = C2000VT(client, 1)
    device.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(20, 1, 6, 0, None),
            manual_zone_mapping(21, 2, 6, 0, None),
        )
    )
    return device


@pytest.mark.asyncio
async def test_numeric_round_robin_reads_one_channel_and_caches_the_other():
    client = RoundRobinClient([0x1480, 0x3780, 0x1580])
    device = round_robin_device(client)

    first = await device.async_get_snapshot()
    second = await device.async_get_snapshot()
    third = await device.async_get_snapshot()

    assert first["numeric_sensors"] == {
        "temperature": {
            "value": 20.5,
            "raw_register": 0x1480,
            "parameter_kind": "temperature",
        }
    }
    assert second["numeric_sensors"]["temperature"]["value"] == 20.5
    assert second["numeric_sensors"]["humidity"]["value"] == 55.5
    assert third["numeric_sensors"]["temperature"]["value"] == 21.5
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 1),
        ("select", 46179, 2),
        ("select", 46179, 1),
    ]
    assert all(len(snapshot["state_sensors"]) == 2 for snapshot in (first, second, third))
    assert first["state_sensors"]["temperature_state"]["state"] == "temperature_normal"
    assert first["state_sensors"]["humidity_state"]["state"] == "level_normal"


@pytest.mark.asyncio
async def test_pending_repeats_result_without_selector_or_cursor_advance():
    client = RoundRobinClient(["pending", 0x1480, 0x3700])
    device = round_robin_device(client)

    first = await device.async_get_snapshot()
    second = await device.async_get_snapshot()
    third = await device.async_get_snapshot()

    assert first["numeric_sensors"] == {}
    assert second["numeric_sensors"]["temperature"]["value"] == 20.5
    assert third["numeric_sensors"]["humidity"]["value"] == 55.0
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 1),
        ("select", 46179, 2),
    ]
    assert len([
        call for call in client.calls
        if call == ("holding", 46328, 1)
    ]) == 3


@pytest.mark.asyncio
async def test_production_like_reconciled_rows_publish_initial_values(caplog):
    """Rows repaired from the live table drive selectors and populate both caches."""
    persisted = make_mapping(
        manual_zone_mapping(51, 5, 6, 14, None),
        base=51,
        kdl=3,
    )
    live = configuration(
        S2000PPZoneRow(63, 3, 51, 14, 6),
        S2000PPZoneRow(64, 3, 52, 14, 6),
    )
    reconciled = C2000VT.reconcile_gateway_mapping(persisted, live)
    client = RoundRobinClient(["pending", "pending", 0x13F0, 0x3960])
    device = C2000VT(client, 2)
    device.apply_gateway_mapping(reconciled)

    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.modbus_devices.equipment.bolid",
    ):
        snapshots = [await device.async_get_snapshot() for _ in range(4)]

    assert [item.gateway_object_number for item in reconciled.objects] == [63, 64]
    assert snapshots[0]["numeric_sensors"] == {}
    assert snapshots[1]["numeric_sensors"] == {}
    assert snapshots[2]["numeric_sensors"]["temperature"]["value"] == 19.9375
    assert snapshots[3]["numeric_sensors"] == {
        "temperature": {
            "value": 19.9375,
            "raw_register": 0x13F0,
            "parameter_kind": "temperature",
        },
        "humidity": {
            "value": 57.375,
            "raw_register": 0x3960,
            "parameter_kind": "relative_humidity",
        },
    }
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 63),
        ("select", 46179, 64),
    ]
    assert all(len(snapshot["state_sensors"]) == 2 for snapshot in snapshots)
    assert "channel=temperature PP-row=63 status=pending" in caplog.text
    assert "channel=temperature PP-row=63 status=ready" in caplog.text
    assert "channel=humidity PP-row=64 status=ready" in caplog.text


@pytest.mark.asyncio
async def test_shared_selector_pending_owner_completes_before_other_vt_starts():
    client = RoundRobinClient(["pending", 0x13F0, 0x1440])
    first = C2000VT(client, 2)
    first.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(51, 63, 6, 14, None),
            manual_zone_mapping(52, 64, 6, 14, None),
            base=51,
            kdl=3,
        )
    )
    second = C2000VT(client, 2)
    second.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(53, 65, 6, 14, None),
            manual_zone_mapping(54, 66, 6, 14, None),
            base=53,
            kdl=3,
        )
    )

    assert (await first.async_get_snapshot())["numeric_sensors"] == {}
    assert (await second.async_get_snapshot())["numeric_sensors"] == {}
    assert (await first.async_get_snapshot())["numeric_sensors"]["temperature"][
        "value"
    ] == 19.9375
    assert (await second.async_get_snapshot())["numeric_sensors"]["temperature"][
        "value"
    ] == 20.25
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 63),
        ("select", 46179, 65),
    ]


def test_round_robin_polling_budget_is_four_requests_per_ready_refresh():
    client = RoundRobinClient([0x1480])
    asyncio.run(round_robin_device(client).async_get_snapshot())

    assert len(client.calls) == 4
    assert client.calls[0:2] == [
        ("holding", 40000, 2),
        ("input", 4096, 32),
    ]


@pytest.mark.parametrize(
    ("rows", "temperature_raw", "temperature", "humidity_raw", "humidity"),
    [
        ((5, 6), 0x13F0, 19.9375, 0x3960, 57.375),
        ((7, 8), 0x1440, 20.25, 0x3CC0, 60.75),
    ],
)
def test_local_hardware_numeric_fixtures(
    rows, temperature_raw, temperature, humidity_raw, humidity
):
    assert rows[1] == rows[0] + 1
    assert decode_s2000_pp_q8_8(temperature_raw) == temperature
    assert decode_s2000_pp_q8_8(humidity_raw) == humidity


@pytest.mark.parametrize(
    ("primary_register", "expected"),
    [
        (0x4EC8, (78, 200)),
        (0x48C8, (72, 200)),
        (0x4E2F, (78, 47)),
        (0x482F, (72, 47)),
    ],
)
def test_local_hardware_primary_state_fixtures(primary_register, expected):
    assert decode_s2000_pp_zone_state_register(primary_register) == expected


@pytest.mark.parametrize(
    ("body", "frame"),
    [
        ("02 06 B4 63 00 05", "02 06 B4 63 00 05 9E 14"),
        ("02 03 B4 F8 00 01", "02 03 B4 F8 00 01 22 38"),
        ("02 03 02 13 F0", "02 03 02 13 F0 F1 30"),
        ("02 03 02 39 60", "02 03 02 39 60 EE 3C"),
        ("02 03 02 14 40", "02 03 02 14 40 F2 B4"),
        ("02 03 02 3C C0", "02 03 02 3C C0 ED 14"),
        ("02 03 02 3C 40", "02 03 02 3C 40 EC B4"),
        ("02 83 0F", "02 83 0F F1 34"),
    ],
)
def test_local_hardware_rtu_frames_have_valid_crc(body, frame):
    assert append_modbus_rtu_crc(bytes.fromhex(body)) == bytes.fromhex(frame)


@pytest.mark.asyncio
async def test_zero_is_real_numeric_value():
    zero_client = RoundRobinClient([0x1480, 0x0000])
    device = round_robin_device(zero_client)
    await device.async_get_snapshot()
    snapshot = await device.async_get_snapshot()
    assert snapshot["numeric_sensors"]["humidity"]["value"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["error3", "error4", "error99"])
async def test_optional_numeric_protocol_error_preserves_states_cache_and_recovers(
    error,
    caplog,
):
    client = RoundRobinClient([0x1480, error, 0x3780])
    device = round_robin_device(client)

    first = await device.async_get_snapshot()
    with caplog.at_level(
        logging.WARNING,
        logger="custom_components.modbus_devices.equipment.bolid",
    ):
        failed = await device.async_get_snapshot()
    recovered = await device.async_get_snapshot()

    assert first["numeric_sensors"]["temperature"]["value"] == 20.5
    assert failed["numeric_sensors"] == first["numeric_sensors"]
    assert len(failed["state_sensors"]) == 2
    assert failed["state_sensors"]["temperature_state"]["state"] == (
        "temperature_normal"
    )
    assert recovered["numeric_sensors"]["humidity"]["value"] == 55.5
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 1),
        ("select", 46179, 2),
        ("select", 46179, 2),
    ]
    expected_code = "99" if error == "error99" else "4" if error == "error4" else "3"
    assert f"exception={expected_code}" in caplog.text
    assert "class=C2000VT" in caplog.text
    assert "orion=10 dpls=20 channel=humidity pp_row=2" in caplog.text
    assert "selector_register=46179 selector_value=2" in caplog.text
    assert "result_register=46328 result_count=1" in caplog.text
    assert "owner=('numeric', 2) generation=" in caplog.text
    assert "response_function=131" in caplog.text


@pytest.mark.asyncio
async def test_first_numeric_protocol_error_keeps_unknown_and_coordinator_successful():
    client = RoundRobinClient(["error3", 0x1480])
    device = round_robin_device(client)
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.device = device
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}

    failed = await coordinator._async_update_data()
    recovered = await coordinator._async_update_data()

    assert failed["numeric_sensors"] == {}
    assert len(failed["state_sensors"]) == 2
    assert recovered["numeric_sensors"]["temperature"]["value"] == 20.5
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 1),
        ("select", 46179, 1),
    ]


@pytest.mark.asyncio
async def test_untyped_numeric_transport_failure_still_fails_coordinator():
    device = round_robin_device(RoundRobinClient(["transport"]))
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.device = device
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}

    with pytest.raises(UpdateFailed, match="numeric transport failed"):
        await coordinator._async_update_data()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client", "message"),
    [
        (RoundRobinClient(["wrong_function"]), "Wrong Modbus function response"),
        (RoundRobinClient(["malformed"]), "Short Modbus response"),
        (
            RoundRobinClient([0x1480], selector_response="invalid"),
            "invalid FC06 selector echo",
        ),
        (
            RoundRobinClient([0x1480], selector_response="exception"),
            "select numeric zone",
        ),
    ],
)
async def test_non_result_exception_protocol_errors_remain_coordinator_fatal(
    client,
    message,
):
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.device = round_robin_device(client)
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}

    with pytest.raises(UpdateFailed, match=message):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_protocol_error_releases_shared_owner_for_other_vt():
    client = RoundRobinClient(["error4", 0x1440])
    first = round_robin_device(client)
    second = C2000VT(client, 1)
    second.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(30, 3, 6, 0, None),
            manual_zone_mapping(31, 4, 6, 0, None),
            base=30,
        )
    )

    assert (await first.async_get_snapshot())["numeric_sensors"] == {}
    second_snapshot = await second.async_get_snapshot()

    assert second_snapshot["numeric_sensors"]["temperature"]["value"] == 20.25
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 1),
        ("select", 46179, 3),
    ]
