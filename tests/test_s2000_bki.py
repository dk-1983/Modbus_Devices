"""Focused support tests for the Bolid S2000-BKI display and control unit."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import C2000BKI
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)
from custom_components.modbus_devices.gateway import (
    CapabilityRequirement,
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
    S2000PPPartitionRow,
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
    def __init__(self, failure=None):
        self.failure = failure
        self.holding_calls = []
        self.input_calls = []

    async def read_holding_registers(self, *, address, count, device_id):
        self.holding_calls.append((address, count, device_id))
        if self.failure == "none":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "wrong_function":
            return Response([39], function_code=4)
        if self.failure == "exception":
            raise ModbusException("offline")
        values = [39]
        if self.failure == "truncated":
            values = []
        return Response(values, function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        self.input_calls.append((address, count, device_id))
        if self.failure == "expanded_none":
            return None
        values = [0] * count
        values[0] = 149
        return Response(values, function_code=4)


def gateway():
    return GatewayContext(GatewayType.S2000_PP, "pp-a", "serial:COM1", 1)


def identity(orion=12, dpls=None):
    return DownstreamDeviceIdentity(
        gateway=gateway(), model="C2000BKI", orion_address=orion, dpls=dpls
    )


def mapping(*objects, dpls=None):
    return ResolvedDeviceMapping(
        identity=identity(dpls=dpls), source=MappingSource.MANUAL, objects=objects
    )


def device_state(gateway_object=1):
    return manual_zone_mapping(0, gateway_object, 3, 0, None)


def configured(client=None):
    device = C2000BKI(client or Client(), 1)
    device.apply_gateway_mapping(mapping(device_state()))
    return device


def test_registry_metadata_and_config_flow_visibility():
    registry = get_equipment_classes_by_manufacturer()
    assert registry["Bolid"].count("C2000BKI") == 1
    assert len(registry["Bolid"]) == 29
    assert sum(map(len, registry.values())) == 33
    assert C2000BKI.equipment_manufacturer == "Bolid"
    assert C2000BKI.equipment_model == "С2000-БКИ"
    assert C2000BKI.documented_firmware == "2.45"
    assert C2000BKI(None, 1).attr_model_name == "С2000-БКИ"


def test_direct_orion_identity_has_no_dpls_and_is_stable():
    first = mapping(device_state())
    second = ResolvedDeviceMapping(
        identity=identity(orion=13), source=MappingSource.MANUAL, objects=(device_state(),)
    )
    assert first.identity.dpls is None
    assert first.identity.stable_id != second.identity.stable_id
    assert configured().attr_device_identifier == first.identity.stable_id

    with pytest.raises(ValueError, match="must not contain DPLS"):
        C2000BKI(None, 1).apply_gateway_mapping(
            mapping(device_state(), dpls=DPLSSubIdentity(1, 1))
        )


def test_exact_device_state_capability_and_entity():
    (capability,) = C2000BKI.get_gateway_capabilities()
    assert (capability.object_kind.value, capability.local_object_number) == ("zone", 0)
    assert capability.zone_type == 3
    assert capability.requirement is CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION
    assert configured().attr_platforms == [Platform.SENSOR]
    assert configured().get_state_sensor_descriptions() == [
        {
            "sensor_id": "device_state",
            "name": "Device state",
            "device_class": None,
            "icon": "mdi:state-machine",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }
    ]


@pytest.mark.parametrize(
    "bad_object",
    [
        manual_zone_mapping(0, 1, 1, 0, None),
        manual_zone_mapping(1, 1, 3, 0, None),
        manual_zone_mapping(1, 1, 1, 0, None),
        manual_relay_mapping(1, 1),
    ],
)
def test_external_wrong_local_type_and_relay_objects_are_rejected(bad_object):
    with pytest.raises(ValueError, match="unsupported C2000-BKI"):
        C2000BKI(None, 1).apply_gateway_mapping(mapping(bad_object))


def test_empty_and_duplicate_mapping_are_rejected():
    with pytest.raises(ValueError, match="must contain objects"):
        mapping()
    with pytest.raises(ValueError, match="Duplicate"):
        C2000BKI(None, 1).apply_gateway_mapping(
            mapping(device_state(1), device_state(2))
        )


def test_data_init_is_local_and_performs_no_modbus_io():
    client = Client()
    assert asyncio.run(configured(client).data_init()) is True
    assert client.holding_calls == []
    assert client.input_calls == []


def test_snapshot_uses_one_primary_and_one_expanded_read():
    client = Client()
    snapshot = asyncio.run(configured(client).async_get_snapshot())["state_sensors"]
    assert client.holding_calls == [(40000, 1, 1)]
    assert client.input_calls == [(4096, 16, 1)]
    assert snapshot["device_state"] == {
        "state": "equipment_normal",
        "primary_code": 39,
        "expanded_codes": (149, *([0] * 15)),
        "expanded_states": ("enclosure_tamper",),
    }


def test_unknown_primary_and_expanded_states_are_preserved():
    class UnknownClient(Client):
        async def read_holding_registers(self, *, address, count, device_id):
            self.holding_calls.append((address, count, device_id))
            return Response([0xFE00], function_code=3)

        async def read_input_registers(self, *, address, count, device_id):
            self.input_calls.append((address, count, device_id))
            return Response([998] + [0] * 15, function_code=4)

    state = asyncio.run(configured(UnknownClient()).async_get_snapshot())["state_sensors"][
        "device_state"
    ]
    assert state["state"] == "unknown_254"
    assert state["expanded_states"] == ("unknown_998",)


@pytest.mark.parametrize(
    "failure", ["none", "error", "wrong_function", "exception", "truncated", "expanded_none"]
)
def test_malformed_and_transport_failures_are_not_normal(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured(Client(failure=failure)).async_get_snapshot())


def test_assisted_mapping_selects_only_own_device_state_at_orion_address():
    configuration = S2000PPConfiguration(
        zones=(
            S2000PPZoneRow(1, 12, 0, 0, 3),
            S2000PPZoneRow(2, 12, 1, 0, 1),
            S2000PPZoneRow(3, 12, 0, 0, 1),
            S2000PPZoneRow(4, 13, 0, 0, 3),
        ),
        relays=(S2000PPRelayRow(1, 12, 1),),
        partitions=(S2000PPPartitionRow(1, 1),),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    automatic = asyncio.run(
        AutomaticDeviceMappingProvider(Reader(), S2000PPConfigurationCache()).async_resolve(
            gateway(),
            "C2000BKI",
            12,
            capabilities=C2000BKI.get_gateway_capabilities(),
        )
    )
    assert automatic.objects == (device_state(),)


def test_external_partitions_indicators_keys_and_controls_are_not_exposed():
    device = configured()
    assert not hasattr(device, "get_output_descriptions")
    assert not hasattr(device, "get_button_descriptions")
    assert not hasattr(device, "get_partition_descriptions")
    assert device.attr_platforms == [Platform.SENSOR]
    assert device.attr_device_metadata["documented_orion_state_objects"] == 1
