"""Tests for the wired СВК15-3-2-Б water meter."""

import pytest

from custom_components.modbus_devices.equipment import bolid
from custom_components.modbus_devices.equipment.bolid import SVK15_3_2_B
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    NumericResultStatus, S2000PPCounterResult, S2000PPZoneState,
    S2000PPZoneRow, manual_zone_mapping, resolve_zone_row,
)


def mapping(*objects, source=MappingSource.MANUAL):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            "SVK15_3_2_B", 10, DPLSSubIdentity(30, 1), DownstreamDeviceMetadata(),
        ), source, objects,
    )


def configured():
    device = SVK15_3_2_B(None, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(30, 22, 7, 0, None)))
    return device


def test_registration_display_and_wired_identity():
    device = configured()
    assert get_equipment_classes_by_manufacturer()["Bolid"].count("SVK15_3_2_B") == 1
    assert device.attr_model_name == "СВК15-3-2-Б"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(30, 1)
    assert device.attr_serial_number is None
    assert "DPLS voltage" in device.attr_device_metadata["transport_limitation"]


def test_manual_and_configuration_assisted_objects_are_equivalent():
    manual = manual_zone_mapping(30, 22, 7, 0, None)
    automatic = resolve_zone_row(S2000PPZoneRow(22, 10, 30, 0, 7), None)
    assert manual == automatic
    auto_device = SVK15_3_2_B(None, 1)
    auto_device.apply_gateway_mapping(mapping(automatic, source=MappingSource.AUTOMATIC))


@pytest.mark.asyncio
async def test_wired_total_and_common_states(monkeypatch):
    class StateReader:
        def __init__(self, *args): pass
        async def async_read_zone_states(self, mappings):
            return {22: S2000PPZoneState(22, 187, (187, 164, 211))}
    class CounterReader:
        def __init__(self, *args): pass
        async def async_read(self, zone):
            return S2000PPCounterResult(NumericResultStatus.READY, zone, raw_count=1000)
    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", StateReader)
    monkeypatch.setattr(bolid, "S2000PPCounterValueReader", CounterReader)
    snapshot = await configured().async_get_snapshot()
    assert snapshot["numeric_sensors"]["water_consumption"] == {"value": 1.0, "raw_count": 1000}
    assert snapshot["state_sensors"]["meter_state"]["expanded_states"] == (
        "input_communication_lost", "sabotage", "battery_low"
    )
