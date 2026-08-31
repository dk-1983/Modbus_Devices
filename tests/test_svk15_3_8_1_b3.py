"""Tests for the radio СВК15-3-8-1-Б3 water meter."""

import asyncio
from types import SimpleNamespace

import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfVolume

from custom_components.modbus_devices.equipment import bolid
from custom_components.modbus_devices.equipment.bolid import (
    SVK15_3_8_1_B3,
)
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.mapping import (
    AutomaticDeviceMappingProvider, DeviceMappingNotFoundError,
)
from custom_components.modbus_devices.sensor import ModBusNumericSensorEntity
from custom_components.modbus_devices.s2000_pp import (
    S2000PPZoneState, S2000PPConfiguration, S2000PPConfigurationCache,
    S2000PPZoneRow,
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
    assert get_equipment_classes_by_manufacturer()["Bolid"].count("SVK15_3_8_1_B3") == 1
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
    assert device.automatic_counter_polling_enabled is False


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
async def test_normal_snapshot_reads_state_without_automatic_counter(monkeypatch):
    expanded = (39, 200, 47, 188, 251, 111)
    calls = {"state": 0, "counter": 0}

    class StateReader:
        def __init__(self, *args):
            pass

        async def async_read_zone_states(self, mappings):
            calls["state"] += 1
            return {
                11: S2000PPZoneState(
                    11,
                    39,
                    expanded,
                    primary_register=0x27C8,
                    priority_states=(39, 200),
                )
            }

    class CounterReader:
        def __init__(self, *args):
            calls["counter"] += 1

        async def async_read(self, zone):
            raise AssertionError("automatic SVK counter polling must stay disabled")

    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", StateReader)
    monkeypatch.setattr(bolid, "S2000PPCounterValueReader", CounterReader)
    device = configured()

    snapshot = await device.async_get_snapshot()

    assert snapshot["numeric_sensors"] == {}
    assert calls == {"state": 1, "counter": 0}
    state = snapshot["state_sensors"]["meter_state"]
    assert state["state"] == "equipment_normal"
    assert state["primary_code"] == 39
    assert state["expanded_codes"] == expanded
    assert state["expanded_states"] == (
        "equipment_normal",
        "battery_restored",
        "dpls_restored",
        "input_communication_restored",
        "device_communication_restored",
        "input_control_enabled",
    )


@pytest.mark.asyncio
async def test_disabled_counter_preserves_existing_last_known_value(monkeypatch):
    class StateReader:
        def __init__(self, *args):
            pass

        async def async_read_zone_states(self, mappings):
            return {11: S2000PPZoneState(11, 39, (39,))}

    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", StateReader)
    monkeypatch.setattr(
        bolid,
        "S2000PPCounterValueReader",
        lambda *_: (_ for _ in ()).throw(AssertionError("counter reader constructed")),
    )
    device = configured()
    device._water_value = {"value": 2.5, "raw_count": 2500}

    snapshot = await device.async_get_snapshot()

    assert snapshot["numeric_sensors"]["water_consumption"] == {
        "value": 2.5,
        "raw_count": 2500,
    }


def test_unknown_water_value_keeps_entity_available():
    device = configured()
    coordinator = SimpleNamespace(
        data={"numeric_sensors": {}},
        device=device,
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="svk-entry", data={}, options={})
    entity = ModBusNumericSensorEntity(
        coordinator,
        device,
        entry,
        device.get_numeric_sensor_descriptions()[0],
    )

    assert entity.available is True
    assert entity.native_value is None


@pytest.mark.asyncio
async def test_four_svk_snapshots_never_start_counter_transactions(monkeypatch):
    calls = {"state": 0, "counter": 0}

    class StateReader:
        def __init__(self, *args):
            pass

        async def async_read_zone_states(self, mappings):
            calls["state"] += 1
            row = mappings[0].gateway_object_number
            return {row: S2000PPZoneState(row, 39, (39,))}

    class CounterReader:
        def __init__(self, *args):
            calls["counter"] += 1

        async def async_read(self, zone):
            raise AssertionError("automatic SVK counter polling must stay disabled")

    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", StateReader)
    monkeypatch.setattr(bolid, "S2000PPCounterValueReader", CounterReader)
    devices = [configured(base=20 + index) for index in range(4)]

    await asyncio.gather(*(device.async_get_snapshot() for device in devices))
    await asyncio.gather(*(device.async_get_snapshot() for device in devices))

    assert calls == {"state": 8, "counter": 0}
    assert all(device._water_value is None for device in devices)
