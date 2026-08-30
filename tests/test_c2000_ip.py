"""Tests for the wired С2000-ИП-03 detector."""

import asyncio
from types import SimpleNamespace

import pytest

import custom_components.modbus_devices.equipment.bolid as bolid
from custom_components.modbus_devices.equipment.bolid import C2000IP03
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.mapping import (
    AmbiguousDeviceMappingError, AutomaticDeviceMappingProvider,
)
from custom_components.modbus_devices.s2000_pp import (
    NumericParameterKind, NumericResultStatus, S2000PPConfiguration,
    S2000PPConfigurationCache, S2000PPZoneRow, manual_zone_mapping,
)


def mapping(zone_type, *, table=7, model="C2000IP03"):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            model, 10, DPLSSubIdentity(20, 1), DownstreamDeviceMetadata(),
        ), MappingSource.MANUAL, (manual_zone_mapping(20, table, zone_type, 0, None),),
    )


def test_two_exact_alternative_mapping_modes():
    state = C2000IP03(None, 1)
    state.apply_gateway_mapping(mapping(1))
    numeric = C2000IP03(None, 1)
    numeric.apply_gateway_mapping(mapping(6))
    assert state.attr_model_name == "С2000-ИП-03"
    assert state.attr_device_metadata["mapping_mode"] == "state_only"
    assert numeric.attr_device_metadata["mapping_mode"] == "state_and_temperature"
    assert state.get_numeric_sensor_descriptions() == []
    assert numeric.get_numeric_sensor_descriptions()[0]["sensor_id"] == "temperature"
    assert numeric.attr_gateway_mapping.identity.dpls.address_count == 1


def test_both_alternatives_and_neighbor_are_rejected_by_equipment():
    both = ResolvedDeviceMapping(
        mapping(1).identity, MappingSource.MANUAL,
        (manual_zone_mapping(20, 1, 1, 0, None), manual_zone_mapping(20, 2, 6, 0, None)),
    )
    with pytest.raises(ValueError):
        C2000IP03(None, 1).apply_gateway_mapping(both)
    wrong = ResolvedDeviceMapping(
        mapping(1).identity, MappingSource.MANUAL,
        (manual_zone_mapping(21, 1, 1, 0, None),),
    )
    with pytest.raises(ValueError):
        C2000IP03(None, 1).apply_gateway_mapping(wrong)


def test_configuration_assisted_mapping_reports_ambiguous_alternatives():
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(1, 10, 20, 0, 1),
               S2000PPZoneRow(2, 10, 20, 0, 6)),
        relays=(), partitions=(), unparsed_registers=(),
    )
    class Reader:
        async def async_read(self): return configuration
    with pytest.raises(AmbiguousDeviceMappingError):
        asyncio.run(AutomaticDeviceMappingProvider(
            Reader(), S2000PPConfigurationCache()
        ).async_resolve(
            mapping(1).identity.gateway, "C2000IP03", 10,
            dpls=DPLSSubIdentity(20, 1),
            capabilities=C2000IP03.get_gateway_capabilities(),
        ))


@pytest.mark.parametrize("zone_type", [1, 6])
def test_manual_and_configuration_assisted_modes_are_equivalent(zone_type):
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(7, 10, 20, 0, zone_type),),
        relays=(), partitions=(), unparsed_registers=(),
    )
    class Reader:
        async def async_read(self): return configuration
    automatic = asyncio.run(AutomaticDeviceMappingProvider(
        Reader(), S2000PPConfigurationCache()
    ).async_resolve(
        mapping(zone_type).identity.gateway, "C2000IP03", 10,
        dpls=DPLSSubIdentity(20, 1),
        capabilities=C2000IP03.get_gateway_capabilities(),
    ))
    assert automatic.objects == mapping(zone_type).objects


@pytest.mark.asyncio
@pytest.mark.parametrize(("value", "raw"), [(23.5, 6016), (-5.25, 64192)])
async def test_numeric_temperature_reuses_reader(monkeypatch, value, raw):
    class NumericReader:
        def __init__(self, *args): pass
        async def async_read(self, zone, kind):
            assert kind is NumericParameterKind.TEMPERATURE
            return SimpleNamespace(status=NumericResultStatus.READY, value=value,
                                   raw_register=raw, parameter_kind=kind, message=None)
    class RuntimeReader:
        def __init__(self, *args): pass
        async def async_read_zone_states(self, objects):
            return {7: SimpleNamespace(primary_state=39, expanded_states=(39, 0))}
    monkeypatch.setattr(bolid, "S2000PPNumericValueReader", NumericReader)
    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", RuntimeReader)
    device = C2000IP03(None, 1)
    device.apply_gateway_mapping(mapping(6))
    snapshot = await device.async_get_snapshot()
    assert snapshot["numeric_sensors"]["temperature"]["value"] == value
    assert snapshot["state_sensors"]["detector_state"]["state"] == "equipment_normal"


@pytest.mark.asyncio
async def test_pending_preserves_last_confirmed_temperature(monkeypatch):
    class NumericReader:
        def __init__(self, *args): pass
        async def async_read(self, zone, kind):
            return SimpleNamespace(status=NumericResultStatus.PENDING, value=None,
                                   raw_register=None, parameter_kind=kind, message=None)
    class RuntimeReader:
        def __init__(self, *args): pass
        async def async_read_zone_states(self, objects):
            return {7: SimpleNamespace(primary_state=41, expanded_states=(41, 0))}
    monkeypatch.setattr(bolid, "S2000PPNumericValueReader", NumericReader)
    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", RuntimeReader)
    device = C2000IP03(None, 1)
    device.apply_gateway_mapping(mapping(6))
    device._temperature_value = {"value": 21.25, "raw_register": 5440,
                                 "parameter_kind": "temperature"}
    snapshot = await device.async_get_snapshot()
    assert snapshot["numeric_sensors"]["temperature"]["value"] == 21.25
    assert snapshot["state_sensors"]["detector_state"]["state"] == "equipment_fault"


@pytest.mark.asyncio
async def test_optional_numeric_protocol_error_preserves_state_and_cached_temperature(
    monkeypatch,
):
    class NumericReader:
        def __init__(self, *args):
            pass

        async def async_read(self, zone, kind):
            return SimpleNamespace(
                status=NumericResultStatus.PROTOCOL_ERROR,
                value=None,
                raw_register=None,
                parameter_kind=kind,
                message="Modbus exception during read numeric result",
                exception_code=4,
                selector_register=46179,
                result_register=46328,
                result_count=1,
                session_owner=("numeric", zone),
                session_generation=3,
                response_function_code=0x83,
                operation="read numeric result",
            )

    class RuntimeReader:
        def __init__(self, *args):
            pass

        async def async_read_zone_states(self, objects):
            return {7: SimpleNamespace(primary_state=39, expanded_states=(39, 0))}

    monkeypatch.setattr(bolid, "S2000PPNumericValueReader", NumericReader)
    monkeypatch.setattr(bolid, "S2000PPRuntimeReader", RuntimeReader)
    device = C2000IP03(None, 1)
    device.apply_gateway_mapping(mapping(6))
    device._temperature_value = {
        "value": 21.25,
        "raw_register": 5440,
        "parameter_kind": "temperature",
    }

    snapshot = await device.async_get_snapshot()

    assert snapshot["numeric_sensors"]["temperature"]["value"] == 21.25
    assert snapshot["state_sensors"]["detector_state"]["state"] == (
        "equipment_normal"
    )
