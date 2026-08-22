"""Characterization tests for Config Flow and Config Entry lifecycle."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pymodbus.exceptions import ConnectionException, ModbusException

from homeassistant.config_entries import ConfigEntryError, ConfigEntryNotReady
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME, CONF_PORT, Platform

import custom_components.modbus_devices as integration
from custom_components.modbus_devices.binary_sensor import (
    async_setup_entry as async_setup_binary_sensor_entry,
)
from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config
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
from custom_components.modbus_devices.runtime import ModbusDevicesRuntimeData


class FakeHass:
    """Small HA surface used by the integration lifecycle."""

    def __init__(self, entries=()):
        self.data = {}
        self.config_entries = SimpleNamespace(
            async_entries=lambda _domain: list(entries),
            async_update_entry=Mock(),
            async_forward_entry_setups=AsyncMock(),
            async_unload_platforms=AsyncMock(return_value=True),
        )

    async def async_add_executor_job(self, target, *args):
        return target(*args)


class FakeEntry:
    """Config Entry subset used by setup and unload."""

    def __init__(self, *, data=None, options=None, unique_id="stable-entry-id"):
        self.entry_id = "entry-1"
        self.title = "Device"
        self.data = data or {}
        self.options = options or {}
        self.unique_id = unique_id


class FakeClient:
    connected = True

    def __init__(self):
        self.close = Mock()


class FakeDevice:
    attr_platforms = [Platform.SENSOR]
    uses_stable_entry_identity = True
    required_gateway = None

    def __init__(self, client, device_id):
        self.client = client
        self.device_id = device_id
        self.data_init = AsyncMock()


def direct_options(manufacturer="Owen", model="TRM138"):
    return {
        Config.CONF_MODBUS_MODE: Config.MODBUS_TCP,
        Config.CONF_MANUFACTURER: manufacturer,
        Config.CONF_DEVICE_CLASS: model,
        CONF_HOST: "192.0.2.1",
        CONF_PORT: 502,
        CONF_DEVICE_ID: 7,
        CONF_NAME: "Plant device",
    }


def form_fields(result):
    return {marker.schema for marker in result["data_schema"].schema}


def bypass_flow_manager(flow):
    """Keep the real unique-ID value while avoiding a full HA flow manager."""

    async def set_unique_id(value):
        flow._captured_unique_id = value

    flow.async_set_unique_id = set_unique_id
    flow._abort_if_unique_id_configured = lambda: None


@pytest.mark.asyncio
async def test_config_flow_transport_manufacturer_and_real_model_steps(monkeypatch):
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.get_equipment_classes_by_manufacturer",
        lambda: {"Bolid": ["C2000KDL"], "Dyna Drive": ["DN310"], "Owen": ["TRM138"]},
    )
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.get_serial_ports",
        lambda: ["COM7"],
    )

    result = await flow.async_step_user()
    assert result["step_id"] == "user"
    assert form_fields(result) == {Config.CONF_MODBUS_MODE}

    result = await flow.async_step_user({Config.CONF_MODBUS_MODE: Config.MODBUS_TCP})
    assert result["step_id"] == "manufacturer"
    manufacturer_schema = next(iter(result["data_schema"].schema.values()))
    assert manufacturer_schema.config["options"] == ["Bolid", "Dyna Drive", "Owen"]

    result = await flow.async_step_manufacturer({Config.CONF_MANUFACTURER: "Dyna Drive"})
    assert result["step_id"] == "device"
    model_schema = next(iter(result["data_schema"].schema.values()))
    assert model_schema.config["options"] == [{"value": "DN310", "label": "DN310"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [Config.MODBUS_TCP, Config.MODBUS_UDP])
async def test_direct_network_creation_freezes_unique_id_and_serialized_shape(monkeypatch, mode):
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._data = {
        Config.CONF_MODBUS_MODE: mode,
        Config.CONF_MANUFACTURER: "Dyna Drive",
        Config.CONF_DEVICE_CLASS: "DN310",
    }
    flow._selected_manufacturer = "Dyna Drive"
    bypass_flow_manager(flow)
    client = FakeClient()
    monkeypatch.setattr("custom_components.modbus_devices.config_flow.connect_modbus", AsyncMock(return_value=client))

    payload = {CONF_HOST: "10.0.2.10", CONF_PORT: 40000, CONF_DEVICE_ID: 9, CONF_NAME: "Drive"}
    result = await flow.async_step_network(payload)

    assert result["type"].value == "create_entry"
    assert flow._captured_unique_id == "10.0.2.10_40000_9_Dyna Drive_DN310"
    assert result["data"] == {**flow._data}
    assert result["data"][Config.CONF_MODBUS_MODE] == mode
    client.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_direct_serial_creation_freezes_unique_id_and_serialized_shape(monkeypatch):
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_SERIAL,
        Config.CONF_MANUFACTURER: "Owen",
        Config.CONF_DEVICE_CLASS: "TRM138",
    }
    flow._selected_manufacturer = "Owen"
    bypass_flow_manager(flow)
    flow._serial_ports = ["COM7"]
    monkeypatch.setattr("custom_components.modbus_devices.config_flow.connect_modbus", AsyncMock(return_value=FakeClient()))
    payload = {
        CONF_DEVICE_ID: 3,
        Config.CONF_COM_PORT: "COM7",
        Config.CONF_BAUDRATE: "9600",
        Config.CONF_BYTESIZE: "8",
        Config.CONF_PARITY: "N",
        Config.CONF_STOPBITS: "1",
        CONF_NAME: "Controller",
    }

    result = await flow.async_step_serial(payload)
    assert result["type"].value == "create_entry"
    assert flow._captured_unique_id == "COM7_3_Owen_TRM138"
    assert result["data"] == flow._data


@pytest.mark.asyncio
async def test_duplicate_detection_uses_the_frozen_direct_unique_id():
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._data = {
        Config.CONF_MANUFACTURER: "Owen",
        Config.CONF_DEVICE_CLASS: "TRM138",
    }
    flow._selected_manufacturer = "Owen"
    seen = []

    async def set_unique_id(value):
        seen.append(value)

    flow.async_set_unique_id = set_unique_id
    flow._abort_if_unique_id_configured = Mock(side_effect=RuntimeError("duplicate"))

    with pytest.raises(RuntimeError, match="duplicate"):
        await flow._async_connection_ready("endpoint_1_Owen_TRM138")
    assert seen == ["endpoint_1_Owen_TRM138"]


@pytest.mark.asyncio
async def test_bolid_gateway_manual_flow_reaches_exact_capability_mapping():
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._selected_manufacturer = "Bolid"
    flow._required_gateway = GatewayType.S2000_PP
    flow._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_TCP,
        Config.CONF_MANUFACTURER: "Bolid",
        Config.CONF_DEVICE_CLASS: "C2000DZ",
        CONF_HOST: "10.0.2.10",
        CONF_PORT: 502,
        CONF_DEVICE_ID: 1,
    }

    result = await flow.async_step_gateway_new({Config.CONF_GATEWAY_ID: "Main PP"})
    assert result["step_id"] == "gateway_device"
    assert form_fields(result) == {
        Config.CONF_DEVICE_VARIANT,
        Config.CONF_ORION_ADDRESS,
        Config.CONF_DPLS_BASE_ADDRESS,
    }

    result = await flow.async_step_gateway_device(
        {Config.CONF_ORION_ADDRESS: 4, Config.CONF_DPLS_BASE_ADDRESS: 30}
    )
    assert result["step_id"] == "mapping_source"

    result = await flow.async_step_mapping_source(
        {Config.CONF_MAPPING_SOURCE: MappingSource.MANUAL.value}
    )
    assert result["step_id"] == "manual_capability"
    assert Config.CONF_CAPABILITY_KEY in form_fields(result)


@pytest.mark.asyncio
async def test_configuration_assisted_ambiguous_mapping_is_reported(monkeypatch):
    from custom_components.modbus_devices.mapping import AmbiguousDeviceMappingError

    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._selected_manufacturer = "Bolid"
    flow._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_TCP,
        Config.CONF_MANUFACTURER: "Bolid",
        Config.CONF_DEVICE_CLASS: "C2000DZ",
        CONF_HOST: "10.0.2.10",
        CONF_PORT: 502,
        CONF_DEVICE_ID: 1,
    }
    flow._gateway_context = GatewayContext(
        GatewayType.S2000_PP, "Main PP", flow._connection_key(), 1
    )
    flow._dpls_identity = DPLSSubIdentity(30, 1)
    flow._orion_address = 4

    class Provider:
        def __init__(self, **_kwargs):
            pass

        async def async_resolve(self, **_kwargs):
            raise AmbiguousDeviceMappingError("ambiguous")

    monkeypatch.setattr("custom_components.modbus_devices.config_flow.connect_modbus", AsyncMock(return_value=FakeClient()))
    monkeypatch.setattr("custom_components.modbus_devices.config_flow.AutomaticDeviceMappingProvider", Provider)

    result = await flow.async_step_automatic_device({Config.CONF_ORION_ADDRESS: 4})
    assert result["step_id"] == "automatic_device"
    assert result["errors"] == {"base": "ambiguous_device_mapping"}


@pytest.mark.asyncio
async def test_configuration_assisted_mapping_persists_the_existing_shape(monkeypatch):
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._selected_manufacturer = "Bolid"
    flow._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_TCP,
        Config.CONF_MANUFACTURER: "Bolid",
        Config.CONF_DEVICE_CLASS: "C2000DZ",
        CONF_HOST: "10.0.2.10",
        CONF_PORT: 502,
        CONF_DEVICE_ID: 1,
    }
    flow._gateway_context = GatewayContext(
        GatewayType.S2000_PP, "Main PP", flow._connection_key(), 1
    )
    flow._dpls_identity = DPLSSubIdentity(30, 1)
    flow._orion_address = 4
    identity = DownstreamDeviceIdentity(
        gateway=flow._gateway_context,
        model="C2000DZ",
        orion_address=4,
        dpls=flow._dpls_identity,
    )
    expected = ResolvedDeviceMapping(
        identity=identity,
        source=MappingSource.AUTOMATIC,
        objects=(manual_zone_mapping(30, 7, 1, 0, None),),
    )

    class Provider:
        def __init__(self, **_kwargs):
            pass

        async def async_resolve(self, **_kwargs):
            return expected

    bypass_flow_manager(flow)
    monkeypatch.setattr("custom_components.modbus_devices.config_flow.connect_modbus", AsyncMock(return_value=FakeClient()))
    monkeypatch.setattr("custom_components.modbus_devices.config_flow.AutomaticDeviceMappingProvider", Provider)

    result = await flow.async_step_automatic_device({Config.CONF_ORION_ADDRESS: 4})
    assert result["type"].value == "create_entry"
    assert result["data"][Config.CONF_GATEWAY_MAPPING] == expected.to_dict()
    assert flow._captured_unique_id == identity.stable_id


@pytest.mark.asyncio
async def test_network_connection_failure_stays_on_form(monkeypatch):
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._selected_manufacturer = "Dyna Drive"
    flow._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_TCP,
        Config.CONF_MANUFACTURER: "Dyna Drive",
        Config.CONF_DEVICE_CLASS: "DN310",
    }
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.connect_modbus",
        AsyncMock(side_effect=OSError("network down")),
    )

    result = await flow.async_step_network(
        {CONF_HOST: "192.0.2.1", CONF_PORT: 502, CONF_DEVICE_ID: 1}
    )
    assert result["step_id"] == "network"
    assert result["errors"] == {"base": "cannot_connect"}


def test_gateway_and_downstream_identity_and_serialization_are_frozen():
    gateway = GatewayContext(GatewayType.S2000_PP, "Main PP", "ModBus TCP/IP:10.0.2.10:502", 1)
    identity = DownstreamDeviceIdentity(
        gateway=gateway,
        model="C2000RSMK",
        orion_address=12,
        dpls=DPLSSubIdentity(40, 2),
        metadata=DownstreamDeviceMetadata(variant="hardware_2_0", topology="contact_and_external_input"),
    )
    mapping = ResolvedDeviceMapping(
        identity=identity,
        source=MappingSource.MANUAL,
        objects=(manual_zone_mapping(40, 1, 1, 0, None),),
    )
    serialized = mapping.to_dict()

    assert gateway.stable_id == "s2000_pp:ModBus TCP/IP:10.0.2.10:502:1:Main PP"
    assert identity.stable_id == f"{gateway.stable_id}:orion:12:dpls:40"
    assert ResolvedDeviceMapping.from_dict(deepcopy(serialized)).to_dict() == serialized
    assert set(serialized) == {"identity", "source", "objects"}


@pytest.mark.asyncio
async def test_setup_first_refresh_platform_forward_unload_and_reload(monkeypatch):
    hass = FakeHass()
    entry = FakeEntry(options=direct_options(), unique_id="frozen-direct-id")
    clients = [FakeClient(), FakeClient()]
    devices = []

    class Device(FakeDevice):
        def __init__(self, client, device_id):
            super().__init__(client, device_id)
            devices.append(self)

    coordinators = []

    class Coordinator:
        def __init__(self, hass, device):
            self.async_config_entry_first_refresh = AsyncMock()
            coordinators.append(self)

    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(side_effect=clients))
    monkeypatch.setattr(integration, "get_class", lambda *_args: Device)
    monkeypatch.setattr(integration, "ModbusDeviceCoordinator", Coordinator)

    assert await integration.async_setup_entry(hass, entry) is True
    assert devices[0].attr_unique_id_prefix == "frozen-direct-id"
    assert devices[0].attr_device_identifier == "frozen-direct-id"
    first_runtime = entry.runtime_data
    assert isinstance(first_runtime, ModbusDevicesRuntimeData)
    assert first_runtime.client is clients[0]
    assert first_runtime.device is devices[0]
    assert first_runtime.coordinator is coordinators[0]
    assert first_runtime.gateway_mapping is None
    devices[0].data_init.assert_awaited_once_with()
    coordinators[0].async_config_entry_first_refresh.assert_awaited_once_with()
    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, [Platform.SENSOR])

    assert await integration.async_unload_entry(hass, entry) is True
    clients[0].close.assert_called_once_with()
    assert entry.runtime_data is first_runtime

    # Home Assistant clears runtime_data after a successful unload callback.
    del entry.runtime_data

    assert await integration.async_setup_entry(hass, entry) is True
    assert entry.runtime_data is not first_runtime
    assert entry.runtime_data.client is clients[1]
    assert entry.runtime_data.device is devices[1]
    assert devices[1].attr_unique_id_prefix == "frozen-direct-id"


@pytest.mark.asyncio
async def test_temporary_connection_failure_becomes_not_ready(monkeypatch):
    hass = FakeHass()
    entry = FakeEntry(options=direct_options())
    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(side_effect=ConnectionException("offline")))

    with pytest.raises(ConfigEntryNotReady, match="offline"):
        await integration.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_device_unavailable_during_initialization_becomes_not_ready(monkeypatch):
    hass = FakeHass()
    entry = FakeEntry(options=direct_options())
    client = FakeClient()

    class OfflineDevice(FakeDevice):
        def __init__(self, client, device_id):
            super().__init__(client, device_id)
            self.data_init = AsyncMock(side_effect=ConnectionException("device unavailable"))

    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(return_value=client))
    monkeypatch.setattr(integration, "get_class", lambda *_args: OfflineDevice)

    with pytest.raises(ConfigEntryNotReady, match="device unavailable"):
        await integration.async_setup_entry(hass, entry)
    client.close.assert_called_once_with()
    assert not hasattr(entry, "runtime_data")


@pytest.mark.asyncio
async def test_first_refresh_failure_never_attempts_post_refresh_maintenance(monkeypatch):
    hass = FakeHass()
    entry = FakeEntry(options=direct_options())
    client = FakeClient()
    devices = []

    class Device(FakeDevice):
        def __init__(self, client, device_id):
            super().__init__(client, device_id)
            self.async_post_first_refresh = AsyncMock()
            devices.append(self)

    class Coordinator:
        def __init__(self, hass, device):
            self.async_config_entry_first_refresh = AsyncMock(
                side_effect=ConfigEntryNotReady("first refresh failed")
            )

    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(return_value=client))
    monkeypatch.setattr(integration, "get_class", lambda *_args: Device)
    monkeypatch.setattr(integration, "ModbusDeviceCoordinator", Coordinator)

    with pytest.raises(ConfigEntryNotReady, match="first refresh failed"):
        await integration.async_setup_entry(hass, entry)

    devices[0].async_post_first_refresh.assert_not_awaited()
    client.close.assert_called_once_with()
    assert not hasattr(entry, "runtime_data")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [
        direct_options(manufacturer="invalid"),
        {**direct_options(), Config.CONF_DEVICE_CLASS: "MissingClass"},
        {**direct_options(), Config.CONF_GATEWAY_MAPPING: {"broken": True}},
    ],
)
async def test_invalid_persisted_configuration_becomes_config_entry_error(monkeypatch, options):
    hass = FakeHass()
    entry = FakeEntry(options=options)
    client = FakeClient()
    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(return_value=client))
    monkeypatch.setattr(integration, "get_class", Mock(side_effect=AttributeError("missing")))

    with pytest.raises(ConfigEntryError):
        await integration.async_setup_entry(hass, entry)
    assert not hasattr(entry, "runtime_data")


@pytest.mark.asyncio
async def test_unexpected_platform_failure_is_not_swallowed_and_resources_close(monkeypatch):
    hass = FakeHass()
    hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("platform bug")
    entry = FakeEntry(options=direct_options())
    client = FakeClient()

    class Coordinator:
        def __init__(self, hass, device):
            self.async_config_entry_first_refresh = AsyncMock()

    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(return_value=client))
    monkeypatch.setattr(integration, "get_class", lambda *_args: FakeDevice)
    monkeypatch.setattr(integration, "ModbusDeviceCoordinator", Coordinator)

    with pytest.raises(RuntimeError, match="platform bug"):
        await integration.async_setup_entry(hass, entry)
    client.close.assert_called_once_with()
    assert not hasattr(entry, "runtime_data")


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_mask_original_setup_failure(monkeypatch):
    hass = FakeHass()
    hass.config_entries.async_forward_entry_setups.side_effect = RuntimeError("platform bug")
    entry = FakeEntry(options=direct_options())
    client = FakeClient()
    client.close.side_effect = RuntimeError("close bug")

    class Coordinator:
        def __init__(self, hass, device):
            self.async_config_entry_first_refresh = AsyncMock()

    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(return_value=client))
    monkeypatch.setattr(integration, "get_class", lambda *_args: FakeDevice)
    monkeypatch.setattr(integration, "ModbusDeviceCoordinator", Coordinator)

    with pytest.raises(RuntimeError, match="platform bug"):
        await integration.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_optional_post_refresh_transport_failure_does_not_block_setup(monkeypatch):
    hass = FakeHass()
    entry = FakeEntry(options=direct_options())
    client = FakeClient()

    class Device(FakeDevice):
        def __init__(self, client, device_id):
            super().__init__(client, device_id)
            self.async_post_first_refresh = AsyncMock(
                side_effect=ModbusException("clock write failed")
            )

    class Coordinator:
        def __init__(self, hass, device):
            self.data = {"time": datetime(2000, 1, 1)}
            self.async_config_entry_first_refresh = AsyncMock()

    monkeypatch.setattr(integration, "connect_modbus", AsyncMock(return_value=client))
    monkeypatch.setattr(integration, "get_class", lambda *_args: Device)
    monkeypatch.setattr(integration, "ModbusDeviceCoordinator", Coordinator)

    assert await integration.async_setup_entry(hass, entry) is True
    runtime_device = entry.runtime_data.device
    runtime_device.async_post_first_refresh.assert_awaited_once_with(
        {"time": datetime(2000, 1, 1)}
    )
    assert client.close.call_count == 0


@pytest.mark.asyncio
async def test_binary_sensor_platform_uses_first_refresh_snapshot_without_io():
    device = SimpleNamespace(get_inputs=AsyncMock(side_effect=RuntimeError("input bug")))
    coordinator = Mock(data={"inputs": {}})
    hass = SimpleNamespace(data={})
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=SimpleNamespace(device=device, coordinator=coordinator),
    )
    add_entities = Mock()

    await async_setup_binary_sensor_entry(hass, entry, add_entities)

    device.get_inputs.assert_not_awaited()
    add_entities.assert_called_once_with([])


def test_config_flow_localization_catalogs_have_identical_keys():
    root = Path(__file__).parents[1] / "custom_components" / "modbus_devices"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((root / "translations" / "en.json").read_text(encoding="utf-8"))
    russian = json.loads((root / "translations" / "ru.json").read_text(encoding="utf-8"))

    def shape(value):
        if isinstance(value, dict):
            return {key: shape(item) for key, item in value.items()}
        return None

    assert english == strings
    assert shape(strings) == shape(russian)
    assert set(strings["config"]["step"]) == {
        "user", "manufacturer", "device", "io_mapping", "network",
        "rtu_over_udp", "serial",
        "gateway_context", "gateway_new", "gateway_device", "mapping_source",
        "manual_device", "manual_object", "manual_capability", "automatic_device",
    }
    assert set(strings["selector"]["modbus_transport"]["options"]) == {
        "modbus_tcp",
        "modbus_udp",
        Config.MODBUS_RTU_OVER_UDP,
        "serial",
    }
