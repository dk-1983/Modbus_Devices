"""Characterization tests for coordinator-owned startup polling."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import custom_components.modbus_devices as integration
from custom_components.modbus_devices.binary_sensor import async_setup_entry as setup_binary
from custom_components.modbus_devices.button import async_setup_entry as setup_button
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.bolid import C2000KPB, M3000BB1020, S2000PP
from custom_components.modbus_devices.equipment.dyna_drive import DN310
from custom_components.modbus_devices.equipment.owen import TRM138
from custom_components.modbus_devices.sensor import async_setup_entry as setup_sensor
from custom_components.modbus_devices.switch import async_setup_entry as setup_switch
from homeassistant.const import Platform


class Response:
    def __init__(self, *, registers=None, bits=None, function_code=None):
        self.registers = registers
        self.bits = bits
        self.function_code = function_code

    def isError(self):
        return False


class CountingClient:
    def __init__(self):
        self.calls = []

    async def read_holding_registers(self, **kwargs):
        self.calls.append(("holding", kwargs["address"], kwargs["count"]))
        address = kwargs["address"]
        if address == 60001:
            registers = [1, 2, 3, 4, 5, 6, 2026, 1, 2, 3, 4, 5]
            return Response(registers=registers[: kwargs["count"]], function_code=3)
        if address == 60007:
            return Response(registers=[2026, 1, 2, 3, 4, 5], function_code=3)
        if address == 46152:
            return Response(registers=[36, 301], function_code=3)
        if address == 0x1001:
            return Response(registers=list(range(7)), function_code=3)
        if address == 0x3000:
            return Response(registers=[3], function_code=3)
        if address == 0x8000:
            return Response(registers=[0], function_code=3)
        raise AssertionError(f"Unexpected holding-register read: {kwargs}")

    async def read_input_registers(self, **kwargs):
        self.calls.append(("input", kwargs["address"], kwargs["count"]))
        return Response(registers=[0] * kwargs["count"], function_code=4)

    async def read_discrete_inputs(self, **kwargs):
        self.calls.append(("discrete", kwargs["address"], kwargs["count"]))
        return Response(bits=[False] * kwargs["count"], function_code=2)

    async def read_coils(self, **kwargs):
        self.calls.append(("coils", kwargs["address"], kwargs["count"]))
        return Response(bits=[False] * kwargs["count"], function_code=1)


@pytest.mark.asyncio
async def test_dn310_local_init_is_io_free_and_first_snapshot_is_three_reads():
    client = CountingClient()
    device = DN310(client, 1)

    await device.data_init()
    assert client.calls == []

    await device.async_get_snapshot()
    assert client.calls == [
        ("holding", 0x1001, 7),
        ("holding", 0x3000, 1),
        ("holding", 0x8000, 1),
    ]


@pytest.mark.asyncio
async def test_owen_local_init_is_io_free_and_first_snapshot_is_one_bulk_read():
    client = CountingClient()
    device = TRM138(client, 1)

    await device.data_init()
    assert client.calls == []

    snapshot = await device.async_get_snapshot()
    assert set(snapshot["chanels"]) == set(range(1, 9))
    assert client.calls == [("input", 0, 40)]


@pytest.mark.asyncio
async def test_m3000_first_snapshot_owns_all_startup_io_without_clock_write():
    client = CountingClient()
    device = M3000BB1020(client, 1)
    device._local_now = lambda: datetime(2026, 1, 2, 3, 4, 5)

    await device.data_init()
    assert client.calls == []

    snapshot = await device.async_get_snapshot()
    assert set(snapshot) == {"inputs", "outputs", "time"}
    assert len(client.calls) == 19
    assert client.calls[-1] == ("holding", 60001, 12)
    assert ("holding", 60007, 6) not in client.calls


@pytest.mark.asyncio
async def test_m3000_snapshot_sensor_and_legacy_clock_cleanup_are_one_path(
    monkeypatch,
):
    """Keep RTC display while removing only the former writable datetime entity."""
    client = CountingClient()
    device = M3000BB1020(client, 1)
    device._local_now = lambda: datetime(2026, 1, 2, 3, 4, 5)
    await device.data_init()
    snapshot = await device.async_get_snapshot()
    coordinator = SimpleNamespace(
        device=device,
        data=snapshot,
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    entry = SimpleNamespace(
        entry_id="m3000-entry",
        options={},
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    added = []

    await setup_sensor(object(), entry, lambda entities: added.extend(entities))

    device_time = next(
        entity for entity in added if entity.unique_id.endswith("_device_time")
    )
    assert device_time.unique_id == "m3000-entry_device_time"
    assert device_time.native_value == "2026-01-02 03:04:05"

    registry = SimpleNamespace(
        async_get_entity_id=Mock(return_value="datetime.m3000_clock"),
        async_remove=Mock(),
    )
    monkeypatch.setattr(integration.er, "async_get", lambda _hass: registry)
    integration._remove_legacy_clock_control(object(), entry, device)

    registry.async_get_entity_id.assert_called_once_with(
        Platform.DATETIME,
        Config.DOMAIN,
        "m3000-entry_clock_1",
    )
    registry.async_remove.assert_called_once_with("datetime.m3000_clock")
    assert Platform.DATETIME not in device.attr_platforms


@pytest.mark.asyncio
async def test_s2000pp_first_snapshot_reads_service_and_diagnostics_once():
    client = CountingClient()
    device = S2000PP(client, 1)

    await device.data_init()
    assert client.calls == []

    snapshot = await device.async_get_snapshot()
    assert set(snapshot["inputs"]) == {1, 2, 3, 4}
    assert client.calls == [("holding", 46152, 2), ("discrete", 8, 4)]


@pytest.mark.asyncio
async def test_bolid_downstream_local_init_validates_mapping_without_polling():
    device = C2000KPB(CountingClient(), 1)
    device.attr_gateway_mapping = object()
    device.async_get_snapshot = AsyncMock()

    await device.data_init()

    device.async_get_snapshot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup", "snapshot", "extra"),
    [
        (setup_binary, {"inputs": {}}, {}),
        (setup_sensor, {"chanels": {}}, {}),
        (setup_switch, {"outputs": {}}, {}),
        (setup_button, {}, {}),
    ],
)
async def test_platform_setup_uses_snapshot_or_static_descriptions_without_io(
    setup, snapshot, extra
):
    device = SimpleNamespace(
        get_inputs=AsyncMock(side_effect=AssertionError("platform input read")),
        get_outputs=AsyncMock(side_effect=AssertionError("platform output read")),
        get_chanels=AsyncMock(side_effect=AssertionError("platform channel read")),
        **extra,
    )
    coordinator = Mock(data=snapshot, last_update_success=True)
    coordinator.device = device
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    hass = SimpleNamespace(data={})
    added = []

    await setup(hass, entry, lambda entities: added.extend(entities))

    assert added == []
    device.get_inputs.assert_not_awaited()
    device.get_outputs.assert_not_awaited()
    device.get_chanels.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_platforms_resolve_one_shared_entry_runtime_object():
    device = SimpleNamespace(
        get_inputs=AsyncMock(),
        get_outputs=AsyncMock(),
        get_chanels=AsyncMock(),
    )
    coordinator = Mock(data={"inputs": {}, "outputs": {}, "chanels": {}})
    coordinator.device = device
    runtime = SimpleNamespace(coordinator=coordinator)
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=runtime)
    hass = SimpleNamespace(data={})

    for setup in (
        setup_sensor,
        setup_binary,
        setup_switch,
        setup_button,
    ):
        await setup(hass, entry, lambda _entities: None)
        assert entry.runtime_data is runtime

    device.get_inputs.assert_not_awaited()
    device.get_outputs.assert_not_awaited()
    device.get_chanels.assert_not_awaited()
