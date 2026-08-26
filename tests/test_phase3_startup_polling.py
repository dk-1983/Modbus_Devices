"""Characterization tests for coordinator-owned startup polling."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.modbus_devices.binary_sensor import async_setup_entry as setup_binary
from custom_components.modbus_devices.button import async_setup_entry as setup_button
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.datetime import async_setup_entry as setup_datetime
from custom_components.modbus_devices.equipment.bolid import C2000KPB, M3000BB1020, S2000PP
from custom_components.modbus_devices.equipment.dyna_drive import DN310
from custom_components.modbus_devices.equipment.owen import TRM138
from custom_components.modbus_devices.sensor import async_setup_entry as setup_sensor
from custom_components.modbus_devices.switch import async_setup_entry as setup_switch


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
            return Response(registers=[1, 2, 3, 4, 5, 6], function_code=3)
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
async def test_owen_local_init_is_io_free_and_first_snapshot_reads_eight_channels():
    client = CountingClient()
    device = TRM138(client, 1)

    await device.data_init()
    assert client.calls == []

    channels = await device.get_chanels()
    assert len(channels) == 8
    assert len(client.calls) == 8


@pytest.mark.asyncio
async def test_m3000_first_snapshot_owns_all_startup_io_without_clock_write():
    client = CountingClient()
    device = M3000BB1020(client, 1)
    device._local_now = lambda: datetime(2026, 1, 2, 3, 4, 5)

    await device.data_init()
    assert client.calls == []

    snapshot = await device.async_get_snapshot()
    assert set(snapshot) == {"inputs", "outputs", "time"}
    assert len(client.calls) == 20
    assert client.calls[0] == ("holding", 60001, 6)
    assert client.calls[-1] == ("holding", 60007, 6)


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
        (setup_datetime, {"time": None}, {"attr_clock_iter": []}),
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
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=SimpleNamespace(device=device, coordinator=coordinator),
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
        attr_clock_iter=[],
        get_inputs=AsyncMock(),
        get_outputs=AsyncMock(),
        get_chanels=AsyncMock(),
    )
    coordinator = Mock(data={"inputs": {}, "outputs": {}, "chanels": {}})
    runtime = SimpleNamespace(device=device, coordinator=coordinator)
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=runtime)
    hass = SimpleNamespace(data={})

    for setup in (
        setup_sensor,
        setup_binary,
        setup_switch,
        setup_datetime,
        setup_button,
    ):
        await setup(hass, entry, lambda _entities: None)
        assert entry.runtime_data is runtime

    device.get_inputs.assert_not_awaited()
    device.get_outputs.assert_not_awaited()
    device.get_chanels.assert_not_awaited()
