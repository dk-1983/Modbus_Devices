"""S2000-PP-specific FC05 relay write policy tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.modbus_client import SerializedModbusClient
from custom_components.modbus_devices.s2000_pp import (
    NumericParameterKind,
    S2000_PP_FC05_MAX_ATTEMPTS,
    S2000PPNumericValueReader,
    async_write_s2000_pp_relay,
)


class Response:
    def __init__(
        self,
        *,
        function_code=5,
        address=10040,
        value=True,
        exception_code=None,
        dev_id=1,
        error=False,
        bits=None,
    ):
        self.function_code = function_code
        self.address = address
        self.value = value
        self.exception_code = exception_code
        self.dev_id = dev_id
        self._error = error
        self.bits = bits

    def isError(self):
        return self._error


def pending(device_id=1):
    return Response(
        function_code=0x85,
        address=None,
        value=None,
        exception_code=15,
        dev_id=device_id,
        error=True,
    )


class SequenceClient:
    def __init__(self, responses, verification=None):
        self.responses = list(responses)
        self.verification = verification
        self.calls = []
        self.reads = []

    async def write_coil(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def read_coils(self, **kwargs):
        self.reads.append(kwargs)
        if isinstance(self.verification, BaseException):
            raise self.verification
        return self.verification


async def write(client, *, address=10040, value=True, device_id=1):
    return await async_write_s2000_pp_relay(
        client,
        address=address,
        value=value,
        device_id=device_id,
        operation="test relay",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses",
    [[Response()], [pending(), Response()], [pending(), pending(), Response()]],
)
async def test_valid_echo_and_pending_retries_preserve_exact_request(
    monkeypatch, responses
):
    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.S2000_PP_FC05_RETRY_DELAY", 0
    )
    client = SequenceClient(responses)

    result = await write(client)

    assert result.confirmation.value == "fc05_echo"
    assert result.response.function_code == 5
    assert result.verified_state is True
    assert client.reads == []
    assert client.calls == [{"address": 10040, "value": True, "device_id": 1}] * len(
        responses
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [False, True])
async def test_pending_exhaustion_matching_readback_is_verified_success(
    monkeypatch, value
):
    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.S2000_PP_FC05_RETRY_DELAY", 0
    )
    client = SequenceClient(
        [pending()] * S2000_PP_FC05_MAX_ATTEMPTS,
        Response(function_code=1, bits=[value], dev_id=1),
    )

    result = await write(client, value=value)

    assert len(client.calls) == S2000_PP_FC05_MAX_ATTEMPTS
    assert client.reads == [{"address": 10040, "count": 1, "device_id": 1}]
    assert result.confirmation.value == "fc01_readback"
    assert result.attempts == 3
    assert result.verified_state is value


@pytest.mark.asyncio
async def test_pending_exhaustion_readback_mismatch_is_failure(monkeypatch):
    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.S2000_PP_FC05_RETRY_DELAY", 0
    )
    client = SequenceClient(
        [pending()] * S2000_PP_FC05_MAX_ATTEMPTS,
        Response(function_code=1, bits=[False], dev_id=1),
    )

    with pytest.raises(ModbusException, match="readback mismatch") as raised:
        await write(client, value=True)

    assert raised.value.verified_state is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verification", "message"),
    [
        (Response(function_code=0x81, exception_code=4, error=True), "error response"),
        (None, "Empty Modbus response"),
        (Response(function_code=1, bits=[]), "Short Modbus response"),
        (Response(function_code=1, bits=[1]), "Invalid FC01 bit payload"),
        (Response(function_code=3, bits=[True]), "Wrong Modbus function"),
        (Response(function_code=1, bits=[True], dev_id=2), "device id"),
    ],
)
async def test_pending_exhaustion_invalid_readback_is_failure(
    monkeypatch, verification, message
):
    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.S2000_PP_FC05_RETRY_DELAY", 0
    )
    client = SequenceClient([pending()] * 3, verification)

    with pytest.raises(ModbusException, match=message):
        await write(client)

    assert len(client.calls) == 3
    assert len(client.reads) == 1


@pytest.mark.asyncio
async def test_pending_exhaustion_readback_timeout_is_failure(monkeypatch):
    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.S2000_PP_FC05_RETRY_DELAY", 0
    )
    client = SequenceClient([pending()] * 3, TimeoutError("verification timeout"))

    with pytest.raises(TimeoutError, match="verification timeout"):
        await write(client)

    assert len(client.calls) == 3
    assert len(client.reads) == 1


@pytest.mark.asyncio
async def test_exhaustion_uses_exact_attempt_sleep_and_read_counts(monkeypatch):
    sleeps = []

    async def record_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.asyncio.sleep", record_sleep
    )
    client = SequenceClient(
        [pending()] * 3,
        Response(function_code=1, bits=[True], dev_id=1),
    )

    result = await write(client)

    assert result.confirmation.value == "fc01_readback"
    assert client.calls == [{"address": 10040, "value": True, "device_id": 1}] * 3
    assert sleeps == [0.1, 0.1]
    assert client.reads == [{"address": 10040, "count": 1, "device_id": 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (Response(function_code=0x85, exception_code=3, error=True), "error response"),
        (Response(function_code=0x85, exception_code=4, error=True), "error response"),
        (Response(function_code=0x85, exception_code=6, error=True), "error response"),
        (Response(function_code=0x86, exception_code=15, error=True), "error response"),
        (SimpleNamespace(function_code=0x85, exception_code=15), "Invalid"),
        (Response(function_code=6), "Wrong Modbus function"),
        (Response(address=10041), "address echo"),
        (Response(value=False), "value echo"),
    ],
)
async def test_non_pending_and_malformed_responses_are_never_retried(response, message):
    client = SequenceClient([response])

    with pytest.raises(ModbusException, match=message):
        await write(client)

    assert len(client.calls) == 1
    assert client.reads == []


@pytest.mark.asyncio
async def test_timeout_is_never_retried():
    client = SequenceClient([asyncio.TimeoutError("after send")])

    with pytest.raises(asyncio.TimeoutError):
        await write(client)

    assert len(client.calls) == 1
    assert client.reads == []


@pytest.mark.asyncio
async def test_poll_cannot_enter_physical_client_between_retry_attempts(monkeypatch):
    real_sleep = asyncio.sleep
    sleep_started = asyncio.Event()
    release_sleep = asyncio.Event()

    async def controlled_sleep(_delay):
        sleep_started.set()
        await release_sleep.wait()

    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.asyncio.sleep", controlled_sleep
    )

    class Client:
        def __init__(self):
            self.trace = []
            self.attempt = 0

        async def write_coil(self, **kwargs):
            self.attempt += 1
            self.trace.append(("write", self.attempt))
            return pending() if self.attempt == 1 else Response()

        async def read_coils(self, **kwargs):
            self.trace.append(("poll", kwargs["address"]))
            return SimpleNamespace(bits=[True])

    raw = Client()
    client = SerializedModbusClient(raw)
    write_task = asyncio.create_task(write(client))
    await sleep_started.wait()
    poll_task = asyncio.create_task(
        client.read_coils(address=10040, count=1, device_id=1)
    )
    await real_sleep(0)
    assert raw.trace == [("write", 1)]

    release_sleep.set()
    await asyncio.gather(write_task, poll_task)
    assert raw.trace == [("write", 1), ("write", 2), ("poll", 10040)]


@pytest.mark.asyncio
async def test_concurrent_relay_retry_sequences_do_not_interleave(monkeypatch):
    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.S2000_PP_FC05_RETRY_DELAY", 0
    )

    class Client:
        def __init__(self):
            self.trace = []
            self.attempts = {}

        async def write_coil(self, **kwargs):
            address = kwargs["address"]
            self.attempts[address] = self.attempts.get(address, 0) + 1
            self.trace.append(address)
            await asyncio.sleep(0)
            return (
                pending()
                if self.attempts[address] == 1
                else Response(
                    address=address,
                    value=kwargs["value"],
                )
            )

    raw = Client()
    client = SerializedModbusClient(raw)
    await asyncio.gather(
        write(client, address=10040, value=True),
        write(client, address=10041, value=False),
    )

    assert raw.trace in ([10040, 10040, 10041, 10041], [10041, 10041, 10040, 10040])


@pytest.mark.asyncio
async def test_exhaustion_readback_excludes_poll_numeric_and_another_fc05(monkeypatch):
    monkeypatch.setattr(
        "custom_components.modbus_devices.s2000_pp.S2000_PP_FC05_RETRY_DELAY", 0
    )

    class Client:
        def __init__(self):
            self.trace = []
            self.verification_started = asyncio.Event()
            self.release_verification = asyncio.Event()

        async def write_coil(self, **kwargs):
            self.trace.append(("fc05", kwargs["address"]))
            return (
                pending()
                if kwargs["address"] == 10040
                else Response(address=kwargs["address"], value=kwargs["value"])
            )

        async def read_coils(self, **kwargs):
            if kwargs["address"] == 10040:
                self.trace.append(("verification", 10040))
                self.verification_started.set()
                await self.release_verification.wait()
            else:
                self.trace.append(("poll", kwargs["address"]))
            return Response(function_code=1, bits=[True], dev_id=1)

        async def write_register(self, **kwargs):
            self.trace.append(("selector", kwargs["value"]))
            return SimpleNamespace(
                function_code=6,
                address=kwargs["address"],
                value=kwargs["value"],
                isError=lambda: False,
            )

        async def read_holding_registers(self, **kwargs):
            self.trace.append(("numeric_result", kwargs["address"]))
            return SimpleNamespace(
                function_code=3, registers=[0x0100], isError=lambda: False
            )

    raw = Client()
    client = SerializedModbusClient(raw)
    primary = asyncio.create_task(write(client))
    await raw.verification_started.wait()
    poll = asyncio.create_task(client.read_coils(address=1, count=1, device_id=1))
    numeric = asyncio.create_task(
        S2000PPNumericValueReader(client, 1, "relay-exclusion").async_read(
            5, NumericParameterKind.TEMPERATURE
        )
    )
    secondary = asyncio.create_task(write(client, address=10041))
    await asyncio.sleep(0)
    assert raw.trace == [
        ("fc05", 10040),
        ("fc05", 10040),
        ("fc05", 10040),
        ("verification", 10040),
    ]

    raw.release_verification.set()
    await asyncio.gather(primary, poll, numeric, secondary)
    assert raw.trace[:4] == [
        ("fc05", 10040),
        ("fc05", 10040),
        ("fc05", 10040),
        ("verification", 10040),
    ]
    selector_index = raw.trace.index(("selector", 5))
    result_index = raw.trace.index(("numeric_result", 46328))
    assert result_index == selector_index + 1
