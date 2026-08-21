"""Tests for the classic C2000-KDL parent equipment model."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import C2000KDL
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.mapping import (
    AutomaticDeviceMappingProvider,
    DeviceMappingNotFoundError,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPConfigurationCache,
    S2000PPRelayRow,
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
)


class Response:
    def __init__(self, *, registers=None, error=False, function_code=None):
        self.registers = registers
        self._error = error
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self, primary=215, expanded=None, failure=None):
        self.primary = primary
        self.expanded = expanded or [215, 217, 198, 149, 203, 135, 999]
        self.failure = failure

    async def read_holding_registers(self, *, address, count, device_id):
        if self.failure == "empty":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "truncated":
            return Response(registers=[])
        return Response(registers=[self.primary] * count, function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        values = (self.expanded + [0] * count)[:count]
        return Response(registers=values, function_code=4)


def gateway(name="pp-a", connection="serial:COM1"):
    return GatewayContext(GatewayType.S2000_PP, name, connection, 1)


def mapping(*objects, kdl=10, gateway_context=None, dpls=None):
    return ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=gateway_context or gateway(),
            model="C2000KDL",
            orion_address=kdl,
            dpls=dpls,
        ),
        source=MappingSource.MANUAL,
        objects=objects,
    )


def configured_device(client=None, **mapping_options):
    device = C2000KDL(client or Client(), 1)
    device.apply_gateway_mapping(
        mapping(manual_zone_mapping(0, 5, 3, 0, None), **mapping_options)
    )
    return device


def test_identity_is_gateway_plus_orion_without_dpls():
    device = configured_device(kdl=10)
    identity = device.attr_gateway_mapping.identity

    assert identity.dpls is None
    assert identity.stable_id == f"{gateway().stable_id}:orion:10"
    assert device.attr_device_identifier == identity.stable_id
    assert device.attr_unique_id_prefix == identity.stable_id


def test_two_kdl_on_one_pp_and_same_address_on_different_pp_are_distinct():
    first = mapping(manual_zone_mapping(0, 1, 3, 0, None), kdl=10)
    second = mapping(manual_zone_mapping(0, 2, 3, 0, None), kdl=20)
    third = mapping(
        manual_zone_mapping(0, 3, 3, 0, None),
        kdl=10,
        gateway_context=gateway("pp-b", "tcp:192.0.2.2:502"),
    )

    assert len({item.identity.stable_id for item in (first, second, third)}) == 3


def test_exact_type_three_local_zero_mapping_and_metadata():
    device = configured_device()

    assert len(device.get_gateway_capabilities()) == 1
    assert device.attr_platforms == [Platform.SENSOR]
    assert device.attr_device_metadata["orion_address"] == 10
    assert device.attr_device_metadata["maximum_dpls_addresses"] == 127
    description = device.get_state_sensor_descriptions()[0]
    assert description["entity_category"] is EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    "object_mapping",
    [
        manual_zone_mapping(0, 1, 1, 0, None),
        manual_zone_mapping(0, 1, 2, 0, None),
        manual_zone_mapping(0, 1, 6, 0, None),
        manual_zone_mapping(0, 1, 7, 0, None),
        manual_zone_mapping(20, 1, 3, 0, None),
        manual_relay_mapping(20, 1),
    ],
)
def test_downstream_and_arbitrary_same_orion_rows_are_rejected(object_mapping):
    with pytest.raises(ValueError, match="zone type 3, local object 0"):
        C2000KDL(Client(), 1).apply_gateway_mapping(mapping(object_mapping))


def test_dpls_subidentity_is_rejected_for_parent_kdl():
    with pytest.raises(ValueError, match="must not contain"):
        C2000KDL(Client(), 1).apply_gateway_mapping(
            mapping(
                manual_zone_mapping(0, 1, 3, 0, None),
                dpls=DPLSSubIdentity(20, 1),
            )
        )


def test_primary_expanded_raw_and_unknown_states_are_lossless():
    state = asyncio.run(configured_device().async_get_snapshot())["state_sensors"][
        "device_state"
    ]

    assert state["state"] == "dpls_short_circuit"
    assert state["primary_code"] == 215
    assert state["expanded_codes"][:7] == (215, 217, 198, 149, 203, 135, 999)
    assert state["expanded_states"] == (
        "dpls_short_circuit",
        "dpls_branch_communication_lost",
        "power_fault",
        "enclosure_tamper",
        "device_restarted",
        "automatic_test_failed",
        "unknown_999",
    )


def test_unknown_primary_state_is_preserved():
    state = asyncio.run(
        configured_device(Client(primary=777, expanded=[777])).async_get_snapshot()
    )["state_sensors"]["device_state"]

    assert state["state"] == "unknown_777"
    assert state["primary_code"] == 777


@pytest.mark.parametrize("failure", ["empty", "error", "truncated"])
def test_communication_failure_is_not_a_normal_state(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured_device(Client(failure=failure)).async_get_snapshot())


def test_missing_required_mapping_is_rejected():
    with pytest.raises(ValueError, match="requires zone type 3"):
        asyncio.run(C2000KDL(Client(), 1).data_init())


def test_manual_and_automatic_mapping_are_equivalent_and_filter_downstream_rows():
    configuration = S2000PPConfiguration(
        zones=(
            S2000PPZoneRow(5, 10, 0, 0, 3),
            S2000PPZoneRow(6, 10, 20, 0, 1),
            S2000PPZoneRow(7, 10, 21, 0, 2),
            S2000PPZoneRow(8, 10, 22, 0, 6),
            S2000PPZoneRow(9, 10, 23, 0, 7),
        ),
        relays=(S2000PPRelayRow(4, 10, 20),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    automatic = asyncio.run(
        AutomaticDeviceMappingProvider(
            Reader(), S2000PPConfigurationCache()
        ).async_resolve(
            gateway(),
            "C2000KDL",
            10,
            capabilities=C2000KDL.get_gateway_capabilities(),
        )
    )
    manual = mapping(manual_zone_mapping(0, 5, 3, 0, None))

    assert automatic.objects == manual.objects
    assert automatic.identity == manual.identity
    assert len(automatic.objects) == 1


def test_automatic_mapping_requires_the_device_level_row():
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(6, 10, 20, 0, 1),),
        relays=(S2000PPRelayRow(4, 10, 20),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    with pytest.raises(DeviceMappingNotFoundError):
        asyncio.run(
            AutomaticDeviceMappingProvider(
                Reader(), S2000PPConfigurationCache()
            ).async_resolve(
                gateway(),
                "C2000KDL",
                10,
                capabilities=C2000KDL.get_gateway_capabilities(),
            )
        )


def test_no_service_metadata_or_control_platforms_are_invented():
    device = configured_device()
    info = asyncio.run(device.get_device_info())

    assert info == {
        "device_type": None,
        "serial_number": None,
        "hardware_version": None,
        "software_version": None,
    }
    assert Platform.SWITCH not in device.attr_platforms
    assert Platform.BUTTON not in device.attr_platforms
    assert not hasattr(device, "set_output")


@pytest.mark.parametrize(
    ("model", "base", "count"),
    [("C2000SP4", 20, 5), ("C2000VT", 30, 2), ("C2000VTI", 40, 3)],
)
def test_existing_dpls_stable_id_contract_is_unchanged(model, base, count):
    identity = DownstreamDeviceIdentity(
        gateway=gateway(),
        model=model,
        orion_address=10,
        dpls=DPLSSubIdentity(base, count),
    )

    assert identity.stable_id == f"{gateway().stable_id}:orion:10:dpls:{base}"
    assert DownstreamDeviceIdentity.from_dict(identity.to_dict()) == identity
