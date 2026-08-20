"""Tests for the documented S2000-PP unsigned 48-bit counter transport."""

import asyncio

import pytest

from custom_components.modbus_devices.s2000_pp import (
    NumericParameterKind,
    NumericResultStatus,
    S2000PPCounterValueReader,
    S2000PPNumericValueReader,
    decode_s2000_pp_counter,
)


class Response:
    def __init__(self, *, registers=None, error=False, code=None, address=None, value=None):
        self.registers = registers
        self._error = error
        self.exception_code = code
        self.address = address
        self.value = value

    def isError(self):
        return self._error


class Client:
    def __init__(self, result=None):
        self.result = result or Response(registers=[0, 0, 0])
        self.writes = []
        self.reads = []

    async def write_register(self, **kwargs):
        self.writes.append(kwargs)
        return Response(address=kwargs["address"], value=kwargs["value"])

    async def read_holding_registers(self, **kwargs):
        self.reads.append(kwargs)
        return self.result


@pytest.mark.parametrize(
    ("registers", "expected"),
    [
        ([0, 0, 0], 0),
        ([0, 0, 1], 1),
        ([0x1234, 0x5678, 0x9ABC], 0x123456789ABC),
        ([0xFFFF, 0xFFFF, 0xFFFF], 0xFFFFFFFFFFFF),
    ],
)
def test_unsigned_48_bit_big_endian_decoder(registers, expected):
    assert decode_s2000_pp_counter(registers) == expected


@pytest.mark.parametrize(
    "registers",
    [[], [1], [1, 2], [1, 2, 3, 4], [-1, 0, 0], [0x10000, 0, 0], [True, 0, 0]],
)
def test_counter_decoder_rejects_invalid_payload(registers):
    with pytest.raises(ValueError):
        decode_s2000_pp_counter(registers)


@pytest.mark.asyncio
async def test_counter_selector_result_contract():
    client = Client(Response(registers=[0x1234, 0x5678, 0x9ABC]))
    result = await S2000PPCounterValueReader(client, 7, "counter-ready").async_read(42)
    assert result.status is NumericResultStatus.READY
    assert result.raw_count == 0x123456789ABC
    assert client.writes == [{"address": 46180, "value": 42, "device_id": 7}]
    assert client.reads == [{"address": 46332, "count": 3, "device_id": 7}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status"),
    [(15, NumericResultStatus.PENDING), (6, NumericResultStatus.RETRYABLE),
     (2, NumericResultStatus.PROTOCOL_ERROR)],
)
async def test_counter_exception_semantics(code, status):
    client = Client(Response(error=True, code=code))
    result = await S2000PPCounterValueReader(
        client, 1, f"counter-exception-{code}"
    ).async_read(1)
    assert result.status is status
    assert result.raw_count is None
    assert result.exception_code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [None, object(), Response(registers=[]), Response(registers=[1, 2])])
async def test_counter_invalid_responses_are_not_zero(response):
    client = Client()
    client.result = response
    result = await S2000PPCounterValueReader(
        client, 1, f"counter-invalid-{id(response)}"
    ).async_read(1)
    assert result.status is NumericResultStatus.PROTOCOL_ERROR
    assert result.raw_count is None


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [None, object(), Response(error=True, code=2)])
async def test_counter_invalid_write_responses_fail(response):
    client = Client()

    async def bad_write(**kwargs):
        return response

    client.write_register = bad_write
    result = await S2000PPCounterValueReader(
        client, 1, f"counter-write-{id(response)}"
    ).async_read(1)
    assert result.status is NumericResultStatus.PROTOCOL_ERROR
    assert result.raw_count is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("address", "value"), [(46179, 3), (46180, 4)])
async def test_counter_fc06_echo_is_exact(address, value):
    client = Client()

    async def wrong_echo(**kwargs):
        return Response(address=address, value=value)

    client.write_register = wrong_echo
    result = await S2000PPCounterValueReader(
        client, 1, f"counter-echo-{address}-{value}"
    ).async_read(3)
    assert result.status is NumericResultStatus.PROTOCOL_ERROR


@pytest.mark.asyncio
async def test_transport_exception_propagates():
    client = Client()

    async def fail(**kwargs):
        raise RuntimeError("transport failed")

    client.write_register = fail
    with pytest.raises(RuntimeError, match="transport failed"):
        await S2000PPCounterValueReader(client, 1, "counter-transport").async_read(1)


@pytest.mark.asyncio
async def test_read_transport_exception_propagates():
    client = Client()

    async def fail(**kwargs):
        raise RuntimeError("read transport failed")

    client.read_holding_registers = fail
    with pytest.raises(RuntimeError, match="read transport failed"):
        await S2000PPCounterValueReader(client, 1, "counter-read-transport").async_read(1)


@pytest.mark.asyncio
async def test_counter_and_numeric_share_selector_serialization():
    client = Client(Response(error=True, code=15))
    counter = S2000PPCounterValueReader(client, 1, "shared-counter-numeric")
    numeric = S2000PPNumericValueReader(client, 1, "shared-counter-numeric")
    first, second = await asyncio.gather(
        counter.async_read(10),
        numeric.async_read(20, NumericParameterKind.TEMPERATURE),
    )
    assert first.status is NumericResultStatus.PENDING
    assert second.status is NumericResultStatus.RETRYABLE
    assert [write["address"] for write in client.writes] == [46180]
