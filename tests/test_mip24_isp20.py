"""Tests for MIP-24 isp.20 behind an S2000-PP gateway."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntryError
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
)
from homeassistant.helpers.entity import EntityCategory
from pymodbus.exceptions import ModbusException

import custom_components.modbus_devices as integration
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.bolid import MIP24Isp20
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)
from custom_components.modbus_devices.gateway import (
    DownstreamDeviceIdentity,
    DPLSSubIdentity,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.mapping import AutomaticDeviceMappingProvider
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPConfigurationCache,
    S2000PPRelayRow,
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
)


class Response:
    def __init__(
        self, registers=None, *, error=False, function_code=None, address=None,
        value=None, code=None
    ):
        self.registers = registers
        self._error = error
        self.function_code = function_code
        self.address = address
        self.value = value
        self.exception_code = code

    def isError(self):
        return self._error


class Client:
    def __init__(self, primary=None, expanded=None, numeric=None, failure=None):
        self.primary = primary or [39, 193, 195, 200, 197, 1]
        self.expanded = expanded or [149, 203, 194, 202, 196, 2]
        self.numeric = iter(numeric or [0x1B80, 0x0180, 0x1800, 0x6400, 0xE600])
        self.failure = failure
        self.holding_calls = []
        self.input_calls = []
        self.writes = []

    async def write_register(self, *, address, value, device_id):
        self.writes.append((address, value, device_id))
        return Response(function_code=6, address=address, value=value)

    async def read_holding_registers(self, *, address, count, device_id):
        self.holding_calls.append((address, count, device_id))
        if self.failure == "none":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "invalid":
            return object()
        values = [next(self.numeric)] if address == 46328 else self.primary[:count]
        if self.failure == "truncated":
            values = values[:-1]
        return Response(values, function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        self.input_calls.append((address, count, device_id))
        if self.failure == "expanded_none":
            return None
        block_count = count // 16
        values = []
        for index in range(block_count):
            values.extend([self.expanded[index], *([0] * 15)])
        return Response(values, function_code=4)


def gateway(name="pp-a", connection="serial:COM1"):
    return GatewayContext(GatewayType.S2000_PP, name, connection, 1)


def identity(orion=2, gateway_context=None, dpls=None):
    return DownstreamDeviceIdentity(
        gateway=gateway_context or gateway(),
        model="MIP24Isp20",
        orion_address=orion,
        dpls=dpls,
    )


def mapping(*objects, **identity_options):
    return ResolvedDeviceMapping(
        identity=identity(**identity_options),
        source=MappingSource.MANUAL,
        objects=objects,
    )


def all_objects():
    return (manual_zone_mapping(0, 20, 3, 0, None),) + tuple(
        manual_zone_mapping(local, local + 20, 8, 0, None)
        for local in range(1, 6)
    )


def configured(client=None, objects=None):
    device = MIP24Isp20(client or Client(), 1)
    device.apply_gateway_mapping(mapping(*(objects or all_objects())))
    return device


def test_registration_model_and_static_metadata():
    assert get_equipment_classes_by_manufacturer()["Bolid"].count("MIP24Isp20") == 1
    device = MIP24Isp20(None, 1)
    assert device.attr_model_name == "МИП-24 исп.20"
    assert device.full_designation == "МИП-24-2/П5-Р-RS"
    assert device.documented_target_firmware == "5.10"
    assert device.attr_software_version is None


def test_direct_orion_identity_is_stable_and_has_no_dpls():
    first = mapping(*all_objects(), orion=12)
    second = mapping(*all_objects(), orion=13)
    third = mapping(
        *all_objects(),
        orion=12,
        gateway_context=gateway("pp-b", "tcp:192.0.2.2:502"),
    )
    assert first.identity.dpls is None
    assert len({item.identity.stable_id for item in (first, second, third)}) == 3
    device = configured()
    assert device.attr_device_identifier == mapping(*all_objects()).identity.stable_id


def test_dpls_identity_is_rejected():
    with pytest.raises(ValueError, match="must not contain DPLS"):
        MIP24Isp20(None, 1).apply_gateway_mapping(
            mapping(*all_objects(), dpls=DPLSSubIdentity(1, 1))
        )


def test_canonical_input_zero_and_five_type_8_capabilities():
    capabilities = MIP24Isp20.get_gateway_capabilities()
    assert [(item.local_object_number, item.zone_type) for item in capabilities] == [
        (0, 3), (1, 8), (2, 8), (3, 8), (4, 8), (5, 8)
    ]
    descriptions = {item["sensor_id"]: item for item in configured().get_state_sensor_descriptions()}
    assert configured().attr_platforms == [Platform.SENSOR, Platform.BINARY_SENSOR]
    assert descriptions["device_state"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert descriptions["charger_state"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert descriptions["mains_state"]["entity_category"] is None


def test_hardware_rows_20_to_25_aggregate_into_one_device():
    device = configured()
    assert [item.gateway_object_number for item in device.attr_gateway_mapping.objects] == [
        20, 21, 22, 23, 24, 25
    ]
    assert {item["sensor_id"] for item in device.get_state_sensor_descriptions()} == {
        "device_state", "output_power_state", "output_load_state", "battery_state",
        "charger_state", "mains_state",
    }
    assert len({device.attr_device_identifier}) == 1


@pytest.mark.parametrize("bad_object", [
    manual_zone_mapping(6, 7, 1, 0, None),
    manual_zone_mapping(0, 2, 1, 0, None),
    manual_zone_mapping(1, 2, 3, 0, None),
    manual_zone_mapping(1, 2, 6, 0, None),
    manual_zone_mapping(1, 2, 7, 0, None),
    manual_relay_mapping(1, 1),
])
def test_unsupported_local_type_relay_numeric_and_counter_are_rejected(bad_object):
    with pytest.raises(ValueError, match="unsupported MIP"):
        configured(objects=(manual_zone_mapping(0, 1, 3, 0, None), bad_object))


def test_missing_required_and_duplicate_mapping_are_errors():
    with pytest.raises(ValueError, match="requires input 0"):
        configured(objects=all_objects()[1:])
    with pytest.raises(ValueError, match="Duplicate"):
        configured(objects=(
            *all_objects(),
            manual_zone_mapping(1, 26, 8, 0, None),
        ))


def test_legacy_type_1_mapping_remains_loadable():
    device = configured(objects=(manual_zone_mapping(0, 1, 3, 0, None),) + tuple(
        manual_zone_mapping(local, local + 1, 1, 0, None)
        for local in range(1, 6)
    ))
    assert len(device.get_state_sensor_descriptions()) == 6
    assert device.get_numeric_sensor_descriptions() == []


def current_configuration(*extra_rows):
    return S2000PPConfiguration(
        zones=(
            S2000PPZoneRow(20, 2, 0, 14, 3),
            *(S2000PPZoneRow(20 + local, 2, local, 14, 8)
              for local in range(1, 6)),
            *extra_rows,
        ),
        relays=(),
        partitions=(),
        unparsed_registers=(),
    )


class RowAwareClient(Client):
    """Return deterministic states by actual PP row, not persisted semantics."""

    def __init__(self):
        super().__init__(numeric=[0x1B30] * 10)
        self.states = {
            20: 152, 21: 193, 22: 195, 23: 200, 24: 197, 25: 1,
            30: 109, 31: 193, 32: 195, 33: 195, 34: 197, 35: 197,
        }

    async def read_holding_registers(self, *, address, count, device_id):
        self.holding_calls.append((address, count, device_id))
        if address == 46328:
            return Response([next(self.numeric)], function_code=3)
        first_row = address - 40000 + 1
        return Response(
            [self.states[first_row + offset] << 8 for offset in range(count)],
            function_code=3,
        )

    async def read_input_registers(self, *, address, count, device_id):
        self.input_calls.append((address, count, device_id))
        first_row = ((address - 4096) // 16) + 1
        values = []
        for offset in range(count // 16):
            row = first_row + offset
            expanded = 152 if row in (20, 30) else self.states[row]
            values.extend([expanded, *([0] * 15)])
        return Response(values, function_code=4)


def stale_type_8_objects():
    return tuple(
        manual_zone_mapping(local, 30 + local, 3 if local == 0 else 8, 14, None)
        for local in range(6)
    )


def test_stale_type_8_mapping_reproduces_live_shifted_semantic_states():
    persisted = mapping(*stale_type_8_objects())
    restored = ResolvedDeviceMapping.from_dict(persisted.to_dict())
    device = MIP24Isp20(RowAwareClient(), 1)
    device.apply_gateway_mapping(restored)

    snapshot = asyncio.run(device.async_get_snapshot())

    assert snapshot["binary_sensors"]["tamper"]["state"] is False
    assert {
        key: value["state"] for key, value in snapshot["state_sensors"].items()
    } == {
        "device_state": "disarmed",
        "output_power_state": "output_voltage_connected",
        "output_load_state": "power_overload_restored",
        "battery_state": "power_overload_restored",
        "charger_state": "charger_restored",
        "mains_state": "charger_restored",
    }
    assert device._state_mappings["battery_state"].gateway_object_number == 33
    assert device._state_mappings["mains_state"].gateway_object_number == 35
    assert device._state_mappings["device_state"].gateway_object_number == 30


def test_live_table_reconciliation_repairs_stale_and_shuffled_mapping():
    persisted = mapping(*reversed(stale_type_8_objects()))

    repaired = MIP24Isp20.reconcile_gateway_mapping(
        persisted,
        current_configuration(),
    )
    device = MIP24Isp20(RowAwareClient(), 1)
    device.apply_gateway_mapping(repaired)
    snapshot = asyncio.run(device.async_get_snapshot())

    assert [item.local_object_number for item in repaired.objects] == list(range(6))
    assert [item.gateway_object_number for item in repaired.objects] == list(range(20, 26))
    assert repaired.identity == persisted.identity
    assert repaired.source is persisted.source
    assert device.attr_device_identifier == persisted.identity.stable_id
    assert snapshot["binary_sensors"]["tamper"]["state"] is False
    assert {
        key: value["state"] for key, value in snapshot["state_sensors"].items()
    } == {
        "device_state": "enclosure_tamper_restored",
        "output_power_state": "output_voltage_connected",
        "output_load_state": "power_overload_restored",
        "battery_state": "battery_restored",
        "charger_state": "charger_restored",
        "mains_state": "mains_restored",
    }


def test_exact_legacy_mapping_remains_loadable_only_when_pp_table_matches():
    legacy_objects = (
        manual_zone_mapping(0, 1, 3, 7, None),
        *(manual_zone_mapping(local, local + 1, 1, 7, None)
          for local in range(1, 6)),
    )
    persisted = mapping(*reversed(legacy_objects))
    configuration = S2000PPConfiguration(
        zones=(
            S2000PPZoneRow(1, 2, 0, 7, 3),
            *(S2000PPZoneRow(local + 1, 2, local, 7, 1)
              for local in range(1, 6)),
        ),
        relays=(), partitions=(), unparsed_registers=(),
    )

    assert MIP24Isp20.reconcile_gateway_mapping(persisted, configuration) is persisted


@pytest.mark.parametrize("configuration", [
    current_configuration(S2000PPZoneRow(26, 2, 3, 14, 8)),
    S2000PPConfiguration(
        zones=current_configuration().zones[:-1],
        relays=(), partitions=(), unparsed_registers=(),
    ),
])
def test_ambiguous_or_missing_current_footprint_fails_instead_of_guessing(
    configuration,
):
    with pytest.raises(ValueError, match="unambiguous current"):
        MIP24Isp20.reconcile_gateway_mapping(
            mapping(*stale_type_8_objects()),
            configuration,
        )


@pytest.mark.asyncio
async def test_config_entry_repair_persists_only_reconciled_objects(monkeypatch):
    persisted = mapping(*stale_type_8_objects())
    options = {
        Config.CONF_DEVICE_CLASS: "MIP24Isp20",
        Config.CONF_GATEWAY_MAPPING: persisted.to_dict(),
    }
    update_entry = Mock()
    hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(async_update_entry=update_entry),
    )
    entry = SimpleNamespace(data={}, options=options)

    class Reader:
        def __init__(self, *_args):
            pass

        async def async_read(self):
            return current_configuration()

    monkeypatch.setattr(integration, "S2000PPConfigurationReader", Reader)

    repaired_options, repaired = await integration._async_reconcile_gateway_mapping(
        hass, entry, options, MIP24Isp20, object(), persisted
    )

    assert [item.gateway_object_number for item in repaired.objects] == list(range(20, 26))
    assert repaired.identity == persisted.identity
    assert repaired_options[Config.CONF_GATEWAY_MAPPING] == repaired.to_dict()
    update_entry.assert_called_once_with(
        entry,
        data={},
        options=repaired_options,
    )


@pytest.mark.asyncio
async def test_ambiguous_config_entry_fails_with_reconfigure_action(monkeypatch):
    persisted = mapping(*stale_type_8_objects())
    options = {Config.CONF_GATEWAY_MAPPING: persisted.to_dict()}
    update_entry = Mock()
    hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(async_update_entry=update_entry),
    )

    class Reader:
        def __init__(self, *_args):
            pass

        async def async_read(self):
            return current_configuration(S2000PPZoneRow(26, 2, 3, 14, 8))

    monkeypatch.setattr(integration, "S2000PPConfigurationReader", Reader)

    with pytest.raises(ConfigEntryError, match="reconfigure the device mapping"):
        await integration._async_reconcile_gateway_mapping(
            hass,
            SimpleNamespace(data={}, options=options),
            options,
            MIP24Isp20,
            object(),
            persisted,
        )
    update_entry.assert_not_called()


def test_grouped_atomic_polling_and_independent_states():
    client = Client()
    snapshot = asyncio.run(configured(client).async_get_snapshot())["state_sensors"]
    assert client.holding_calls == [(46328, 1, 1), (40019, 6, 1)]
    assert len(client.input_calls) == 1
    assert snapshot["output_power_state"]["state"] == "output_voltage_connected"
    assert snapshot["mains_state"]["state"] == "mains_restored"
    assert snapshot["output_power_state"]["expanded_states"] == ("device_restarted",)
    assert snapshot["device_state"]["expanded_states"] == ("enclosure_tamper",)
    assert snapshot["charger_state"]["primary_code"] == 197


def test_numeric_entity_matrix_and_unsigned_q8_8_decoding():
    device = configured()
    descriptions = {
        item["sensor_id"]: item for item in device.get_numeric_sensor_descriptions()
    }
    assert {
        key: (item["device_class"], item["state_class"], item["unit"])
        for key, item in descriptions.items()
    } == {
        "output_voltage": (SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT,
                           UnitOfElectricPotential.VOLT),
        "output_current": (SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT,
                           UnitOfElectricCurrent.AMPERE),
        "battery_voltage": (SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT,
                            UnitOfElectricPotential.VOLT),
        "battery_charge": (SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT,
                           PERCENTAGE),
        "mains_voltage": (SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT,
                          UnitOfElectricPotential.VOLT),
    }
    snapshots = [asyncio.run(device.async_get_snapshot()) for _ in range(5)]
    snapshot = snapshots[-1]
    assert {key: value["value"] for key, value in snapshot["numeric_sensors"].items()} == {
        "output_voltage": 27.5,
        "output_current": 1.5,
        "battery_voltage": 24.0,
        "battery_charge": 100.0,
        "mains_voltage": 230.0,
    }
    assert device.attr_client.writes == [
        (46181, row, 1) for row in range(21, 26)
    ]
    assert set(snapshots[0]["numeric_sensors"]) == {"output_voltage"}
    assert set(snapshots[1]["numeric_sensors"]) == {
        "output_voltage", "output_current"
    }


def test_round_robin_cycles_one_numeric_input_per_state_refresh():
    client = Client(numeric=[0x0100, 0x0200, 0x0300, 0x0400, 0x0500, 0x0600])
    device = configured(client)

    snapshots = [asyncio.run(device.async_get_snapshot()) for _ in range(6)]

    assert client.writes == [
        (46181, 21, 1),
        (46181, 22, 1),
        (46181, 23, 1),
        (46181, 24, 1),
        (46181, 25, 1),
        (46181, 21, 1),
    ]
    assert [len(snapshot["numeric_sensors"]) for snapshot in snapshots] == [
        1, 2, 3, 4, 5, 5
    ]
    assert snapshots[0]["numeric_sensors"]["output_voltage"]["value"] == 1.0
    assert snapshots[4]["numeric_sensors"]["output_voltage"]["value"] == 1.0
    assert snapshots[5]["numeric_sensors"]["output_voltage"]["value"] == 6.0
    assert all(len(snapshot["state_sensors"]) == 6 for snapshot in snapshots)
    assert len(client.input_calls) == 6
    assert len(client.holding_calls) == 12


def test_round_robin_order_is_independent_of_mapping_object_order():
    client = Client()
    objects = all_objects()
    device = configured(client, (objects[0], *reversed(objects[1:])))

    for _ in range(5):
        asyncio.run(device.async_get_snapshot())

    assert client.writes == [(46181, row, 1) for row in range(21, 26)]


def test_first_refresh_leaves_not_yet_read_numeric_entities_unknown():
    snapshot = asyncio.run(configured().async_get_snapshot())

    assert snapshot["numeric_sensors"] == {
        "output_voltage": {
            "value": 27.5,
            "raw_register": 0x1B80,
            "parameter_kind": "output_voltage",
        }
    }
    assert snapshot["numeric_sensors"].get("output_current") is None
    assert snapshot["numeric_sensors"].get("battery_voltage") is None
    assert snapshot["numeric_sensors"].get("battery_charge") is None
    assert snapshot["numeric_sensors"].get("mains_voltage") is None


def test_round_robin_steady_state_load_is_48_requests_per_minute():
    client = Client(numeric=[0x0100] * 12)
    device = configured(client)

    for _ in range(12):
        asyncio.run(device.async_get_snapshot())

    assert len(client.writes) == 12
    assert len([call for call in client.holding_calls if call[0] == 46328]) == 12
    assert len([call for call in client.holding_calls if call[0] == 40019]) == 12
    assert len(client.input_calls) == 12
    assert len(client.writes) + len(client.holding_calls) + len(client.input_calls) == 48


def test_local_hardware_rows_and_numeric_payloads():
    """Preserve the read-only COM3 validation fixture without using real hardware."""
    objects = (manual_zone_mapping(0, 6, 3, 14, None),) + tuple(
        manual_zone_mapping(local, local + 6, 8, 14, None)
        for local in range(1, 6)
    )
    client = Client(
        primary=[0x98FB, 0xC1C7, 0xC3FB, 0xC8FB, 0xC5FB, 0x01FB],
        expanded=[152, 193, 195, 200, 197, 1],
        numeric=[0x1B30, 0x0070, 0x1B20, 0x0000, 0xD400],
    )

    device = configured(client, objects)
    snapshots = [asyncio.run(device.async_get_snapshot()) for _ in range(5)]
    snapshot = snapshots[-1]

    assert snapshot["binary_sensors"]["tamper"]["state"] is False
    assert {
        key: value["state"] for key, value in snapshot["state_sensors"].items()
    } == {
        "device_state": "enclosure_tamper_restored",
        "output_power_state": "output_voltage_connected",
        "output_load_state": "power_overload_restored",
        "battery_state": "battery_restored",
        "charger_state": "charger_restored",
        "mains_state": "mains_restored",
    }
    assert {
        key: value["value"] for key, value in snapshot["numeric_sensors"].items()
    } == {
        "output_voltage": 27.1875,
        "output_current": 0.4375,
        "battery_voltage": 27.125,
        "battery_charge": 0.0,
        "mains_voltage": 212.0,
    }
    assert client.writes == [(46181, row, 1) for row in range(7, 12)]


@pytest.mark.parametrize(("code", "expected"), [(149, True), (152, False), (39, None)])
def test_input_zero_tamper_open_restored_and_unknown(code, expected):
    client = Client(expanded=[code, 0, 0, 0, 0, 0])
    snapshot = asyncio.run(configured(client).async_get_snapshot())
    assert snapshot["binary_sensors"]["tamper"] == {
        "state": expected,
        "primary_code": 39,
        "expanded_codes": (code, *([0] * 15)),
    }
    description = configured().get_binary_sensor_descriptions()[0]
    assert description["device_class"].value == "tamper"
    assert description["entity_category"] is EntityCategory.DIAGNOSTIC


@pytest.mark.asyncio
async def test_pending_numeric_request_retries_result_without_new_selector():
    class PendingClient(Client):
        def __init__(self):
            super().__init__()
            self.pending = True

        async def read_holding_registers(self, *, address, count, device_id):
            if address == 46328 and self.pending:
                self.holding_calls.append((address, count, device_id))
                return Response(error=True, code=15, function_code=0x83)
            return await super().read_holding_registers(
                address=address, count=count, device_id=device_id
            )

    client = PendingClient()
    device = configured(client)
    first = await device.async_get_snapshot()
    assert first["numeric_sensors"] == {}
    assert client.writes == [(46181, 21, 1)]

    client.pending = False
    second = await device.async_get_snapshot()
    assert second["numeric_sensors"]["output_voltage"]["value"] == 27.5
    assert client.writes[0] == (46181, 21, 1)
    assert client.writes.count((46181, 21, 1)) == 1

    third = await device.async_get_snapshot()
    assert third["numeric_sensors"]["output_voltage"]["value"] == 27.5
    assert client.writes[-1] == (46181, 22, 1)


def test_numeric_protocol_error_remains_fatal_and_does_not_publish_zero():
    client = Client()

    async def unavailable(*, address, count, device_id):
        if address == 46328:
            return Response(error=True, code=3, function_code=0x83)
        return await Client.read_holding_registers(
            client, address=address, count=count, device_id=device_id
        )

    client.read_holding_registers = unavailable
    with pytest.raises(ModbusException):
        asyncio.run(configured(client).async_get_snapshot())


@pytest.mark.parametrize("code, name", [
    (1, "mains_restored"), (2, "mains_fault"),
    (61, "configuration_reset"), (62, "configuration_changed"),
    (149, "enclosure_tamper"), (152, "enclosure_tamper_restored"),
    (186, "battery_replacement_required"),
    (192, "output_voltage_disconnected"), (193, "output_voltage_connected"),
    (194, "power_overload"), (195, "power_overload_restored"),
    (196, "charger_fault"), (197, "charger_restored"),
    (198, "power_fault"), (199, "power_restored"),
    (200, "battery_restored"), (202, "battery_fault"),
    (203, "device_restarted"), (205, "battery_test_failed"),
    (211, "battery_low"), (250, "device_communication_lost"),
    (251, "device_communication_restored"), (999, "unknown_999"),
])
def test_common_state_codes(code, name):
    assert MIP24Isp20._state_name(code) == name


@pytest.mark.parametrize("failure", ["none", "error", "invalid", "truncated", "expanded_none"])
def test_invalid_and_communication_responses_are_not_normal(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured(Client(failure=failure)).async_get_snapshot())


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(20, 2, 0, 0, 3),) + tuple(
            S2000PPZoneRow(local + 20, 2, local, 0, 8)
            for local in range(1, 6)
        ) + (
            S2000PPZoneRow(19, 2, 7, 0, 1),
            S2000PPZoneRow(26, 3, 0, 0, 3),
        ),
        relays=(S2000PPRelayRow(1, 2, 1),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    automatic = asyncio.run(AutomaticDeviceMappingProvider(
        Reader(), S2000PPConfigurationCache()
    ).async_resolve(
        gateway(), "MIP24Isp20", 2,
        capabilities=MIP24Isp20.get_gateway_capabilities(),
    ))
    assert automatic.objects == mapping(*all_objects()).objects


def test_no_outputs_controls_or_invented_service_metadata():
    device = configured()
    assert not hasattr(device, "get_output_descriptions")
    assert device.attr_platforms == [Platform.SENSOR, Platform.BINARY_SENSOR]
    assert asyncio.run(device.get_device_info()) == {
        "device_type": None,
        "serial_number": None,
        "hardware_version": None,
        "software_version": None,
    }
