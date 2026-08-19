"""Tests for the radio magnetic-contact detector С2000Р-СМК."""

import asyncio

import pytest

from custom_components.modbus_devices.equipment.bolid import C2000RSMK
from custom_components.modbus_devices.equipment.equipment import get_gateway_capabilities
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
    resolve_zone_row,
)


class Response:
    def __init__(self, registers): self.registers = registers
    def isError(self): return False


class Client:
    async def read_holding_registers(self, *, address, count, device_id):
        return Response([3, 35][:count])

    async def read_input_registers(self, *, address, count, device_id):
        code = 3 if address < 30000 else 35
        return Response([code, 149, 211, 187, 999] + [0] * (count - 5))


def mapping(*objects, topology="contact_only", variant=None, base=20, connection="tcp:pp"):
    count = 2 if topology == "contact_and_external_input" else 1
    return ResolvedDeviceMapping(DownstreamDeviceIdentity(
        GatewayContext(GatewayType.S2000_PP, "pp", connection, 1),
        "C2000RSMK", 10, DPLSSubIdentity(base, count),
        DownstreamDeviceMetadata(variant=variant, topology=topology),
    ), MappingSource.MANUAL, objects)


@pytest.mark.parametrize("variant", [None, "hardware_1_0", "hardware_2_0"])
def test_variants_are_optional_static_metadata(variant):
    device = C2000RSMK(Client(), 1)
    device.apply_gateway_mapping(mapping(
        manual_zone_mapping(20, 1, 1, 0, None), variant=variant
    ))
    assert device.attr_model_name == "С2000Р-СМК"
    assert device.attr_hardware_version is None
    assert device.attr_software_version is None
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(20, 1)


def test_topology_capabilities_and_two_independent_zones():
    metadata = DownstreamDeviceMetadata(topology="contact_and_external_input")
    assert [item.key for item in get_gateway_capabilities(
        "Bolid", "C2000RSMK", metadata
    )] == ["opening_state", "external_input_state"]
    device = C2000RSMK(Client(), 1)
    device.apply_gateway_mapping(mapping(
        manual_zone_mapping(20, 1, 1, 0, None),
        manual_zone_mapping(21, 2, 1, 0, None),
        topology="contact_and_external_input",
    ))
    snapshot = asyncio.run(device.async_get_snapshot())["state_sensors"]
    assert set(snapshot) == {"opening_state", "external_input_state"}
    assert len(device.get_state_sensor_descriptions()) == 2
    assert device.attr_device_metadata["dpls_address_count"] == 2


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    for table, local in ((1, 20), (2, 21)):
        row = S2000PPZoneRow(table, 10, local, 0, 1)
        assert resolve_zone_row(row, None) == manual_zone_mapping(
            local, table, 1, 0, None
        )


def test_contact_only_rejects_neighbor_and_two_zone_requires_both():
    with pytest.raises(ValueError):
        C2000RSMK(Client(), 1).apply_gateway_mapping(mapping(
            manual_zone_mapping(20, 1, 1, 0, None),
            manual_zone_mapping(21, 2, 1, 0, None),
        ))
    with pytest.raises(ValueError):
        C2000RSMK(Client(), 1).apply_gateway_mapping(mapping(
            manual_zone_mapping(20, 1, 1, 0, None),
            topology="contact_and_external_input",
        ))


@pytest.mark.parametrize("wrong", [
    manual_zone_mapping(0, 1, 3, 0, None),
    manual_zone_mapping(20, 1, 6, 0, None),
    manual_relay_mapping(20, 1),
])
def test_unrelated_object_kinds_and_types_rejected(wrong):
    with pytest.raises(ValueError):
        C2000RSMK(Client(), 1).apply_gateway_mapping(mapping(wrong))


def test_radio_identity_and_unsupported_entities():
    device = C2000RSMK(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))
    assert "arr" not in device.attr_device_identifier.lower()
    assert not hasattr(device, "get_numeric_sensor_descriptions")
    assert not hasattr(device, "get_output_descriptions")
    assert C2000RSMK._state_name(211) == "battery_low"
    assert C2000RSMK._state_name(999) == "unknown_999"
