"""Tests for С2000Р-РМ and the shared DPLS output mechanics."""

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.equipment.bolid import (
    BolidDPLSOutputBase,
    C2000RRM,
)
from custom_components.modbus_devices.equipment.equipment import get_gateway_capabilities
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    manual_relay_mapping,
    manual_zone_mapping,
)


class Response:
    def __init__(self, *, bits=None, registers=None, error=False, address=None, value=None):
        self.bits = bits
        self.registers = registers
        self.address = address
        self.value = value
        self._error = error

    def isError(self):
        return self._error


class Client:
    def __init__(self):
        self.writes = []
        self.fail_write = False

    async def read_coils(self, *, address, count, device_id):
        return Response(bits=[False, True][:count])

    async def read_holding_registers(self, *, address, count, device_id):
        return Response(registers=[79] * count)

    async def read_input_registers(self, *, address, count, device_id):
        return Response(registers=([79, 80] + [0] * 14)[:count])

    async def write_coil(self, *, address, value, device_id):
        self.writes.append((address, value, device_id))
        return Response(error=self.fail_write, address=address, value=value)


def mapping(*objects, variant="standard", topology="outputs_only", base=20):
    count = 3 if topology == "outputs_and_input" else 2
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            "C2000RRM",
            10,
            DPLSSubIdentity(base, count),
            DownstreamDeviceMetadata(variant=variant, topology=topology),
        ),
        MappingSource.MANUAL,
        objects,
    )


def relay_objects(base=20):
    return (manual_relay_mapping(base, 100), manual_relay_mapping(base + 1, 101))


def test_base_is_not_discoverable_equipment_and_variants_are_typed():
    with pytest.raises(TypeError):
        BolidDPLSOutputBase(None, 1)
    assert C2000RRM.get_variant_options() == {
        "standard": "С2000Р-РМ",
        "isp_01": "С2000Р-РМ исп.01",
    }


def test_configured_topology_exposes_only_its_exact_capabilities():
    outputs_only = get_gateway_capabilities(
        "Bolid", "C2000RRM",
        DownstreamDeviceMetadata(variant="standard", topology="outputs_only"),
    )
    with_input = get_gateway_capabilities(
        "Bolid", "C2000RRM",
        DownstreamDeviceMetadata(variant="standard", topology="outputs_and_input"),
    )
    assert [item.key for item in outputs_only] == ["relay_1", "relay_2"]
    assert [item.key for item in with_input] == [
        "relay_1", "relay_2", "controlled_circuit"
    ]


@pytest.mark.parametrize("variant", ["standard", "isp_01"])
def test_two_output_topology_and_identity(variant):
    device = C2000RRM(Client(), 1)
    device.apply_gateway_mapping(mapping(*relay_objects(), variant=variant))
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(20, 2)
    assert len(device.get_output_descriptions()) == 2
    assert device.attr_serial_number is None
    assert device.attr_software_version is None


def test_standard_controlled_circuit_is_third_address_zone_type_one():
    device = C2000RRM(Client(), 1)
    device.apply_gateway_mapping(mapping(
        *relay_objects(), manual_zone_mapping(22, 5, 1, 0, None),
        topology="outputs_and_input",
    ))
    assert device.attr_gateway_mapping.identity.dpls.address_count == 3
    assert device.get_state_sensor_descriptions()[0]["name"] == "Controlled circuit state"


def test_isp01_rejects_controlled_circuit_and_wrong_neighbors():
    with pytest.raises(ValueError):
        C2000RRM(Client(), 1).apply_gateway_mapping(mapping(
            *relay_objects(), manual_zone_mapping(22, 5, 1, 0, None),
            variant="isp_01", topology="outputs_and_input",
        ))
    with pytest.raises(ValueError):
        C2000RRM(Client(), 1).apply_gateway_mapping(mapping(
            manual_relay_mapping(20, 100), manual_relay_mapping(22, 101)
        ))


def test_grouped_read_and_independent_validated_fc05_write():
    client = Client()
    device = C2000RRM(client, 7)
    device.apply_gateway_mapping(mapping(*relay_objects()))
    snapshot = asyncio.run(device.async_get_snapshot())
    assert snapshot["outputs"][1]["state"] is False
    assert snapshot["outputs"][2]["state"] is True
    asyncio.run(device.set_output(2, True))
    assert client.writes == [(10100, True, 7)]
    assert device.get_output_descriptions()[0]["state"] is False


def test_failed_or_invalid_write_never_patches_output():
    client = Client()
    device = C2000RRM(client, 1)
    device.apply_gateway_mapping(mapping(*relay_objects()))
    client.fail_write = True
    with pytest.raises(ModbusException):
        asyncio.run(device.set_output(1, True))
    assert device.get_output_descriptions()[0]["state"] is None
