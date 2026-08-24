"""Tests for universal dynamic Modbus Devices presentation."""

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.presentation import async_build_device_card
from custom_components.modbus_devices.presentation import builder
from custom_components.modbus_devices.presentation.profile import (
    PresentationProfile,
    PresentationRole,
)
from custom_components.modbus_devices.presentation.registry import (
    DevicePresentationRegistry,
)


@dataclass
class Device:
    id: str
    identifier: str
    manufacturer: str = "Bolid"
    model: str = "Test model"
    name: str = "Test device"
    name_by_user: str | None = None
    area_id: str | None = None
    config_entry_id: str = "entry-1"
    via_device_id: str | None = None
    identifiers: set[tuple[str, str]] = field(init=False)
    config_entries: set[str] = field(init=False)
    primary_config_entry: str = field(init=False)

    def __post_init__(self) -> None:
        self.identifiers = {(Config.DOMAIN, self.identifier)}
        self.config_entries = {self.config_entry_id}
        self.primary_config_entry = self.config_entry_id


@dataclass
class Entity:
    entity_id: str
    unique_id: str
    device_id: str
    domain: str = "sensor"
    platform: str = Config.DOMAIN
    disabled_by: object | None = None
    entity_category: EntityCategory | None = None
    state: str | None = None


class DeviceRegistry:
    def __init__(self, devices: list[Device]) -> None:
        self.devices = {device.id: device for device in devices}

    def async_get(self, device_id: str):
        return self.devices.get(device_id)


class EntityRegistry:
    def __init__(self, entities: list[Entity]) -> None:
        self.entities = entities


class ConfigEntries:
    def __init__(self, entries: dict[str, object]) -> None:
        self.entries = entries

    def async_get_entry(self, entry_id: str):
        return self.entries.get(entry_id)


def config_entry(manufacturer: str, equipment_class: str):
    return SimpleNamespace(
        domain=Config.DOMAIN,
        options={
            Config.CONF_MANUFACTURER: manufacturer,
            Config.CONF_DEVICE_CLASS: equipment_class,
        },
        data={},
    )


@pytest.fixture
def registry_hass(monkeypatch):
    def factory(
        devices: list[Device],
        entities: list[Entity],
        entries: dict[str, object],
    ):
        hass = SimpleNamespace(
            device_registry=DeviceRegistry(devices),
            entity_registry=EntityRegistry(entities),
            config_entries=ConfigEntries(entries),
            states={},
        )
        return hass

    monkeypatch.setattr(builder.dr, "async_get", lambda hass: hass.device_registry)
    monkeypatch.setattr(builder.er, "async_get", lambda hass: hass.entity_registry)
    monkeypatch.setattr(
        builder.er,
        "async_entries_for_device",
        lambda registry, device_id: [
            entity
            for entity in registry.entities
            if entity.device_id == device_id and entity.disabled_by is None
        ],
    )
    return factory


def entity(
    device: Device,
    role: str,
    *,
    entity_id: str | None = None,
    domain: str = "sensor",
    category: EntityCategory | None = None,
    disabled: bool = False,
    state: str | None = None,
) -> Entity:
    return Entity(
        entity_id or f"{domain}.{device.id}_{role}",
        f"{device.identifier}_{role}",
        device.id,
        domain,
        disabled_by="user" if disabled else None,
        entity_category=category,
        state=state,
    )


async def build(factory, device: Device, entities: list[Entity], equipment: str):
    hass = factory(
        [device],
        entities,
        {device.config_entry_id: config_entry(device.manufacturer, equipment)},
    )
    return await async_build_device_card(hass, device.id)


@pytest.mark.asyncio
async def test_unknown_manufacturer_and_model_use_generic_fallback(registry_hass):
    device = Device(
        "future",
        "future-id",
        manufacturer="Example Manufacturer",
        model="Future Modbus Device",
    )
    result = await build(
        registry_hass,
        device,
        [entity(device, "value"), entity(device, "alarm")],
        "FutureDeviceV2",
    )

    assert result.profile_id == "generic"
    assert result.card["entities"] == ["sensor.future_alarm", "sensor.future_value"]


@pytest.mark.asyncio
async def test_future_manufacturer_can_register_without_changing_builder(registry_hass):
    device = Device(
        "future",
        "future-id",
        manufacturer="Example Manufacturer",
        model="Future Modbus Device",
    )
    hass = registry_hass(
        [device],
        [entity(device, "second"), entity(device, "first")],
        {
            device.config_entry_id: config_entry(
                "Example Manufacturer", "FutureDevice"
            )
        },
    )
    profiles = DevicePresentationRegistry()
    profiles.register_equipment(
        "Example Manufacturer",
        "FutureDevice",
        PresentationProfile(
            "example_future",
            roles=(PresentationRole("first"), PresentationRole("second")),
        ),
    )

    result = await async_build_device_card(hass, device.id, profiles=profiles)
    assert result.profile_id == "example_future"
    assert result.card["entities"] == [
        "sensor.future_first",
        "sensor.future_second",
    ]


@pytest.mark.asyncio
async def test_device_with_no_enabled_entities_returns_none(registry_hass):
    device = Device("empty", "empty-id")
    result = await build(
        registry_hass,
        device,
        [entity(device, "temperature", disabled=True)],
        "C2000VT",
    )
    assert result is None


@pytest.mark.asyncio
async def test_non_modbus_device_is_ignored(registry_hass):
    device = Device("foreign", "foreign-id")
    device.identifiers = {("tasmota", "foreign-id")}
    hass = registry_hass(
        [device],
        [entity(device, "power")],
        {device.config_entry_id: config_entry("Other", "Other")},
    )
    assert await async_build_device_card(hass, device.id) is None


@pytest.mark.asyncio
async def test_c2000_vt_card_expands_and_shrinks_with_registry(registry_hass):
    device = Device("vt", "vt-stable", model="С2000-ВТ")
    temperature = entity(device, "temperature")
    temperature_state = entity(
        device, "temperature_state", category=EntityCategory.DIAGNOSTIC
    )
    humidity = entity(device, "humidity")
    humidity_state = entity(
        device, "humidity_state", category=EntityCategory.DIAGNOSTIC
    )
    hass = registry_hass(
        [device],
        [temperature],
        {device.config_entry_id: config_entry("Bolid", "C2000VT")},
    )

    first = await async_build_device_card(hass, device.id)
    assert first.card["entities"] == ["sensor.vt_temperature"]

    hass.entity_registry.entities.append(temperature_state)
    second = await async_build_device_card(hass, device.id)
    assert second.card["entities"] == [
        "sensor.vt_temperature",
        "sensor.vt_temperature_state",
    ]

    hass.entity_registry.entities.extend((humidity, humidity_state))
    expanded = await async_build_device_card(hass, device.id)
    assert expanded.card["entities"] == [
        "sensor.vt_temperature",
        "sensor.vt_humidity",
        "sensor.vt_temperature_state",
        "sensor.vt_humidity_state",
    ]

    hass.entity_registry.entities.remove(humidity)
    shrunk = await async_build_device_card(hass, device.id)
    assert shrunk.card["entities"] == [
        "sensor.vt_temperature",
        "sensor.vt_temperature_state",
        "sensor.vt_humidity_state",
    ]


@pytest.mark.asyncio
async def test_disabled_is_excluded_but_unavailable_is_included(registry_hass):
    device = Device("vt", "vt-stable")
    result = await build(
        registry_hass,
        device,
        [
            entity(device, "temperature", state="unavailable"),
            entity(device, "humidity", disabled=True),
            entity(
                device,
                "temperature_state",
                category=EntityCategory.DIAGNOSTIC,
                disabled=True,
            ),
        ],
        "C2000VT",
    )
    assert result.card["entities"] == ["sensor.vt_temperature"]


@pytest.mark.asyncio
async def test_entity_and_device_user_renames_are_respected(registry_hass):
    device = Device(
        "vt",
        "vt-stable",
        name="Addressable temperature and humidity sensor",
        name_by_user="C2000-VT Balcony",
    )
    renamed = entity(
        device,
        "temperature",
        entity_id="sensor.balcony_temperature",
    )
    result = await build(registry_hass, device, [renamed], "C2000VT")

    assert result.card == {
        "type": "entities",
        "title": "C2000-VT Balcony",
        "show_header_toggle": False,
        "entities": ["sensor.balcony_temperature"],
    }


@pytest.mark.asyncio
async def test_primary_precedes_diagnostic_and_unknown_config_is_excluded(
    registry_hass,
):
    device = Device(
        "future",
        "future-id",
        manufacturer="Example Manufacturer",
    )
    result = await build(
        registry_hass,
        device,
        [
            entity(device, "diagnostic", category=EntityCategory.DIAGNOSTIC),
            entity(device, "primary"),
            entity(device, "setting", category=EntityCategory.CONFIG),
        ],
        "NewEquipment",
    )
    assert result.card["entities"] == [
        "sensor.future_primary",
        "sensor.future_diagnostic",
    ]


@pytest.mark.asyncio
async def test_kpb_outputs_follow_physical_order(registry_hass):
    device = Device("kpb", "kpb-stable", model="С2000-КПБ")
    result = await build(
        registry_hass,
        device,
        [
            entity(device, "output_6", domain="switch"),
            entity(device, "output_2", domain="switch"),
            entity(device, "output_4", domain="switch"),
            entity(device, "output_1", domain="switch"),
            entity(device, "output_5", domain="switch"),
            entity(device, "output_3", domain="switch"),
        ],
        "C2000KPB",
    )
    assert result.card["entities"] == [
        "switch.kpb_output_1",
        "switch.kpb_output_2",
        "switch.kpb_output_3",
        "switch.kpb_output_4",
        "switch.kpb_output_5",
        "switch.kpb_output_6",
    ]


@pytest.mark.asyncio
async def test_two_kpb_devices_build_separate_cards(registry_hass):
    first = Device("kpb-9", "kpb-9-stable", config_entry_id="entry-9")
    second = Device("kpb-10", "kpb-10-stable", config_entry_id="entry-10")
    entities = [
        entity(first, "output_1", domain="switch"),
        entity(second, "output_1", domain="switch"),
    ]
    hass = registry_hass(
        [first, second],
        entities,
        {
            "entry-9": config_entry("Bolid", "C2000KPB"),
            "entry-10": config_entry("Bolid", "C2000KPB"),
        },
    )
    first_card = await async_build_device_card(hass, first.id)
    second_card = await async_build_device_card(hass, second.id)

    assert first_card.card["entities"] == ["switch.kpb-9_output_1"]
    assert second_card.card["entities"] == ["switch.kpb-10_output_1"]


@pytest.mark.asyncio
async def test_gateway_topology_does_not_change_child_card(registry_hass):
    direct = Device("direct", "direct-stable", config_entry_id="direct-entry")
    child = Device(
        "child",
        "child-stable",
        config_entry_id="child-entry",
        via_device_id="gateway-device-id",
    )
    direct_entity = entity(
        direct,
        "temperature",
        entity_id="sensor.temperature",
    )
    child_entity = entity(
        child,
        "temperature",
        entity_id="sensor.temperature",
    )
    entries = {
        "direct-entry": config_entry("Bolid", "C2000VT"),
        "child-entry": config_entry("Bolid", "C2000VT"),
    }
    direct_hass = registry_hass([direct], [direct_entity], entries)
    child_hass = registry_hass([child], [child_entity], entries)

    direct_card = await async_build_device_card(direct_hass, direct.id)
    child_card = await async_build_device_card(child_hass, child.id)
    assert direct_card.card["entities"] == child_card.card["entities"]


@pytest.mark.asyncio
async def test_same_bolid_model_behind_different_gateways_stays_separate(
    registry_hass,
):
    first = Device(
        "vt-a", "gateway-a:vt", config_entry_id="vt-a-entry", via_device_id="pp-a"
    )
    second = Device(
        "vt-b", "gateway-b:vt", config_entry_id="vt-b-entry", via_device_id="pp-b"
    )
    hass = registry_hass(
        [first, second],
        [entity(first, "temperature"), entity(second, "temperature")],
        {
            "vt-a-entry": config_entry("Bolid", "C2000VT"),
            "vt-b-entry": config_entry("Bolid", "C2000VT"),
        },
    )
    first_card = await async_build_device_card(hass, first.id)
    second_card = await async_build_device_card(hass, second.id)

    assert first_card.device_id == "vt-a"
    assert second_card.device_id == "vt-b"
    assert first_card.card["entities"] == ["sensor.vt-a_temperature"]
    assert second_card.card["entities"] == ["sensor.vt-b_temperature"]


@pytest.mark.asyncio
async def test_sp4_partial_capabilities_keep_operational_order(registry_hass):
    device = Device("sp4", "sp4-stable", model="С2000-СП4/24")
    result = await build(
        registry_hass,
        device,
        [
            entity(device, "working_limit_switch"),
            entity(device, "actuator_state"),
            entity(device, "output_1", domain="switch"),
        ],
        "C2000SP4",
    )
    assert result.card["entities"] == [
        "switch.sp4_output_1",
        "sensor.sp4_actuator_state",
        "sensor.sp4_working_limit_switch",
    ]


@pytest.mark.asyncio
async def test_direct_owen_trm138_uses_generic_card_without_gateway(registry_hass):
    device = Device(
        "trm138",
        "trm138-entry",
        manufacturer="Owen",
        model="TRM-138",
        name="TRM-138 Greenhouse",
    )
    result = await build(
        registry_hass,
        device,
        [
            entity(device, "2", entity_id="sensor.trm138_temperature_2"),
            entity(device, "1", entity_id="sensor.trm138_temperature_1"),
        ],
        "TRM138",
    )

    assert result.profile_id == "generic"
    assert result.card == {
        "type": "entities",
        "title": "TRM-138 Greenhouse",
        "show_header_toggle": False,
        "entities": [
            "sensor.trm138_temperature_1",
            "sensor.trm138_temperature_2",
        ],
    }


@pytest.mark.asyncio
async def test_area_id_is_metadata_not_card_grouping(registry_hass):
    device = Device("vt", "vt-stable", area_id="balcony")
    result = await build(
        registry_hass,
        device,
        [entity(device, "temperature")],
        "C2000VT",
    )
    assert result.area_id == "balcony"
    assert "area" not in result.card
