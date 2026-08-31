"""Focused tests for the radio С2000Р-ДИП smoke detector."""

from types import SimpleNamespace

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.binary_sensor import ModBusDescribedBinarySensorEntity
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.bolid import C2000RDIP
from custom_components.modbus_devices.equipment.equipment import get_equipment_classes_by_manufacturer
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity, DownstreamDeviceIdentity, DownstreamDeviceMetadata,
    GatewayContext, GatewayType, MappingSource, ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import manual_zone_mapping
from custom_components.modbus_devices.sensor import ModBusStateSensorEntity


HARDWARE_NORMAL_EXPANDED = (
    24, 200, 213, 47, 188, 251, 111, 0, 0, 0, 0, 0, 0, 0, 0, 0
)


class Response:
    def __init__(self, registers, function_code):
        self.registers = list(registers)
        self.function_code = function_code

    def isError(self):
        return False


class Client:
    """Return one exact row-29-shaped grouped state response."""

    def __init__(self, primary=0x18C8, expanded=HARDWARE_NORMAL_EXPANDED):
        self.primary = primary
        self.expanded = tuple(expanded)

    async def read_holding_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (40028, 1, 2)
        return Response((self.primary,), 3)

    async def read_input_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (4544, 16, 2)
        return Response((self.expanded + (0,) * 16)[:16], 4)


class Entry:
    entry_id = "rdip-entry"
    options = {Config.CONF_GATEWAY_ENTRY_ID: "gateway-entry"}
    data = {}


def mapping(*objects, base=4, orion=3, connection="serial:com3"):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", connection, 2),
            "C2000RDIP", orion, DPLSSubIdentity(base, 1),
            DownstreamDeviceMetadata(),
        ),
        MappingSource.MANUAL,
        objects,
    )


def configured(client=None):
    device = C2000RDIP(client, 2)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(4, 29, 1, 28, None)))
    return device


def coordinator(device, data):
    return SimpleNamespace(data=data, device=device, last_update_success=True)


def test_registration_mapping_identity_and_runtime_metadata_are_product_specific():
    device = configured()
    assert "C2000RDIP" in get_equipment_classes_by_manufacturer()["Bolid"]
    assert device.attr_model_name == "С2000Р-ДИП"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(4, 1)
    assert device.attr_platforms == [Platform.SENSOR, Platform.BINARY_SENSOR]
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert device.attr_hardware_version is None
    assert device.attr_device_metadata["dpls_address_count"] == 1
    assert not {"rssi", "lqi", "rf_channel", "radio_address", "route"} & (
        device.attr_device_metadata.keys()
    )


@pytest.mark.parametrize(("local", "zone_type"), [(0, 3), (3, 1), (5, 1), (4, 6)])
def test_only_exact_own_pp_zone_type_one_is_accepted(local, zone_type):
    with pytest.raises(ValueError):
        C2000RDIP(None, 2).apply_gateway_mapping(
            mapping(manual_zone_mapping(local, 29, zone_type, 28, None))
        )


@pytest.mark.asyncio
async def test_two_unit_hardware_normal_fixture_is_lossless_and_exposes_batteries():
    """HARDWARE FIXTURE: two independent units returned this exact tuple."""
    for dpls, row in ((4, 29), (5, 30)):
        client = Client()
        if row == 30:
            async def holding(*, address, count, device_id):
                assert (address, count, device_id) == (40029, 1, 2)
                return Response((0x18C8,), 3)

            async def inputs(*, address, count, device_id):
                assert (address, count, device_id) == (4560, 16, 2)
                return Response(HARDWARE_NORMAL_EXPANDED, 4)

            client.read_holding_registers = holding
            client.read_input_registers = inputs
        device = C2000RDIP(client, 2)
        device.apply_gateway_mapping(
            ResolvedDeviceMapping(
                DownstreamDeviceIdentity(
                    GatewayContext(GatewayType.S2000_PP, "pp", "serial:com3", 2),
                    "C2000RDIP", 3, DPLSSubIdentity(dpls, 1),
                    DownstreamDeviceMetadata(),
                ),
                MappingSource.MANUAL,
                (manual_zone_mapping(dpls, row, 1, 28, None),),
            )
        )
        snapshot = await device.async_get_snapshot()
        detector = snapshot["state_sensors"]["detector_state"]
        assert detector["state"] == "armed"
        assert detector["primary_code"] == 24
        assert detector["expanded_codes"] == HARDWARE_NORMAL_EXPANDED
        assert detector["expanded_states"] == (
            "armed", "battery_restored", "reserve_battery_restored",
            "dpls_restored", "input_communication_restored",
            "device_communication_restored", "input_control_enabled",
        )
        assert snapshot["state_sensors"]["main_battery_state"]["state"] == "battery_restored"
        assert snapshot["state_sensors"]["reserve_battery_state"]["state"] == "reserve_battery_restored"
        assert snapshot["binary_sensors"]["enclosure_tamper"]["state"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("primary", "expected"),
    [
        (0x18C8, "armed"),
        (0x25C8, "fire"),
        (0x2BC8, "warning"),
        (0x29C8, "equipment_fault"),
        (0xFEC8, "unknown_254"),
    ],
)
async def test_primary_smoke_states_and_unknown_code_are_lossless(primary, expected):
    device = configured(Client(primary=primary))
    detector = (await device.async_get_snapshot())["state_sensors"]["detector_state"]
    assert detector["state"] == expected
    assert detector["primary_code"] == (primary >> 8)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expanded", "main", "reserve"),
    [
        ((24, 211, 213), "battery_low", "reserve_battery_restored"),
        ((24, 202, 212), "battery_fault", "reserve_battery_low"),
        ((24, 200, 202, 213), None, "reserve_battery_restored"),
        ((24, 47, 188, 251, 111, 999), None, None),
    ],
)
async def test_documented_battery_states_are_conservative_and_lossless(expanded, main, reserve):
    """Active codes are documented; only 200/213 are hardware-observed here."""
    device = configured(Client(expanded=expanded))
    snapshot = await device.async_get_snapshot()
    assert snapshot["state_sensors"]["main_battery_state"]["state"] == main
    assert snapshot["state_sensors"]["reserve_battery_state"]["state"] == reserve
    detector = snapshot["state_sensors"]["detector_state"]
    assert detector["expanded_codes"] == expanded + (0,) * (16 - len(expanded))
    if 999 in expanded:
        assert "unknown_999" in detector["expanded_states"]


@pytest.mark.asyncio
async def test_documented_future_tamper_codes_have_stateful_unknown_lifecycle():
    """DOCUMENTED fixture: 149/152 were not observed in current PP hardware."""
    device = configured(Client())
    baseline = await device.async_get_snapshot()
    assert baseline["binary_sensors"]["enclosure_tamper"]["state"] is None

    device.attr_client = Client(expanded=(24, 149, 200, 213, 999))
    opened = await device.async_get_snapshot()
    assert opened["binary_sensors"]["enclosure_tamper"]["state"] is True
    assert "unknown_999" in opened["state_sensors"]["detector_state"]["expanded_states"]

    device.attr_client = Client()
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"]["state"] is True

    device.attr_client = Client(expanded=(24, 149, 152, 200, 213))
    conflicting = await device.async_get_snapshot()
    assert conflicting["binary_sensors"]["enclosure_tamper"]["state"] is True

    device.attr_client = Client(expanded=(24, 152, 200, 213))
    restored = await device.async_get_snapshot()
    assert restored["binary_sensors"]["enclosure_tamper"]["state"] is False

    device.attr_client = Client()
    assert (await device.async_get_snapshot())["binary_sensors"]["enclosure_tamper"]["state"] is False


def test_entity_matrix_identity_device_grouping_and_tamper_defaults():
    device = configured()
    descriptions = device.get_state_sensor_descriptions()
    state_entities = [
        ModBusStateSensorEntity(coordinator(device, {}), device, Entry(), item)
        for item in descriptions
    ]
    tamper_description = device.get_binary_sensor_descriptions()[0]
    tamper = ModBusDescribedBinarySensorEntity(
        coordinator(device, {"binary_sensors": {"enclosure_tamper": {"state": None}}}),
        device, Entry(), tamper_description,
    )
    entities = [*state_entities, tamper]
    assert [item["sensor_id"] for item in descriptions] == [
        "detector_state", "main_battery_state", "reserve_battery_state"
    ]
    assert tamper_description["device_class"] is BinarySensorDeviceClass.TAMPER
    assert tamper_description["entity_category"] is EntityCategory.DIAGNOSTIC
    assert tamper.entity_registry_enabled_default is False
    assert tamper.is_on is None
    assert {entity.unique_id for entity in entities} == {
        f"{device.attr_unique_id_prefix}_{key}"
        for key in ("detector_state", "main_battery_state", "reserve_battery_state", "enclosure_tamper")
    }
    assert all(
        entity.device_info["identifiers"] == {(Config.DOMAIN, device.attr_device_identifier)}
        for entity in entities
    )
    assert all(entity.device_info["via_device"] == (Config.DOMAIN, "gateway-entry") for entity in entities)


@pytest.mark.parametrize(
    ("state", "icon"),
    [
        ("armed", "mdi:smoke-detector"),
        ("fire", "mdi:smoke-detector-alert"),
        ("attention", "mdi:smoke-detector-alert"),
        ("equipment_fault", "mdi:alert-circle"),
        ("unknown_999", "mdi:help-circle-outline"),
    ],
)
def test_detector_dynamic_icons_use_semantic_state(state, icon):
    device = configured()
    current = {"state_sensors": {"detector_state": {
        "state": state, "primary_code": 999, "expanded_codes": (), "expanded_states": (),
    }}}
    entity = ModBusStateSensorEntity(
        coordinator(device, current), device, Entry(), device.get_state_sensor_descriptions()[0]
    )
    assert entity.icon == icon


@pytest.mark.parametrize(
    ("sensor_id", "state", "icon"),
    [
        ("main_battery_state", "battery_restored", "mdi:battery-check"),
        ("main_battery_state", "battery_low", "mdi:battery-alert"),
        ("reserve_battery_state", "reserve_battery_restored", "mdi:battery-check"),
        ("reserve_battery_state", "reserve_battery_low", "mdi:battery-alert"),
        ("main_battery_state", None, "mdi:battery"),
    ],
)
def test_battery_dynamic_icons_use_decoded_state(sensor_id, state, icon):
    device = configured()
    description = next(
        item for item in device.get_state_sensor_descriptions()
        if item["sensor_id"] == sensor_id
    )
    current = {"state_sensors": {sensor_id: {
        "state": state, "primary_code": 24,
        "expanded_codes": HARDWARE_NORMAL_EXPANDED,
        "expanded_states": (),
    }}}
    entity = ModBusStateSensorEntity(
        coordinator(device, current), device, Entry(), description
    )
    assert entity.icon == icon


@pytest.mark.parametrize(
    ("state", "icon"),
    [(None, "mdi:shield-question"), (True, "mdi:shield-lock-open"), (False, "mdi:shield-check")],
)
def test_tamper_dynamic_icons_preserve_unknown(state, icon):
    device = configured()
    entity = ModBusDescribedBinarySensorEntity(
        coordinator(device, {"binary_sensors": {"enclosure_tamper": {"state": state}}}),
        device, Entry(), device.get_binary_sensor_descriptions()[0],
    )
    assert entity.icon == icon
