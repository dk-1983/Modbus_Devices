"""Strict Modbus RTU ADUs over a transparent TCP stream (no MBAP).

The integration's SerializedModbusClient owns request serialization. A failed
exchange closes the stream; commands are never automatically replayed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import struct

from pymodbus.exceptions import ModbusException

_READ_FUNCTIONS = {1, 2, 3, 4}
_FIXED_RESPONSE_FUNCTIONS = {5, 6, 16}


def modbus_rtu_crc(data: bytes) -> int:
    """Return the standard Modbus RTU CRC16 for *data*."""
    crc = 0xFFFF
    for octet in data:
        crc ^= octet
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def append_modbus_rtu_crc(data: bytes) -> bytes:
    """Append Modbus RTU CRC in wire order: low byte, then high byte."""
    return data + struct.pack("<H", modbus_rtu_crc(data))


@dataclass(slots=True)
class RtuOverTcpResponse:
    """Minimal pymodbus-compatible response consumed by common validators."""

    function_code: int
    dev_id: int
    bits: list[bool] | None = None
    registers: list[int] | None = None
    address: int | None = None
    value: int | bool | None = None
    count: int | None = None
    exception_code: int | None = None

    def isError(self) -> bool:  # noqa: N802 - pymodbus compatibility contract
        """Return whether this is a remote Modbus exception response."""
        return self.exception_code is not None


class _RtuStream(asyncio.Protocol):
    """Bound incoming data independently of TCP packet boundaries."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.changed = asyncio.Event()
        self.lost = False

    def data_received(self, data: bytes) -> None:
        # One maximum ADU plus one byte is enough to detect overflow.
        self.buffer.extend(data[: max(0, 257 - len(self.buffer))])
        self.changed.set()

    def connection_lost(self, exc: Exception | None) -> None:
        self.lost = True
        self.changed.set()


class ModbusRtuOverTcpClient:
    """Persistent RAW TCP connection; serialize calls through the shared wrapper."""

    def __init__(self, host: str, port: int, *, timeout: float = 3.0) -> None:
        if not isinstance(host, str) or not host.strip():
            raise ValueError("RTU-over-TCP host must not be empty")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("RTU-over-TCP timeout must be positive and finite")
        self.host = host
        self.port = port
        self.timeout = float(timeout)
        self._transport: asyncio.Transport | None = None
        self._protocol: _RtuStream | None = None
        self._explicitly_closed = False

    @property
    def connected(self) -> bool:
        return (
            self._transport is not None
            and not self._transport.is_closing()
            and self._protocol is not None
            and not self._protocol.lost
        )

    async def connect(self) -> bool:
        if self.connected:
            return True
        self._disconnect()
        self._explicitly_closed = False
        try:
            async with asyncio.timeout(self.timeout):
                (
                    transport,
                    protocol,
                ) = await asyncio.get_running_loop().create_connection(
                    _RtuStream, self.host, self.port
                )
            if self._explicitly_closed:
                transport.close()
                raise ModbusException("RTU-over-TCP client closed during connect")
            self._transport, self._protocol = transport, protocol
        except OSError as exc:
            raise ModbusException("Unable to connect RTU-over-TCP endpoint") from exc
        return self.connected

    def _disconnect(self) -> None:
        transport, self._transport = self._transport, None
        protocol, self._protocol = self._protocol, None
        if protocol is not None:
            protocol.lost = True
            protocol.changed.set()
        if transport is not None:
            transport.close()

    def close(self) -> None:
        self._explicitly_closed = True
        self._disconnect()

    async def _request(
        self, device_id: int, function: int, payload: bytes, *, expected_count: int
    ) -> RtuOverTcpResponse:
        if self._explicitly_closed:
            raise ModbusException("RTU-over-TCP client is closed")
        try:
            # A single deadline covers connect, send and all response fragments.
            async with asyncio.timeout(self.timeout):
                if not self.connected:
                    await self.connect()
                protocol = self._protocol
                if protocol.buffer:
                    raise ModbusException(
                        "Unsolicited RTU-over-TCP data before request"
                    )
                request = append_modbus_rtu_crc(bytes((device_id, function)) + payload)
                self._transport.write(request)
                while True:
                    frame = protocol.buffer
                    if frame and frame[0] != device_id:
                        raise ModbusException("Wrong RTU-over-TCP response device id")
                    length = self._expected_frame_length(
                        frame, function, expected_count
                    )
                    if length is not None and len(frame) >= length:
                        if len(frame) != length:
                            raise ModbusException(
                                "RTU-over-TCP response has trailing bytes"
                            )
                        result = self._decode_response(
                            bytes(frame), device_id, function, expected_count
                        )
                        if (
                            not result.isError()
                            and function in _FIXED_RESPONSE_FUNCTIONS
                        ):
                            if frame[2:6] != payload[:4]:
                                raise ModbusException(
                                    "RTU-over-TCP write echo mismatch"
                                )
                        frame.clear()
                        protocol.changed.clear()
                        return result
                    if protocol.lost:
                        raise ModbusException(
                            "RTU-over-TCP connection closed during response"
                        )
                    protocol.changed.clear()
                    await protocol.changed.wait()
        except BaseException:
            # Includes cancellation: discard this stream before the next request.
            self._disconnect()
            raise

    async def read_coils(self, *, address: int, count: int, device_id: int):
        return await self._read_bits(1, address, count, device_id)

    async def read_discrete_inputs(self, *, address: int, count: int, device_id: int):
        return await self._read_bits(2, address, count, device_id)

    async def read_holding_registers(self, *, address: int, count: int, device_id: int):
        return await self._read_registers(3, address, count, device_id)

    async def read_input_registers(self, *, address: int, count: int, device_id: int):
        return await self._read_registers(4, address, count, device_id)

    async def write_coil(self, *, address: int, value: bool, device_id: int):
        self._validate_device_and_span(device_id, address, 1)
        if type(value) is not bool:
            raise ValueError("FC05 value must be bool")
        wire_value = 0xFF00 if value else 0x0000
        return await self._request(
            device_id, 5, struct.pack(">HH", address, wire_value), expected_count=1
        )

    async def write_register(self, *, address: int, value: int, device_id: int):
        self._validate_device_and_span(device_id, address, 1)
        self._validate_register(value)
        return await self._request(
            device_id, 6, struct.pack(">HH", address, value), expected_count=1
        )

    async def write_registers(self, *, address: int, values: list[int], device_id: int):
        if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 123:
            raise ValueError("FC16 values must contain 1..123 registers")
        for value in values:
            self._validate_register(value)
        self._validate_device_and_span(device_id, address, len(values))
        payload = struct.pack(">HHB", address, len(values), len(values) * 2)
        payload += struct.pack(f">{len(values)}H", *values)
        return await self._request(device_id, 16, payload, expected_count=len(values))

    async def _read_bits(
        self, function: int, address: int, count: int, device_id: int
    ) -> RtuOverTcpResponse:
        if type(count) is not int or not 1 <= count <= 2000:
            raise ValueError(f"FC{function:02d} count must be between 1 and 2000")
        self._validate_device_and_span(device_id, address, count)
        return await self._request(
            device_id,
            function,
            struct.pack(">HH", address, count),
            expected_count=count,
        )

    async def _read_registers(
        self, function: int, address: int, count: int, device_id: int
    ) -> RtuOverTcpResponse:
        if type(count) is not int or not 1 <= count <= 125:
            raise ValueError(f"FC{function:02d} count must be between 1 and 125")
        self._validate_device_and_span(device_id, address, count)
        return await self._request(
            device_id,
            function,
            struct.pack(">HH", address, count),
            expected_count=count,
        )

    @staticmethod
    def _validate_device_and_span(device_id: int, address: int, count: int) -> None:
        if type(device_id) is not int or not 1 <= device_id <= 247:
            raise ValueError("device_id must be between 1 and 247")
        if type(address) is not int or not 0 <= address <= 0xFFFF:
            raise ValueError("address must be between 0 and 65535")
        if address + count > 0x10000:
            raise ValueError("requested Modbus range exceeds address 65535")

    @staticmethod
    def _validate_register(value: int) -> None:
        if type(value) is not int or not 0 <= value <= 0xFFFF:
            raise ValueError("register value must be between 0 and 65535")

    @staticmethod
    def _expected_frame_length(
        frame: bytearray, function: int, expected_count: int
    ) -> int | None:
        if len(frame) < 2:
            return None
        response_function = frame[1]
        if response_function == function | 0x80:
            return 5
        if response_function != function:
            raise ModbusException("Wrong RTU-over-TCP response function")
        if function in _READ_FUNCTIONS:
            if len(frame) < 3:
                return None
            expected_bytes = (
                (expected_count + 7) // 8 if function in (1, 2) else expected_count * 2
            )
            if frame[2] != expected_bytes:
                raise ModbusException("Invalid RTU response byte count")
            return 5 + expected_bytes
        if function in _FIXED_RESPONSE_FUNCTIONS:
            return 8
        raise ModbusException(f"Unsupported RTU-over-TCP function {function}")

    @staticmethod
    def _decode_response(
        frame: bytes, device_id: int, function: int, expected_count: int
    ) -> RtuOverTcpResponse:
        if len(frame) < 5:
            raise ModbusException("RTU-over-TCP response is too short")
        if len(frame) != ModbusRtuOverTcpClient._expected_frame_length(
            frame, function, expected_count
        ):
            raise ModbusException("Invalid RTU-over-TCP response length")
        received_crc = struct.unpack("<H", frame[-2:])[0]
        if modbus_rtu_crc(frame[:-2]) != received_crc:
            raise ModbusException("Invalid RTU-over-TCP response CRC")
        if frame[0] != device_id:
            raise ModbusException("Wrong RTU-over-TCP response device id")
        response_function = frame[1]
        if response_function == function | 0x80:
            if frame[2] not in (1, 2, 3, 4, 5, 6, 8, 10, 11):
                raise ModbusException("Invalid RTU-over-TCP exception code")
            return RtuOverTcpResponse(
                function_code=response_function,
                dev_id=device_id,
                exception_code=frame[2],
            )
        if response_function != function:
            raise ModbusException("Wrong RTU-over-TCP response function")

        if function in (1, 2):
            byte_count = frame[2]
            expected_bytes = (expected_count + 7) // 8
            if byte_count != expected_bytes or len(frame) != byte_count + 5:
                raise ModbusException("Invalid RTU bit-read byte count")
            if expected_count % 8 and frame[-3] >> (expected_count % 8):
                raise ModbusException("Invalid RTU bit-read padding")
            bits = [
                bool(frame[3 + index // 8] & (1 << (index % 8)))
                for index in range(expected_count)
            ]
            return RtuOverTcpResponse(function, device_id, bits=bits)
        if function in (3, 4):
            byte_count = frame[2]
            if byte_count != expected_count * 2 or byte_count % 2:
                raise ModbusException("Invalid RTU register-read byte count")
            registers = list(struct.unpack(f">{expected_count}H", frame[3:-2]))
            return RtuOverTcpResponse(function, device_id, registers=registers)

        address, echoed = struct.unpack(">HH", frame[2:6])
        if function == 5:
            if echoed not in (0x0000, 0xFF00):
                raise ModbusException("Invalid FC05 response value")
            return RtuOverTcpResponse(
                function, device_id, address=address, value=echoed
            )
        if function == 6:
            return RtuOverTcpResponse(
                function, device_id, address=address, value=echoed, registers=[echoed]
            )
        return RtuOverTcpResponse(function, device_id, address=address, count=echoed)
