"""Tests for the documented S2000-PP unsigned 48-bit counter transport."""

import asyncio

import pytest

from custom_components.modbus_devices.s2000_pp import (
    NumericParameterKind,
    NumericResultStatus,
    S2000PPCounterValueReader,
    S2000PPNumericValueReader,
    S2000PPRuntimeReader,
    decode_s2000_pp_counter,
    manual_zone_mapping,
)
from custom_components.modbus_devices.modbus_client import SerializedModbusClient


class Response:
    def __init__(self, *, registers=None, error=False, code=None, address=None,
                 value=None, function_code=None):
        self.registers = registers
        self._error = error
        self.exception_code = code
        self.address = address
        self.value = value
        self.function_code = function_code

    def isError(self):
        return self._error


class Client:
    def __init__(self, result=None):
        self.result = result or Response(registers=[0, 0, 0])
        self.writes = []
        self.reads = []

    async def write_register(self, **kwargs):
        self.writes.append(kwargs)
        return Response(
            address=kwargs["address"],
            value=kwargs["value"],
            function_code=6,
        )

    async def read_holding_registers(self, **kwargs):
        self.reads.append(kwargs)
        if hasattr(self.result, "_error") and not self.result._error:
            self.result.function_code = 3
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
    assert result.result_register_read is True


@pytest.mark.asyncio
async def test_selector_exception_3_is_distinct_from_result_read_exception_3():
    client = Client()

    async def selector_error(**kwargs):
        return Response(error=True, code=3)

    client.write_register = selector_error
    result = await S2000PPCounterValueReader(
        client, 1, "counter-selector-exception-3"
    ).async_read(1)
    assert result.status is NumericResultStatus.PROTOCOL_ERROR
    assert result.exception_code == 3
    assert result.result_register_read is False


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


@pytest.mark.asyncio
async def test_pending_counter_repeats_only_result_until_completion():
    client = Client(Response(error=True, code=15))
    reader = S2000PPCounterValueReader(client, 1, "pending-counter")

    first = await reader.async_read(10)
    client.result = Response(registers=[0, 0, 25])
    second = await reader.async_read(10)

    assert first.status is NumericResultStatus.PENDING
    assert second.status is NumericResultStatus.READY
    assert second.raw_count == 25
    assert [write["address"] for write in client.writes] == [46180]
    assert [read["address"] for read in client.reads] == [46332, 46332]


@pytest.mark.asyncio
async def test_historical_aligned_four_svk_attempts_remain_session_serialized():
    """Characterize the former four-entry cadence without enabling B3 polling."""
    class TraceClient(Client):
        def __init__(self):
            super().__init__()
            self.trace = []

        async def write_register(self, **kwargs):
            self.trace.append(("selector", kwargs["value"]))
            await asyncio.sleep(0)
            return await super().write_register(**kwargs)

        async def read_holding_registers(self, **kwargs):
            self.trace.append(("result", None))
            await asyncio.sleep(0)
            return await super().read_holding_registers(**kwargs)

    client = TraceClient()
    results = await asyncio.gather(*(
        S2000PPCounterValueReader(client, 1, "four-svk").async_read(zone)
        for zone in range(1, 5)
    ))

    assert all(result.status is NumericResultStatus.READY for result in results)
    assert client.trace == [
        ("selector", 1), ("result", None),
        ("selector", 2), ("result", None),
        ("selector", 3), ("result", None),
        ("selector", 4), ("result", None),
    ]


@pytest.mark.asyncio
async def test_two_svk_counters_cannot_both_own_pending_selector_state():
    client = Client(Response(error=True, code=15))
    first, second = await asyncio.gather(
        S2000PPCounterValueReader(client, 1, "two-pending-svk").async_read(10),
        S2000PPCounterValueReader(client, 1, "two-pending-svk").async_read(11),
    )

    assert first.status is NumericResultStatus.PENDING
    assert second.status is NumericResultStatus.RETRYABLE
    assert client.writes == [{"address": 46180, "value": 10, "device_id": 1}]
    assert client.reads == [{"address": 46332, "count": 3, "device_id": 1}]


@pytest.mark.asyncio
async def test_grouped_state_request_can_interleave_counter_selector_and_result():
    """Characterize request locking without claiming vendor transaction semantics."""

    class InterleavingClient:
        def __init__(self):
            self.trace = []
            self.selector_started = asyncio.Event()
            self.release_selector = asyncio.Event()

        async def write_register(self, **kwargs):
            self.trace.append(("counter_selector", kwargs["value"]))
            self.selector_started.set()
            await self.release_selector.wait()
            return Response(
                address=kwargs["address"],
                value=kwargs["value"],
                function_code=6,
            )

        async def read_holding_registers(self, **kwargs):
            if kwargs["address"] == 46332:
                self.trace.append(("counter_result", kwargs["count"]))
                return Response(registers=[0, 0, 1], function_code=3)
            self.trace.append(("grouped_primary", kwargs["address"]))
            return Response(registers=[0x50C8], function_code=3)

        async def read_input_registers(self, **kwargs):
            self.trace.append(("grouped_expanded", kwargs["address"]))
            return Response(registers=[80, *([0] * 15)], function_code=4)

    physical = InterleavingClient()
    client = SerializedModbusClient(physical)
    counter_task = asyncio.create_task(
        S2000PPCounterValueReader(client, 1, "grouped-interleave").async_read(10)
    )
    await physical.selector_started.wait()
    grouped_task = asyncio.create_task(
        S2000PPRuntimeReader(client, 1).async_read_zone_states(
            [manual_zone_mapping(0, 1, 1, 0, None)]
        )
    )
    await asyncio.sleep(0)
    physical.release_selector.set()

    counter, grouped = await asyncio.gather(counter_task, grouped_task)

    assert counter.status is NumericResultStatus.READY
    assert grouped[1].primary_state == 80
    assert physical.trace == [
        ("counter_selector", 10),
        ("grouped_primary", 40000),
        ("counter_result", 3),
        ("grouped_expanded", 4096),
    ]
