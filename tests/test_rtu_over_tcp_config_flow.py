"""Config flow, identity and translation coverage for the RAW TCP transport."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)


def flow():
    async def executor(target, *args):
        return target(*args)

    result = ModbusDevicesConfigFlow()
    result.hass = SimpleNamespace(
        data={},
        config_entries=SimpleNamespace(async_entries=lambda _: []),
        async_add_executor_job=executor,
    )
    result._selected_manufacturer = "Haier"
    result._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_RTU_OVER_TCP,
        Config.CONF_MANUFACTURER: "Haier",
        Config.CONF_DEVICE_CLASS: "YCJA002",
    }
    result.async_set_unique_id = AsyncMock()
    result._abort_if_unique_id_configured = Mock()
    return result


def inputs(**kwargs):
    return {
        "host": " Gateway.Example ",
        "port": 40000,
        "device_id": 7,
        "timeout": 2.5,
        "name": "Haier",
    } | kwargs


@pytest.mark.asyncio
async def test_model_selection_routes_to_separate_raw_tcp_form():
    instance = flow()
    instance._device_classes = get_equipment_classes_by_manufacturer()
    instance._serial_ports = ["Not Found"]
    result = await instance.async_step_device({Config.CONF_DEVICE_CLASS: "YCJA002"})
    assert result["step_id"] == "rtu_over_tcp"
    assert {marker.schema for marker in result["data_schema"].schema} == {
        "host",
        "port",
        "timeout",
        "device_id",
        "name",
    }


@pytest.mark.asyncio
async def test_persistence_canonical_identity_and_connection_cleanup(monkeypatch):
    instance = flow()
    client = SimpleNamespace(connected=True, close=Mock())
    connect = AsyncMock(return_value=client)
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus", connect
    )
    result = await instance.async_step_rtu_over_tcp(inputs())
    assert result["type"].value == "create_entry"
    assert result["data"]["host"] == "gateway.example"
    assert result["data"]["port"] == 40000
    assert result["data"]["timeout"] == 2.5
    assert result["data"][Config.CONF_MODBUS_MODE] == Config.MODBUS_RTU_OVER_TCP
    instance.async_set_unique_id.assert_awaited_once_with(
        "rtu_over_tcp:gateway.example:40000:7"
    )
    assert instance._connection_key() == "rtu_over_tcp:gateway.example:40000"
    connect.assert_awaited_once_with(result["data"])
    client.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "values",
    [
        {"host": " "},
        {"port": 0},
        {"port": 65536},
        {"port": True},
        {"device_id": 0},
        {"device_id": 248},
        {"device_id": True},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": float("inf")},
        {"timeout": float("nan")},
        {"timeout": True},
    ],
)
async def test_invalid_input_rejected_before_connect(monkeypatch, values):
    connect = AsyncMock()
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus", connect
    )
    result = await flow().async_step_rtu_over_tcp(inputs(**values))
    assert result["errors"] == {"base": "invalid_rtu_over_tcp_config"}
    connect.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, OSError("offline"), TimeoutError()])
async def test_connect_errors(monkeypatch, failure):
    connect = (
        AsyncMock(return_value=None)
        if failure is None
        else AsyncMock(side_effect=failure)
    )
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus", connect
    )
    result = await flow().async_step_rtu_over_tcp(inputs())
    assert result["errors"] == {"base": "cannot_connect"}


def test_all_localizations_describe_raw_tcp_and_keep_udp():
    root = Path(__file__).resolve().parents[1] / "custom_components/modbus_devices"
    for path in [root / "strings.json", *(root / "translations").glob("*.json")]:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "rtu_over_tcp" in data["selector"]["modbus_transport"]["options"]
        assert "rtu_over_udp" in data["selector"]["modbus_transport"]["options"]
        step = data["config"]["step"]["rtu_over_tcp"]
        assert "MBAP" in step["description"]
        assert set(step["data"]) == {"host", "port", "timeout", "device_id", "name"}
