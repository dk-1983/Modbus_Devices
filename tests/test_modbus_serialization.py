"""Characterize shared physical Modbus request serialization."""

from __future__ import annotations

import asyncio

import pytest

from custom_components.modbus_devices.modbus_client import (
    SerializedModbusClient,
    ensure_serialized_client,
)
from custom_components.modbus_devices.s2000_pp import (
    NumericParameterKind,
    S2000PPNumericValueReader,
)


class BlockingClient:
    connected = True

    def __init__(self):
        self.started = asyncio.Queue()
        self.release = asyncio.Event()
        self.active = 0
        self.maximum_active = 0
        self.trace = []

    def close(self):
        self.connected = False

    async def _request(self, name, **kwargs):
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.trace.append(("start", name, kwargs.get("address")))
        await self.started.put(name)
        await self.release.wait()
        self.trace.append(("end", name, kwargs.get("address")))
        self.active -= 1
        return object()

    async def read_holding_registers(self, **kwargs):
        return await self._request("poll", **kwargs)

    async def write_coil(self, **kwargs):
        return await self._request("switch", **kwargs)

    async def write_register(self, **kwargs):
        return await self._request("button", **kwargs)

    async def write_registers(self, **kwargs):
        return await self._request("datetime", **kwargs)


def test_serialized_client_is_idempotent_and_owns_underlying_lifecycle():
    raw = BlockingClient()
    client = ensure_serialized_client(raw)
    assert isinstance(client, SerializedModbusClient)
    assert ensure_serialized_client(client) is client
    assert client.connected is True
    client.close()
    assert client.connected is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("read_holding_registers", "write_coil"),
        ("write_coil", "read_holding_registers"),
        ("read_holding_registers", "write_register"),
        ("read_holding_registers", "write_registers"),
        ("write_coil", "write_register"),
        ("write_coil", "write_coil"),
    ],
)
async def test_same_client_serializes_poll_and_all_write_platforms(first, second):
    raw = BlockingClient()
    client = SerializedModbusClient(raw)
    task_a = asyncio.create_task(getattr(client, first)(address=1, count=1))
    assert await raw.started.get() in {"poll", "switch", "button", "datetime"}

    task_b = asyncio.create_task(getattr(client, second)(address=2, count=1))
    await asyncio.sleep(0)
    assert raw.active == 1
    assert raw.started.empty()

    raw.release.set()
    await asyncio.gather(task_a, task_b)
    assert raw.maximum_active == 1


@pytest.mark.asyncio
async def test_different_clients_do_not_share_request_lock():
    first = BlockingClient()
    second = BlockingClient()
    client_a = SerializedModbusClient(first)
    client_b = SerializedModbusClient(second)

    task_a = asyncio.create_task(client_a.read_holding_registers(address=1, count=1))
    task_b = asyncio.create_task(client_b.write_coil(address=2, value=True))
    await first.started.get()
    await second.started.get()
    assert first.active == second.active == 1

    first.release.set()
    second.release.set()
    await asyncio.gather(task_a, task_b)


class SelectorResponse:
    function_code = 6
    address = 46179
    value = 1

    def isError(self):
        return False


class NumericResponse:
    function_code = 3
    registers = [256]

    def isError(self):
        return False


@pytest.mark.asyncio
async def test_selector_lock_precedes_request_lock_and_sequence_cannot_interleave():
    class Client:
        connected = True

        def __init__(self):
            self.trace = []

        async def write_register(self, **kwargs):
            self.trace.append("selector")
            await asyncio.sleep(0)
            return SelectorResponse()

        async def read_holding_registers(self, **kwargs):
            name = "result" if kwargs["address"] == 46328 else "ordinary"
            self.trace.append(name)
            await asyncio.sleep(0)
            return NumericResponse()

    raw = Client()
    client = SerializedModbusClient(raw)
    reader = S2000PPNumericValueReader(client, 1, "lock-hierarchy")

    selector = asyncio.create_task(
        reader.async_read(1, NumericParameterKind.TEMPERATURE)
    )
    ordinary = asyncio.create_task(
        client.read_holding_registers(address=100, count=1, device_id=1)
    )
    await asyncio.wait_for(asyncio.gather(selector, ordinary), timeout=1)

    assert raw.trace in (
        ["selector", "result", "ordinary"],
        ["ordinary", "selector", "result"],
    )


@pytest.mark.asyncio
async def test_fc05_cannot_enter_between_selector_and_result():
    class Client:
        def __init__(self):
            self.trace = []

        async def write_register(self, **kwargs):
            self.trace.append("selector")
            await asyncio.sleep(0)
            return SelectorResponse()

        async def read_holding_registers(self, **kwargs):
            self.trace.append("result")
            await asyncio.sleep(0)
            return NumericResponse()

        async def write_coil(self, **kwargs):
            self.trace.append("fc05")
            await asyncio.sleep(0)
            return object()

    raw = Client()
    client = SerializedModbusClient(raw)
    await asyncio.gather(
        S2000PPNumericValueReader(client, 1, "fc05-exclusion").async_read(
            1, NumericParameterKind.TEMPERATURE
        ),
        client.write_coil(address=10000, value=True, device_id=1),
    )
    assert raw.trace in (
        ["selector", "result", "fc05"],
        ["fc05", "selector", "result"],
    )


@pytest.mark.asyncio
async def test_two_selector_transactions_do_not_interleave_or_deadlock():
    class Client:
        connected = True

        def __init__(self):
            self.trace = []

        async def write_register(self, **kwargs):
            self.trace.append(("selector", kwargs["value"]))
            await asyncio.sleep(0)
            response = SelectorResponse()
            response.value = kwargs["value"]
            return response

        async def read_holding_registers(self, **kwargs):
            self.trace.append(("result", None))
            await asyncio.sleep(0)
            return NumericResponse()

    raw = Client()
    client = SerializedModbusClient(raw)
    first = S2000PPNumericValueReader(client, 1, "same-gateway")
    second = S2000PPNumericValueReader(client, 1, "same-gateway")
    await asyncio.wait_for(
        asyncio.gather(
            first.async_read(1, NumericParameterKind.TEMPERATURE),
            second.async_read(2, NumericParameterKind.TEMPERATURE),
        ),
        timeout=1,
    )
    assert raw.trace == [
        ("selector", 1),
        ("result", None),
        ("selector", 2),
        ("result", None),
    ]


@pytest.mark.asyncio
async def test_selector_sessions_are_scoped_per_client_not_process_global():
    class PendingClient:
        connected = True

        async def write_register(self, **kwargs):
            response = SelectorResponse()
            response.value = kwargs["value"]
            return response

        async def read_holding_registers(self, **kwargs):
            response = NumericResponse()
            response._error = False
            return response

    first = SerializedModbusClient(PendingClient())
    second = SerializedModbusClient(PendingClient())
    results = await asyncio.gather(
        S2000PPNumericValueReader(first, 1, "same-key").async_read(
            1, NumericParameterKind.TEMPERATURE
        ),
        S2000PPNumericValueReader(second, 1, "same-key").async_read(
            2, NumericParameterKind.TEMPERATURE
        ),
    )
    assert all(result.value == 1.0 for result in results)
