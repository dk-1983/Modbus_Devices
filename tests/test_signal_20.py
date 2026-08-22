"""Focused support tests for the Bolid Signal-20M control panel."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import Signal20M
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.mapping import AutomaticDeviceMappingProvider
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPConfigurationCache,
    S2000PPRelayRow,
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
)


class Response:
    def __init__(self, registers=None, *, error=False, function_code=None):
        self.registers = registers
        self._error = error
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self, failure=None):
        self.failure = failure
        self.holding_calls = []
        self.input_calls = []

    async def read_holding_registers(self, *, address, count, device_id):
        self.holding_calls.append((address, count, device_id))
        if self.failure == "none":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "wrong_function":
            return Response([39] * count, function_code=4)
        if self.failure == "exception":
            raise ModbusException("offline")
        values = [39, *([24] * (count - 1))]
        if self.failure == "truncated":
            values = values[:-1]
        return Response(values, function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        self.input_calls.append((address, count, device_id))
        if self.failure == "expanded_none":
            return None
        values = [0] * count
        for offset in range(0, count, 16):
            values[offset] = 28 if offset else 149
        return Response(values, function_code=4)


def gateway():
    return GatewayContext(GatewayType.S2000_PP, "pp-a", "serial:COM1", 1)


def identity(orion=12, dpls=None):
    return DownstreamDeviceIdentity(
        gateway=gateway(), model="Signal20M", orion_address=orion, dpls=dpls
    )


def mapping(*objects, dpls=None):
    return ResolvedDeviceMapping(
        identity=identity(dpls=dpls), source=MappingSource.MANUAL, objects=objects
    )


def all_objects():
    return tuple(
        manual_zone_mapping(local, local + 1, 3 if local == 0 else 1, 0, None)
        for local in range(21)
    )


def configured(client=None, objects=None):
    device = Signal20M(client or Client(), 1)
    device.apply_gateway_mapping(mapping(*(objects or all_objects())))
    return device


def test_registry_metadata_and_config_flow_visibility():
    registry = get_equipment_classes_by_manufacturer()
    assert registry["Bolid"].count("Signal20M") == 1
    assert len(registry["Bolid"]) == 27
    assert sum(map(len, registry.values())) == 30
    assert Signal20M.equipment_manufacturer == "Bolid"
    assert Signal20M.equipment_model == "Сигнал-20М"
    assert Signal20M(None, 1).attr_model_name == "Сигнал-20М"


def test_direct_orion_identity_has_no_dpls_and_is_stable():
    first = mapping(*all_objects())
    second = ResolvedDeviceMapping(
        identity=identity(orion=13), source=MappingSource.MANUAL, objects=all_objects()
    )
    assert first.identity.dpls is None
    assert first.identity.stable_id != second.identity.stable_id
    assert configured().attr_device_identifier == first.identity.stable_id

    with pytest.raises(ValueError, match="must not contain DPLS"):
        Signal20M(None, 1).apply_gateway_mapping(
            mapping(
                manual_zone_mapping(1, 1, 1, 0, None),
                dpls=DPLSSubIdentity(1, 1),
            )
        )


def test_exact_data_driven_capabilities_and_partial_mapping():
    capabilities = Signal20M.get_gateway_capabilities()
    assert len(capabilities) == 21
    assert (capabilities[0].local_object_number, capabilities[0].zone_type) == (0, 3)
    assert [(item.local_object_number, item.zone_type) for item in capabilities[1:]] == [
        (number, 1) for number in range(1, 21)
    ]
    partial = configured(objects=(manual_zone_mapping(20, 7, 1, 0, None),))
    assert partial.attr_platforms == [Platform.SENSOR]
    assert [item["sensor_id"] for item in partial.get_state_sensor_descriptions()] == [
        "input_20_state"
    ]
    descriptions = {
        item["sensor_id"]: item for item in configured().get_state_sensor_descriptions()
    }
    assert descriptions["device_state"]["entity_category"] is EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    "bad_object",
    [
        manual_zone_mapping(21, 22, 1, 0, None),
        manual_zone_mapping(0, 1, 1, 0, None),
        manual_zone_mapping(1, 2, 3, 0, None),
        manual_zone_mapping(1, 2, 2, 0, None),
        manual_zone_mapping(1, 2, 6, 0, None),
        manual_relay_mapping(1, 1),
        manual_relay_mapping(7, 1),
    ],
)
def test_wrong_types_neighbors_and_all_relay_rows_are_rejected(bad_object):
    with pytest.raises(ValueError, match="unsupported Signal-20M"):
        configured(objects=(bad_object,))


def test_duplicate_mapping_is_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        configured(
            objects=(
                manual_zone_mapping(1, 1, 1, 0, None),
                manual_zone_mapping(1, 2, 1, 0, None),
            )
        )


def test_data_init_is_local_and_performs_no_modbus_io():
    client = Client()
    assert asyncio.run(configured(client).data_init()) is True
    assert client.holding_calls == []
    assert client.input_calls == []


def test_full_mapping_uses_one_primary_and_three_expanded_reads():
    client = Client()
    snapshot = asyncio.run(configured(client).async_get_snapshot())["state_sensors"]
    assert client.holding_calls == [(40000, 21, 1)]
    assert len(client.input_calls) == 3
    assert [count for _, count, _ in client.input_calls] == [112, 112, 112]
    assert snapshot["device_state"]["state"] == "equipment_normal"
    assert snapshot["device_state"]["primary_code"] == 39
    assert snapshot["input_1_state"]["state"] == "armed"
    assert snapshot["input_1_state"]["expanded_states"] == ("access_granted",)


def test_unknown_primary_and_expanded_states_are_preserved():
    class UnknownClient(Client):
        async def read_holding_registers(self, *, address, count, device_id):
            self.holding_calls.append((address, count, device_id))
            return Response([999] * count, function_code=3)

        async def read_input_registers(self, *, address, count, device_id):
            self.input_calls.append((address, count, device_id))
            values = [0] * count
            values[0] = 998
            return Response(values, function_code=4)

    snapshot = asyncio.run(configured(UnknownClient()).async_get_snapshot())["state_sensors"]
    assert snapshot["device_state"]["state"] == "unknown_999"
    assert snapshot["device_state"]["expanded_states"] == ("unknown_998",)


@pytest.mark.parametrize(
    "failure",
    ["none", "error", "wrong_function", "exception", "truncated", "expanded_none"],
)
def test_malformed_and_transport_failures_are_not_normal(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured(Client(failure=failure)).async_get_snapshot())


def test_configuration_assisted_mapping_filters_exact_rows_and_orion_address():
    configuration = S2000PPConfiguration(
        zones=tuple(
            S2000PPZoneRow(local + 1, 12, local, 0, 3 if local == 0 else 1)
            for local in range(21)
        )
        + (
            S2000PPZoneRow(30, 12, 21, 0, 1),
            S2000PPZoneRow(31, 12, 1, 0, 3),
            S2000PPZoneRow(32, 13, 1, 0, 1),
        ),
        relays=tuple(S2000PPRelayRow(number, 12, number) for number in range(1, 8)),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    automatic = asyncio.run(
        AutomaticDeviceMappingProvider(Reader(), S2000PPConfigurationCache()).async_resolve(
            gateway(),
            "Signal20M",
            12,
            capabilities=Signal20M.get_gateway_capabilities(),
        )
    )
    assert automatic.objects == mapping(*all_objects()).objects


def test_relays_commands_databases_logs_and_service_metadata_are_not_exposed():
    device = configured()
    assert not hasattr(device, "get_output_descriptions")
    assert not hasattr(device, "get_button_descriptions")
    assert device.attr_platforms == [Platform.SENSOR]
    assert asyncio.run(device.get_device_info()) == {
        "device_type": None,
        "serial_number": None,
        "hardware_version": None,
        "software_version": None,
    }
