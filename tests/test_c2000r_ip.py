"""Tests for the radio С2000Р-ИП detector."""

import pytest

from custom_components.modbus_devices.equipment.bolid import C2000RIP
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import manual_zone_mapping


def mapping(local=40, zone_type=1):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            "C2000RIP", 10, DPLSSubIdentity(40, 1), DownstreamDeviceMetadata(),
        ), MappingSource.MANUAL, (manual_zone_mapping(local, 1, zone_type, 0, None),),
    )


def test_physical_temperature_does_not_invent_numeric_transport():
    device = C2000RIP(None, 1)
    device.apply_gateway_mapping(mapping())
    assert device.attr_model_name == "С2000Р-ИП"
    assert "temperature_measurement" in device.attr_device_metadata["physical_capabilities"]
    assert "not confirmed" in device.attr_device_metadata["transport_limitation"]
    assert not hasattr(device, "get_numeric_sensor_descriptions")
    assert device.attr_serial_number is None
    assert device.attr_software_version is None


@pytest.mark.parametrize(("local", "zone_type"), [(20, 1), (39, 1), (41, 1), (0, 3), (40, 6)])
def test_arr_other_radio_kdl_neighbor_and_numeric_rows_rejected(local, zone_type):
    with pytest.raises(ValueError):
        C2000RIP(None, 1).apply_gateway_mapping(mapping(local, zone_type))


def test_radio_state_decoder_and_identity_have_no_arr_component():
    device = C2000RIP(None, 1)
    device.apply_gateway_mapping(mapping())
    assert C2000RIP._state_name(212) == "reserve_battery_low"
    assert C2000RIP._state_name(152) == "enclosure_tamper_restored"
    assert C2000RIP._state_name(188) == "input_communication_restored"
    assert "arr" not in device.attr_device_identifier.lower()
