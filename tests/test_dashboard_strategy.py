"""Tests for the dynamic Modbus Devices dashboard strategy."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.dashboard import builder
from custom_components.modbus_devices.dashboard.frontend import (
    DEVICE_CARD_TAG,
    STRATEGY_MODULE_URL,
    WS_BUILD_DEVICE_CARD,
    async_build_device_card_config,
    strategy_module_url,
)
from custom_components.modbus_devices.presentation.profile import DevicePresentation
import pytest


@dataclass
class Device:
    id: str
    name: str
    area_id: str | None = None
    name_by_user: str | None = None
    via_device_id: str | None = None
    identifiers: set[tuple[str, str]] = field(init=False)

    def __post_init__(self) -> None:
        self.identifiers = {(Config.DOMAIN, self.id)}
        self.model = self.name


class DeviceRegistry:
    def __init__(self, devices=()):
        self.devices = {device.id: device for device in devices}


class AreaRegistry:
    def __init__(self, areas=()):
        self.areas = {area.id: area for area in areas}

    def async_get_area(self, area_id):
        return self.areas.get(area_id)


@pytest.fixture
def dashboard_hass(monkeypatch):
    def factory(devices=(), areas=(), cards=None):
        hass = SimpleNamespace(
            device_registry=DeviceRegistry(devices),
            area_registry=AreaRegistry(areas),
            cards=cards or {},
        )
        return hass

    monkeypatch.setattr(builder.dr, "async_get", lambda hass: hass.device_registry)
    monkeypatch.setattr(builder.ar, "async_get", lambda hass: hass.area_registry)

    async def build_card(hass, device_id):
        card = hass.cards.get(device_id)
        if card is None:
            return None
        device = hass.device_registry.devices[device_id]
        return DevicePresentation(device_id, device.area_id, "test", card)

    monkeypatch.setattr(builder, "async_build_device_card", build_card)
    return factory


def card(title, *entities):
    return {
        "type": "entities",
        "title": title,
        "show_header_toggle": False,
        "entities": list(entities),
    }


async def build(hass):
    return await builder.async_build_dashboard(hass)


@pytest.mark.asyncio
async def test_no_devices_returns_valid_empty_sections_dashboard(dashboard_hass):
    result = await build(dashboard_hass())
    assert result["views"][0]["type"] == "sections"
    assert result["views"][0]["sections"] == []


@pytest.mark.asyncio
async def test_same_area_devices_are_indivisible_cards_in_stable_order(
    dashboard_hass,
):
    vt = Device("vt", "C2000-VT", "balcony", via_device_id="pp")
    kpb = Device("kpb", "C2000-KPB", "balcony", via_device_id="pp")
    hass = dashboard_hass(
        [vt, kpb],
        [SimpleNamespace(id="balcony", name="Balcony")],
        {
            "vt": card("C2000-VT", "sensor.temperature", "sensor.temperature_state"),
            "kpb": card("C2000-KPB", "switch.output_1", "switch.output_2"),
        },
    )

    sections = (await build(hass))["views"][0]["sections"]
    assert sections == [
        {
            "type": "grid",
            "cards": [
                {"type": "heading", "heading": "Balcony"},
                hass.cards["kpb"],
                hass.cards["vt"],
            ],
        }
    ]
    assert all(
        config["type"] == "entities" for config in sections[0]["cards"][1:]
    )


@pytest.mark.asyncio
async def test_areas_sort_by_name_and_unassigned_is_last(dashboard_hass):
    devices = [
        Device("workshop", "Bolid direct", "z-area"),
        Device("greenhouse", "Owen TRM-138", "a-area"),
        Device("future", "Future Modbus Device"),
    ]
    hass = dashboard_hass(
        devices,
        [
            SimpleNamespace(id="z-area", name="Workshop"),
            SimpleNamespace(id="a-area", name="Greenhouse"),
        ],
        {device.id: card(device.name, f"sensor.{device.id}") for device in devices},
    )

    sections = (await build(hass))["views"][0]["sections"]
    assert [section["cards"][0]["heading"] for section in sections] == [
        "Greenhouse",
        "Workshop",
        "Unassigned",
    ]


@pytest.mark.asyncio
async def test_rebuild_reflects_entity_device_name_and_area_changes(dashboard_hass):
    vt = Device("vt", "C2000-VT", "balcony")
    hass = dashboard_hass(
        [vt],
        [
            SimpleNamespace(id="balcony", name="Balcony"),
            SimpleNamespace(id="kitchen", name="Kitchen"),
        ],
        {"vt": card("C2000-VT", "sensor.temperature")},
    )
    first = await build(hass)
    assert first["views"][0]["sections"][0]["cards"][1]["entities"] == [
        "sensor.temperature"
    ]

    hass.cards["vt"] = card(
        "C2000-VT Balcony",
        "sensor.renamed_temperature",
        "sensor.humidity",
    )
    vt.name_by_user = "C2000-VT Balcony"
    vt.area_id = "kitchen"
    hass.device_registry.devices["kpb"] = Device("kpb", "C2000-KPB", "balcony")
    hass.cards["kpb"] = card("C2000-KPB", "switch.output_1")

    rebuilt = await build(hass)
    sections = rebuilt["views"][0]["sections"]
    assert [section["cards"][0]["heading"] for section in sections] == [
        "Balcony",
        "Kitchen",
    ]
    assert sections[1]["cards"][1]["title"] == "C2000-VT Balcony"
    assert sections[1]["cards"][1]["entities"] == [
        "sensor.renamed_temperature",
        "sensor.humidity",
    ]

    del hass.device_registry.devices["kpb"]
    assert [
        section["cards"][0]["heading"]
        for section in (await build(hass))["views"][0]["sections"]
    ] == ["Kitchen"]


@pytest.mark.asyncio
async def test_non_modbus_devices_are_ignored(dashboard_hass):
    foreign = Device("foreign", "Tasmota")
    foreign.identifiers = {("tasmota", "foreign")}
    hass = dashboard_hass([foreign], cards={"foreign": card("Tasmota", "switch.x")})
    assert (await build(hass))["views"][0]["sections"] == []


@pytest.mark.asyncio
async def test_via_device_does_not_merge_parent_and_child(dashboard_hass):
    gateway = Device("pp", "S2000-PP")
    child = Device("vt", "C2000-VT", via_device_id="pp")
    hass = dashboard_hass(
        [gateway, child],
        cards={
            "pp": card("S2000-PP", "sensor.gateway"),
            "vt": card("C2000-VT", "sensor.temperature"),
        },
    )
    cards = (await build(hass))["views"][0]["sections"][0]["cards"][1:]
    assert [item["title"] for item in cards] == ["C2000-VT", "S2000-PP"]


@pytest.mark.asyncio
async def test_identically_named_physical_devices_remain_separate(dashboard_hass):
    """Use device id only as a deterministic tie-breaker, never as a title suffix."""
    first = Device("kpb-9", "Control and launch unit", "hallway")
    second = Device("kpb-10", "Control and launch unit", "hallway")
    hass = dashboard_hass(
        [first, second],
        [SimpleNamespace(id="hallway", name="Hallway")],
        {
            "kpb-9": card("Control and launch unit", "switch.kpb_9_output_1"),
            "kpb-10": card("Control and launch unit", "switch.kpb_10_output_1"),
        },
    )

    cards = (await build(hass))["views"][0]["sections"][0]["cards"][1:]
    assert len(cards) == 2
    assert [item["title"] for item in cards] == [
        "Control and launch unit",
        "Control and launch unit",
    ]
    assert [item["entities"][0] for item in cards] == [
        "switch.kpb_10_output_1",
        "switch.kpb_9_output_1",
    ]


def test_frontend_module_registers_exact_ha_dashboard_strategy_contract():
    """Keep the adapter aligned with the HA 2026.8 custom strategy loader."""
    module_path = (
        Path(__file__).parents[1]
        / "custom_components"
        / "modbus_devices"
        / "dashboard"
        / "frontend"
        / "dashboard-strategy.js"
    )
    source = module_path.read_text(encoding="utf-8")

    assert 'STRATEGY_TAG = "ll-strategy-dashboard-modbus-devices"' in source
    assert "extends HTMLElement" in source
    assert "static async generate(_strategyConfig, hass)" in source
    assert "globalThis.customElements.define(" in source
    assert "registerModbusDevicesDashboardStrategy();" in source
    assert 'type: "modbus_devices/dashboard/build"' in source


def test_frontend_module_registers_dynamic_device_card_contract():
    """Keep the picker entry generator-only and emit native HA configs."""
    module_path = (
        Path(__file__).parents[1]
        / "custom_components"
        / "modbus_devices"
        / "dashboard"
        / "frontend"
        / "dashboard-strategy.js"
    )
    source = module_path.read_text(encoding="utf-8")

    assert f'DEVICE_CARD_TAG = "{DEVICE_CARD_TAG}"' in source
    assert f'type: "{WS_BUILD_DEVICE_CARD}"' in source
    assert "static getConfigElement()" in source
    assert 'document.createElement(DEVICE_CARD_EDITOR_TAG)' in source
    assert 'device: { filter: { integration: "modbus_devices" } }' in source
    assert 'new CustomEvent("config-changed"' in source
    assert 'generatedConfig.type !== "entities"' in source
    assert 'new CustomEvent("ll-rebuild"' not in source
    assert "globalThis.loadCardHelpers()" not in source
    assert "createCardElement" not in source
    assert "subscribeEvents" not in source
    assert "registerModbusDeviceCard();" in source


def test_clean_integration_package_exports_device_card_builder():
    """Guard the public API required by a clean production installation."""
    repository = Path(__file__).parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(repository), str(repository.parents[2]))
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import custom_components.modbus_devices; "
                "import custom_components.modbus_devices.presentation; "
                "from custom_components.modbus_devices.presentation import "
                "async_build_device_card; "
                "assert callable(async_build_device_card); "
                "import custom_components.modbus_devices.dashboard.frontend"
            ),
        ],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_device_card_endpoint_returns_only_builder_native_card(monkeypatch):
    expected = card("C2000-VT Balcony", {"entity": "sensor.temperature"})

    async def build_device_card(hass, device_id):
        assert hass == "hass"
        assert device_id == "device-vt"
        return DevicePresentation(device_id, "balcony", "C2000VT", expected)

    monkeypatch.setattr(
        "custom_components.modbus_devices.dashboard.frontend.async_build_device_card",
        build_device_card,
    )

    assert await async_build_device_card_config("hass", "device-vt") == expected


@pytest.mark.asyncio
async def test_device_card_endpoint_rejects_non_modbus_or_empty_device(monkeypatch):
    async def build_device_card(_hass, _device_id):
        return None

    monkeypatch.setattr(
        "custom_components.modbus_devices.dashboard.frontend.async_build_device_card",
        build_device_card,
    )

    assert await async_build_device_card_config("hass", "foreign") is None


def test_frontend_module_url_changes_with_content(tmp_path):
    """Prevent a prior ES-module instance from hiding updated registration code."""
    module = tmp_path / "dashboard-strategy.js"
    module.write_text("first", encoding="utf-8")
    first = strategy_module_url(tmp_path)
    module.write_text("second", encoding="utf-8")
    second = strategy_module_url(tmp_path)

    assert first.startswith(f"{STRATEGY_MODULE_URL}?v=")
    assert second.startswith(f"{STRATEGY_MODULE_URL}?v=")
    assert first != second
