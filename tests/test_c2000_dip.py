"""Tests for the wired ДИП-34А-05 detector."""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.bolid import DIP34A05
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import manual_relay_mapping, manual_zone_mapping
from custom_components.modbus_devices.sensor import ModBusStateSensorEntity


class Response:
    def __init__(self, registers):
        self.registers = registers
        self.function_code = 3

    def isError(self):
        return False


class Client:
    def __init__(self, primary, expanded=()):
        self.primary = primary
        self.expanded = expanded

    async def read_holding_registers(self, **kwargs):
        return Response([self.primary])

    async def read_input_registers(self, **kwargs):
        response = Response(list(self.expanded) + [0] * (16 - len(self.expanded)))
        response.function_code = 4
        return response


class Entry:
    entry_id = "dip-entry"
    options = {Config.CONF_GATEWAY_ENTRY_ID: "gateway-entry"}
    data = {}


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
    assert device.attr_device_metadata["documented_target_firmware"] == "1.22"
    assert device.attr_device_metadata["supported_kdl_input_types"] == (6, 21)
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


@pytest.mark.parametrize(
    ("primary", "expected"),
    [
        (39, "equipment_normal"),
        (37, "fire"),
        (41, "equipment_fault"),
        (250, "device_communication_lost"),
        (254, "unknown_254"),
    ],
)
def test_documented_and_lossless_primary_states(primary, expected):
    device = DIP34A05(Client(primary), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))

    snapshot = asyncio.run(device.async_get_snapshot())["state_sensors"][
        "detector_state"
    ]

    assert snapshot["state"] == expected
    assert snapshot["primary_code"] == primary


def test_expanded_states_preserve_service_and_unknown_codes():
    device = DIP34A05(Client(39, (39, 204, 999)), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))

    snapshot = asyncio.run(device.async_get_snapshot())["state_sensors"][
        "detector_state"
    ]

    assert snapshot["expanded_codes"] == (39, 204, 999) + (0,) * 13
    assert snapshot["expanded_states"] == (
        "equipment_normal",
        "maintenance_required",
        "unknown_999",
    )


@pytest.mark.parametrize(
    ("state", "expected_icon"),
    [
        ("equipment_normal", "mdi:smoke-detector"),
        ("fire", "mdi:smoke-detector-alert"),
        ("equipment_fault", "mdi:alert-circle"),
        ("device_communication_lost", "mdi:alert-circle"),
        ("unknown_999", "mdi:help-circle-outline"),
    ],
)
def test_semantic_state_drives_icon_without_raw_code_mapping(state, expected_icon):
    device = DIP34A05(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 7, 1, 0, None)))
    coordinator = SimpleNamespace(
        data={
            "state_sensors": {
                "detector_state": {
                    "state": state,
                    "primary_code": 999,
                    "expanded_codes": (),
                    "expanded_states": (),
                }
            }
        },
        device=device,
        last_update_success=True,
    )
    entity = ModBusStateSensorEntity(
        coordinator,
        device,
        Entry(),
        device.get_state_sensor_descriptions()[0],
    )

    assert entity.icon == expected_icon
    assert entity.unique_id == f"{device.attr_unique_id_prefix}_detector_state"
    assert entity.device_info["identifiers"] == {
        (Config.DOMAIN, device.attr_device_identifier)
    }
    assert entity.device_info["via_device"] == (Config.DOMAIN, "gateway-entry")
