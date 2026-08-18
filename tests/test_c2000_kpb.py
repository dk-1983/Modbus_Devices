"""Tests for the gateway-dependent C2000-KPB equipment model."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.coordinator import ModbusDeviceCoordinator
from custom_components.modbus_devices.equipment.bolid import C2000KPB
from custom_components.modbus_devices.gateway import (
    CapabilityRequirement,
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


def gateway(name: str = "gateway-a") -> GatewayContext:
    return GatewayContext(
        gateway_type=GatewayType.S2000_PP,
        gateway_id=name,
        connection_key="serial:COM1",
        modbus_unit_id=1,
    )


def mapping(*objects, orion_address: int = 10) -> ResolvedDeviceMapping:
    return ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=gateway(),
            model="C2000KPB",
            orion_address=orion_address,
        ),
        source=MappingSource.MANUAL,
        objects=tuple(objects),
    )


class Response:
    def __init__(self, *, bits=None, registers=None, error: bool = False) -> None:
        self.bits = bits
        self.registers = registers
        self._error = error

    def isError(self) -> bool:
        return self._error


class Client:
    def __init__(self) -> None:
        self.coil_reads: list[tuple[int, int, int]] = []
        self.writes: list[tuple[int, bool, int]] = []
        self.write_error = False
        self.read_error = False

    async def read_coils(self, address: int, count: int, device_id: int):
        self.coil_reads.append((address, count, device_id))
        return Response(bits=[True] * count, error=self.read_error)

    async def read_holding_registers(self, address: int, count: int, device_id: int):
        return Response(registers=[121] * count, error=self.read_error)

    async def read_input_registers(self, address: int, count: int, device_id: int):
        registers = []
        for _ in range(count // 16):
            registers.extend([121, 122, 123] + [0] * 13)
        return Response(registers=registers, error=self.read_error)

    async def write_coil(self, address: int, value: bool, device_id: int):
        self.writes.append((address, value, device_id))
        return Response(error=self.write_error)


def test_rejects_missing_mapping_before_io() -> None:
    device = C2000KPB(Client(), 1)

    with pytest.raises(ValueError, match="requires a validated"):
        asyncio.run(device.data_init())


def test_maps_all_six_outputs_to_resolved_coils() -> None:
    device = C2000KPB(Client(), 1)
    device.apply_gateway_mapping(
        mapping(*(manual_relay_mapping(number, number + 40) for number in range(1, 7)))
    )

    assert [item["address"] for item in device.get_output_descriptions()] == list(
        range(10040, 10046)
    )


def test_partial_configured_subset_is_valid_and_does_not_invent_entities() -> None:
    device = C2000KPB(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(3, 41)))

    assert [item["out_number"] for item in device.get_output_descriptions()] == [3]


def test_every_physical_capability_is_optional_in_one_gateway_configuration() -> None:
    """Missing table rows do not imply missing physical model capabilities."""
    assert len(C2000KPB.get_gateway_capabilities()) == 15
    assert {
        item.requirement for item in C2000KPB.get_gateway_capabilities()
    } == {CapabilityRequirement.OPTIONAL_IF_CONFIGURED}


def test_two_devices_on_one_gateway_have_distinct_identity() -> None:
    first = mapping(manual_relay_mapping(1, 1), orion_address=10)
    second = mapping(manual_relay_mapping(1, 2), orion_address=20)

    assert first.identity.stable_id != second.identity.stable_id


def test_duplicate_local_relay_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate local object"):
        mapping(manual_relay_mapping(1, 1), manual_relay_mapping(1, 2))


def test_unknown_local_relay_is_rejected_by_model() -> None:
    device = C2000KPB(Client(), 1)

    with pytest.raises(ValueError, match="unsupported"):
        device.apply_gateway_mapping(mapping(manual_relay_mapping(7, 1)))


def test_correct_resolved_coil_is_used_for_read_and_write() -> None:
    client = Client()
    device = C2000KPB(client, 7)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(2, 41)))

    output = asyncio.run(device.get_output(2))
    assert output["state"] is True
    assert client.coil_reads == [(10040, 1, 7)]

    asyncio.run(device.set_output(2, False))
    assert client.writes == [(10040, False, 7)]


def test_write_error_is_not_optimistically_applied() -> None:
    client = Client()
    client.write_error = True
    device = C2000KPB(client, 1)
    device.apply_gateway_mapping(mapping(manual_relay_mapping(1, 1)))

    with pytest.raises(ModbusException, match="Modbus error response"):
        asyncio.run(device.set_output(1, True))
    assert device.attr_out1["state"] is None


def test_optimistic_write_generation_protects_against_stale_poll() -> None:
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.data = {"outputs": {1: {"state": False}}}
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}
    published = []
    coordinator.async_set_updated_data = published.append

    coordinator.async_apply_optimistic_write(("outputs", 1, "state"), True)
    stale = {"outputs": {1: {"state": False}}}
    coordinator._reconcile_pending_writes(stale, update_generation=0)

    assert published[-1]["outputs"][1]["state"] is True
    assert stale["outputs"][1]["state"] is True


def test_circuit_and_technological_input_mappings_can_share_local_number() -> None:
    circuit = manual_zone_mapping(1, 11, 2, 0, None)
    technological_input = manual_zone_mapping(1, 12, 1, 0, None)
    device = C2000KPB(Client(), 1)

    device.apply_gateway_mapping(mapping(circuit, technological_input))

    assert [item["sensor_id"] for item in device.get_state_sensor_descriptions()] == [
        "output_1_circuit",
        "technological_input_1",
    ]


def test_wrong_zone_type_and_unknown_local_zone_are_rejected() -> None:
    device = C2000KPB(Client(), 1)

    with pytest.raises(ValueError, match="unsupported"):
        device.apply_gateway_mapping(mapping(manual_zone_mapping(3, 1, 1, 0, None)))


def test_multistate_snapshot_preserves_raw_codes() -> None:
    device = C2000KPB(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(1, 1, 2, 0, None)))

    snapshot = asyncio.run(device.async_get_snapshot())
    state = snapshot["state_sensors"]["output_1_circuit"]

    assert state["state"] == "output_open_circuit"
    assert state["primary_code"] == 121
    assert state["expanded_codes"] == (121, 122, 123, *([0] * 13))
    assert state["expanded_states"] == (
        "output_open_circuit",
        "output_short_circuit",
        "output_circuit_restored",
    )


def test_communication_error_does_not_become_normal() -> None:
    client = Client()
    client.read_error = True
    device = C2000KPB(client, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(0, 1, 3, 0, None)))

    with pytest.raises(ModbusException, match="Modbus error response"):
        asyncio.run(device.async_get_snapshot())


def test_device_info_does_not_invent_service_values() -> None:
    device = C2000KPB(Client(), 1)

    info = asyncio.run(device.get_device_info())

    assert info["serial_number"] is None
    assert info["hardware_version"] is None
    assert info["software_version"] is None


def test_manual_capability_mapping_uses_gateway_derived_addresses() -> None:
    relay = manual_relay_mapping(6, 41)
    circuit = manual_zone_mapping(6, 101, 2, 0, None)

    assert relay.modbus_address == 10040
    assert circuit.modbus_address == 40100
    assert circuit.zone_details.expanded_state_address == 5696


def test_automatic_and_manual_candidates_are_equivalent() -> None:
    """Both sources converge on the same resolved runtime objects."""
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(101, 10, 6, 0, 2),),
        relays=(S2000PPRelayRow(41, 10, 6),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    provider = AutomaticDeviceMappingProvider(
        Reader(),
        S2000PPConfigurationCache(),
    )
    automatic = asyncio.run(provider.async_resolve(gateway(), "C2000KPB", 10))
    manual = mapping(
        manual_relay_mapping(6, 41),
        manual_zone_mapping(6, 101, 2, 0, None),
    )

    assert automatic.objects == manual.objects
