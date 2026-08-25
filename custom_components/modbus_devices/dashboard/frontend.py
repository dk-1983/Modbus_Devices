"""Register the frontend card generator and legacy dashboard strategy."""

from hashlib import sha256
from pathlib import Path
from typing import Any

from custom_components.modbus_devices.presentation.builder import (
    async_build_device_card,
)
import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .builder import async_build_dashboard

STATIC_URL = "/modbus_devices_static"
STRATEGY_MODULE_FILENAME = "dashboard-strategy.js"
STRATEGY_MODULE_URL = f"{STATIC_URL}/{STRATEGY_MODULE_FILENAME}"
DEVICE_CARD_TAG = "modbus-device-card"
WS_BUILD_DASHBOARD = "modbus_devices/dashboard/build"
WS_BUILD_DEVICE_CARD = "modbus_devices/presentation/build"


def strategy_module_url(asset_dir: Path) -> str:
    """Return a content-versioned URL so an updated ES module executes again."""
    digest = sha256((asset_dir / STRATEGY_MODULE_FILENAME).read_bytes()).hexdigest()
    return f"{STRATEGY_MODULE_URL}?v={digest[:12]}"


async def async_build_device_card_config(
    hass: HomeAssistant, device_id: str
) -> dict[str, Any] | None:
    """Return the native card config requested by the device-card generator."""
    presentation = await async_build_device_card(hass, device_id)
    return None if presentation is None else presentation.card


@websocket_api.websocket_command({vol.Required("type"): WS_BUILD_DASHBOARD})
@websocket_api.async_response
async def websocket_build_dashboard(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return a newly generated native dashboard configuration."""
    connection.send_result(msg["id"], await async_build_dashboard(hass))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_BUILD_DEVICE_CARD,
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response
async def websocket_build_device_card(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return one current native card for a Modbus Devices device."""
    connection.send_result(
        msg["id"], await async_build_device_card_config(hass, msg["device_id"])
    )


async def async_register_dashboard_frontend(hass: HomeAssistant) -> None:
    """Register the frontend module and its read-only builder commands."""
    asset_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(asset_dir), cache_headers=False)]
    )
    module_url = await hass.async_add_executor_job(strategy_module_url, asset_dir)
    frontend.add_extra_js_url(hass, module_url)
    websocket_api.async_register_command(hass, websocket_build_dashboard)
    websocket_api.async_register_command(hass, websocket_build_device_card)
