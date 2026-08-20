"""Tests for the radio СВК15-3-8-1-Б3 water meter."""

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfVolume

from custom_components.modbus_devices.equipment import bolid
from custom_components.modbus_devices.equipment.bolid import SVK15_3_8_1_B3
from custom_components.modbus_devices.equipment.equipment import get_classes_from_files
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.mapping import (
    AutomaticDeviceMappingProvider, DeviceMappingNotFoundError,
)
from custom_components.modbus_devices.s2000_pp import (
    NumericResultStatus, S2000PPCounterResult, S2000PPZoneState,
    S2000PPConfiguration, S2000PPConfigurationCache, S2000PPZoneRow,
    manual_relay_mapping, manual_zone_mapping,
)


def make_mapping(*objects, base=20, model="SVK15_3_8_1_B3", kdl=10):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            model, kdl, DPLSSubIdentity(base, 1), DownstreamDeviceMetadata(),
        ), MappingSource.MANUAL, objects,
    )


def configured(client=None, base=20):
    device = SVK15_3_8_1_B3(client, 1)
    device.apply_gateway_mapping(
        make_mapping(manual_zone_mapping(base, 11, 7, 0, None), base=base)
    )
    return device


def test_registration_identity_and_metadata():
    device = configured()
    assert get_classes_from_files()["Bolid"].count("SVK15_3_8_1_B3") == 1
    assert device.attr_model_name == "СВК15-3-8-1-Б3"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(20, 1)
    assert device.attr_device_identifier.endswith(":orion:10:dpls:20")
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert "ARR125 is not part of stable identity" in device.attr_device_metadata["transport_limitation"]


@pytest.mark.parametrize("wrong", [
    manual_zone_mapping(20, 1, 1, 0, None), manual_zone_mapping(20, 1, 3, 0, None),
    manual_zone_mapping(20, 1, 6, 0, None), manual_zone_mapping(20, 1, 8, 0, None),
    manual_zone_mapping(21, 1, 7, 0, None), manual_zone_mapping(0, 1, 3, 0, None),
    manual_relay_mapping(20, 1),
])
def test_exact_type7_base_ownership(wrong):
    with pytest.raises(ValueError):
        SVK15_3_8_1_B3(None, 1).apply_gateway_mapping(make_mapping(wrong))


def test_water_and_meter_state_entity_metadata():
    device = configured()
    water = device.get_numeric_sensor_descriptions()[0]
    assert water["device_class"] is SensorDeviceClass.WATER
    assert water["state_class"] is SensorStateClass.TOTAL_INCREASING
    assert water["unit"] == UnitOfVolume.CUBIC_METERS
    assert water["precision"] == 3
    assert device.get_state_sensor_descriptions()[0]["name"] == "Meter state"
    assert device.attr_platforms == [bolid.Platform.SENSOR]


@pytest.mark.asyncio
async def test_configuration_assisted_mapping_is_exact():
    class Reader:
        async def async_read(self):
            return S2000PPConfiguration(
                zones=(
                    S2000PPZoneRow(1, 10, 20, 0, 1),
                    S2000PPZoneRow(2, 10, 20, 0, 7),
                    S2000PPZoneRow(3, 10, 21, 0, 7),
                    S2000PPZoneRow(4, 11, 20, 0, 7),
                ), relays=(), partitions=(), unparsed_registers=(),
            )
    provider = AutomaticDeviceMappingProvider(Reader(), S2000PPConfigurationCache())
    identity = make_mapping(manual_zone_mapping(20, 1, 7, 0, None)).identity
    resolved = await provider.async_resolve(
        identity.gateway, "SVK15_3_8_1_B3", identity.orion_address,
        dpls=identity.dpls, capabilities=SVK15_3_8_1_B3.get_gateway_capabilities(),
    )
    assert len(resolved.objects) == 1
    assert resolved.objects[0].gateway_object_number == 2
    SVK15_3_8_1_B3(None, 1).apply_gateway_mapping(resolved)

    with pytest.raises(DeviceMappingNotFoundError):
        await provider.async_resolve(
            identity.gateway, "SVK15_3_8_1_B3", identity.orion_address,
            dpls=DPLSSubIdentity(22, 1),
            capabilities=SVK15_3_8_1_B3.get_gateway_capabilities(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "water"), [(0, 0.0), (1, 0.001), (1000, 1.0), (1234567, 1234.567)])
async def test_water_conversion_and_state_snapshot(monkeypatch, raw, water):
    class StateReader:
        def __init__(self, *args): pass
        async def async_read_zone_states(self, mappings):
            return {11: S2000PPZoneState(11, 164, (164, 211, 250, 999))}
    class CounterReader:
        def __init__(self, *args): pass
        async def async_read(self, zone):
            return S2000PPCounterResult(NumericResultStatus.READY, zone, raw_count=raw)
    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", StateReader)
    monkeypatch.setattr(bolid, "S2000PPCounterValueReader", CounterReader)
    snapshot = await configured().async_get_snapshot()
    assert snapshot["numeric_sensors"]["water_consumption"]["value"] == water
    state = snapshot["state_sensors"]["meter_state"]
    assert state["state"] == "sabotage"
    assert state["expanded_codes"] == (164, 211, 250, 999)
    assert state["expanded_states"][-1] == "unknown_999"


@pytest.mark.asyncio
async def test_pending_preserves_last_confirmed_and_protocol_error_fails(monkeypatch):
    class StateReader:
        def __init__(self, *args): pass
        async def async_read_zone_states(self, mappings):
            return {11: S2000PPZoneState(11, 39, ())}
    class CounterReader:
        status = NumericResultStatus.PENDING
        def __init__(self, *args): pass
        async def async_read(self, zone):
            return S2000PPCounterResult(self.status, zone, message="bad")
    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", StateReader)
    monkeypatch.setattr(bolid, "S2000PPCounterValueReader", CounterReader)
    device = configured()
    assert (await device.async_get_snapshot())["numeric_sensors"] == {}
    device._water_value = {"value": 2.5, "raw_count": 2500}
    assert (await device.async_get_snapshot())["numeric_sensors"]["water_consumption"]["value"] == 2.5
    CounterReader.status = NumericResultStatus.PROTOCOL_ERROR
    with pytest.raises(ModbusException):
        await device.async_get_snapshot()
