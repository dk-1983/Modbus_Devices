"""Tests for the documented S2000-PP numeric selector/result protocol."""

import asyncio

import pytest

from custom_components.modbus_devices.s2000_pp import (
    NumericParameterKind,
    NumericResultStatus,
    S2000PPNumericValueReader,
    decode_s2000_pp_q8_8,
    decode_s2000_pp_unsigned_q8_8,
)


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
    def __init__(self, result):
        self.result = result
        self.writes = []

    async def write_register(self, **kwargs):
        self.writes.append(kwargs)
        return Response(
            address=kwargs["address"],
            value=kwargs["value"],
            function_code=6,
        )

    async def read_holding_registers(self, **kwargs):
        if self.result is not None and self.result.function_code is None:
            self.result.function_code = 0x83 if self.result._error else 3
        return self.result


@pytest.mark.parametrize(
    ("raw", "value"), [(0x1A70, 26.4375), (0xECD0, -19.1875), (0, 0.0)]
)
def test_q8_8(raw, value):
    assert decode_s2000_pp_q8_8(raw) == value


@pytest.mark.parametrize(("raw", "value"), [(0x1B80, 27.5), (0xFFFF, 255.99609375)])
def test_unsigned_q8_8(raw, value):
    assert decode_s2000_pp_unsigned_q8_8(raw) == value


@pytest.mark.asyncio
async def test_selector_and_ready_result_are_validated():
    client = Client(Response(registers=[0x0180]))
    result = await S2000PPNumericValueReader(client, 3, "ready").async_read(
        10, NumericParameterKind.TEMPERATURE
    )
    assert result.status is NumericResultStatus.READY
    assert result.value == 1.5
    assert client.writes[0] == {"address": 46179, "value": 10, "device_id": 3}


@pytest.mark.asyncio
async def test_type_8_power_value_uses_selector_46181_and_unsigned_q8_8():
    client = Client(Response(registers=[0xFF00]))
    result = await S2000PPNumericValueReader(client, 2, "mip").async_read(
        21, NumericParameterKind.OUTPUT_VOLTAGE
    )
    assert result.status is NumericResultStatus.READY
    assert result.value == 255.0
    assert client.writes == [{"address": 46181, "value": 21, "device_id": 2}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status"),
    [(15, NumericResultStatus.PENDING), (6, NumericResultStatus.RETRYABLE)],
)
async def test_retryable_modbus_exceptions(code, status):
    result = await S2000PPNumericValueReader(
        Client(Response(error=True, code=code)), 1, f"exception-{code}"
    ).async_read(1, NumericParameterKind.RELATIVE_HUMIDITY)
    assert result.status is status
    assert result.exception_code == code
    assert result.value is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("code", "status"), [
    (15, NumericResultStatus.PENDING),
    (6, NumericResultStatus.RETRYABLE),
])
async def test_selector_retryable_exceptions_are_phase_correlated(code, status):
    client = Client(Response(registers=[0]))

    async def selector_error(**kwargs):
        return Response(error=True, code=code, function_code=0x86)

    client.write_register = selector_error
    result = await S2000PPNumericValueReader(
        client, 1, f"selector-exception-{code}"
    ).async_read(1, NumericParameterKind.TEMPERATURE)
    assert result.status is status
    assert result.exception_code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["selector", "result"])
@pytest.mark.parametrize("code", [6, 15])
async def test_wrong_exception_function_is_protocol_error(phase, code):
    response = Response(
        error=True,
        code=code,
        function_code=0x83 if phase == "selector" else 0x86,
    )
    client = Client(response)
    if phase == "selector":
        client.write_register = lambda **kwargs: _async_response(response)
    result = await S2000PPNumericValueReader(
        client, 1, f"wrong-{phase}-function-{code}"
    ).async_read(1, NumericParameterKind.TEMPERATURE)
    assert result.status is NumericResultStatus.PROTOCOL_ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["selector", "result"])
async def test_mismatched_exception_device_is_protocol_error(phase):
    function = 0x86 if phase == "selector" else 0x83
    response = Response(error=True, code=15, function_code=function)
    response.dev_id = 2
    client = Client(response)
    if phase == "selector":
        client.write_register = lambda **kwargs: _async_response(response)
    result = await S2000PPNumericValueReader(
        client, 1, f"wrong-{phase}-device"
    ).async_read(1, NumericParameterKind.TEMPERATURE)
    assert result.status is NumericResultStatus.PROTOCOL_ERROR


async def _async_response(response):
    return response


@pytest.mark.asyncio
async def test_selector_timeout_does_not_create_pending_owner():
    client = Client(Response(registers=[0x0100]))
    calls = 0
    original_write = client.write_register

    async def timeout_once(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("selector timeout")
        return await original_write(**kwargs)

    client.write_register = timeout_once
    reader = S2000PPNumericValueReader(client, 1, "numeric-selector-timeout")
    with pytest.raises(TimeoutError, match="selector timeout"):
        await reader.async_read(7, NumericParameterKind.TEMPERATURE)
    result = await reader.async_read(7, NumericParameterKind.TEMPERATURE)
    assert result.status is NumericResultStatus.READY
    assert calls == 2


@pytest.mark.asyncio
async def test_protocol_and_short_response_are_not_zero():
    result = await S2000PPNumericValueReader(
        Client(Response(registers=[])), 1, "short"
    ).async_read(1, NumericParameterKind.TEMPERATURE)
    assert result.status is NumericResultStatus.PROTOCOL_ERROR
    assert result.value is None


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [3, 4])
async def test_terminal_result_exception_keeps_protocol_error_and_releases_session(code):
    class SequenceClient(Client):
        def __init__(self):
            super().__init__(None)
            self.results = iter(
                (
                    Response(error=True, code=code, function_code=0x83),
                    Response(registers=[0x1480], function_code=3),
                )
            )

        async def read_holding_registers(self, **kwargs):
            return next(self.results)

    client = SequenceClient()
    reader = S2000PPNumericValueReader(client, 1, "terminal-error")

    failed = await reader.async_read(12, NumericParameterKind.TEMPERATURE)
    recovered = await reader.async_read(12, NumericParameterKind.TEMPERATURE)

    assert failed.status is NumericResultStatus.PROTOCOL_ERROR
    assert failed.exception_code == code
    assert failed.response_function_code == 0x83
    assert failed.selector_register == 46179
    assert failed.result_register == 46328
    assert failed.result_count == 1
    assert failed.session_owner == ("numeric", 12)
    assert failed.session_generation == 1
    assert recovered.status is NumericResultStatus.READY
    assert recovered.session_generation == 2
    assert [write["value"] for write in client.writes] == [12, 12]


@pytest.mark.asyncio
async def test_invalid_selector_echo_is_protocol_error():
    client = Client(Response(registers=[0]))

    async def bad_write(**kwargs):
        return Response(address=46179, value=kwargs["value"] + 1)

    client.write_register = bad_write
    result = await S2000PPNumericValueReader(client, 1, "bad-echo").async_read(
        2, NumericParameterKind.TEMPERATURE
    )
    assert result.status is NumericResultStatus.PROTOCOL_ERROR


@pytest.mark.asyncio
async def test_parked_request_serializes_other_zones():
    client = Client(Response(error=True, code=15))
    reader_a = S2000PPNumericValueReader(client, 1, "shared")
    reader_b = S2000PPNumericValueReader(client, 1, "shared")
    first, second = await asyncio.gather(
        reader_a.async_read(10, NumericParameterKind.TEMPERATURE),
        reader_b.async_read(20, NumericParameterKind.RELATIVE_HUMIDITY),
    )
    assert first.status is NumericResultStatus.PENDING
    assert second.status is NumericResultStatus.RETRYABLE
    assert [write["value"] for write in client.writes] == [10]
