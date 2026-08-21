"""Tests for the wired С2000-ДЗ water-leak detector."""

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.equipment.bolid import C2000DZ
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    manual_relay_mapping, manual_zone_mapping,
)


class Response:
    def __init__(self, *, registers=None, error=False, function_code=None):
        self.registers = registers
        self._error = error
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self, primary=79, expanded=None, failure=None):
        self.primary = primary
        self.expanded = expanded or [79, 80, 999]
        self.failure = failure

    async def read_holding_registers(self, *, address, count, device_id):
        if self.failure == "empty":
            return None
        if self.failure == "invalid":
            return object()
        if self.failure == "truncated":
            return Response(registers=[])
        if self.failure == "error":
            return Response(error=True)
        return Response(registers=[self.primary] * count, function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        return Response(
            registers=(self.expanded + [0] * count)[:count], function_code=4
        )


def mapping(*objects, base=30, variant="v1_13"):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            "C2000DZ", 10, DPLSSubIdentity(base, 1),
            DownstreamDeviceMetadata(variant=variant),
        ), MappingSource.MANUAL, objects,
    )


@pytest.mark.parametrize("variant", ["v1_06", "v1_10", "v1_13"])
def test_variants_share_one_address_protocol_and_keep_static_metadata(variant):
    device = C2000DZ(Client(), 1)
    device.apply_gateway_mapping(mapping(
        manual_zone_mapping(30, 4, 1, 0, None), variant=variant
    ))
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(30, 1)
    assert device.attr_device_metadata["supported_kdl_input_types"] == (6, 17)
    assert device.attr_device_metadata["documented_classic_kdl_minimum"] == "2.10"
    assert device.attr_hardware_version is None
    assert device.attr_software_version is None


@pytest.mark.parametrize("wrong", [
    manual_zone_mapping(31, 4, 1, 0, None),
    manual_zone_mapping(30, 4, 6, 0, None),
    manual_zone_mapping(0, 4, 3, 0, None),
    manual_relay_mapping(30, 4),
])
def test_exact_zone_type_one_ownership(wrong):
    with pytest.raises(ValueError):
        C2000DZ(Client(), 1).apply_gateway_mapping(mapping(wrong))


def test_water_alarm_restore_raw_and_unknown_states():
    device = C2000DZ(Client(primary=79, expanded=[79, 80, 999]), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 4, 1, 0, None)))
    value = asyncio.run(device.async_get_snapshot())["state_sensors"]["water_leak_state"]
    assert value["state"] == "water_alarm"
    assert value["primary_code"] == 79
    assert value["expanded_codes"][:3] == (79, 80, 999)
    assert value["expanded_states"][:3] == (
        "water_alarm", "water_alarm_restored", "unknown_999"
    )


@pytest.mark.parametrize("failure", ["empty", "invalid", "truncated", "error"])
def test_communication_and_payload_failures_are_not_normal(failure):
    device = C2000DZ(Client(failure=failure), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 4, 1, 0, None)))
    with pytest.raises((ModbusException, ValueError)):
        asyncio.run(device.async_get_snapshot())


def test_only_operational_multistate_entity_is_exposed():
    device = C2000DZ(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 4, 1, 0, None)))
    assert device.get_state_sensor_descriptions() == [{
        "sensor_id": "water_leak_state", "name": "Water leak state",
        "device_class": None, "icon": "mdi:water-alert",
    }]
    assert not hasattr(device, "get_output_descriptions")
    assert not hasattr(device, "get_numeric_sensor_descriptions")
