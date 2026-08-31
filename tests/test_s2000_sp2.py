"""Focused support tests for the Bolid S2000-SP2 relay unit."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform

from custom_components.modbus_devices.equipment.bolid import C2000SP2
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)
from custom_components.modbus_devices.gateway import (
    CapabilityRequirement,
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
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
    def __init__(self, bits=None, *, error=False, function_code=1):
        self.bits = bits
        self._error = error
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self, failure=None):
        self.failure = failure
        self.coil_calls = []

    async def read_coils(self, *, address, count, device_id):
        self.coil_calls.append((address, count, device_id))
        if self.failure == "none":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "wrong_function":
            return Response([False] * count, function_code=2)
        if self.failure == "exception":
            raise ModbusException("offline")
        bits = [True, False][:count]
        if self.failure == "truncated":
            bits = bits[: max(0, count - 1)]
        return Response(bits)


def gateway():
    return GatewayContext(GatewayType.S2000_PP, "pp-a", "serial:COM1", 1)


def identity(*, base=20, count=2, topology="two_outputs", kdl=10):
    return DownstreamDeviceIdentity(
        gateway=gateway(),
        model="C2000SP2",
        orion_address=kdl,
        dpls=DPLSSubIdentity(base, count),
        metadata=DownstreamDeviceMetadata(topology=topology),
    )


def mapping(*objects, base=20, count=2, topology="two_outputs", kdl=10):
    return ResolvedDeviceMapping(
        identity=identity(base=base, count=count, topology=topology, kdl=kdl),
        source=MappingSource.MANUAL,
        objects=objects,
    )


def configured(client=None, *, topology="two_outputs", second=True):
    objects = [manual_relay_mapping(20, 1)]
    if second:
        objects.append(manual_relay_mapping(21, 2))
    device = C2000SP2(client or Client(), 1)
    device.apply_gateway_mapping(
        mapping(
            *objects,
            count=1 if topology == "one_output" else 2,
            topology=topology,
        )
    )
    return device


def test_registry_metadata_and_config_flow_visibility():
    registry = get_equipment_classes_by_manufacturer()
    assert registry["Bolid"].count("C2000SP2") == 1
    assert len(registry["Bolid"]) == 29
    assert sum(map(len, registry.values())) == 33
    assert C2000SP2.equipment_manufacturer == "Bolid"
    assert C2000SP2.equipment_model == "С2000-СП2"
    assert C2000SP2.documented_firmware == "1.21"
    assert C2000SP2(None, 1).attr_model_name == "С2000-СП2"


def test_dpls_identity_uses_gateway_kdl_and_base_address():
    first = mapping(manual_relay_mapping(20, 1))
    moved = mapping(manual_relay_mapping(21, 1), base=21)
    other_kdl = mapping(manual_relay_mapping(20, 1), kdl=11)
    assert first.identity.dpls == DPLSSubIdentity(20, 2)
    assert len({first.identity.stable_id, moved.identity.stable_id, other_kdl.identity.stable_id}) == 3
    assert configured().attr_device_identifier == first.identity.stable_id


def test_exact_topology_capabilities_and_read_only_entities():
    capabilities = C2000SP2.get_gateway_capabilities()
    assert [item.key for item in capabilities] == ["relay_1", "relay_2"]
    assert [item.object_kind.value for item in capabilities] == ["relay", "relay"]
    assert [item.local_object_offset for item in capabilities] == [0, 1]
    assert {item.requirement for item in capabilities} == {
        CapabilityRequirement.OPTIONAL_IF_CONFIGURED
    }

    one = configured(topology="one_output", second=False)
    two = configured()
    assert one.attr_platforms == two.attr_platforms == [Platform.SENSOR]
    assert [item["sensor_id"] for item in one.get_state_sensor_descriptions()] == [
        "relay_1"
    ]
    assert [item["sensor_id"] for item in two.get_state_sensor_descriptions()] == [
        "relay_1",
        "relay_2",
    ]
    assert not hasattr(two, "set_output")
    assert not hasattr(two, "get_output_descriptions")
    assert not hasattr(two, "get_button_descriptions")


def test_partial_two_output_mapping_is_valid_but_at_least_one_row_is_required():
    device = C2000SP2(None, 1)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(21, 2)))
    assert [item["sensor_id"] for item in device.get_state_sensor_descriptions()] == [
        "relay_2"
    ]
    with pytest.raises(ValueError, match="must contain objects"):
        mapping()


@pytest.mark.parametrize(
    "bad_object",
    [
        manual_relay_mapping(19, 1),
        manual_relay_mapping(22, 1),
        manual_zone_mapping(20, 1, 1, 0, None),
    ],
)
def test_wrong_local_kind_and_neighboring_objects_are_rejected(bad_object):
    with pytest.raises(ValueError, match="unsupported C2000-SP2"):
        C2000SP2(None, 1).apply_gateway_mapping(mapping(bad_object))


def test_wrong_topology_count_missing_dpls_and_duplicate_are_rejected():
    with pytest.raises(ValueError, match="range does not match"):
        C2000SP2(None, 1).apply_gateway_mapping(
            mapping(manual_relay_mapping(20, 1), count=1)
        )
    no_dpls = ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=gateway(),
            model="C2000SP2",
            orion_address=10,
            metadata=DownstreamDeviceMetadata(topology="two_outputs"),
        ),
        source=MappingSource.MANUAL,
        objects=(manual_relay_mapping(20, 1),),
    )
    with pytest.raises(ValueError, match="requires a DPLS"):
        C2000SP2(None, 1).apply_gateway_mapping(no_dpls)
    with pytest.raises(ValueError, match="Duplicate"):
        C2000SP2(None, 1).apply_gateway_mapping(
            mapping(manual_relay_mapping(20, 1), manual_relay_mapping(20, 2))
        )


def test_assisted_mapping_filters_exact_kdl_dpls_relay_rows():
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(1, 10, 20, 0, 1),),
        relays=(
            S2000PPRelayRow(1, 10, 20),
            S2000PPRelayRow(2, 10, 21),
            S2000PPRelayRow(3, 10, 22),
            S2000PPRelayRow(4, 11, 20),
        ),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    metadata = DownstreamDeviceMetadata(topology="two_outputs")
    automatic = asyncio.run(
        AutomaticDeviceMappingProvider(Reader(), S2000PPConfigurationCache()).async_resolve(
            gateway(),
            "C2000SP2",
            10,
            dpls=DPLSSubIdentity(20, 2),
            metadata=metadata,
            capabilities=C2000SP2.get_gateway_capabilities_for_metadata(metadata),
        )
    )
    assert automatic.objects == (
        manual_relay_mapping(20, 1),
        manual_relay_mapping(21, 2),
    )


def test_full_mapping_uses_one_grouped_fc01_read_and_preserves_states():
    client = Client()
    snapshot = asyncio.run(configured(client).async_get_snapshot())
    assert client.coil_calls == [(10000, 2, 1)]
    assert snapshot == {
        "state_sensors": {
            "relay_1": {
                "state": "on",
                "primary_code": 1,
                "expanded_codes": (),
                "expanded_states": (),
            },
            "relay_2": {
                "state": "off",
                "primary_code": 0,
                "expanded_codes": (),
                "expanded_states": (),
            },
        }
    }


@pytest.mark.parametrize(
    "failure", ["none", "error", "wrong_function", "exception", "truncated"]
)
def test_malformed_and_transport_failures_are_not_fake_states(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured(Client(failure=failure)).async_get_snapshot())


def test_data_init_is_local_and_performs_no_modbus_io_or_writes():
    client = Client()
    assert asyncio.run(configured(client).data_init()) is True
    assert client.coil_calls == []
