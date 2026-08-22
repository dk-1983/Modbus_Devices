"""Tests for the wired magnetic-contact detector С2000-СМК."""

import pytest

from custom_components.modbus_devices.equipment.bolid import C2000SMK
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
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


def mapping(*objects, base=50):
    return ResolvedDeviceMapping(DownstreamDeviceIdentity(
        GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
        "C2000SMK", 10, DPLSSubIdentity(base, 1), DownstreamDeviceMetadata(),
    ), MappingSource.MANUAL, objects)


def test_canonical_registration_wired_identity_and_documented_metadata():
    device = C2000SMK(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(50, 1, 1, 0, None)))
    assert "C2000SMK" in get_equipment_classes_by_manufacturer()["Bolid"]
    assert device.attr_model_name == "С2000-СМК"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(50, 1)
    assert device.attr_device_metadata["supported_kdl_input_types"] == (4, 5, 6, 7, 11, 22)
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert "radio_supervision" not in device.attr_device_metadata["physical_capabilities"]


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    row = S2000PPZoneRow(1, 10, 50, 0, 1)
    assert resolve_zone_row(row, None) == manual_zone_mapping(50, 1, 1, 0, None)


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
    }]
    assert C2000SMK._state_name(3) == "intrusion_alarm"
    assert C2000SMK._state_name(999) == "unknown_999"
    assert not hasattr(device, "get_numeric_sensor_descriptions")
    assert not hasattr(device, "get_output_descriptions")
