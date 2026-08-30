"""Regression tests for the hardware-validated radio С2000Р-ВТИ."""

from types import SimpleNamespace

import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.coordinator import ModbusDeviceCoordinator
from custom_components.modbus_devices.device_info import device_info_for_entry
from custom_components.modbus_devices.equipment.bolid import (
    BolidDPLSThermohygrometerBase,
    C2000RVTI,
    C2000VT,
    C2000VTI,
)
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
    dpls_ranges_overlap,
)
from custom_components.modbus_devices.s2000_pp import (
    NumericParameterKind,
    S2000PPConfiguration,
    S2000PPNumericValueReader,
    S2000PPZoneRow,
    manual_zone_mapping,
)


class Response:
    """Minimal pymodbus-compatible response."""

    def __init__(
        self,
        *,
        registers=None,
        exception_code=None,
        address=None,
        value=None,
        function_code=None,
    ):
        self.registers = registers
        self.exception_code = exception_code
        self.address = address
        self.value = value
        self.function_code = function_code

    def isError(self):
        return self.exception_code is not None


class HardwareClient:
    """Serve captured state rows and controlled numeric results."""

    def __init__(
        self, results, *, include_251=True, expanded_rows=None, first_row=19
    ):
        self.results = iter(results)
        self.include_251 = include_251
        self.expanded_rows = expanded_rows
        self.first_row = first_row
        self.calls = []

    async def write_register(self, *, address, value, device_id):
        self.calls.append(("select", address, value))
        return Response(address=address, value=value, function_code=6)

    async def read_holding_registers(self, *, address, count, device_id):
        self.calls.append(("holding", address, count))
        if address == 46328:
            result = next(self.results)
            if result == "pending":
                return Response(exception_code=15, function_code=0x83)
            if result in {"error3", "error4"}:
                return Response(
                    exception_code=3 if result == "error3" else 4,
                    function_code=0x83,
                )
            if isinstance(result, BaseException):
                raise result
            return Response(registers=[result], function_code=3)
        assert address == 39999 + self.first_row
        assert count == 2
        return Response(registers=[0x4EC8, 0x48C8], function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        self.calls.append(("input", address, count))
        assert address == 4096 + ((self.first_row - 1) * 16)
        assert count == 32
        if self.expanded_rows is None:
            common = [200, 47, 188]
            tail = [251, 111] if self.include_251 else [111]
            temperature = [78, *common, *tail]
            humidity = [72, *common, *tail]
        else:
            temperature, humidity = self.expanded_rows
        blocks = (
            [*temperature, *([0] * (16 - len(temperature)))],
            [*humidity, *([0] * (16 - len(humidity)))],
        )
        return Response(
            registers=[value for block in blocks for value in block],
            function_code=4,
        )


def gateway():
    return GatewayContext(GatewayType.S2000_PP, "pp", "serial:COM3", 2)


def identity(*, base=4, orion=8):
    return DownstreamDeviceIdentity(
        gateway(),
        "C2000RVTI",
        orion,
        DPLSSubIdentity(base, 2),
        DownstreamDeviceMetadata("rvti"),
    )


def mapping(*, base=4, first_row=19, orion=8, partitions=(0, 0)):
    return ResolvedDeviceMapping(
        identity(base=base, orion=orion),
        MappingSource.AUTOMATIC,
        (
            manual_zone_mapping(base, first_row, 6, partitions[0], None),
            manual_zone_mapping(base + 1, first_row + 1, 6, partitions[1], None),
        ),
    )


def configuration(*rows):
    return S2000PPConfiguration(
        zones=rows,
        relays=(),
        partitions=(),
        unparsed_registers=(),
    )


def test_radio_vti_is_a_separate_product_using_only_shared_protocol_mechanics():
    assert C2000RVTI is not C2000VTI
    assert C2000RVTI.__base__ is BolidDPLSThermohygrometerBase
    assert not issubclass(C2000RVTI, C2000VT)
    assert C2000RVTI.__name__ == "C2000RVTI"
    assert C2000RVTI.equipment_model == "С2000Р-ВТИ"
    assert C2000RVTI.variant_dpls_address_counts == {"rvti": 2}


@pytest.mark.parametrize(
    ("base", "first_row", "temperature_codes", "humidity_codes"),
    [
        (4, 19, (78, 200, 47, 188, 251, 111), (72, 200, 47, 188, 251, 111)),
        (6, 21, (78, 200, 47, 188, 251, 111), (72, 200, 47, 188, 251, 111)),
        (8, 23, (78, 200, 47, 188, 111), (72, 200, 47, 188, 111)),
        (10, 25, (78, 200, 47, 188, 111), (72, 200, 47, 188, 111)),
        (12, 27, (78, 200, 47, 188, 111), (72, 200, 47, 188, 111)),
    ],
)
@pytest.mark.asyncio
async def test_five_hardware_footprints_preserve_exact_expanded_captures(
    base, first_row, temperature_codes, humidity_codes
):
    client = HardwareClient(
        [0x1A00],
        expanded_rows=(temperature_codes, humidity_codes),
        first_row=first_row,
    )
    device = C2000RVTI(client, 2)
    device.apply_gateway_mapping(mapping(base=base, first_row=first_row))
    snapshot = await device.async_get_snapshot()

    assert device._numeric_mappings["temperature"].local_object_number == base
    assert device._numeric_mappings["humidity"].local_object_number == base + 1
    assert [
        item.gateway_object_number for item in device.attr_gateway_mapping.objects
    ] == [first_row, first_row + 1]
    temperature_state = snapshot["state_sensors"]["temperature_state"]
    humidity_state = snapshot["state_sensors"]["humidity_state"]
    assert tuple(code for code in temperature_state["expanded_codes"] if code) == (
        temperature_codes
    )
    assert tuple(code for code in humidity_state["expanded_codes"] if code) == (
        humidity_codes
    )


def test_entity_matrix_metadata_and_one_physical_battery():
    device = C2000RVTI(None, 2)
    device.apply_gateway_mapping(mapping())
    numeric = {item["sensor_id"]: item for item in device.get_numeric_sensor_descriptions()}
    states = {item["sensor_id"]: item for item in device.get_state_sensor_descriptions()}

    assert list(numeric) == ["temperature", "humidity"]
    assert list(states) == [
        "temperature_state",
        "humidity_state",
        "main_battery_state",
    ]
    assert numeric["temperature"]["device_class"] is SensorDeviceClass.TEMPERATURE
    assert numeric["temperature"]["unit"] == UnitOfTemperature.CELSIUS
    assert numeric["temperature"]["state_class"] is SensorStateClass.MEASUREMENT
    assert numeric["humidity"]["device_class"] is SensorDeviceClass.HUMIDITY
    assert numeric["humidity"]["unit"] == PERCENTAGE
    assert numeric["humidity"]["precision"] == 1
    assert states["main_battery_state"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert "reserve_battery_state" not in states


def test_identity_is_product_specific_and_independent_of_rows_and_partitions():
    first = C2000RVTI(None, 2)
    second = C2000RVTI(None, 2)
    first.apply_gateway_mapping(mapping(first_row=19, partitions=(0, 0)))
    second.apply_gateway_mapping(mapping(first_row=63, partitions=(11, 12)))

    assert first.attr_device_identifier == second.attr_device_identifier
    assert first.attr_device_identifier.endswith(":model:C2000RVTI")
    assert ":19" not in first.attr_device_identifier
    assert first.attr_unique_id_prefix == first.attr_device_identifier


def test_device_info_uses_radio_model_and_gateway_parent_without_versions():
    device = C2000RVTI(None, 2)
    device.apply_gateway_mapping(mapping())
    entry = SimpleNamespace(
        entry_id="rvti-entry",
        options={Config.CONF_GATEWAY_ENTRY_ID: "pp-entry"},
        data={},
    )

    info = device_info_for_entry(device, entry)

    assert info["model"] == "С2000Р-ВТИ"
    assert info["manufacturer"] == "Bolid"
    assert info["via_device"] == (Config.DOMAIN, "pp-entry")
    assert info.get("sw_version") is None
    assert info.get("hw_version") is None
    assert info.get("serial_number") is None


def test_reconciliation_repairs_stale_nonadjacent_pp_rows_and_ignores_partition():
    stale = mapping(first_row=63, partitions=(99, 99))
    live = configuration(
        S2000PPZoneRow(25, 8, 10, 41, 6),
        S2000PPZoneRow(7, 8, 4, 17, 6),
        S2000PPZoneRow(3, 9, 4, 0, 6),
        S2000PPZoneRow(42, 8, 5, 23, 6),
    )

    repaired = C2000RVTI.reconcile_gateway_mapping(stale, live)

    assert [item.gateway_object_number for item in repaired.objects] == [7, 42]
    assert repaired.identity == stale.identity
    assert repaired.source is stale.source
    assert [item.zone_details.partition_number for item in repaired.objects] == [17, 23]


@pytest.mark.parametrize(
    "rows",
    [
        (S2000PPZoneRow(19, 8, 4, 0, 6),),
        (
            S2000PPZoneRow(19, 8, 4, 0, 6),
            S2000PPZoneRow(20, 8, 5, 0, 1),
        ),
        (
            S2000PPZoneRow(19, 8, 4, 0, 6),
            S2000PPZoneRow(20, 8, 5, 0, 6),
            S2000PPZoneRow(28, 8, 5, 1, 6),
        ),
    ],
)
def test_reconciliation_rejects_missing_wrong_type_and_ambiguous_footprints(rows):
    with pytest.raises(ValueError, match="unambiguous"):
        C2000RVTI.reconcile_gateway_mapping(mapping(), configuration(*rows))


def test_reconciliation_rejects_complete_footprint_on_wrong_orion():
    wrong_orion = configuration(
        S2000PPZoneRow(19, 9, 4, 0, 6),
        S2000PPZoneRow(20, 9, 5, 0, 6),
    )

    with pytest.raises(ValueError, match="unambiguous"):
        C2000RVTI.reconcile_gateway_mapping(mapping(orion=8), wrong_orion)


def test_overlap_protection_uses_the_complete_two_address_range():
    radio = identity(base=4)
    overlapping = DownstreamDeviceIdentity(
        gateway(),
        "C2000VT",
        8,
        DPLSSubIdentity(5, 2),
        DownstreamDeviceMetadata("vt"),
    )
    separate = DownstreamDeviceIdentity(
        gateway(),
        "C2000VT",
        8,
        DPLSSubIdentity(6, 2),
        DownstreamDeviceMetadata("vt"),
    )

    assert dpls_ranges_overlap(radio, overlapping)
    assert not dpls_ranges_overlap(radio, separate)


@pytest.mark.asyncio
async def test_hardware_quiescent_states_numeric_q8_8_and_battery_aggregation():
    client = HardwareClient([0x1A00, 0x2000])
    device = C2000RVTI(client, 2)
    device.apply_gateway_mapping(mapping())

    temperature = await device.async_get_snapshot()
    humidity = await device.async_get_snapshot()

    assert temperature["state_sensors"]["temperature_state"]["state"] == "temperature_normal"
    assert temperature["state_sensors"]["humidity_state"]["state"] == "level_normal"
    assert temperature["state_sensors"]["main_battery_state"]["state"] == "battery_restored"
    assert temperature["state_sensors"]["main_battery_state"]["primary_code"] == 200
    assert humidity["numeric_sensors"]["temperature"]["value"] == 26.0
    assert humidity["numeric_sensors"]["humidity"]["value"] == 32.0
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 19),
        ("select", 46179, 20),
    ]


@pytest.mark.asyncio
async def test_numeric_diagnostics_use_the_runtime_radio_product_context(caplog):
    caplog.set_level(
        "DEBUG", logger="custom_components.modbus_devices.equipment.bolid"
    )
    device = C2000RVTI(HardwareClient([0x1A00]), 2)
    device.apply_gateway_mapping(mapping())

    await device.async_get_snapshot()

    messages = [record.getMessage() for record in caplog.records]
    numeric_messages = [message for message in messages if " numeric " in message]
    assert numeric_messages
    assert all(message.startswith("C2000RVTI numeric ") for message in numeric_messages)
    assert not any("C2000-VT numeric" in message for message in numeric_messages)


@pytest.mark.asyncio
async def test_unknown_zone_state_is_lossless_and_missing_battery_is_unknown():
    client = HardwareClient([0x1A00])

    async def unknown_expanded(*, address, count, device_id):
        blocks = ([254, 47, *([0] * 14)], [72, 188, *([0] * 14)])
        return Response(
            registers=[value for block in blocks for value in block],
            function_code=4,
        )

    client.read_input_registers = unknown_expanded
    device = C2000RVTI(client, 2)
    device.apply_gateway_mapping(mapping())

    snapshot = await device.async_get_snapshot()

    assert snapshot["state_sensors"]["temperature_state"]["expanded_states"][0] == "unknown_254"
    assert snapshot["state_sensors"]["main_battery_state"]["state"] is None


@pytest.mark.parametrize(
    ("temperature_codes", "humidity_codes", "expected"),
    [
        ((78, 200, 47, 188, 111), (72, 47, 188, 111), "battery_restored"),
        ((78, 47, 188, 111), (72, 200, 47, 188, 111), "battery_restored"),
        ((78, 200, 47, 188, 111), (72, 200, 47, 188, 111), "battery_restored"),
        ((78,), (72,), None),
        ((78, 47, 188, 251, 111), (72, 47, 188, 251, 111), None),
        ((78, 200), (72, 202), None),
        ((78, 200), (72, 211), None),
        ((78, 202), (72, 211), None),
        ((78, 202), (72, 202), "battery_fault"),
        ((78, 211), (72, 211), "battery_low"),
    ],
)
@pytest.mark.asyncio
async def test_battery_aggregation_requires_one_distinct_code(
    temperature_codes, humidity_codes, expected
):
    client = HardwareClient(
        [0x1A00], expanded_rows=(temperature_codes, humidity_codes)
    )
    device = C2000RVTI(client, 2)
    device.apply_gateway_mapping(mapping())

    snapshot = await device.async_get_snapshot()
    battery = snapshot["state_sensors"]["main_battery_state"]

    assert battery["state"] == expected
    assert tuple(code for code in battery["expanded_codes"] if code) == (
        *temperature_codes,
        *humidity_codes,
    )


@pytest.mark.asyncio
async def test_native_serial_exception4_sequence_releases_session_and_recovers():
    client = HardwareClient(["pending", "pending", "error4", 0x1A00])
    device = C2000RVTI(client, 2)
    device.apply_gateway_mapping(mapping())

    first = await device.async_get_snapshot()
    second = await device.async_get_snapshot()
    terminal = await device.async_get_snapshot()
    recovered = await device.async_get_snapshot()

    assert first["numeric_sensors"] == {}
    assert second["numeric_sensors"] == {}
    assert terminal["numeric_sensors"] == {}
    assert set(terminal["state_sensors"]) == {
        "temperature_state",
        "humidity_state",
        "main_battery_state",
    }
    assert recovered["numeric_sensors"]["temperature"]["value"] == 26.0
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 19),
        ("select", 46179, 19),
    ]


@pytest.mark.asyncio
async def test_production_row77_pending_then_exception3_recovers_fresh_selector():
    """Reproduce the production-observed 15 -> 3 lifecycle without blaming transport."""
    client = HardwareClient(
        ["pending", "error3", "pending", 0x1860], first_row=77
    )
    device = C2000RVTI(client, 2)
    row77_mapping = mapping(base=10, first_row=77)
    device.apply_gateway_mapping(row77_mapping)
    device._numeric_values["temperature"] = {
        "value": 24.0,
        "raw_register": 0x1800,
        "parameter_kind": NumericParameterKind.TEMPERATURE.value,
    }
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.device = device
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}
    session = S2000PPNumericValueReader(
        client,
        2,
        row77_mapping.identity.gateway.stable_id,
    )._session

    pending = await coordinator._async_update_data()
    assert pending["numeric_sensors"]["temperature"]["value"] == 24.0
    assert session.pending_request == ("numeric", 77)
    assert session.generation == 1
    assert device._numeric_cursor == 0

    terminal = await coordinator._async_update_data()
    assert terminal["numeric_sensors"]["temperature"]["value"] == 24.0
    assert terminal["state_sensors"]["temperature_state"]["state"] == (
        "temperature_normal"
    )
    assert terminal["state_sensors"]["humidity_state"]["state"] == "level_normal"
    assert session.pending_request is None
    assert session.generation == 1
    assert device._numeric_cursor == 0

    retry_pending = await coordinator._async_update_data()
    assert retry_pending["numeric_sensors"]["temperature"]["value"] == 24.0
    assert session.pending_request == ("numeric", 77)
    assert session.generation == 2

    recovered = await coordinator._async_update_data()
    assert recovered["numeric_sensors"]["temperature"]["value"] == 24.375
    assert session.pending_request is None
    assert session.generation == 2
    assert device._numeric_cursor == 1
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 77),
        ("select", 46179, 77),
    ]
    assert [call for call in client.calls if call[:2] == ("holding", 46328)] == [
        ("holding", 46328, 1),
        ("holding", 46328, 1),
        ("holding", 46328, 1),
        ("holding", 46328, 1),
    ]


@pytest.mark.asyncio
async def test_last_known_good_survives_terminal_numeric_exception():
    client = HardwareClient([0x1A00, "error4"])
    device = C2000RVTI(client, 2)
    device.apply_gateway_mapping(mapping())

    await device.async_get_snapshot()
    failed = await device.async_get_snapshot()

    assert failed["numeric_sensors"]["temperature"]["value"] == 26.0
    assert "humidity" not in failed["numeric_sensors"]


@pytest.mark.asyncio
async def test_untyped_transport_failure_remains_fatal():
    client = HardwareClient([TimeoutError("transport timeout")])
    device = C2000RVTI(client, 2)
    device.apply_gateway_mapping(mapping())

    with pytest.raises(TimeoutError, match="transport timeout"):
        await device.async_get_snapshot()
