"""Tests for the radio glass-break detector С2000Р-СТ исп.01."""

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.equipment.bolid import C2000RST01
from custom_components.modbus_devices.equipment.equipment import get_classes_from_files
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
    def __init__(self, registers=None, error=False):
        self.registers, self._error = registers, error

    def isError(self):
        return self._error


class Client:
    def __init__(self, failure=None):
        self.failure = failure

    async def read_holding_registers(self, **kwargs):
        if self.failure == "empty": return None
        if self.failure == "invalid": return object()
        if self.failure == "truncated": return Response([])
        if self.failure == "error": return Response(error=True)
        return Response([3])

    async def read_input_registers(self, **kwargs):
        return Response([3, 149, 211, 187, 999] + [0] * 11)


def mapping(*objects, base=30, kdl=10, connection="tcp:pp"):
    return ResolvedDeviceMapping(DownstreamDeviceIdentity(
        GatewayContext(GatewayType.S2000_PP, "pp", connection, 1),
        "C2000RST01", kdl, DPLSSubIdentity(base, 1), DownstreamDeviceMetadata(),
    ), MappingSource.MANUAL, objects)


def test_registration_identity_model_and_metadata():
    device = C2000RST01(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 1, 1, 0, None)))
    assert "C2000RST01" in get_classes_from_files()["Bolid"]
    assert device.attr_model_name == "С2000Р-СТ исп.01"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(30, 1)
    assert "arr" not in device.attr_device_identifier.lower()
    assert device.attr_device_metadata["supported_kdl_input_types"] == (5,)
    assert device.attr_software_version is None


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    row = S2000PPZoneRow(1, 10, 30, 0, 1)
    assert resolve_zone_row(row, None) == manual_zone_mapping(30, 1, 1, 0, None)


@pytest.mark.parametrize("wrong", [
    manual_zone_mapping(31, 1, 1, 0, None),
    manual_zone_mapping(0, 1, 3, 0, None),
    manual_zone_mapping(30, 1, 6, 0, None),
    manual_relay_mapping(30, 1),
])
def test_exact_own_zone_only(wrong):
    with pytest.raises(ValueError):
        C2000RST01(Client(), 1).apply_gateway_mapping(mapping(wrong))


def test_multistate_raw_expanded_and_unknown_codes():
    device = C2000RST01(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 1, 1, 0, None)))
    value = asyncio.run(device.async_get_snapshot())["state_sensors"]["glass_break_state"]
    assert value["state"] == "intrusion_alarm"
    assert value["primary_code"] == 3
    assert value["expanded_states"][-1] == "unknown_999"
    assert device.get_state_sensor_descriptions()[0].get("entity_category") is None
    assert not hasattr(device, "get_numeric_sensor_descriptions")


@pytest.mark.parametrize("failure", ["empty", "invalid", "truncated", "error"])
def test_communication_failures_are_not_normal(failure):
    device = C2000RST01(Client(failure), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 1, 1, 0, None)))
    with pytest.raises((ModbusException, ValueError)):
        asyncio.run(device.async_get_snapshot())
