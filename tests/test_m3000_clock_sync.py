"""Conditional startup clock synchronization for M3000-BB-1020."""

from datetime import datetime, timedelta, timezone

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.equipment.bolid import M3000BB1020


class Response:
    def __init__(self, *, error=False):
        self._error = error

    def isError(self):
        return self._error


class Client:
    def __init__(self):
        self.writes = []
        self.response = Response()

    async def write_registers(self, **kwargs):
        self.writes.append(kwargs)
        return self.response


def device_at(now: datetime, client=None):
    device = M3000BB1020(client or Client(), 1)
    device._local_now = lambda: now
    return device


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", [timedelta(0), timedelta(seconds=119)])
async def test_correct_or_small_clock_drift_does_not_write(drift):
    now = datetime(2026, 8, 22, 12, 0, 0)
    device = device_at(now)

    assert await device.async_post_first_refresh({"time": now - drift}) is False
    assert device.attr_client.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", [timedelta(seconds=120), timedelta(seconds=-120)])
async def test_large_clock_drift_synchronizes_exactly_once(drift):
    now = datetime(2026, 8, 22, 12, 0, 0)
    device = device_at(now)

    assert await device.async_post_first_refresh({"time": now - drift}) is True
    assert await device.async_post_first_refresh({"time": now - drift}) is False
    assert device.attr_client.writes == [
        {
            "address": 60007,
            "values": [2026, 8, 22, 12, 0, 0],
            "device_id": 1,
        }
    ]


@pytest.mark.asyncio
async def test_old_valid_clock_synchronizes_by_drift_not_reset_heuristic():
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    old_clock = datetime(2000, 1, 1, tzinfo=timezone(timedelta(hours=7)))
    device = device_at(now)

    assert await device.async_post_first_refresh({"time": old_clock}) is True
    assert device.attr_client.writes[0]["values"] == [2026, 8, 22, 12, 0, 0]


@pytest.mark.asyncio
async def test_missing_clock_snapshot_never_becomes_a_sync_write():
    device = device_at(datetime(2026, 8, 22, 12, 0, 0))

    assert await device.async_post_first_refresh({}) is False
    assert device.attr_client.writes == []


@pytest.mark.asyncio
async def test_sync_protocol_failure_is_not_retried_or_faked():
    client = Client()
    client.response = Response(error=True)
    now = datetime(2026, 8, 22, 12, 0, 0)
    device = device_at(now, client)

    with pytest.raises(ModbusException):
        await device.async_post_first_refresh({"time": datetime(2000, 1, 1)})

    assert len(client.writes) == 1
    assert device.attr_init_time is None
    assert await device.async_post_first_refresh({"time": datetime(2000, 1, 1)}) is False
    assert len(client.writes) == 1


@pytest.mark.asyncio
async def test_manual_clock_write_remains_available_after_automatic_evaluation():
    now = datetime(2026, 8, 22, 12, 0, 0)
    device = device_at(now)
    await device.async_post_first_refresh({"time": now})

    manual = datetime(2026, 8, 22, 13, 15, 30)
    assert await device.set_time(manual) == manual
    assert device.attr_client.writes == [
        {
            "address": 60007,
            "values": [2026, 8, 22, 13, 15, 30],
            "device_id": 1,
        }
    ]
