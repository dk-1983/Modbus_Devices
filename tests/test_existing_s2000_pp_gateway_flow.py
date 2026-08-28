"""Regression coverage for adding devices through a loaded С2000-ПП."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from homeassistant.const import CONF_DEVICE_ID, CONF_NAME, Platform

import custom_components.modbus_devices as integration
from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.gateway import (
    DownstreamDeviceIdentity,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPRelayRow,
    S2000PPZoneRow,
    manual_relay_mapping,
)


class FakeClient:
    connected = True

    def __init__(self) -> None:
        self.close = Mock()


class FakeEntry:
    def __init__(
        self,
        entry_id: str,
        *,
        options: dict,
        title: str = "Gateway",
        unique_id: str | None = None,
        runtime_data=None,
    ) -> None:
        self.entry_id = entry_id
        self.options = options
        self.data = {}
        self.title = title
        self.unique_id = unique_id or entry_id
        if runtime_data is not None:
            self.runtime_data = runtime_data


class FakeHass:
    def __init__(self, entries=()) -> None:
        self.data = {}
        self._entries = list(entries)
        self.config_entries = SimpleNamespace(
            async_get_entry=lambda entry_id: next(
                (entry for entry in self._entries if entry.entry_id == entry_id), None
            ),
            async_entries=lambda _domain: list(self._entries),
            async_update_entry=Mock(),
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        )

    async def async_add_executor_job(self, target, *args):
        return target(*args)


class StaticCache:
    def __init__(self, configuration: S2000PPConfiguration) -> None:
        self.configuration = configuration

    async def async_get_or_load(self, _gateway_id, _loader):
        return self.configuration


def gateway_options(port: str = "COM7") -> dict:
    return {
        Config.CONF_MODBUS_MODE: Config.MODBUS_SERIAL,
        Config.CONF_MANUFACTURER: "Bolid",
        Config.CONF_DEVICE_CLASS: "S2000PP",
        Config.CONF_COM_PORT: port,
        Config.CONF_BAUDRATE: "9600",
        Config.CONF_BYTESIZE: "8",
        Config.CONF_PARITY: "N",
        Config.CONF_STOPBITS: "1",
        CONF_DEVICE_ID: 1,
    }


def loaded_gateway(entry_id="gateway-1", port="COM7") -> FakeEntry:
    return FakeEntry(
        entry_id,
        options=gateway_options(port),
        title=f"С2000-ПП {entry_id}",
        unique_id=f"gateway-uid-{entry_id}",
        runtime_data=SimpleNamespace(client=FakeClient()),
    )


def configuration(*addresses: int) -> S2000PPConfiguration:
    return S2000PPConfiguration(
        zones=tuple(
            S2000PPZoneRow(index, address, 0, 1, 3)
            for index, address in enumerate(addresses, 1)
        ),
        relays=tuple(
            S2000PPRelayRow(index, address, 1)
            for index, address in enumerate(addresses, 1)
        ),
        partitions=(),
        unparsed_registers=(),
    )


def bypass_duplicates(flow: ModbusDevicesConfigFlow) -> None:
    async def set_unique_id(value):
        flow._captured_unique_id = value

    flow.async_set_unique_id = set_unique_id
    flow._abort_if_unique_id_configured = lambda: None


async def prepare_gateway_flow(flow: ModbusDevicesConfigFlow, gateway: FakeEntry):
    flow.hass = FakeHass([gateway])
    flow._device_classes = {"Bolid": ["S2000PP", "C2000KPB"]}
    result = await flow.async_step_user(
        {Config.CONF_MODBUS_MODE: "existing_gateway"}
    )
    assert result["step_id"] == "existing_gateway"
    result = await flow.async_step_existing_gateway(
        {Config.CONF_GATEWAY_ENTRY_ID: gateway.entry_id}
    )
    assert result["step_id"] == "gateway_child_model"
    return await flow.async_step_gateway_child_model(
        {Config.CONF_DEVICE_CLASS: "C2000KPB"}
    )


@pytest.mark.asyncio
async def test_direct_serial_tcp_and_direct_s2000_pp_routes_remain_available(
    monkeypatch,
):
    gateway = loaded_gateway()
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass([gateway])
    flow._device_classes = {"Bolid": ["S2000PP"], "Owen": ["TRM138"]}
    flow._serial_ports = ["COM7"]

    result = await flow.async_step_user()
    choices = next(iter(result["data_schema"].schema.values())).config["options"]
    assert choices == [
        "modbus_tcp",
        "modbus_udp",
        "rtu_over_udp",
        "serial",
        "existing_gateway",
    ]
    assert (await flow.async_step_user(
        {Config.CONF_MODBUS_MODE: Config.MODBUS_TCP}
    ))["step_id"] == "manufacturer"

    direct = ModbusDevicesConfigFlow()
    direct.hass = FakeHass([gateway])
    direct._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_SERIAL,
        Config.CONF_MANUFACTURER: "Bolid",
        Config.CONF_DEVICE_CLASS: "S2000PP",
    }
    direct._selected_manufacturer = "Bolid"
    direct._serial_ports = ["COM8"]
    bypass_duplicates(direct)
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus",
        AsyncMock(return_value=FakeClient()),
    )
    result = await direct.async_step_serial(
        {
            CONF_DEVICE_ID: 2,
            Config.CONF_COM_PORT: "COM8",
            Config.CONF_BAUDRATE: "9600",
            Config.CONF_BYTESIZE: "8",
            Config.CONF_PARITY: "N",
            Config.CONF_STOPBITS: "1",
            CONF_NAME: "Second PP",
        }
    )
    assert result["type"].value == "create_entry"
    assert Config.CONF_GATEWAY_ENTRY_ID not in result["data"]


@pytest.mark.asyncio
async def test_gateway_selection_supports_multiple_loaded_s2000_pp_entries():
    first = loaded_gateway("gateway-1", "COM7")
    second = loaded_gateway("gateway-2", "COM8")
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass([first, second])
    flow._device_classes = {"Bolid": ["S2000PP", "C2000KPB"]}

    result = await flow.async_step_existing_gateway()
    options = next(iter(result["data_schema"].schema.values())).config["options"]
    assert [item["value"] for item in options] == ["gateway-1", "gateway-2"]

    result = await flow.async_step_existing_gateway(
        {Config.CONF_GATEWAY_ENTRY_ID: "gateway-2"}
    )
    assert result["step_id"] == "gateway_child_model"
    assert flow._gateway_context.connection_key == "config_entry:gateway-2"


@pytest.mark.asyncio
async def test_discovery_lists_remaining_addresses_and_adds_selected_kpb():
    gateway = loaded_gateway()
    flow = ModbusDevicesConfigFlow()
    result = await prepare_gateway_flow(flow, gateway)
    assert result["step_id"] == "mapping_source"
    flow.hass.data[Config.DOMAIN] = {
        "s2000_pp_configuration_cache": StaticCache(configuration(6, 7))
    }
    bypass_duplicates(flow)

    result = await flow.async_step_mapping_source(
        {Config.CONF_MAPPING_SOURCE: MappingSource.AUTOMATIC.value}
    )
    assert result["step_id"] == "discovered_device"
    options = next(iter(result["data_schema"].schema.values())).config["options"]
    assert [item["value"] for item in options] == ["6", "7"]

    result = await flow.async_step_discovered_device(
        {Config.CONF_DISCOVERED_ADDRESS: "6"}
    )
    assert result["type"].value == "create_entry"
    assert result["data"][Config.CONF_GATEWAY_ENTRY_ID] == "gateway-1"
    assert Config.CONF_COM_PORT not in result["data"]
    mapping = ResolvedDeviceMapping.from_dict(
        result["data"][Config.CONF_GATEWAY_MAPPING]
    )
    assert mapping.identity.orion_address == 6
    assert any(item.modbus_address >= 10000 for item in mapping.objects)


@pytest.mark.asyncio
async def test_added_address_is_excluded_but_other_discovery_remains_available():
    gateway = loaded_gateway()
    context = GatewayContext(
        GatewayType.S2000_PP,
        gateway.unique_id,
        f"config_entry:{gateway.entry_id}",
        1,
    )
    existing_mapping = ResolvedDeviceMapping(
        DownstreamDeviceIdentity(context, "C2000KPB", 6),
        MappingSource.MANUAL,
        (manual_relay_mapping(1, 1),),
    )
    child = FakeEntry(
        "child-6",
        options={Config.CONF_GATEWAY_MAPPING: existing_mapping.to_dict()},
    )
    flow = ModbusDevicesConfigFlow()
    await prepare_gateway_flow(flow, gateway)
    flow.hass._entries.append(child)
    flow.hass.data[Config.DOMAIN] = {
        "s2000_pp_configuration_cache": StaticCache(configuration(6, 7))
    }

    result = await flow.async_step_discovered_device()
    options = next(iter(result["data_schema"].schema.values())).config["options"]
    assert options == [{"value": "7", "label": "Orion 7"}]


@pytest.mark.asyncio
async def test_manual_kpb_add_never_requests_or_opens_a_transport(monkeypatch):
    gateway = loaded_gateway()
    flow = ModbusDevicesConfigFlow()
    await prepare_gateway_flow(flow, gateway)
    connect = AsyncMock(side_effect=AssertionError("must not open a client"))
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus", connect
    )

    result = await flow.async_step_mapping_source(
        {Config.CONF_MAPPING_SOURCE: MappingSource.MANUAL.value}
    )
    assert result["step_id"] == "manual_device"
    result = await flow.async_step_manual_device({Config.CONF_ORION_ADDRESS: 9})
    assert result["step_id"] == "manual_capability"
    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_identity_is_scoped_to_gateway():
    first = loaded_gateway("gateway-1")
    second = loaded_gateway("gateway-2")
    first_flow = ModbusDevicesConfigFlow()
    await prepare_gateway_flow(first_flow, first)
    second_flow = ModbusDevicesConfigFlow()
    await prepare_gateway_flow(second_flow, second)
    first_id = DownstreamDeviceIdentity(
        first_flow._gateway_context, "C2000KPB", 5
    ).stable_id
    second_id = DownstreamDeviceIdentity(
        second_flow._gateway_context, "C2000KPB", 5
    ).stable_id
    assert first_id != second_id

    seen = []
    first_flow.async_set_unique_id = AsyncMock(side_effect=lambda value: seen.append(value))
    first_flow._abort_if_unique_id_configured = Mock(
        side_effect=RuntimeError("duplicate")
    )
    mapping = ResolvedDeviceMapping(
        DownstreamDeviceIdentity(first_flow._gateway_context, "C2000KPB", 5),
        MappingSource.MANUAL,
        (manual_relay_mapping(1, 1),),
    )
    with pytest.raises(RuntimeError, match="duplicate"):
        await first_flow._async_validate_and_store_mapping(mapping)
    assert seen == [first_id]


@pytest.mark.asyncio
async def test_gateway_disappearing_is_a_form_error_and_cancellation_is_inert():
    gateway = loaded_gateway()
    flow = ModbusDevicesConfigFlow()
    await prepare_gateway_flow(flow, gateway)
    before = list(flow.hass._entries)
    result = await flow.async_step_mapping_source()
    assert result["step_id"] == "mapping_source"
    assert flow.hass._entries == before

    flow.hass._entries.clear()

    result = await flow.async_step_discovered_device()
    assert result["errors"] == {"base": "gateway_unavailable"}
    assert flow.hass._entries == []


@pytest.mark.asyncio
async def test_child_setup_reuses_gateway_client_and_child_unload_does_not_close_it(
    monkeypatch,
):
    gateway = loaded_gateway()
    context = GatewayContext(
        GatewayType.S2000_PP, gateway.unique_id, "config_entry:gateway-1", 1
    )
    mapping = ResolvedDeviceMapping(
        DownstreamDeviceIdentity(context, "C2000KPB", 5),
        MappingSource.MANUAL,
        (manual_relay_mapping(1, 1),),
    )
    child = FakeEntry(
        "child-1",
        options={
            Config.CONF_GATEWAY_ENTRY_ID: "gateway-1",
            Config.CONF_MANUFACTURER: "Bolid",
            Config.CONF_DEVICE_CLASS: "C2000KPB",
            CONF_DEVICE_ID: 1,
            Config.CONF_GATEWAY_MAPPING: mapping.to_dict(),
        },
    )
    hass = FakeHass([gateway, child])
    hass.config_entries.async_entries = Mock(
        side_effect=AssertionError("setup scanned all config entries")
    )

    class Device:
        required_gateway = GatewayType.S2000_PP
        attr_platforms = [Platform.SENSOR]

        def __init__(self, client, _device_id):
            assert client is gateway.runtime_data.client

        def apply_gateway_mapping(self, _mapping):
            pass

        async def data_init(self):
            pass

        async def async_get_snapshot(self):
            return {"state_sensors": {}}

    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(), data={}
    )
    monkeypatch.setattr(integration, "get_class", lambda *_args: Device)
    def coordinator_factory(**kwargs):
        coordinator.device = kwargs["device"]
        return coordinator

    monkeypatch.setattr(integration, "ModbusDeviceCoordinator", coordinator_factory)
    connect = AsyncMock(side_effect=AssertionError("child opened a connection"))
    monkeypatch.setattr(integration, "connect_modbus", connect)

    assert await integration.async_setup_entry(hass, child)
    connect.assert_not_awaited()
    assert child.runtime_data.owns_client is False
    assert await integration.async_unload_entry(hass, child)
    gateway.runtime_data.client.close.assert_not_called()


@pytest.mark.asyncio
async def test_existing_direct_entry_loads_without_migration_or_shape_change(
    monkeypatch,
):
    options = gateway_options()
    entry = FakeEntry("direct", options=dict(options))
    hass = FakeHass([entry])

    class Device:
        required_gateway = None
        attr_platforms = []

        def __init__(self, _client, _device_id):
            pass

        async def data_init(self):
            pass

        async def async_get_snapshot(self):
            return {}

    monkeypatch.setattr(integration, "get_class", lambda *_args: Device)
    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(return_value=FakeClient()))
    monkeypatch.setattr(
        integration,
        "ModbusDeviceCoordinator",
        lambda **_kwargs: SimpleNamespace(
            async_config_entry_first_refresh=AsyncMock(), data={}
        ),
    )
    assert await integration.async_setup_entry(hass, entry)
    assert entry.options == options
    hass.config_entries.async_update_entry.assert_not_called()
