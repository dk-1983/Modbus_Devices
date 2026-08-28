"""RTC lifecycle tests for the direct M3000-BB-1020 device."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import custom_components.modbus_devices as integration
from custom_components.modbus_devices.equipment import bolid
from custom_components.modbus_devices.equipment.bolid import M3000BB1020
from custom_components.modbus_devices.sensor import (
    ModBusDeviceTimeSensorEntity,
    async_setup_entry as setup_sensor,
)
from pymodbus.exceptions import ModbusException
import pytest

from homeassistant.const import Platform


class Response:
    address = 60007
    count = 6
    device_id = 1

    def __init__(self, *, error=False, registers=None, function_code=16):
        self._error = error
        self.registers = registers
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self):
        self.writes = []
        self.reads = []
        self.write_response = Response()
        self.read_response = Response(
            registers=[2026, 8, 26, 20, 45, 12],
            function_code=3,
        )

    async def write_registers(self, **kwargs):
        self.writes.append(kwargs)
        return self.write_response

    async def read_holding_registers(self, **kwargs):
        self.reads.append(kwargs)
        if kwargs["count"] == M3000BB1020.RUNTIME_HEADER_REGISTER_COUNT:
            return Response(
                registers=[74, 100, 100, 1, 2, 3, *self.read_response.registers],
                function_code=3,
            )
        return self.read_response


def device_at(now: datetime, client=None):
    device = M3000BB1020(client or Client(), 1)
    device._local_now = lambda: now
    return device


@pytest.mark.asyncio
async def test_rtc_decode_preserves_timezone_less_device_wall_clock():
    device_time = await M3000BB1020(Client(), 1).get_time()

    assert device_time == datetime(2026, 8, 26, 20, 45, 12)
    assert device_time.tzinfo is None


@pytest.mark.asyncio
async def test_runtime_header_reads_documented_info_and_rtc_block_once():
    client = Client()
    device = M3000BB1020(client, 1)

    device_time = await device._get_runtime_header()

    assert device_time == datetime(2026, 8, 26, 20, 45, 12)
    assert device.attr_device_type == 74
    assert device.attr_software_version == 100
    assert device.attr_hardware_version == 100
    assert device.attr_serial_number == "123"
    assert client.reads == [
        {"address": 60001, "count": 12, "device_id": 1}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("drift_seconds", [0, 5, 10, -10])
async def test_clock_drift_at_or_below_tolerance_does_not_write(drift_seconds):
    now = datetime(2026, 8, 26, 20, 45, 12)
    device = device_at(now)

    corrected = await device._async_correct_clock(
        now + timedelta(seconds=drift_seconds),
        now,
    )

    assert corrected is False
    assert device.attr_client.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("drift_seconds", [11, -11, -86400])
async def test_clock_drift_above_tolerance_writes_exactly_once(drift_seconds):
    now = datetime(2026, 8, 26, 20, 45, 12)
    device = device_at(now)

    corrected = await device._async_correct_clock(
        now + timedelta(seconds=drift_seconds),
        now,
    )

    assert corrected is True
    assert device.attr_client.writes == [
        {
            "address": 60007,
            "values": [2026, 8, 26, 20, 45, 12],
            "device_id": 1,
        }
    ]


@pytest.mark.asyncio
async def test_set_time_defaults_to_home_assistant_configured_time(monkeypatch):
    now = datetime(2026, 8, 26, 21, 10, 5, tzinfo=timezone(timedelta(hours=5)))
    client = Client()
    device = M3000BB1020(client, 1)
    monkeypatch.setattr(bolid.dt_util, "now", lambda: now)

    assert await device.set_time() == now
    assert client.writes[0]["values"] == [2026, 8, 26, 21, 10, 5]


@pytest.mark.asyncio
async def test_clock_write_has_no_immediate_readback():
    client = Client()
    client.read_holding_registers = AsyncMock(side_effect=AssertionError("blind readback"))
    device = M3000BB1020(client, 1)

    await device.set_time(datetime(2026, 8, 26, 20, 45, 12))

    client.read_holding_registers.assert_not_awaited()


@pytest.mark.asyncio
async def test_clock_writes_cannot_overlap():
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    active = 0
    max_active = 0

    class BlockingClient(Client):
        async def write_registers(self, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            if not first_started.is_set():
                first_started.set()
                await release_first.wait()
            response = await super().write_registers(**kwargs)
            active -= 1
            return response

    device = M3000BB1020(BlockingClient(), 1)
    first = asyncio.create_task(device.set_time(datetime(2026, 8, 26, 20, 0, 0)))
    await first_started.wait()
    second = asyncio.create_task(device.set_time(datetime(2026, 8, 26, 21, 0, 0)))
    await asyncio.sleep(0)
    release_first.set()
    await asyncio.gather(first, second)

    assert max_active == 1


@pytest.mark.asyncio
async def test_sync_protocol_failure_is_not_retried_or_faked():
    client = Client()
    client.write_response = Response(error=True)
    device = device_at(datetime(2026, 8, 26, 20, 45, 12), client)

    corrected = await device._async_correct_clock(
        datetime(2000, 1, 1),
        datetime(2026, 8, 26, 20, 45, 12),
    )

    assert corrected is False
    assert len(client.writes) == 1
    assert device.attr_init_time is None


@pytest.mark.asyncio
async def test_snapshot_reads_rtc_naturally_and_exposes_actual_value():
    device = M3000BB1020(Client(), 1)
    device.get_inputs = AsyncMock(return_value=[])
    device.get_outputs = AsyncMock(return_value=[])
    device._get_runtime_header = AsyncMock(
        return_value=datetime(2026, 8, 26, 20, 45, 12)
    )
    device._async_correct_clock = AsyncMock(return_value=False)
    device._local_now = lambda: datetime(2026, 8, 26, 20, 45, 13)

    snapshot = await device.async_get_snapshot()

    assert snapshot["time"] == datetime(2026, 8, 26, 20, 45, 12)
    device._get_runtime_header.assert_awaited_once_with()
    device._async_correct_clock.assert_awaited_once_with(
        datetime(2026, 8, 26, 20, 45, 12),
        datetime(2026, 8, 26, 20, 45, 13),
    )


@pytest.mark.asyncio
async def test_first_and_ordinary_snapshots_share_one_correction_policy():
    now = datetime(2026, 8, 26, 20, 45, 12)
    device = device_at(now)
    device.get_inputs = AsyncMock(return_value=[])
    device.get_outputs = AsyncMock(return_value=[])
    device._get_runtime_header = AsyncMock(
        side_effect=[datetime(2000, 1, 1), now]
    )
    device.set_time = AsyncMock()

    first = await device.async_get_snapshot()
    ordinary = await device.async_get_snapshot()

    assert first["time"] == datetime(2000, 1, 1)
    assert ordinary["time"] == now
    device.set_time.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_failed_rtc_modbus_read_does_not_write_or_discard_other_data():
    device = M3000BB1020(Client(), 1)
    device.get_inputs = AsyncMock(return_value=[{"input_number": 1, "state": True}])
    device.get_outputs = AsyncMock(return_value=[{"out_number": 1, "state": False}])
    device._get_runtime_header = AsyncMock(
        side_effect=ModbusException("invalid RTC")
    )
    device.set_time = AsyncMock()

    snapshot = await device.async_get_snapshot()

    assert snapshot == {
        "inputs": {1: {"input_number": 1, "state": True}},
        "outputs": {1: {"out_number": 1, "state": False}},
        "time": None,
    }
    device.set_time.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_read_with_invalid_calendar_fields_corrects_once():
    now = datetime(2026, 8, 26, 20, 45, 12)
    client = Client()
    client.read_response = Response(
        registers=[0, 0, 0, 0, 0, 0],
        function_code=3,
    )
    device = device_at(now, client)
    device.get_inputs = AsyncMock(return_value=[])
    device.get_outputs = AsyncMock(return_value=[])

    invalid_snapshot = await device.async_get_snapshot()

    assert invalid_snapshot["time"] is None
    assert len(client.writes) == 1
    assert client.writes[0]["values"] == [2026, 8, 26, 20, 45, 12]

    client.read_response = Response(
        registers=[2026, 8, 26, 20, 45, 12],
        function_code=3,
    )
    valid_snapshot = await device.async_get_snapshot()

    assert valid_snapshot["time"] == now
    assert len(client.writes) == 1


@pytest.mark.asyncio
async def test_failed_write_cooldown_suppresses_poll_rate_retry_storm():
    now = datetime(2026, 8, 26, 20, 45, 12)
    device = device_at(now)
    device.get_inputs = AsyncMock(
        return_value=[{"input_number": 1, "state": True}]
    )
    device.get_outputs = AsyncMock(
        return_value=[{"out_number": 1, "state": False}]
    )
    device._get_runtime_header = AsyncMock(return_value=datetime(2000, 1, 1))
    device.set_time = AsyncMock(side_effect=ModbusException("write failed"))
    device._monotonic_now = Mock(side_effect=[100, 100, 105, 110, 160, 160])

    snapshots = [await device.async_get_snapshot() for _ in range(4)]

    assert device.set_time.await_count == 2
    assert all(snapshot["inputs"][1]["state"] is True for snapshot in snapshots)
    assert all(snapshot["outputs"][1]["state"] is False for snapshot in snapshots)
    assert all(snapshot["time"] == datetime(2000, 1, 1) for snapshot in snapshots)


@pytest.mark.asyncio
async def test_clock_write_failure_does_not_discard_other_snapshot_data():
    now = datetime(2026, 8, 26, 20, 45, 12)
    device = device_at(now)
    device.get_inputs = AsyncMock(return_value=[{"input_number": 1, "state": True}])
    device.get_outputs = AsyncMock(return_value=[{"out_number": 1, "state": False}])
    device._get_runtime_header = AsyncMock(return_value=datetime(2000, 1, 1))
    device.set_time = AsyncMock(side_effect=ModbusException("write failed"))

    snapshot = await device.async_get_snapshot()

    assert snapshot["inputs"][1]["state"] is True
    assert snapshot["outputs"][1]["state"] is False
    assert snapshot["time"] == datetime(2000, 1, 1)
    device.set_time.assert_awaited_once_with()


def test_read_only_sensor_preserves_literal_wall_clock_fields():
    coordinator = SimpleNamespace(
        data={"time": datetime(2026, 8, 26, 20, 45, 12)},
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    device = SimpleNamespace(
        attr_manufactures_name="Bolid",
        attr_model_name="M3000-BB-1020",
        attr_description="Programmable relay",
        attr_hardware_version="1.0",
        attr_software_version="1.0",
        attr_serial_number="123",
    )
    entry = SimpleNamespace(entry_id="m3000", options={})

    entity = ModBusDeviceTimeSensorEntity(coordinator, device, entry)

    assert entity.native_value == "2026-08-26 20:45:12"
    assert entity.device_class is None
    assert entity.unique_id == "m3000_device_time"


def test_invalid_rtc_is_unknown_without_hiding_other_device_entities():
    coordinator = SimpleNamespace(
        data={"time": None, "inputs": {1: {"state": True}}},
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    device = SimpleNamespace(
        attr_manufactures_name="Bolid",
        attr_model_name="M3000-BB-1020",
        attr_description="Programmable relay",
        attr_hardware_version="1.0",
        attr_software_version="1.0",
        attr_serial_number="123",
    )
    entity = ModBusDeviceTimeSensorEntity(
        coordinator,
        device,
        SimpleNamespace(entry_id="m3000", options={}),
    )

    assert entity.available is True
    assert entity.native_value is None
    assert coordinator.data["inputs"][1]["state"] is True


@pytest.mark.asyncio
async def test_sensor_platform_adds_device_time_without_modbus_io():
    device = M3000BB1020(Client(), 1)
    device.get_time = AsyncMock(side_effect=AssertionError("platform RTC read"))
    coordinator = SimpleNamespace(
        device=device,
        data={"time": datetime(2026, 8, 26, 20, 45, 12)},
        last_update_success=True,
        async_add_listener=Mock(return_value=Mock()),
    )
    entry = SimpleNamespace(
        entry_id="m3000",
        options={},
        runtime_data=SimpleNamespace(coordinator=coordinator),
    )
    added = []

    await setup_sensor(object(), entry, lambda entities: added.extend(entities))

    assert len(added) == 1
    assert isinstance(added[0], ModBusDeviceTimeSensorEntity)
    device.get_time.assert_not_awaited()


def test_m3000_replaces_manual_datetime_platform_with_read_only_sensor():
    device = M3000BB1020(Client(), 1)

    assert device.attr_platforms == [
        Platform.BINARY_SENSOR,
        Platform.SENSOR,
        Platform.SWITCH,
    ]
    assert not hasattr(device, "attr_clock_iter")


def test_legacy_manual_clock_registry_entry_is_removed_idempotently(monkeypatch):
    registry = SimpleNamespace(
        async_get_entity_id=Mock(side_effect=["datetime.m3000_clock", None]),
        async_remove=Mock(),
    )
    monkeypatch.setattr(integration.er, "async_get", lambda _hass: registry)
    entry = SimpleNamespace(entry_id="m3000")
    device = SimpleNamespace(attr_has_device_time_sensor=True)

    integration._remove_legacy_clock_control(object(), entry, device)
    integration._remove_legacy_clock_control(object(), entry, device)

    registry.async_remove.assert_called_once_with("datetime.m3000_clock")


def test_no_separate_rtc_scheduler_exists():
    source = Path(integration.__file__)

    assert "async_track_time_interval" not in source.read_text(encoding="utf-8")
