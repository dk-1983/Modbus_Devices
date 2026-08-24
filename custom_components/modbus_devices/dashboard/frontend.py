"""Register the thin frontend dashboard-strategy adapter."""

from hashlib import sha256
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .builder import async_build_dashboard

STATIC_URL = "/modbus_devices_static"
STRATEGY_MODULE_FILENAME = "dashboard-strategy.js"
STRATEGY_MODULE_URL = f"{STATIC_URL}/{STRATEGY_MODULE_FILENAME}"
WS_BUILD_DASHBOARD = "modbus_devices/dashboard/build"


def strategy_module_url(asset_dir: Path) -> str:
    """Return a content-versioned URL so an updated ES module executes again."""
    digest = sha256((asset_dir / STRATEGY_MODULE_FILENAME).read_bytes()).hexdigest()
    return f"{STRATEGY_MODULE_URL}?v={digest[:12]}"


@websocket_api.websocket_command({vol.Required("type"): WS_BUILD_DASHBOARD})
@websocket_api.async_response
async def websocket_build_dashboard(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return a newly generated native dashboard configuration."""
    connection.send_result(msg["id"], await async_build_dashboard(hass))


async def async_register_dashboard_frontend(hass: HomeAssistant) -> None:
    """Register one global strategy module and its read-only backend command."""
    asset_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(asset_dir), cache_headers=False)]
    )
    module_url = await hass.async_add_executor_job(strategy_module_url, asset_dir)
    frontend.add_extra_js_url(hass, module_url)
    websocket_api.async_register_command(hass, websocket_build_dashboard)
