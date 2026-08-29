"""Focused support tests for the Bolid C2000-2 access controller."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import C20002
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
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
    def __init__(self, registers=None, *, error=False, function_code=None):
        self.registers = registers
        self._error = error
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self, primary=None, expanded=None, failure=None):
        self.primary = primary or [39, 15, 36, 24, 109]
        self.expanded = expanded or [149, 28, 31, 118, 999]
        self.failure = failure
        self.holding_calls = []
        self.input_calls = []

    async def read_holding_registers(self, *, address, count, device_id):
        self.holding_calls.append((address, count, device_id))
        if self.failure == "none":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "exception":
            raise ModbusException("offline")
        values = self.primary[:count]
        if self.failure == "truncated":
            values = values[:-1]
        return Response(values, function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        self.input_calls.append((address, count, device_id))
        if self.failure == "expanded_none":
            return None
        values = []
        for index in range(count // 16):
            values.extend([self.expanded[index], *([0] * 15)])
        return Response(values, function_code=4)


def gateway():
    return GatewayContext(GatewayType.S2000_PP, "pp-a", "serial:COM1", 1)


def identity(orion=12, dpls=None):
    return DownstreamDeviceIdentity(
        gateway=gateway(), model="C20002", orion_address=orion, dpls=dpls
    )


def mapping(*objects, dpls=None):
    return ResolvedDeviceMapping(
        identity=identity(dpls=dpls), source=MappingSource.MANUAL, objects=objects
    )


def all_objects():
    return tuple(
        manual_zone_mapping(local, local + 1, 3 if local == 0 else 1, 0, None)
        for local in range(5)
    )


def configured(client=None, objects=None):
    device = C20002(client or Client(), 1)
    device.apply_gateway_mapping(mapping(*(objects or all_objects())))
    return device


def test_registry_metadata_and_config_flow_visibility():
    registry = get_equipment_classes_by_manufacturer()
    assert registry["Bolid"].count("C20002") == 1
    assert len(registry["Bolid"]) == 28
    assert sum(map(len, registry.values())) == 31
    assert C20002.equipment_manufacturer == "Bolid"
    assert C20002.equipment_model == "С2000-2"
    assert C20002(None, 1).attr_model_name == "С2000-2"


def test_direct_orion_identity_has_no_dpls_and_is_stable():
    first = mapping(*all_objects())
    second = ResolvedDeviceMapping(
        identity=identity(orion=13), source=MappingSource.MANUAL, objects=all_objects()
    )
    assert first.identity.dpls is None
    assert first.identity.stable_id != second.identity.stable_id
    assert configured().attr_device_identifier == first.identity.stable_id

    with pytest.raises(ValueError, match="must not contain DPLS"):
        C20002(None, 1).apply_gateway_mapping(
            mapping(
                manual_zone_mapping(1, 1, 1, 0, None),
                dpls=DPLSSubIdentity(1, 1),
            )
        )


def test_exact_optional_capabilities_and_entities():
    capabilities = C20002.get_gateway_capabilities()
    assert [(item.local_object_number, item.zone_type) for item in capabilities] == [
        (0, 3), (1, 1), (2, 1), (3, 1), (4, 1)
    ]
    partial = configured(objects=(manual_zone_mapping(2, 7, 1, 0, None),))
    assert partial.attr_platforms == [Platform.SENSOR]
    assert [item["sensor_id"] for item in partial.get_state_sensor_descriptions()] == [
        "access_input_2_state"
    ]
    descriptions = {
        item["sensor_id"]: item for item in configured().get_state_sensor_descriptions()
    }
    assert descriptions["device_state"]["entity_category"] is EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    "bad_object",
    [
        manual_zone_mapping(5, 6, 1, 0, None),
        manual_zone_mapping(0, 1, 1, 0, None),
        manual_zone_mapping(1, 2, 3, 0, None),
        manual_zone_mapping(1, 2, 2, 0, None),
        manual_zone_mapping(1, 2, 6, 0, None),
        manual_relay_mapping(1, 1),
    ],
)
def test_unrelated_types_neighbors_and_relays_are_rejected(bad_object):
    with pytest.raises(ValueError, match="unsupported C2000-2"):
        configured(objects=(bad_object,))


def test_duplicate_mapping_is_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        configured(
            objects=(
                manual_zone_mapping(1, 1, 1, 0, None),
                manual_zone_mapping(1, 2, 1, 0, None),
            )
        )


def test_data_init_is_local_and_performs_no_modbus_io():
    client = Client()
    assert asyncio.run(configured(client).data_init()) is True
    assert client.holding_calls == []
    assert client.input_calls == []


def test_grouped_polling_multistate_access_and_unknown_codes():
    client = Client()
    snapshot = asyncio.run(configured(client).async_get_snapshot())["state_sensors"]
    assert len(client.holding_calls) == 1
    assert len(client.input_calls) == 1
    assert snapshot["device_state"]["state"] == "equipment_normal"
    assert snapshot["access_input_1_state"]["state"] == "door_opened"
    assert snapshot["access_input_1_state"]["expanded_states"] == ("access_granted",)
    assert snapshot["input_4_state"]["expanded_states"] == ("unknown_999",)


@pytest.mark.parametrize(
    ("code", "name"),
    [
        (14, "code_guessing_detected"),
        (15, "door_opened"),
        (25, "access_closed"),
        (26, "access_rejected_unknown_code"),
        (27, "door_forced"),
        (28, "access_granted"),
        (29, "access_denied"),
        (30, "access_restored"),
        (31, "door_closed"),
        (32, "passage_registered"),
        (33, "door_held_open"),
        (999, "unknown_999"),
    ],
)
def test_documented_access_and_unknown_state_codes(code, name):
    assert C20002._state_name(code) == name


@pytest.mark.parametrize(
    "failure", ["none", "error", "exception", "truncated", "expanded_none"]
)
def test_malformed_and_transport_failures_are_not_normal(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured(Client(failure=failure)).async_get_snapshot())


def test_configuration_assisted_mapping_filters_exact_rows():
    configuration = S2000PPConfiguration(
        zones=tuple(
            S2000PPZoneRow(local + 1, 12, local, 0, 3 if local == 0 else 1)
            for local in range(5)
        )
        + (
            S2000PPZoneRow(20, 12, 5, 0, 1),
            S2000PPZoneRow(21, 12, 1, 0, 3),
            S2000PPZoneRow(22, 13, 1, 0, 1),
        ),
        relays=(S2000PPRelayRow(1, 12, 1),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    automatic = asyncio.run(
        AutomaticDeviceMappingProvider(Reader(), S2000PPConfigurationCache()).async_resolve(
            gateway(),
            "C20002",
            12,
            capabilities=C20002.get_gateway_capabilities(),
        )
    )
    assert automatic.objects == mapping(*all_objects()).objects


def test_no_relays_access_database_commands_or_service_metadata_exposed():
    device = configured()
    assert not hasattr(device, "get_output_descriptions")
    assert not hasattr(device, "get_button_descriptions")
    assert device.attr_platforms == [Platform.SENSOR]
    assert asyncio.run(device.get_device_info()) == {
        "device_type": None,
        "serial_number": None,
        "hardware_version": None,
        "software_version": None,
    }
