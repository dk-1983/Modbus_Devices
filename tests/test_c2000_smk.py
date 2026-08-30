"""Tests for the wired magnetic-contact detector С2000-СМК исп.04."""

import asyncio

import pytest
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import C2000SMK
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
    resolve_zone_row,
)


class Response:
    def __init__(self, registers, function_code):
        self.registers = registers
        self.function_code = function_code

    def isError(self):
        return False


class HardwareClient:
    def __init__(self, row):
        self.row = row

    async def read_holding_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (39999 + self.row, 1, 2)
        return Response([0x6D2F], 3)

    async def read_input_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (
            4096 + (self.row - 1) * 16,
            16,
            2,
        )
        return Response([109, 47, 188, 251, 111] + [0] * 11, 4)


def mapping(*objects, base=50):
    return ResolvedDeviceMapping(DownstreamDeviceIdentity(
        GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
        "C2000SMK", 10, DPLSSubIdentity(base, 1), DownstreamDeviceMetadata(),
    ), MappingSource.MANUAL, objects)


def test_canonical_registration_wired_identity_and_documented_metadata():
    device = C2000SMK(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(50, 1, 1, 0, None)))
    assert "C2000SMK" in get_equipment_classes_by_manufacturer()["Bolid"]
    assert device.attr_model_name == "С2000-СМК исп.04"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(50, 1)
    assert device.attr_device_metadata["supported_kdl_input_types"] == (4, 5, 6, 7, 11)
    assert device.attr_device_metadata["documented_target_firmware"] is None
    assert device.attr_device_metadata["documented_firmware_family"] == (
        "1.10",
        "1.11",
    )
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert "radio_supervision" not in device.attr_device_metadata["physical_capabilities"]


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    row = S2000PPZoneRow(1, 10, 50, 0, 1)
    assert resolve_zone_row(row, None) == manual_zone_mapping(50, 1, 1, 0, None)


def test_reconciliation_repairs_only_one_exact_type_one_row_without_partition_identity():
    stale = mapping(manual_zone_mapping(50, 2, 1, 99, None), base=50)
    configuration = S2000PPConfiguration(
        (S2000PPZoneRow(15, 10, 50, 8, 1),), (), (), ()
    )

    repaired = C2000SMK.reconcile_gateway_mapping(stale, configuration)

    assert repaired.identity == stale.identity
    assert repaired.source is stale.source
    assert repaired.objects[0].gateway_object_number == 15
    assert repaired.objects[0].zone_details.partition_number == 8


@pytest.mark.parametrize("rows", [
    (),
    (S2000PPZoneRow(15, 10, 50, 8, 6),),
    (
        S2000PPZoneRow(15, 10, 50, 8, 1),
        S2000PPZoneRow(16, 10, 50, 9, 1),
    ),
])
def test_reconciliation_rejects_missing_wrong_type_or_ambiguous_rows(rows):
    with pytest.raises(ValueError, match="unambiguous zone-type-1"):
        C2000SMK.reconcile_gateway_mapping(
            mapping(manual_zone_mapping(50, 15, 1, 8, None)),
            S2000PPConfiguration(rows, (), (), ()),
        )


@pytest.mark.parametrize("wrong", [
    manual_zone_mapping(51, 1, 1, 0, None),
    manual_zone_mapping(0, 1, 3, 0, None),
    manual_zone_mapping(50, 1, 6, 0, None),
    manual_relay_mapping(50, 1),
])
def test_exact_single_wired_zone_only(wrong):
    with pytest.raises(ValueError):
        C2000SMK(None, 1).apply_gateway_mapping(mapping(wrong))


def test_only_authoritative_opening_multistate_is_exposed():
    device = C2000SMK(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(50, 1, 1, 0, None)))
    assert device.get_state_sensor_descriptions() == [{
        "sensor_id": "opening_state", "name": "Opening state",
        "device_class": None, "icon": "mdi:door",
        "entity_category": EntityCategory.DIAGNOSTIC,
    }]
    assert C2000SMK._state_name(3) == "intrusion_alarm"
    assert C2000SMK._state_name(999) == "unknown_999"
    assert not hasattr(device, "get_numeric_sensor_descriptions")
    assert not hasattr(device, "get_output_descriptions")


def test_two_wired_quiescent_hardware_rows_remain_lossless_without_battery():
    for dpls, row in ((33, 15), (34, 16)):
        device = C2000SMK(HardwareClient(row), 2)
        device.apply_gateway_mapping(
            mapping(manual_zone_mapping(dpls, row, 1, 8, None), base=dpls)
        )

        snapshot = asyncio.run(device.async_get_snapshot())

        assert snapshot["state_sensors"]["opening_state"] == {
            "sensor_id": "opening_state",
            "state": "disarmed",
            "primary_code": 109,
            "expanded_codes": (109, 47, 188, 251, 111, *([0] * 11)),
            "expanded_states": (
                "disarmed",
                "dpls_restored",
                "input_communication_restored",
                "device_communication_restored",
                "input_control_enabled",
            ),
        }
        assert set(snapshot["state_sensors"]) == {"opening_state"}
        assert not hasattr(device, "get_binary_sensor_descriptions")
