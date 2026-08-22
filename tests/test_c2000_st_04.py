"""Tests for the wired glass-break detector С2000-СТ исп.04."""

import pytest

from custom_components.modbus_devices.equipment.bolid import C2000ST04
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


def mapping(*objects, base=40):
    return ResolvedDeviceMapping(DownstreamDeviceIdentity(
        GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
        "C2000ST04", 10, DPLSSubIdentity(base, 1), DownstreamDeviceMetadata(),
    ), MappingSource.MANUAL, objects)


def test_registration_exact_model_and_one_address_identity():
    device = C2000ST04(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(40, 2, 1, 0, None)))
    assert "C2000ST04" in get_equipment_classes_by_manufacturer()["Bolid"]
    assert device.attr_model_name == "С2000-СТ исп.04"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(40, 1)
    assert device.attr_device_metadata["supported_kdl_input_types"] == (5,)
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert not hasattr(device, "get_numeric_sensor_descriptions")


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    row = S2000PPZoneRow(2, 10, 40, 0, 1)
    assert resolve_zone_row(row, None) == manual_zone_mapping(40, 2, 1, 0, None)


@pytest.mark.parametrize("wrong", [
    manual_zone_mapping(41, 2, 1, 0, None),
    manual_zone_mapping(0, 2, 3, 0, None),
    manual_zone_mapping(40, 2, 5, 0, None),
    manual_relay_mapping(40, 2),
])
def test_exact_zone_type_one_without_service_voltage_mapping(wrong):
    with pytest.raises(ValueError):
        C2000ST04(None, 1).apply_gateway_mapping(mapping(wrong))


def test_common_state_decoder_and_operational_entity():
    assert C2000ST04._state_name(3) == "intrusion_alarm"
    assert C2000ST04._state_name(149) == "enclosure_tamper"
    assert C2000ST04._state_name(999) == "unknown_999"
    device = C2000ST04(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(40, 2, 1, 0, None)))
    assert device.get_state_sensor_descriptions() == [{
        "sensor_id": "glass_break_state", "name": "Glass break detector state",
        "device_class": None, "icon": "mdi:glass-fragile",
    }]
