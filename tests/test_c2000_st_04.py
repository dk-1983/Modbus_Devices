"""Focused tests for wired glass-break detector С2000-СТ исп.04."""

from types import SimpleNamespace

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory, Platform
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.binary_sensor import (
    ModBusDescribedBinarySensorEntity,
)
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.bolid import C2000ST04
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
    resolve_zone_row,
)
from custom_components.modbus_devices.sensor import ModBusStateSensorEntity


class Response:
    def __init__(self, registers=None, error=False, function_code=None):
        self.registers, self._error = registers, error
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self, primary=24, expanded=(24,), failure=None):
        self.primary, self.expanded, self.failure = primary, tuple(expanded), failure

    async def read_holding_registers(self, **kwargs):
        assert kwargs == {"address": 40000, "count": 1, "device_id": 1}
        if self.failure == "empty":
            return None
        if self.failure == "invalid":
            return object()
        if self.failure == "truncated":
            return Response([])
        if self.failure == "error":
            return Response(error=True)
        return Response([self.primary << 8], function_code=3)

    async def read_input_registers(self, **kwargs):
        assert kwargs == {"address": 4096, "count": 16, "device_id": 1}
        return Response((self.expanded + (0,) * 16)[:16], function_code=4)


class Entry:
    entry_id = "st04-entry"
    options = {Config.CONF_GATEWAY_ENTRY_ID: "gateway-entry"}
    data = {}


def mapping(*objects, base=40):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            "C2000ST04",
            10,
            DPLSSubIdentity(base, 1),
            DownstreamDeviceMetadata(),
        ),
        MappingSource.MANUAL,
        objects,
    )


def configured(client=None):
    device = C2000ST04(client or Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(40, 1, 1, 0, None)))
    return device


def coordinator(device, data):
    return SimpleNamespace(data=data, device=device, last_update_success=True)


def test_registration_one_row_identity_and_current_documented_metadata():
    device = configured()
    assert "C2000ST04" in get_equipment_classes_by_manufacturer()["Bolid"]
    assert device.attr_model_name == "С2000-СТ исп.04"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(40, 1)
    assert device.attr_device_metadata["dpls_address_count"] == 1
    assert device.attr_device_metadata["supported_kdl_input_types"] == (4, 5, 6, 7, 11)
    assert device.attr_device_metadata["documented_target_firmware"] == "1.24"
    assert device.attr_platforms == [Platform.SENSOR, Platform.BINARY_SENSOR]
    assert device.attr_software_version is None
    assert device.attr_hardware_version is None
    assert device.attr_serial_number is None


def test_pp_type_one_is_distinct_from_documented_kdl_input_types():
    row = S2000PPZoneRow(1, 10, 40, 0, 1)
    assert resolve_zone_row(row, None) == manual_zone_mapping(40, 1, 1, 0, None)
    assert configured().supported_kdl_input_types == (4, 5, 6, 7, 11)


@pytest.mark.parametrize(
    "wrong",
    [
        manual_zone_mapping(41, 1, 1, 0, None),
        manual_zone_mapping(0, 1, 3, 0, None),
        manual_zone_mapping(40, 1, 6, 0, None),
        manual_relay_mapping(40, 1),
    ],
)
def test_exact_own_pp_type_one_zone_only(wrong):
    with pytest.raises(ValueError):
        C2000ST04(Client(), 1).apply_gateway_mapping(mapping(wrong))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("primary", "expected"),
    [
        (24, "armed"),
        (3, "intrusion_alarm"),
        (4, "interference"),
        (19, "test"),
        (20, "test_mode_started"),
        (21, "test_mode_finished"),
        (39, "equipment_normal"),
        (41, "equipment_fault"),
        (187, "input_communication_lost"),
        (188, "input_communication_restored"),
        (250, "device_communication_lost"),
        (251, "device_communication_restored"),
        (254, "unknown_254"),
    ],
)
async def test_canonical_primary_states_and_unknown_are_lossless(primary, expected):
    state = (await configured(Client(primary, (primary,))).async_get_snapshot())[
        "state_sensors"
    ]["glass_break_state"]
    assert (state["state"], state["primary_code"]) == (expected, primary)


@pytest.mark.asyncio
async def test_expanded_unknown_and_communication_codes_remain_lossless():
    expanded = (3, 149, 41, 187, 250, 999)
    state = (await configured(Client(3, expanded)).async_get_snapshot())[
        "state_sensors"
    ]["glass_break_state"]
    assert state["expanded_codes"] == expanded + (0,) * 10
    assert state["expanded_states"][-1] == "unknown_999"


@pytest.mark.asyncio
async def test_glass_alarm_latches_until_explicit_armed_or_reset_evidence():
    device = configured(Client(24, (24,)))
    assert (await device.async_get_snapshot())["binary_sensors"]["glass_break"][
        "state"
    ] is False
    device.attr_client = Client(3, (3, 149))
    assert (await device.async_get_snapshot())["binary_sensors"]["glass_break"][
        "state"
    ] is True
    device.attr_client = Client(149, (149, 41))
    assert (await device.async_get_snapshot())["binary_sensors"]["glass_break"][
        "state"
    ] is True
    device.attr_client = Client(110, (110, 152, 39))
    assert (await device.async_get_snapshot())["binary_sensors"]["glass_break"][
        "state"
    ] is False


@pytest.mark.asyncio
async def test_conflicting_alarm_and_restore_evidence_preserves_unknown():
    device = configured(Client(149, (3, 24, 149)))
    assert (await device.async_get_snapshot())["binary_sensors"]["glass_break"][
        "state"
    ] is None


@pytest.mark.asyncio
async def test_enclosure_tamper_requires_explicit_active_or_restore():
    device = configured(Client(24, (24,)))
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is None
    device.attr_client = Client(149, (24,))
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is True
    device.attr_client = Client(24, (24,))
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is True
    device.attr_client = Client(24, (24, 152))
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is False


@pytest.mark.asyncio
async def test_self_test_and_antimasking_share_equipment_fault_semantics():
    device = configured(Client(24, (24,)))
    assert (await device.async_get_snapshot())["binary_sensors"]["equipment_fault"][
        "state"
    ] is None
    device.attr_client = Client(41, (24,))
    assert (await device.async_get_snapshot())["binary_sensors"]["equipment_fault"][
        "state"
    ] is True
    device.attr_client = Client(24, (24,))
    assert (await device.async_get_snapshot())["binary_sensors"]["equipment_fault"][
        "state"
    ] is True
    device.attr_client = Client(39, (39, 24))
    assert (await device.async_get_snapshot())["binary_sensors"]["equipment_fault"][
        "state"
    ] is False


@pytest.mark.asyncio
async def test_conflicting_tamper_and_fault_pairs_do_not_invent_state():
    snapshot = await configured(Client(24, (24, 149, 152, 39, 41))).async_get_snapshot()
    assert snapshot["binary_sensors"]["enclosure_tamper"]["state"] is None
    assert snapshot["binary_sensors"]["equipment_fault"]["state"] is None


def test_entity_matrix_has_no_radio_or_battery_entities_and_keeps_one_device():
    device = configured()
    states = device.get_state_sensor_descriptions()
    binaries = device.get_binary_sensor_descriptions()
    assert [item["sensor_id"] for item in states] == ["glass_break_state"]
    assert [item["sensor_id"] for item in binaries] == [
        "glass_break",
        "enclosure_tamper",
        "equipment_fault",
    ]
    assert binaries[0]["device_class"] is BinarySensorDeviceClass.SOUND
    assert binaries[1]["device_class"] is BinarySensorDeviceClass.TAMPER
    assert binaries[2]["device_class"] is BinarySensorDeviceClass.PROBLEM
    assert binaries[1]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert binaries[2]["entity_category"] is EntityCategory.DIAGNOSTIC
    assert all(item["enabled_default"] is True for item in binaries)
    assert not any("battery" in item["sensor_id"] for item in states + binaries)
    entities = [
        ModBusStateSensorEntity(coordinator(device, {}), device, Entry(), states[0]),
        *(
            ModBusDescribedBinarySensorEntity(
                coordinator(
                    device, {"binary_sensors": {item["sensor_id"]: {"state": None}}}
                ),
                device,
                Entry(),
                item,
            )
            for item in binaries
        ),
    ]
    assert {entity.unique_id for entity in entities} == {
        f"{device.attr_unique_id_prefix}_{key}"
        for key in (
            "glass_break_state",
            "glass_break",
            "enclosure_tamper",
            "equipment_fault",
        )
    }
    assert all(
        entity.device_info["identifiers"]
        == {(Config.DOMAIN, device.attr_device_identifier)}
        for entity in entities
    )


@pytest.mark.parametrize(
    ("state", "icon"),
    [
        ("armed", "mdi:glass-fragile"),
        ("intrusion_alarm", "mdi:alarm-light"),
        ("equipment_fault", "mdi:alert-circle"),
        ("unknown_999", "mdi:help-circle-outline"),
    ],
)
def test_dynamic_icons_use_wired_glass_break_semantics(state, icon):
    device = configured()
    entity = ModBusStateSensorEntity(
        coordinator(device, {"state_sensors": {"glass_break_state": {"state": state}}}),
        device,
        Entry(),
        device.get_state_sensor_descriptions()[0],
    )
    assert entity.icon == icon


@pytest.mark.parametrize(
    ("sensor_id", "state", "icon"),
    [
        ("glass_break", None, "mdi:help-circle-outline"),
        ("glass_break", True, "mdi:alarm-light"),
        ("glass_break", False, "mdi:glass-fragile"),
        ("enclosure_tamper", None, "mdi:shield-question"),
        ("enclosure_tamper", True, "mdi:shield-lock-open"),
        ("enclosure_tamper", False, "mdi:shield-check"),
        ("equipment_fault", None, "mdi:help-circle-outline"),
        ("equipment_fault", True, "mdi:alert-circle"),
        ("equipment_fault", False, "mdi:check-circle"),
    ],
)
def test_binary_icons_preserve_alarm_tamper_fault_and_unknown_semantics(
    sensor_id, state, icon
):
    device = configured()
    description = next(
        item
        for item in device.get_binary_sensor_descriptions()
        if item["sensor_id"] == sensor_id
    )
    entity = ModBusDescribedBinarySensorEntity(
        coordinator(device, {"binary_sensors": {sensor_id: {"state": state}}}),
        device,
        Entry(),
        description,
    )
    assert entity.icon == icon


@pytest.mark.parametrize("failure", ["empty", "invalid", "truncated", "error"])
@pytest.mark.asyncio
async def test_communication_failures_are_not_normal(failure):
    with pytest.raises((ModbusException, ValueError)):
        await configured(Client(failure=failure)).async_get_snapshot()
