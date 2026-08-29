"""Tests for the ordinary two-battery radio С2000Р-ДЗ."""

from types import SimpleNamespace

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.modbus_devices.device_info import device_info_for_entry
from custom_components.modbus_devices.equipment.bolid import C2000RDZ
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPZoneRow,
    manual_zone_mapping,
)


class Response:
    """Minimal successful pymodbus response."""

    def __init__(self, registers, function_code):
        self.registers = registers
        self.function_code = function_code

    def isError(self):
        return False


class Client:
    """Return one hardware-shaped primary and expanded state row."""

    def __init__(self, primary=0x50C8, expanded=None, row=11):
        self.primary = primary
        self.expanded = expanded or [80, 200, 213, 47, 188, 251, 111]
        self.row = row

    async def read_holding_registers(self, *, address, count, device_id):
        assert address == 39999 + self.row
        assert count == 1
        assert device_id == 2
        return Response([self.primary], 3)

    async def read_input_registers(self, *, address, count, device_id):
        assert address == 4096 + (self.row - 1) * 16
        assert count == 16
        assert device_id == 2
        return Response((self.expanded + [0] * count)[:count], 4)


def mapping(*objects, dpls=53):
    """Build one ordinary radio detector mapping without partition identity."""
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "serial:local", 2),
            "C2000RDZ",
            20,
            DPLSSubIdentity(dpls, 1),
        ),
        MappingSource.MANUAL,
        objects,
    )


def configuration(*rows):
    return S2000PPConfiguration(rows, (), (), ())


@pytest.mark.asyncio
async def test_two_unit_quiescent_hardware_fixture_exposes_radio_semantics():
    """Both observed units returned the same lossless quiescent snapshot."""
    for dpls, row in ((53, 11), (54, 12)):
        device = C2000RDZ(Client(row=row), 2)
        device.apply_gateway_mapping(
            mapping(manual_zone_mapping(dpls, row, 1, 20, None), dpls=dpls)
        )

        snapshot = await device.async_get_snapshot()

        assert snapshot["binary_sensors"]["water_leak"]["state"] is False
        assert snapshot["state_sensors"]["water_leak_state"] == {
            "state": "water_alarm_restored",
            "primary_code": 80,
            "expanded_codes": (80, 200, 213, 47, 188, 251, 111, *([0] * 9)),
            "expanded_states": (
                "water_alarm_restored",
                "battery_restored",
                "reserve_battery_restored",
                "dpls_restored",
                "input_communication_restored",
                "device_communication_restored",
                "input_control_enabled",
            ),
        }
        assert snapshot["state_sensors"]["main_battery_state"]["state"] == (
            "battery_restored"
        )
        assert snapshot["state_sensors"]["reserve_battery_state"]["state"] == (
            "reserve_battery_restored"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expanded", "main", "reserve"),
    [
        ([80, 211, 213], "battery_low", "reserve_battery_restored"),
        ([80, 202, 212], "battery_fault", "reserve_battery_low"),
        ([80], None, None),
    ],
)
async def test_documented_battery_codes_are_unknown_preserving(
    expanded, main, reserve
):
    """Candidate fault codes are documentation-derived, not transition fixtures."""
    device = C2000RDZ(Client(expanded=expanded), 2)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(53, 11, 1, 20, None)))

    snapshot = await device.async_get_snapshot()

    assert snapshot["state_sensors"]["main_battery_state"]["state"] == main
    assert snapshot["state_sensors"]["reserve_battery_state"]["state"] == reserve


@pytest.mark.asyncio
async def test_documented_water_mapping_does_not_assume_expanded_coexistence():
    device = C2000RDZ(Client(primary=0x4F00, expanded=[79, 999]), 2)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(53, 11, 1, 20, None)))

    snapshot = await device.async_get_snapshot()

    assert snapshot["binary_sensors"]["water_leak"]["state"] is True
    assert snapshot["state_sensors"]["water_leak_state"]["expanded_states"] == (
        "water_alarm",
        "unknown_999",
    )


def test_identity_device_info_and_capabilities_are_product_specific():
    device = C2000RDZ(Client(), 2)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(53, 11, 1, 20, None)))
    entry = SimpleNamespace(
        entry_id="rdz-entry",
        options={"gateway_entry_id": "pp-entry"},
        data={},
    )

    info = device_info_for_entry(device, entry)

    assert device.attr_model_name == "С2000Р-ДЗ"
    assert device.get_variant_options() == {}
    assert "1.06" in device.documented_firmware_family
    assert info["model"] == "С2000Р-ДЗ"
    assert info["sw_version"] is None
    assert info["hw_version"] is None
    assert info["serial_number"] is None
    assert info["via_device"] == ("modbus_devices", "pp-entry")
    assert device.get_binary_sensor_descriptions()[0]["device_class"] is (
        BinarySensorDeviceClass.MOISTURE
    )
    assert [item["sensor_id"] for item in device.get_state_sensor_descriptions()] == [
        "water_leak_state",
        "main_battery_state",
        "reserve_battery_state",
    ]
    assert not hasattr(device, "get_numeric_sensor_descriptions")


def test_reconciliation_uses_orion_dpls_and_type_not_partition():
    stale = mapping(manual_zone_mapping(53, 2, 1, 99, None))
    live = configuration(S2000PPZoneRow(11, 20, 53, 20, 1))

    repaired = C2000RDZ.reconcile_gateway_mapping(stale, live)

    assert repaired.identity == stale.identity
    assert repaired.source is stale.source
    assert repaired.objects[0].gateway_object_number == 11
    assert repaired.objects[0].zone_details.partition_number == 20


@pytest.mark.parametrize(
    "rows",
    [
        (),
        (S2000PPZoneRow(11, 20, 53, 20, 6),),
        (
            S2000PPZoneRow(11, 20, 53, 20, 1),
            S2000PPZoneRow(12, 20, 53, 21, 1),
        ),
    ],
)
def test_missing_wrong_type_or_ambiguous_mapping_is_rejected(rows):
    with pytest.raises(ValueError, match="unambiguous zone-type-1"):
        C2000RDZ.reconcile_gateway_mapping(
            mapping(manual_zone_mapping(53, 11, 1, 20, None)),
            configuration(*rows),
        )
