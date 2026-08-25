"""Tests for the Modbus Device Lovelace card generator."""

import os
from pathlib import Path
import subprocess
import sys

from custom_components.modbus_devices.dashboard.frontend import (
    DEVICE_CARD_TAG,
    FRONTEND_MODULE_URL,
    WS_BUILD_DEVICE_CARD,
    async_build_device_card_config,
    frontend_module_url,
)
from custom_components.modbus_devices.presentation.profile import DevicePresentation
import pytest


def native_card(title, *entities):
    """Return a native Entities card fixture."""
    return {
        "type": "entities",
        "title": title,
        "show_header_toggle": False,
        "entities": list(entities),
    }


def frontend_source() -> str:
    """Return the production generator module source."""
    return (
        Path(__file__).parents[1]
        / "custom_components"
        / "modbus_devices"
        / "dashboard"
        / "frontend"
        / "device-card-generator.js"
    ).read_text(encoding="utf-8")


def test_frontend_module_registers_generator_only_contract():
    """Keep the picker entry generator-only and emit native HA configs."""
    source = frontend_source()

    assert f'DEVICE_CARD_TAG = "{DEVICE_CARD_TAG}"' in source
    assert f'type: "{WS_BUILD_DEVICE_CARD}"' in source
    assert "static getConfigElement()" in source
    assert 'document.createElement(DEVICE_CARD_EDITOR_TAG)' in source
    assert 'device: { filter: { integration: "modbus_devices" } }' in source
    assert 'new CustomEvent("config-changed"' in source
    assert 'generatedConfig.type !== "entities"' in source
    assert "registerModbusDeviceCard();" in source


def test_frontend_module_contains_no_removed_strategy_or_runtime_wrapper():
    """Prevent the dashboard-wide prototype and rebuild loop from returning."""
    source = frontend_source()

    for removed in (
        "ll-strategy-dashboard-modbus-devices",
        "modbus_devices/dashboard/build",
        "custom:modbus-devices",
        "ll-rebuild",
        "subscribeEvents",
        "state_changed",
        "globalThis.loadCardHelpers()",
        "createCardElement",
        "getCardSize",
        "getGridOptions",
    ):
        assert removed not in source


def test_dashboard_wide_builder_production_path_is_removed():
    """Keep Area/Sections auto-dashboard generation out of production."""
    integration = Path(__file__).parents[1] / "custom_components" / "modbus_devices"
    frontend = (integration / "dashboard" / "frontend.py").read_text(encoding="utf-8")

    assert not (integration / "dashboard" / "builder.py").exists()
    assert "async_build_dashboard" not in frontend
    assert "modbus_devices/dashboard/build" not in frontend


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
    """Return a complete native card from the presentation boundary."""
    expected = native_card("C2000-VT Balcony", {"entity": "sensor.temperature"})

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
    """Do not generate a config when the presentation builder rejects a device."""

    async def build_device_card(_hass, _device_id):
        return None

    monkeypatch.setattr(
        "custom_components.modbus_devices.dashboard.frontend.async_build_device_card",
        build_device_card,
    )

    assert await async_build_device_card_config("hass", "foreign") is None


def test_frontend_module_url_changes_with_content(tmp_path):
    """Prevent a prior ES-module instance from hiding updated registration code."""
    module = tmp_path / "device-card-generator.js"
    module.write_text("first", encoding="utf-8")
    first = frontend_module_url(tmp_path)
    module.write_text("second", encoding="utf-8")
    second = frontend_module_url(tmp_path)

    assert first.startswith(f"{FRONTEND_MODULE_URL}?v=")
    assert second.startswith(f"{FRONTEND_MODULE_URL}?v=")
    assert first != second
