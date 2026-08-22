"""Raw Modbus RTU application data units transported over UDP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import socket
import struct
from typing import Any

from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)

_READ_FUNCTIONS = {1, 2, 3, 4}
_FIXED_RESPONSE_FUNCTIONS = {5, 6, 16}
_MAX_STALE_DATAGRAMS = 16


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
class RtuOverUdpResponse:
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


class ModbusRtuOverUdpClient:
    """One persistent raw-RTU-over-UDP client without transaction identifiers.

    The caller must serialize requests. The integration supplies that guarantee
    through ``SerializedModbusClient``; this transport intentionally has no
    second request lock.
    """

    def __init__(
        self,
        host: str,
        remote_port: int,
        *,
        local_udp_port: int | None = None,
        timeout: float = 3.0,
        local_bind_address: str | None = None,
        strict_source_port: bool = False,
    ) -> None:
        if not host:
            raise ValueError("RTU-over-UDP host must not be empty")
        self._validate_port(remote_port, "remote_port")
        effective_local_port = remote_port if local_udp_port is None else local_udp_port
        self._validate_port(effective_local_port, "local_udp_port")
        if timeout <= 0:
            raise ValueError("RTU-over-UDP timeout must be positive")
        self.host = host
        self.remote_port = remote_port
        self.local_udp_port = effective_local_port
        self.timeout = float(timeout)
        self.local_bind_address = local_bind_address or "0.0.0.0"
        self.strict_source_port = strict_source_port
        self._socket: socket.socket | None = None
        self._remote_endpoint: tuple[str, int] | None = None
        self._remote_ip: str | None = None

    @staticmethod
    def _validate_port(port: int, name: str) -> None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError(f"{name} must be between 1 and 65535")

    @property
    def connected(self) -> bool:
        """Return whether the persistent UDP socket is open."""
        return self._socket is not None

    async def connect(self) -> bool:
        """Resolve the peer and bind one persistent non-blocking UDP socket."""
        if self.connected:
            return True
        loop = asyncio.get_running_loop()
        udp_socket: socket.socket | None = None
        try:
            addresses = await loop.getaddrinfo(
                self.host,
                self.remote_port,
                family=socket.AF_INET,
                type=socket.SOCK_DGRAM,
            )
            if not addresses:
                raise OSError("host resolution returned no UDP endpoint")
            remote = addresses[0][4]
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setblocking(False)
            udp_socket.bind((self.local_bind_address, self.local_udp_port))
        except OSError as exc:
            if udp_socket is not None:
                udp_socket.close()
            raise ModbusException(
                f"Unable to prepare RTU-over-UDP endpoint {self.host}:{self.remote_port}"
            ) from exc
        self._socket = udp_socket
        self._remote_endpoint = (remote[0], remote[1])
        self._remote_ip = remote[0]
        _LOGGER.debug(
            "Prepared RTU-over-UDP endpoint %s:%s from %s:%s",
            self._remote_ip,
            self.remote_port,
            self.local_bind_address,
            self.local_udp_port,
        )
        return True

    def close(self) -> None:
        """Close the persistent socket; repeated calls are harmless."""
        udp_socket, self._socket = self._socket, None
        self._remote_endpoint = None
        self._remote_ip = None
        if udp_socket is not None:
            udp_socket.close()

    async def read_coils(self, *, address: int, count: int, device_id: int):
        return await self._read_bits(1, address, count, device_id)

    async def read_discrete_inputs(
        self, *, address: int, count: int, device_id: int
    ):
        return await self._read_bits(2, address, count, device_id)

    async def read_holding_registers(
        self, *, address: int, count: int, device_id: int
    ):
        return await self._read_registers(3, address, count, device_id)

    async def read_input_registers(
        self, *, address: int, count: int, device_id: int
    ):
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

    async def write_registers(
        self, *, address: int, values: list[int], device_id: int
    ):
        if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 123:
            raise ValueError("FC16 values must contain 1..123 registers")
        for value in values:
            self._validate_register(value)
        self._validate_device_and_span(device_id, address, len(values))
        payload = struct.pack(">HHB", address, len(values), len(values) * 2)
        payload += struct.pack(f">{len(values)}H", *values)
        return await self._request(
            device_id, 16, payload, expected_count=len(values)
        )

    async def _read_bits(
        self, function: int, address: int, count: int, device_id: int
    ) -> RtuOverUdpResponse:
        if type(count) is not int or not 1 <= count <= 2000:
            raise ValueError(f"FC{function:02d} count must be between 1 and 2000")
        self._validate_device_and_span(device_id, address, count)
        return await self._request(
            device_id, function, struct.pack(">HH", address, count), expected_count=count
        )

    async def _read_registers(
        self, function: int, address: int, count: int, device_id: int
    ) -> RtuOverUdpResponse:
        if type(count) is not int or not 1 <= count <= 125:
            raise ValueError(f"FC{function:02d} count must be between 1 and 125")
        self._validate_device_and_span(device_id, address, count)
        return await self._request(
            device_id, function, struct.pack(">HH", address, count), expected_count=count
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

    async def _request(
        self, device_id: int, function: int, payload: bytes, *, expected_count: int
    ) -> RtuOverUdpResponse:
        if self._socket is None or self._remote_endpoint is None:
            raise ModbusException("RTU-over-UDP socket is not connected")
        request = append_modbus_rtu_crc(bytes((device_id, function)) + payload)
        self._drain_stale_datagrams()
        try:
            await self._sendto(request, self._remote_endpoint)
        except OSError as exc:
            raise ModbusException("Unable to send RTU-over-UDP request") from exc

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        frame = bytearray()
        expected_length: int | None = None
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError("Timed out waiting for RTU-over-UDP response")
            try:
                datagram, source = await asyncio.wait_for(
                    self._recvfrom(remaining), timeout=remaining
                )
            except asyncio.TimeoutError:
                raise
            except OSError as exc:
                raise ModbusException("Unable to receive RTU-over-UDP response") from exc
            self._validate_source(source)
            frame.extend(datagram)
            expected_length = self._expected_frame_length(
                frame, function, expected_count
            )
            if expected_length is None:
                continue
            if len(frame) > expected_length:
                raise ModbusException("RTU-over-UDP response has trailing bytes")
            if len(frame) == expected_length:
                return self._decode_response(
                    bytes(frame), device_id, function, expected_count
                )

    async def _sendto(self, data: bytes, endpoint: tuple[str, int]) -> None:
        await asyncio.get_running_loop().sock_sendto(self._socket, data, endpoint)

    async def _recvfrom(self, _remaining: float) -> tuple[bytes, tuple[str, int]]:
        return await asyncio.get_running_loop().sock_recvfrom(self._socket, 260)

    def _drain_stale_datagrams(self) -> None:
        """Discard only packets already queued immediately before a new request."""
        if self._socket is None:
            return
        for _ in range(_MAX_STALE_DATAGRAMS):
            try:
                self._socket.recvfrom(260)
            except (BlockingIOError, InterruptedError):
                return
            except OSError as exc:
                raise ModbusException("Unable to drain stale UDP datagrams") from exc

    def _validate_source(self, source: tuple[str, int]) -> None:
        if source[0] != self._remote_ip:
            raise ModbusException("RTU-over-UDP response came from an unexpected IP")
        if self.strict_source_port and source[1] != self.remote_port:
            raise ModbusException("RTU-over-UDP response came from an unexpected port")

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
            raise ModbusException("Wrong RTU-over-UDP response function")
        if function in _READ_FUNCTIONS:
            if len(frame) < 3:
                return None
            expected_bytes = (
                (expected_count + 7) // 8
                if function in (1, 2)
                else expected_count * 2
            )
            if frame[2] != expected_bytes:
                raise ModbusException("Invalid RTU response byte count")
            return 5 + expected_bytes
        if function in _FIXED_RESPONSE_FUNCTIONS:
            return 8
        raise ModbusException(f"Unsupported RTU-over-UDP function {function}")

    @staticmethod
    def _decode_response(
        frame: bytes, device_id: int, function: int, expected_count: int
    ) -> RtuOverUdpResponse:
        if len(frame) < 5:
            raise ModbusException("RTU-over-UDP response is too short")
        received_crc = struct.unpack("<H", frame[-2:])[0]
        if modbus_rtu_crc(frame[:-2]) != received_crc:
            raise ModbusException("Invalid RTU-over-UDP response CRC")
        if frame[0] != device_id:
            raise ModbusException("Wrong RTU-over-UDP response device id")
        response_function = frame[1]
        if response_function == function | 0x80:
            return RtuOverUdpResponse(
                function_code=response_function,
                dev_id=device_id,
                exception_code=frame[2],
            )
        if response_function != function:
            raise ModbusException("Wrong RTU-over-UDP response function")

        if function in (1, 2):
            byte_count = frame[2]
            expected_bytes = (expected_count + 7) // 8
            if byte_count != expected_bytes or len(frame) != byte_count + 5:
                raise ModbusException("Invalid RTU bit-read byte count")
            bits = [
                bool(frame[3 + index // 8] & (1 << (index % 8)))
                for index in range(expected_count)
            ]
            return RtuOverUdpResponse(function, device_id, bits=bits)
        if function in (3, 4):
            byte_count = frame[2]
            if byte_count != expected_count * 2 or byte_count % 2:
                raise ModbusException("Invalid RTU register-read byte count")
            registers = list(struct.unpack(f">{expected_count}H", frame[3:-2]))
            return RtuOverUdpResponse(function, device_id, registers=registers)

        address, echoed = struct.unpack(">HH", frame[2:6])
        if function == 5:
            if echoed not in (0x0000, 0xFF00):
                raise ModbusException("Invalid FC05 response value")
            return RtuOverUdpResponse(
                function, device_id, address=address, value=echoed
            )
        if function == 6:
            return RtuOverUdpResponse(
                function, device_id, address=address, value=echoed,
                registers=[echoed]
            )
        return RtuOverUdpResponse(function, device_id, address=address, count=echoed)
