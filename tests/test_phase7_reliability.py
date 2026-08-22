"""Final reliability closure for connection and legacy read paths."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.bolid import M3000BB1020
from custom_components.modbus_devices.equipment.owen import TRM138
from custom_components.modbus_devices.modbus_client import (
    SerializedModbusClient,
    connect_modbus,
)


class Response:
    def __init__(self, *, function_code, registers=None, bits=None, error=False):
        self.function_code = function_code
        self.registers = registers
        self.bits = bits
        self._error = error

    def isError(self):
        return self._error


@pytest.mark.asyncio
async def test_connect_modbus_wraps_successful_client(monkeypatch):
    raw = AsyncMock()
    raw.connect.return_value = True
    factory = lambda **kwargs: raw
    monkeypatch.setattr(
        "custom_components.modbus_devices.modbus_client.AsyncModbusTcpClient", factory
    )

    client = await connect_modbus(
        {Config.CONF_MODBUS_MODE: Config.MODBUS_TCP, "host": "127.0.0.1", "port": 502}
    )

    assert isinstance(client, SerializedModbusClient)
    assert client._client is raw


@pytest.mark.asyncio
async def test_connect_modbus_preserves_expected_modbus_failure(monkeypatch):
    factory = lambda **kwargs: (_ for _ in ()).throw(ModbusException("offline"))
    monkeypatch.setattr(
        "custom_components.modbus_devices.modbus_client.AsyncModbusTcpClient", factory
    )

    assert await connect_modbus(
        {Config.CONF_MODBUS_MODE: Config.MODBUS_TCP, "host": "127.0.0.1", "port": 502}
    ) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError("invalid"), RuntimeError("bug")])
async def test_connect_modbus_propagates_unexpected_errors(monkeypatch, error):
    factory = lambda **kwargs: (_ for _ in ()).throw(error)
    monkeypatch.setattr(
        "custom_components.modbus_devices.modbus_client.AsyncModbusTcpClient", factory
    )

    with pytest.raises(type(error), match=str(error)):
        await connect_modbus(
            {Config.CONF_MODBUS_MODE: Config.MODBUS_TCP, "host": "127.0.0.1", "port": 502}
        )


@pytest.mark.asyncio
async def test_unknown_transport_mode_propagates_value_error():
    with pytest.raises(ValueError, match="Unknown Modbus mode"):
        await connect_modbus({Config.CONF_MODBUS_MODE: "invalid"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "method"),
    [
        (None, "get_time"),
        (Response(function_code=3, registers=[2026]), "get_time"),
        (Response(function_code=4, registers=[2026, 8, 22, 12, 0, 0]), "get_time"),
        (Response(function_code=3, registers=[2026, 8, -1, 12, 0, 0]), "get_time"),
        (Response(function_code=3, registers=[2026, 13, 22, 12, 0, 0]), "get_time"),
        (Response(function_code=2, bits=None), "get_input"),
        (Response(function_code=1, bits=[True]), "get_input"),
        (Response(function_code=2, bits=[True], error=True), "get_input"),
    ],
)
async def test_m3000_malformed_reads_raise_modbus_exception(response, method):
    client = AsyncMock()
    client.read_holding_registers.return_value = response
    client.read_discrete_inputs.return_value = response
    device = M3000BB1020(client, 1)

    with pytest.raises(ModbusException):
        if method == "get_time":
            await device.get_time()
        else:
            await device.get_input(1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        None,
        Response(function_code=4, registers=None),
        Response(function_code=4, registers=[1]),
        Response(function_code=3, registers=[1, 2]),
        Response(function_code=4, registers=[1, -1]),
        Response(function_code=4, registers=[1, 2], error=True),
    ],
)
async def test_trm138_malformed_reads_raise_modbus_exception(response):
    client = AsyncMock()
    client.read_input_registers.return_value = response
    device = TRM138(client, 1)

    with pytest.raises(ModbusException):
        await device.get_chanel(1)
