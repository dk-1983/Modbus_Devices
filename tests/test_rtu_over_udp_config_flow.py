"""Config Flow coverage for Modbus RTU over UDP."""

from __future__ import annotations

from math import inf, nan
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME

from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)


class FakeHass:
    def __init__(self):
        self.data = {}
        self.config_entries = SimpleNamespace(async_entries=lambda _domain: [])

    async def async_add_executor_job(self, target, *args):
        return target(*args)


class FakeClient:
    connected = True

    def __init__(self):
        self.close = Mock()


def flow_for_rtu():
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._selected_manufacturer = "Dyna Drive"
    flow._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_RTU_OVER_UDP,
        Config.CONF_MANUFACTURER: "Dyna Drive",
        Config.CONF_DEVICE_CLASS: "DN310",
    }
    return flow


def bypass_flow_manager(flow):
    async def set_unique_id(value):
        flow._captured_unique_id = value

    flow.async_set_unique_id = set_unique_id
    flow._abort_if_unique_id_configured = Mock()


def valid_input(**overrides):
    data = {
        CONF_HOST: "10.0.2.10",
        Config.CONF_REMOTE_PORT: 40000,
        Config.CONF_TIMEOUT: 2.5,
        CONF_DEVICE_ID: 7,
        CONF_NAME: "Drive",
    }
    data.update(overrides)
    return data


def schema_fields(result):
    return {marker.schema: marker for marker in result["data_schema"].schema}


@pytest.mark.asyncio
async def test_transport_is_a_separate_localized_selector_option(monkeypatch):
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.get_serial_ports", lambda: []
    )
    result = await flow.async_step_user()
    selector_field = next(iter(result["data_schema"].schema.values()))
    assert selector_field.config["options"] == [
        "modbus_tcp",
        "modbus_udp",
        Config.MODBUS_RTU_OVER_UDP,
        "serial",
    ]
    assert selector_field.config["translation_key"] == "modbus_transport"


@pytest.mark.asyncio
async def test_flow_order_continues_through_manufacturer_model_and_rtu_form():
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._device_classes = get_equipment_classes_by_manufacturer()
    flow._serial_ports = ["Not Found"]
    assert (
        await flow.async_step_user(
            {Config.CONF_MODBUS_MODE: Config.MODBUS_RTU_OVER_UDP}
        )
    )["step_id"] == "manufacturer"
    assert (
        await flow.async_step_manufacturer(
            {Config.CONF_MANUFACTURER: "Dyna Drive"}
        )
    )["step_id"] == "device"
    result = await flow.async_step_device({Config.CONF_DEVICE_CLASS: "DN310"})
    assert result["step_id"] == "rtu_over_udp"
    fields = schema_fields(result)
    assert set(fields) == {
        CONF_HOST,
        Config.CONF_REMOTE_PORT,
        Config.CONF_LOCAL_UDP_PORT,
        Config.CONF_TIMEOUT,
        Config.CONF_LOCAL_BIND_ADDRESS,
        CONF_DEVICE_ID,
        CONF_NAME,
    }
    assert fields[Config.CONF_REMOTE_PORT].default() == 40000
    assert fields[Config.CONF_LOCAL_UDP_PORT].default() == 40000
    assert fields[Config.CONF_TIMEOUT].default() == 2.5
    assert fields[Config.CONF_LOCAL_BIND_ADDRESS].default() == ""


@pytest.mark.asyncio
async def test_defaults_custom_fields_persistence_and_unique_id(monkeypatch):
    flow = flow_for_rtu()
    bypass_flow_manager(flow)
    client = FakeClient()
    connect = AsyncMock(return_value=client)
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus", connect
    )
    result = await flow.async_step_rtu_over_udp(
        valid_input(
            **{
                Config.CONF_REMOTE_PORT: 41000,
                Config.CONF_TIMEOUT: 3.25,
                Config.CONF_LOCAL_BIND_ADDRESS: "192.0.2.5",
            }
        )
    )
    assert result["type"].value == "create_entry"
    assert flow._captured_unique_id == "rtu_over_udp:10.0.2.10:41000:7"
    assert result["data"] == {
        Config.CONF_MODBUS_MODE: Config.MODBUS_RTU_OVER_UDP,
        Config.CONF_MANUFACTURER: "Dyna Drive",
        Config.CONF_DEVICE_CLASS: "DN310",
        CONF_HOST: "10.0.2.10",
        Config.CONF_REMOTE_PORT: 41000,
        Config.CONF_LOCAL_UDP_PORT: 41000,
        Config.CONF_TIMEOUT: 3.25,
        Config.CONF_LOCAL_BIND_ADDRESS: "192.0.2.5",
        CONF_DEVICE_ID: 7,
        CONF_NAME: "Drive",
    }
    connect.assert_awaited_once_with(result["data"])
    client.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_custom_local_port_and_blank_bind_are_persisted(monkeypatch):
    flow = flow_for_rtu()
    bypass_flow_manager(flow)
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus",
        AsyncMock(return_value=FakeClient()),
    )
    result = await flow.async_step_rtu_over_udp(
        valid_input(
            **{
                Config.CONF_LOCAL_UDP_PORT: 42000,
                Config.CONF_LOCAL_BIND_ADDRESS: "   ",
            }
        )
    )
    assert result["data"][Config.CONF_LOCAL_UDP_PORT] == 42000
    assert result["data"][Config.CONF_LOCAL_BIND_ADDRESS] == ""


@pytest.mark.asyncio
async def test_hostname_is_normalized_for_persistence_and_identity(monkeypatch):
    flow = flow_for_rtu()
    bypass_flow_manager(flow)
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus",
        AsyncMock(return_value=FakeClient()),
    )
    result = await flow.async_step_rtu_over_udp(
        valid_input(**{CONF_HOST: " Gateway.Example "})
    )
    assert result["data"][CONF_HOST] == "gateway.example"
    assert flow._captured_unique_id == "rtu_over_udp:gateway.example:40000:7"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {Config.CONF_REMOTE_PORT: 0},
        {Config.CONF_REMOTE_PORT: 65536},
        {Config.CONF_LOCAL_UDP_PORT: 0},
        {Config.CONF_LOCAL_UDP_PORT: 65536},
        {Config.CONF_TIMEOUT: 0},
        {Config.CONF_TIMEOUT: -1},
        {Config.CONF_TIMEOUT: nan},
        {Config.CONF_TIMEOUT: inf},
        {Config.CONF_LOCAL_BIND_ADDRESS: "gateway.local"},
        {Config.CONF_LOCAL_BIND_ADDRESS: "999.1.1.1"},
    ],
)
async def test_invalid_local_configuration_is_rejected_before_connect(
    monkeypatch, overrides
):
    flow = flow_for_rtu()
    connect = AsyncMock()
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus", connect
    )
    result = await flow.async_step_rtu_over_udp(valid_input(**overrides))
    assert result["step_id"] == "rtu_over_udp"
    assert result["errors"] == {"base": "invalid_rtu_over_udp_config"}
    connect.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, OSError("offline"), TimeoutError()])
async def test_connection_failures_use_existing_cannot_connect(monkeypatch, failure):
    flow = flow_for_rtu()
    connect = AsyncMock(return_value=None) if failure is None else AsyncMock(side_effect=failure)
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus", connect
    )
    result = await flow.async_step_rtu_over_udp(valid_input())
    assert result["step_id"] == "rtu_over_udp"
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_unexpected_programming_exception_is_not_swallowed(monkeypatch):
    flow = flow_for_rtu()
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus",
        AsyncMock(side_effect=RuntimeError("bug")),
    )
    with pytest.raises(RuntimeError, match="bug"):
        await flow.async_step_rtu_over_udp(valid_input())


@pytest.mark.asyncio
async def test_duplicate_same_rtu_endpoint_uses_canonical_identity(monkeypatch):
    flow = flow_for_rtu()
    seen = []

    async def set_unique_id(value):
        seen.append(value)

    flow.async_set_unique_id = set_unique_id
    flow._abort_if_unique_id_configured = Mock(side_effect=RuntimeError("duplicate"))
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus",
        AsyncMock(return_value=FakeClient()),
    )
    with pytest.raises(RuntimeError, match="duplicate"):
        await flow.async_step_rtu_over_udp(valid_input())
    assert seen == ["rtu_over_udp:10.0.2.10:40000:7"]


def test_native_udp_and_rtu_identity_namespaces_are_distinct():
    native = "10.0.2.10_40000_7_Dyna Drive_DN310"
    rtu = "rtu_over_udp:10.0.2.10:40000:7"
    assert native != rtu


def test_gateway_connection_key_ignores_local_bind_routing_details():
    flow = flow_for_rtu()
    flow._data.update(
        {
            CONF_HOST: "10.0.2.10",
            Config.CONF_REMOTE_PORT: 40000,
            Config.CONF_LOCAL_UDP_PORT: 41000,
            Config.CONF_LOCAL_BIND_ADDRESS: "192.0.2.5",
        }
    )
    assert flow._connection_key() == "rtu_over_udp:10.0.2.10:40000"


def test_s2000_ethernet_is_not_an_equipment_model():
    equipment = get_equipment_classes_by_manufacturer()
    assert [len(equipment[name]) for name in equipment] == [29, 1, 2, 1]
    assert all("Ethernet" not in model for models in equipment.values() for model in models)
