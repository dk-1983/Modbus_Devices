"""Tests for the independent С2000Р-Сирена light and sound outputs."""

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.equipment.bolid import C2000RSirena
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    manual_relay_mapping, manual_zone_mapping,
)


class Response:
    def __init__(self, *, bits=None, error=False, address=None, value=None):
        self.bits = bits
        self._error = error
        self.address = address
        self.value = value

    def isError(self):
        return self._error


class Client:
    def __init__(self):
        self.writes = []

    async def read_coils(self, *, address, count, device_id):
        return Response(bits=[True, False][:count])

    async def write_coil(self, *, address, value, device_id):
        self.writes.append((address, value))
        return Response(address=address, value=value)


def mapping(*objects, base=40, count=2, kdl=10, connection="tcp:a"):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", connection, 1),
            "C2000RSirena", kdl, DPLSSubIdentity(base, count),
            DownstreamDeviceMetadata(),
        ), MappingSource.MANUAL, objects,
    )


def test_exact_two_address_light_sound_topology():
    device = C2000RSirena(Client(), 1)
    device.apply_gateway_mapping(mapping(
        manual_relay_mapping(40, 200), manual_relay_mapping(41, 201)
    ))
    outputs = device.get_output_descriptions()
    assert [item["out_number_view"] for item in outputs] == ["Light", "Sound"]
    assert device.attr_gateway_mapping.identity.dpls.address_count == 2
    assert device.attr_model_name == "С2000Р-Сирена"


@pytest.mark.parametrize("bad", [
    (manual_relay_mapping(40, 200), manual_relay_mapping(42, 201)),
    (manual_relay_mapping(40, 200), manual_zone_mapping(41, 2, 1, 0, None)),
])
def test_neighbor_and_zone_rows_are_rejected(bad):
    with pytest.raises(ValueError):
        C2000RSirena(Client(), 1).apply_gateway_mapping(mapping(*bad))


def test_light_and_sound_are_read_and_written_independently():
    client = Client()
    device = C2000RSirena(client, 1)
    device.apply_gateway_mapping(mapping(
        manual_relay_mapping(40, 200), manual_relay_mapping(41, 201)
    ))
    snapshot = asyncio.run(device.async_get_snapshot())
    assert snapshot["outputs"][1]["state"] is True
    assert snapshot["outputs"][2]["state"] is False
    asyncio.run(device.set_output(2, True))
    asyncio.run(device.set_output(1, False))
    assert client.writes == [(10200, True), (10199, False)]


def test_missing_and_invalid_fc05_responses_fail():
    class EmptyClient(Client):
        async def write_coil(self, **kwargs):
            return None

    device = C2000RSirena(EmptyClient(), 1)
    device.apply_gateway_mapping(mapping(
        manual_relay_mapping(40, 200), manual_relay_mapping(41, 201)
    ))
    with pytest.raises(ModbusException):
        asyncio.run(device.set_output(1, True))


def test_identity_does_not_require_arr125_or_radio_id():
    identities = {
        mapping(
            manual_relay_mapping(40, 200), manual_relay_mapping(41, 201),
            kdl=kdl, connection=connection,
        ).identity.stable_id
        for kdl, connection in ((10, "tcp:a"), (11, "tcp:a"), (10, "tcp:b"))
    }
    assert len(identities) == 3
