"""Tests for the gateway-dependent C2000-SP4 family."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.coordinator import ModbusDeviceCoordinator
from custom_components.modbus_devices.equipment.bolid import C2000SP4
from custom_components.modbus_devices.gateway import (
    CapabilityRequirement,
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
    dpls_ranges_overlap,
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
    def __init__(self, *, bits=None, registers=None, error=False,
                 function_code=None, address=None, value=None):
        self.bits = bits
        self.registers = registers
        self._error = error
        self.function_code = function_code
        self.address = address
        self.value = value

    def isError(self):
        return self._error


class Client:
    def __init__(self):
        self.writes = []
        self.error = False

    async def read_coils(self, address, count, device_id):
        return Response(bits=[False] * count, error=self.error, function_code=1)

    async def read_holding_registers(self, address, count, device_id):
        return Response(registers=[54] * count, error=self.error, function_code=3)

    async def read_input_registers(self, address, count, device_id):
        values = ([54, 149, 198, 999] + [0] * 12) * (count // 16)
        return Response(registers=values, error=self.error, function_code=4)

    async def write_coil(self, address, value, device_id):
        self.writes.append((address, value, device_id))
        return Response(
            error=self.error,
            function_code=5,
            address=address,
            value=value,
        )


def gateway(name="pp-a"):
    return GatewayContext(GatewayType.S2000_PP, name, "serial:COM1", 1)


def mapping(*objects, base=20, kdl=10, variant="sp4_24", gateway_name="pp-a"):
    return ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=gateway(gateway_name),
            model="C2000SP4",
            orion_address=kdl,
            dpls=DPLSSubIdentity(base, 5),
            metadata=DownstreamDeviceMetadata(variant),
        ),
        source=MappingSource.MANUAL,
        objects=tuple(objects),
    )


@pytest.mark.parametrize("variant", [item.value for item in C2000SP4.Variant])
def test_four_supported_variants(variant):
    device = C2000SP4(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(20, 1), variant=variant))
    assert device.attr_device_metadata["variant"]


def test_220_02_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        C2000SP4(Client(), 1).apply_gateway_mapping(
            mapping(manual_relay_mapping(20, 1), variant="sp4_220_02")
        )


def test_flow_metadata_lists_220_02_only_as_explicitly_unsupported():
    assert "sp4_220_02" in C2000SP4.get_variant_options()
    assert "sp4_220_02" in C2000SP4.unsupported_variants
    assert C2000SP4.Variant.SP4_220_01 in C2000SP4.variants


def test_all_configured_capabilities_are_optional():
    assert len(C2000SP4.get_gateway_capabilities()) == 6
    assert {item.requirement for item in C2000SP4.get_gateway_capabilities()} == {
        CapabilityRequirement.OPTIONAL_IF_CONFIGURED
    }


def test_missing_and_empty_mapping_are_rejected():
    with pytest.raises(ValueError, match="requires a validated"):
        asyncio.run(C2000SP4(Client(), 1).data_init())


def test_nested_identity_distinguishes_kdl_and_dpls_devices():
    first = mapping(manual_relay_mapping(20, 1), base=20, kdl=10)
    second = mapping(manual_relay_mapping(40, 2), base=40, kdl=10)
    third = mapping(manual_relay_mapping(20, 3), base=20, kdl=11)
    assert len({first.identity.stable_id, second.identity.stable_id, third.identity.stable_id}) == 3


def test_overlapping_range_only_rejected_on_same_gateway_and_kdl():
    first = mapping(manual_relay_mapping(20, 1), base=20, kdl=10)
    overlap = mapping(manual_relay_mapping(23, 2), base=23, kdl=10)
    other_kdl = mapping(manual_relay_mapping(20, 3), base=20, kdl=11)
    other_gateway = mapping(manual_relay_mapping(20, 4), base=20, kdl=10, gateway_name="pp-b")
    assert dpls_ranges_overlap(first.identity, overlap.identity)
    assert not dpls_ranges_overlap(first.identity, other_kdl.identity)
    assert not dpls_ranges_overlap(first.identity, other_gateway.identity)


def test_identity_roundtrip_and_legacy_identity():
    current = mapping(manual_relay_mapping(20, 1))
    assert ResolvedDeviceMapping.from_dict(current.to_dict()) == current
    legacy = DownstreamDeviceIdentity(gateway(), "C2000KPB", 10)
    assert DownstreamDeviceIdentity.from_dict(legacy.to_dict()) == legacy


def test_partial_mapping_and_all_five_dpls_objects():
    partial = C2000SP4(Client(), 1)
    partial.apply_gateway_mapping(mapping(manual_zone_mapping(23, 10, 1, 0, None)))
    assert [item["sensor_id"] for item in partial.get_state_sensor_descriptions()] == ["working_limit_switch"]

    device = C2000SP4(Client(), 1)
    device.apply_gateway_mapping(mapping(
        manual_relay_mapping(20, 1),
        manual_zone_mapping(20, 2, 1, 0, None),
        manual_zone_mapping(21, 3, 2, 0, None),
        manual_zone_mapping(22, 4, 2, 0, None),
        manual_zone_mapping(23, 5, 1, 0, None),
        manual_zone_mapping(24, 6, 1, 0, None),
    ))
    assert len(device.get_output_descriptions()) == 1
    assert len(device.get_state_sensor_descriptions()) == 5


def test_wrong_type_and_out_of_range_object_rejected():
    device = C2000SP4(Client(), 1)
    with pytest.raises(ValueError, match="unsupported"):
        device.apply_gateway_mapping(mapping(manual_zone_mapping(21, 1, 1, 0, None)))
    with pytest.raises(ValueError, match="unsupported"):
        device.apply_gateway_mapping(mapping(manual_relay_mapping(21, 1)))


def test_actuator_on_off_uses_one_resolved_coil():
    client = Client()
    device = C2000SP4(client, 7)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(20, 41)))
    asyncio.run(device.set_output(1, True))
    asyncio.run(device.set_output(1, False))
    assert client.writes == [(10040, True, 7), (10040, False, 7)]


def test_write_error_is_not_applied():
    client = Client()
    client.error = True
    device = C2000SP4(client, 1)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(20, 1)))
    with pytest.raises(ModbusException):
        asyncio.run(device.set_output(1, True))
    assert device.attr_out1["state"] is None


def test_multistate_expanded_and_unknown_codes_preserved():
    device = C2000SP4(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))
    state = asyncio.run(device.async_get_snapshot())["state_sensors"]["actuator_state"]
    assert state["state"] == "actuator_working_position"
    assert state["expanded_codes"][:4] == (54, 149, 198, 999)
    assert state["expanded_states"][-1] == "unknown_999"


def test_communication_failure_is_not_normal():
    client = Client()
    client.error = True
    device = C2000SP4(client, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))
    with pytest.raises(ModbusException):
        asyncio.run(device.async_get_snapshot())


def test_service_metadata_is_not_invented_and_passport_is_exposed():
    device = C2000SP4(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(20, 1), variant="sp4_220_01"))
    info = asyncio.run(device.get_device_info())
    assert info["serial_number"] is None
    assert info["hardware_version"] is None
    assert info["software_version"] is None
    assert device.attr_device_metadata["nominal_power"] == "230 V AC ±10%"
    assert device.attr_device_metadata["integrated_dpls_isolator"] is True


def test_optimistic_lifecycle_keeps_existing_generation_protection():
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.data = {"outputs": {1: {"state": False}}}
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}
    coordinator.async_set_updated_data = lambda data: None
    coordinator.async_apply_optimistic_write(("outputs", 1, "state"), True)
    stale = {"outputs": {1: {"state": False}}}
    coordinator._reconcile_pending_writes(stale, 0)
    assert stale["outputs"][1]["state"] is True


def test_manual_and_automatic_resolution_are_equivalent():
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(2, 10, 20, 0, 1), S2000PPZoneRow(3, 10, 30, 0, 1)),
        relays=(S2000PPRelayRow(1, 10, 20), S2000PPRelayRow(4, 10, 30)),
        partitions=(), unparsed_registers=(),
    )
    class Reader:
        async def async_read(self):
            return configuration
    automatic = asyncio.run(AutomaticDeviceMappingProvider(
        Reader(), S2000PPConfigurationCache()
    ).async_resolve(
        gateway(), "C2000SP4", 10,
        dpls=DPLSSubIdentity(20, 5),
        metadata=DownstreamDeviceMetadata("sp4_24"),
    ))
    manual = mapping(manual_relay_mapping(20, 1), manual_zone_mapping(20, 2, 1, 0, None))
    assert automatic.objects == manual.objects
    assert automatic.identity == manual.identity
