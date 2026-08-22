"""Tests for the wired ДИП-34А-05 detector."""

import pytest

from custom_components.modbus_devices.equipment.bolid import DIP34A05
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import manual_relay_mapping, manual_zone_mapping


def mapping(*objects, base=20, kdl=10, connection="tcp:pp-a", model="DIP34A05"):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", connection, 1),
            model, kdl, DPLSSubIdentity(base, 1), DownstreamDeviceMetadata(),
        ), MappingSource.MANUAL, objects,
    )


def test_registration_model_identity_and_metadata():
    device = DIP34A05(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))
    assert "DIP34A05" in get_equipment_classes_by_manufacturer()["Bolid"]
    assert device.attr_model_name == "ДИП-34А-05"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(20, 1)
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert device.get_state_sensor_descriptions()[0].get("entity_category") is None


@pytest.mark.parametrize("wrong", [
    manual_zone_mapping(21, 1, 1, 0, None),
    manual_zone_mapping(0, 1, 3, 0, None),
    manual_zone_mapping(20, 1, 6, 0, None),
    manual_relay_mapping(20, 1),
])
def test_exact_own_zone_only(wrong):
    with pytest.raises(ValueError):
        DIP34A05(None, 1).apply_gateway_mapping(mapping(wrong))


def test_identity_distinguishes_kdl_and_gateway():
    identities = {
        mapping(manual_zone_mapping(20, 1, 1, 0, None), kdl=kdl, connection=connection).identity.stable_id
        for kdl, connection in ((10, "tcp:a"), (11, "tcp:a"), (10, "tcp:b"))
    }
    assert len(identities) == 3


def test_legacy_model_mapping_loads_without_identity_rewrite():
    legacy = mapping(manual_zone_mapping(20, 1, 1, 0, None), model="C2000DIP")
    canonical = mapping(manual_zone_mapping(20, 1, 1, 0, None))
    device = DIP34A05(None, 1)
    device.apply_gateway_mapping(legacy)
    assert device.attr_gateway_mapping.identity.model == "C2000DIP"
    assert legacy.identity.stable_id == canonical.identity.stable_id
