"""Focused tests for the radio С2000Р-ИП heat detector."""

from types import SimpleNamespace

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.binary_sensor import (
    ModBusDescribedBinarySensorEntity,
)
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.bolid import C2000RIP
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
from custom_components.modbus_devices.s2000_pp import manual_zone_mapping
from custom_components.modbus_devices.sensor import ModBusStateSensorEntity


DOCUMENTED_NORMAL_EXPANDED = (
    24,
    200,
    213,
    47,
    188,
    251,
    111,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
)


class Response:
    def __init__(self, registers, function_code):
        self.registers = list(registers)
        self.function_code = function_code

    def isError(self):
        return False


class Client:
    def __init__(self, primary=0x18C8, expanded=DOCUMENTED_NORMAL_EXPANDED):
        self.primary = primary
        self.expanded = tuple(expanded)

    async def read_holding_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (40000, 1, 1)
        return Response((self.primary,), 3)

    async def read_input_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (4096, 16, 1)
        return Response((self.expanded + (0,) * 16)[:16], 4)


class Entry:
    entry_id = "rip-entry"
    options = {Config.CONF_GATEWAY_ENTRY_ID: "gateway-entry"}
    data = {}


def mapping(local=40, zone_type=1):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "tcp:pp", 1),
            "C2000RIP",
            10,
            DPLSSubIdentity(40, 1),
            DownstreamDeviceMetadata(),
        ),
        MappingSource.MANUAL,
        (manual_zone_mapping(local, 1, zone_type, 0, None),),
    )


def configured(client=None):
    device = C2000RIP(client, 1)
    device.apply_gateway_mapping(mapping())
    return device


def coordinator(device, data):
    return SimpleNamespace(data=data, device=device, last_update_success=True)


def test_registration_topology_identity_and_documented_metadata():
    device = configured()
    assert "C2000RIP" in get_equipment_classes_by_manufacturer()["Bolid"]
    assert device.attr_model_name == "С2000Р-ИП"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(40, 1)
    assert device.attr_device_metadata["dpls_address_count"] == 1
    assert device.attr_device_metadata["supported_kdl_input_types"] == (3, 6, 9, 10, 21)
    assert device.attr_device_metadata["documented_target_firmware"] == "1.30"
    assert device.attr_platforms == [Platform.SENSOR, Platform.BINARY_SENSOR]
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert device.attr_hardware_version is None
    assert (
        not {"rssi", "lqi", "rf_channel", "radio_address", "route"}
        & device.attr_device_metadata.keys()
    )


def test_physical_temperature_does_not_invent_unlisted_pp_numeric_transport():
    device = configured()
    assert (
        "temperature_measurement"
        in device.attr_device_metadata["physical_capabilities"]
    )
    assert "not confirmed" in device.attr_device_metadata["transport_limitation"]
    assert not hasattr(device, "get_numeric_sensor_descriptions")


def test_generic_communication_codes_are_not_renamed_as_radio_link_metrics():
    assert C2000RIP._state_name(187) == "input_communication_lost"
    assert C2000RIP._state_name(188) == "input_communication_restored"
    assert C2000RIP._state_name(250) == "device_communication_lost"
    assert C2000RIP._state_name(251) == "device_communication_restored"


@pytest.mark.parametrize(
    ("local", "zone_type"), [(20, 1), (39, 1), (41, 1), (0, 3), (40, 6)]
)
def test_exact_own_pp_type_one_row_is_required_not_kdl_input_type(local, zone_type):
    with pytest.raises(ValueError):
        C2000RIP(None, 1).apply_gateway_mapping(mapping(local, zone_type))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("primary", "expected"),
    [
        (0x18C8, "armed"),
        (0x25C8, "fire"),
        (0x2BC8, "warning"),
        (0x2CC8, "attention"),
        (0x29C8, "equipment_fault"),
        (0x13C8, "test"),
        (0xFEC8, "unknown_254"),
    ],
)
async def test_documented_primary_states_and_unknown_are_lossless(primary, expected):
    detector = (await configured(Client(primary=primary)).async_get_snapshot())[
        "state_sensors"
    ]["detector_state"]
    assert detector["state"] == expected
    assert detector["primary_code"] == primary >> 8


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expanded", "main", "reserve"),
    [
        ((24, 200, 213), "battery_restored", "reserve_battery_restored"),
        ((24, 211, 213), "battery_low", "reserve_battery_restored"),
        ((24, 202, 212), "battery_fault", "reserve_battery_low"),
        ((24, 200, 202, 213), None, "reserve_battery_restored"),
        ((24, 47, 188, 251, 111, 999), None, None),
    ],
)
async def test_documented_battery_channels_are_conservative_and_lossless(
    expanded, main, reserve
):
    snapshot = await configured(Client(expanded=expanded)).async_get_snapshot()
    states = snapshot["state_sensors"]
    assert states["main_battery_state"]["state"] == main
    assert states["reserve_battery_state"]["state"] == reserve
    detector = states["detector_state"]
    assert detector["expanded_codes"] == expanded + (0,) * (16 - len(expanded))
    if 999 in expanded:
        assert "unknown_999" in detector["expanded_states"]


@pytest.mark.asyncio
async def test_documented_tamper_lifecycle_is_explicit_stateful_and_idempotent():
    device = configured(Client())
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is None
    device.attr_client = Client(primary=0x9518, expanded=(149, 24, 200, 213))
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is True
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is True
    device.attr_client = Client(primary=0x18C8, expanded=DOCUMENTED_NORMAL_EXPANDED)
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is True
    device.attr_client = Client(expanded=(24, 200, 213, 152, 188, 251, 111))
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is False
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"][
        "state"
    ] is False


@pytest.mark.asyncio
async def test_measurement_fault_requires_explicit_fault_or_restore_code():
    device = configured(Client())
    assert (await device.async_get_snapshot())["binary_sensors"]["measurement_fault"][
        "state"
    ] is None
    device.attr_client = Client(primary=0x52C8, expanded=(82, 24, 200, 213))
    assert (await device.async_get_snapshot())["binary_sensors"]["measurement_fault"][
        "state"
    ] is True
    assert (await device.async_get_snapshot())["binary_sensors"]["measurement_fault"][
        "state"
    ] is True
    device.attr_client = Client(expanded=DOCUMENTED_NORMAL_EXPANDED)
    assert (await device.async_get_snapshot())["binary_sensors"]["measurement_fault"][
        "state"
    ] is True
    device.attr_client = Client(expanded=(24, 200, 213, 83, 188, 251, 111))
    assert (await device.async_get_snapshot())["binary_sensors"]["measurement_fault"][
        "state"
    ] is False


def test_entity_matrix_unique_ids_and_one_physical_device_are_stable():
    device = configured()
    state_descriptions = device.get_state_sensor_descriptions()
    binary_descriptions = device.get_binary_sensor_descriptions()
    entities = [
        *(
            ModBusStateSensorEntity(coordinator(device, {}), device, Entry(), item)
            for item in state_descriptions
        ),
        *(
            ModBusDescribedBinarySensorEntity(
                coordinator(
                    device, {"binary_sensors": {item["sensor_id"]: {"state": None}}}
                ),
                device,
                Entry(),
                item,
            )
            for item in binary_descriptions
        ),
    ]
    assert [item["sensor_id"] for item in state_descriptions] == [
        "detector_state",
        "main_battery_state",
        "reserve_battery_state",
    ]
    assert [item["sensor_id"] for item in binary_descriptions] == [
        "enclosure_tamper",
        "measurement_fault",
    ]
    assert binary_descriptions[0]["device_class"] is BinarySensorDeviceClass.TAMPER
    assert binary_descriptions[1]["device_class"] is BinarySensorDeviceClass.PROBLEM
    assert all(item["enabled_default"] is True for item in binary_descriptions)
    assert all(
        item["entity_category"] is EntityCategory.DIAGNOSTIC
        for item in binary_descriptions
    )
    assert {entity.unique_id for entity in entities} == {
        f"{device.attr_unique_id_prefix}_{key}"
        for key in (
            "detector_state",
            "main_battery_state",
            "reserve_battery_state",
            "enclosure_tamper",
            "measurement_fault",
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
        ("armed", "mdi:thermometer"),
        ("temperature_normal", "mdi:thermometer"),
        ("fire", "mdi:fire-alert"),
        ("attention", "mdi:fire-alert"),
        ("temperature_sensor_fault", "mdi:alert-circle"),
        ("unknown_999", "mdi:help-circle-outline"),
    ],
)
def test_heat_detector_dynamic_icons_use_semantic_state(state, icon):
    device = configured()
    description = device.get_state_sensor_descriptions()[0]
    entity = ModBusStateSensorEntity(
        coordinator(
            device,
            {
                "state_sensors": {
                    "detector_state": {
                        "state": state,
                        "primary_code": 999,
                        "expanded_codes": (),
                        "expanded_states": (),
                    }
                }
            },
        ),
        device,
        Entry(),
        description,
    )
    assert entity.icon == icon


@pytest.mark.parametrize(
    ("sensor_id", "state", "icon"),
    [
        ("main_battery_state", "battery_restored", "mdi:battery-check"),
        ("main_battery_state", "battery_low", "mdi:battery-alert"),
        ("main_battery_state", "battery_fault", "mdi:battery-alert"),
        ("reserve_battery_state", "reserve_battery_restored", "mdi:battery-check"),
        ("reserve_battery_state", "reserve_battery_low", "mdi:battery-alert"),
    ],
)
def test_battery_icons_use_documented_semantic_state(sensor_id, state, icon):
    device = configured()
    description = next(
        item
        for item in device.get_state_sensor_descriptions()
        if item["sensor_id"] == sensor_id
    )
    entity = ModBusStateSensorEntity(
        coordinator(
            device,
            {"state_sensors": {sensor_id: {"state": state}}},
        ),
        device,
        Entry(),
        description,
    )
    assert entity.icon == icon


@pytest.mark.parametrize(
    ("sensor_id", "state", "icon"),
    [
        ("enclosure_tamper", None, "mdi:shield-question"),
        ("enclosure_tamper", True, "mdi:shield-lock-open"),
        ("enclosure_tamper", False, "mdi:shield-check"),
        ("measurement_fault", None, "mdi:thermometer-question"),
        ("measurement_fault", True, "mdi:thermometer-alert"),
        ("measurement_fault", False, "mdi:thermometer-check"),
    ],
)
def test_diagnostic_binary_icons_preserve_unknown(sensor_id, state, icon):
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
