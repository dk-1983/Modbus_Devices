"""Tests for MIP-24 isp.20 behind an S2000-PP gateway."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import MIP24Isp20
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
from custom_components.modbus_devices.gateway import (
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
    def __init__(self, primary=None, expanded=None, failure=None):
        self.primary = primary or [39, 193, 195, 200, 197, 1]
        self.expanded = expanded or [149, 152, 203, 61, 62, 0]
        self.failure = failure
        self.holding_calls = []
        self.input_calls = []

    async def read_holding_registers(self, *, address, count, device_id):
        self.holding_calls.append((address, count, device_id))
        if self.failure == "none":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "invalid":
            return object()
        values = self.primary[:count]
        if self.failure == "truncated":
            values = values[:-1]
        return Response(values, function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        self.input_calls.append((address, count, device_id))
        if self.failure == "expanded_none":
            return None
        block_count = count // 16
        values = []
        for index in range(block_count):
            values.extend([self.expanded[index], *([0] * 15)])
        return Response(values, function_code=4)


def gateway(name="pp-a", connection="serial:COM1"):
    return GatewayContext(GatewayType.S2000_PP, name, connection, 1)


def identity(orion=12, gateway_context=None, dpls=None):
    return DownstreamDeviceIdentity(
        gateway=gateway_context or gateway(),
        model="MIP24Isp20",
        orion_address=orion,
        dpls=dpls,
    )


def mapping(*objects, **identity_options):
    return ResolvedDeviceMapping(
        identity=identity(**identity_options),
        source=MappingSource.MANUAL,
        objects=objects,
    )


def all_objects():
    return tuple(
        manual_zone_mapping(local, local + 1, 3 if local == 0 else 1, 0, None)
        for local in range(6)
    )


def configured(client=None, objects=None):
    device = MIP24Isp20(client or Client(), 1)
    device.apply_gateway_mapping(mapping(*(objects or all_objects())))
    return device


def test_registration_model_and_static_metadata():
    assert get_equipment_classes_by_manufacturer()["Bolid"].count("MIP24Isp20") == 1
    device = MIP24Isp20(None, 1)
    assert device.attr_model_name == "МИП-24 исп.20"
    assert device.full_designation == "МИП-24-2/П5-Р-RS"
    assert device.documented_target_firmware == "5.10"
    assert device.attr_software_version is None


def test_direct_orion_identity_is_stable_and_has_no_dpls():
    first = mapping(*all_objects(), orion=12)
    second = mapping(*all_objects(), orion=13)
    third = mapping(
        *all_objects(),
        orion=12,
        gateway_context=gateway("pp-b", "tcp:192.0.2.2:502"),
    )
    assert first.identity.dpls is None
    assert len({item.identity.stable_id for item in (first, second, third)}) == 3
    device = configured()
    assert device.attr_device_identifier == mapping(*all_objects()).identity.stable_id


def test_dpls_identity_is_rejected():
    with pytest.raises(ValueError, match="must not contain DPLS"):
        configured(objects=(manual_zone_mapping(0, 1, 3, 0, None),)).apply_gateway_mapping(
            mapping(
                manual_zone_mapping(0, 1, 3, 0, None),
                dpls=DPLSSubIdentity(1, 1),
            )
        )


def test_six_exact_capabilities_required_optional_and_categories():
    capabilities = MIP24Isp20.get_gateway_capabilities()
    assert [(item.local_object_number, item.zone_type) for item in capabilities] == [
        (0, 3), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1)
    ]
    descriptions = {item["sensor_id"]: item for item in configured().get_state_sensor_descriptions()}
    assert configured().attr_platforms == [Platform.SENSOR]
    assert descriptions["device_state"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert descriptions["charger_state"]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert descriptions["mains_state"]["entity_category"] is None


def test_partial_optional_subset_creates_only_mapped_entities():
    device = configured(objects=(
        manual_zone_mapping(0, 1, 3, 0, None),
        manual_zone_mapping(3, 4, 1, 0, None),
        manual_zone_mapping(5, 6, 1, 0, None),
    ))
    assert [item["sensor_id"] for item in device.get_state_sensor_descriptions()] == [
        "device_state", "battery_state", "mains_state"
    ]


@pytest.mark.parametrize("bad_object", [
    manual_zone_mapping(6, 7, 1, 0, None),
    manual_zone_mapping(0, 2, 1, 0, None),
    manual_zone_mapping(1, 2, 3, 0, None),
    manual_zone_mapping(1, 2, 6, 0, None),
    manual_zone_mapping(1, 2, 8, 0, None),
    manual_zone_mapping(1, 2, 7, 0, None),
    manual_relay_mapping(1, 1),
])
def test_unsupported_local_type_relay_numeric_and_counter_are_rejected(bad_object):
    with pytest.raises(ValueError, match="unsupported MIP"):
        configured(objects=(manual_zone_mapping(0, 1, 3, 0, None), bad_object))


def test_missing_required_and_duplicate_mapping_are_errors():
    with pytest.raises(ValueError, match="requires zone type 3"):
        configured(objects=(manual_zone_mapping(1, 2, 1, 0, None),))
    with pytest.raises(ValueError, match="Duplicate"):
        configured(objects=(
            manual_zone_mapping(0, 1, 3, 0, None),
            manual_zone_mapping(0, 2, 3, 0, None),
        ))


def test_grouped_atomic_polling_and_independent_states():
    client = Client()
    snapshot = asyncio.run(configured(client).async_get_snapshot())["state_sensors"]
    assert len(client.holding_calls) == 1
    assert len(client.input_calls) == 1
    assert snapshot["device_state"]["state"] == "equipment_normal"
    assert snapshot["output_power_state"]["state"] == "output_voltage_connected"
    assert snapshot["mains_state"]["state"] == "mains_restored"
    assert snapshot["device_state"]["expanded_states"] == ("enclosure_tamper",)
    assert snapshot["charger_state"]["primary_code"] == 197


@pytest.mark.parametrize("code, name", [
    (1, "mains_restored"), (2, "mains_fault"),
    (61, "configuration_reset"), (62, "configuration_changed"),
    (149, "enclosure_tamper"), (152, "enclosure_tamper_restored"),
    (186, "battery_replacement_required"),
    (192, "output_voltage_disconnected"), (193, "output_voltage_connected"),
    (194, "power_overload"), (195, "power_overload_restored"),
    (196, "charger_fault"), (197, "charger_restored"),
    (198, "power_fault"), (199, "power_restored"),
    (200, "battery_restored"), (202, "battery_fault"),
    (203, "device_restarted"), (205, "battery_test_failed"),
    (211, "battery_low"), (250, "device_communication_lost"),
    (251, "device_communication_restored"), (999, "unknown_999"),
])
def test_common_state_codes(code, name):
    assert MIP24Isp20._state_name(code) == name


@pytest.mark.parametrize("failure", ["none", "error", "invalid", "truncated", "expanded_none"])
def test_invalid_and_communication_responses_are_not_normal(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured(Client(failure=failure)).async_get_snapshot())


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    configuration = S2000PPConfiguration(
        zones=tuple(
            S2000PPZoneRow(local + 1, 12, local, 0, 3 if local == 0 else 1)
            for local in range(6)
        ) + (
            S2000PPZoneRow(20, 12, 7, 0, 1),
            S2000PPZoneRow(21, 12, 1, 0, 8),
            S2000PPZoneRow(22, 13, 0, 0, 3),
        ),
        relays=(S2000PPRelayRow(1, 12, 1),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    automatic = asyncio.run(AutomaticDeviceMappingProvider(
        Reader(), S2000PPConfigurationCache()
    ).async_resolve(
        gateway(), "MIP24Isp20", 12,
        capabilities=MIP24Isp20.get_gateway_capabilities(),
    ))
    assert automatic.objects == mapping(*all_objects()).objects


def test_no_numeric_outputs_controls_or_invented_service_metadata():
    device = configured()
    assert not hasattr(device, "get_numeric_sensor_descriptions")
    assert not hasattr(device, "get_output_descriptions")
    assert device.attr_platforms == [Platform.SENSOR]
    assert asyncio.run(device.get_device_info()) == {
        "device_type": None,
        "serial_number": None,
        "hardware_version": None,
        "software_version": None,
    }
