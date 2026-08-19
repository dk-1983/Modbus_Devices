"""Tests for the radio С2000Р-ДИП detector."""

import pytest

from custom_components.modbus_devices.equipment.bolid import C2000RDIP
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import manual_zone_mapping


def mapping(*objects, base=30):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            "C2000RDIP", 10, DPLSSubIdentity(base, 1), DownstreamDeviceMetadata(),
        ), MappingSource.MANUAL, objects,
    )


def test_radio_detector_is_independent_one_address_device():
    device = C2000RDIP(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 4, 1, 0, None)))
    assert device.attr_model_name == "С2000Р-ДИП"
    assert "arr" not in device.attr_gateway_mapping.identity.stable_id.lower()
    assert device.attr_device_metadata["dpls_address_count"] == 1
    assert not hasattr(device, "get_numeric_sensor_descriptions")


@pytest.mark.parametrize("local", [0, 29, 31, 40])
def test_arr_kdl_neighbor_and_other_radio_rows_rejected(local):
    zone_type = 3 if local == 0 else 1
    with pytest.raises(ValueError):
        C2000RDIP(None, 1).apply_gateway_mapping(
            mapping(manual_zone_mapping(local, 1, zone_type, 0, None))
        )


def test_common_radio_states_are_decoded_without_synthetic_entities():
    assert C2000RDIP._state_name(211) == "battery_low"
    assert C2000RDIP._state_name(149) == "enclosure_tamper"
    assert C2000RDIP._state_name(187) == "input_communication_lost"
    assert C2000RDIP._state_name(999) == "unknown_999"
