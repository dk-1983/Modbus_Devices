"""Raw Modbus RTU application data units transported over UDP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import socket
import struct
from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)

_READ_FUNCTIONS = {1, 2, 3, 4}
_FIXED_RESPONSE_FUNCTIONS = {5, 6, 16}
_MAX_STALE_DATAGRAMS = 16

# Raw RTU-over-UDP has no transaction identifier. Rebinding the same fixed local
# port cannot mathematically exclude every arbitrarily late datagram, but leaving
# it unbound for one normal coordinator cycle substantially narrows the proven
# stale-after-drain race. Healthy traffic never enters this quarantine.
RTU_OVER_UDP_EPOCH_QUARANTINE_SECONDS = 5.0


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


@dataclass(frozen=True, slots=True)
class RtuOverUdpRequestDiagnostic:
    """Non-sensitive history for correlating adjacent UDP requests."""

    seq: int
    expected_slave: int
    expected_function: int
    outcome: str
    completion_monotonic: float


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
        self._request_sequence = 0
        self._previous_request: RtuOverUdpRequestDiagnostic | None = None
        self._transport_epoch = 0
        self._epoch_tainted = False
        self._ambiguity_cause: str | None = None
        self._ambiguity_started: float | None = None
        self._explicitly_closed = False
        self._quarantine_seconds = RTU_OVER_UDP_EPOCH_QUARANTINE_SECONDS

    @staticmethod
    def _validate_port(port: int, name: str) -> None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError(f"{name} must be between 1 and 65535")

    @property
    def connected(self) -> bool:
        """Return whether the persistent UDP socket is open."""
        return self._socket is not None

    @property
    def last_request_diagnostic(self) -> RtuOverUdpRequestDiagnostic | None:
        """Return the last non-sensitive request outcome for diagnostics."""
        return self._previous_request

    @property
    def transport_epoch(self) -> int:
        """Return the current fixed-port transport generation."""
        return self._transport_epoch

    @property
    def epoch_tainted(self) -> bool:
        """Return whether a post-send ambiguity invalidated this epoch."""
        return self._epoch_tainted

    async def connect(self) -> bool:
        """Resolve the peer and bind one persistent non-blocking UDP socket."""
        if self.connected:
            return True
        if self._epoch_tainted:
            await self._recover_transport_epoch()
            return True
        self._explicitly_closed = False
        loop = asyncio.get_running_loop()
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
            self._remote_endpoint = (remote[0], remote[1])
            self._remote_ip = remote[0]
            self._bind_fixed_port_socket()
        except OSError as exc:
            self._close_socket(clear_remote=True)
            raise ModbusException(
                f"Unable to prepare RTU-over-UDP endpoint {self.host}:{self.remote_port}"
            ) from exc
        self._transport_epoch += 1
        self._epoch_tainted = False
        self._ambiguity_cause = None
        self._ambiguity_started = None
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
        self._explicitly_closed = True
        self._epoch_tainted = False
        self._ambiguity_cause = None
        self._ambiguity_started = None
        self._close_socket(clear_remote=True)

    def _close_socket(self, *, clear_remote: bool) -> None:
        """Close only the current socket, optionally forgetting its peer."""
        udp_socket, self._socket = self._socket, None
        if clear_remote:
            self._remote_endpoint = None
            self._remote_ip = None
        if udp_socket is not None:
            udp_socket.close()

    def _bind_fixed_port_socket(self) -> None:
        """Bind one fresh non-blocking socket on the configured fixed port."""
        udp_socket: socket.socket | None = None
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setblocking(False)
            udp_socket.bind((self.local_bind_address, self.local_udp_port))
        except OSError:
            if udp_socket is not None:
                udp_socket.close()
            raise
        self._socket = udp_socket

    def _taint_transport_epoch(self, cause: str, started: float) -> None:
        """Invalidate a sent request's socket and begin fixed-port quarantine."""
        if self._epoch_tainted:
            return
        self._epoch_tainted = True
        self._ambiguity_cause = cause
        self._ambiguity_started = started
        self._close_socket(clear_remote=False)
        _LOGGER.debug(
            "RTU-over-UDP epoch=%s disposition=tainted cause=%s "
            "quarantine_seconds=%.3f monotonic=%.6f",
            self._transport_epoch,
            cause,
            self._quarantine_seconds,
            started,
        )

    async def _recover_transport_epoch(self) -> None:
        """Wait unbound, then create a new fixed-port transport generation."""
        if not self._epoch_tainted:
            return
        loop = asyncio.get_running_loop()
        started = self._ambiguity_started
        if started is None:
            raise ModbusException("RTU-over-UDP transport epoch is invalid")
        remaining = self._quarantine_seconds - (loop.time() - started)
        if remaining > 0:
            await asyncio.sleep(remaining)
        if self._explicitly_closed:
            raise ModbusException("RTU-over-UDP client was closed during recovery")
        if self._remote_endpoint is None or self._remote_ip is None:
            raise ModbusException("RTU-over-UDP peer is unavailable during recovery")
        try:
            self._bind_fixed_port_socket()
        except OSError as exc:
            self._ambiguity_started = loop.time()
            self._ambiguity_cause = "recovery-bind-failed"
            _LOGGER.debug(
                "RTU-over-UDP epoch=%s disposition=recovery-failed "
                "cause=%s quarantine_seconds=%.3f monotonic=%.6f",
                self._transport_epoch,
                self._ambiguity_cause,
                self._quarantine_seconds,
                self._ambiguity_started,
            )
            raise ModbusException(
                "Unable to recover RTU-over-UDP fixed-port transport"
            ) from exc
        self._transport_epoch += 1
        previous_epoch = self._transport_epoch - 1
        cause = self._ambiguity_cause
        self._epoch_tainted = False
        self._ambiguity_cause = None
        self._ambiguity_started = None
        _LOGGER.debug(
            "RTU-over-UDP epoch recovery previous_epoch=%s epoch=%s "
            "cause=%s local=%s:%s",
            previous_epoch,
            self._transport_epoch,
            cause,
            self.local_bind_address,
            self.local_udp_port,
        )

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
        if self._epoch_tainted:
            await self._recover_transport_epoch()
        if self._socket is None or self._remote_endpoint is None:
            raise ModbusException("RTU-over-UDP socket is not connected")
        loop = asyncio.get_running_loop()
        self._request_sequence += 1
        seq = self._request_sequence
        started = loop.time()
        address, request_count, request_value = self._request_fields(
            function, payload, expected_count
        )
        local_endpoint = self._local_endpoint()
        _LOGGER.debug(
            "RTU-over-UDP request start seq=%s epoch=%s remote=%s:%s local=%s:%s "
            "slave=%s expected_function=%s address=%s count=%s value=%s "
            "monotonic=%.6f",
            seq,
            self._transport_epoch,
            self._remote_endpoint[0],
            self._remote_endpoint[1],
            local_endpoint[0],
            local_endpoint[1],
            device_id,
            function,
            address,
            request_count,
            request_value,
            started,
        )
        request = append_modbus_rtu_crc(bytes((device_id, function)) + payload)
        completed = False
        send_attempted = False
        sent: float | None = None
        frame = bytearray()
        last_source: tuple[str, int] | None = None
        try:
            try:
                self._drain_stale_datagrams(seq, started)
                send_attempted = True
                await self._sendto(request, self._remote_endpoint)
            except OSError as exc:
                raise ModbusException("Unable to send RTU-over-UDP request") from exc

            sent = loop.time()
            deadline = sent + self.timeout
            expected_length: int | None = None
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise asyncio.TimeoutError(
                        "Timed out waiting for RTU-over-UDP response"
                    )
                try:
                    datagram, source = await asyncio.wait_for(
                        self._recvfrom(remaining), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    raise
                except OSError as exc:
                    raise ModbusException(
                        "Unable to receive RTU-over-UDP response"
                    ) from exc
                last_source = source
                self._log_response_candidate(
                    seq, sent, source, datagram, device_id, function
                )
                if not self._source_is_expected(source):
                    self._log_rejected_source(seq, sent, source, datagram)
                    continue
                frame.extend(datagram)
                expected_length = self._expected_frame_length(
                    frame, function, expected_count
                )
                if expected_length is None:
                    continue
                if len(frame) > expected_length:
                    raise ModbusException("RTU-over-UDP response has trailing bytes")
                if len(frame) == expected_length:
                    result = self._decode_response(
                        bytes(frame), device_id, function, expected_count
                    )
                    elapsed = (loop.time() - sent) * 1000
                    _LOGGER.debug(
                        "RTU-over-UDP response seq=%s epoch=%s disposition=accepted "
                        "elapsed_ms=%.3f source=%s:%s slave=%s function=%s "
                        "expected_function=%s length=%s crc_valid=true exception=%s",
                        seq,
                        self._transport_epoch,
                        elapsed,
                        last_source[0],
                        last_source[1],
                        result.dev_id,
                        result.function_code,
                        function,
                        len(frame),
                        result.exception_code,
                    )
                    self._complete_request(seq, device_id, function, "success")
                    completed = True
                    return result
        except asyncio.CancelledError:
            self._log_terminal_failure(
                seq,
                started,
                sent,
                device_id,
                function,
                "cancelled",
                None,
                last_source,
                frame,
            )
            self._complete_request(seq, device_id, function, "cancelled")
            completed = True
            if send_attempted:
                self._taint_transport_epoch("cancelled", loop.time())
            raise
        except asyncio.TimeoutError:
            self._log_terminal_failure(
                seq,
                started,
                sent,
                device_id,
                function,
                "timeout",
                None,
                last_source,
                frame,
            )
            self._complete_request(seq, device_id, function, "timeout")
            completed = True
            if sent is not None:
                self._taint_transport_epoch("timeout", loop.time())
            raise
        except ModbusException as exc:
            disposition = (
                "wrong-function"
                if "Wrong RTU-over-UDP response function" in str(exc)
                else "malformed"
            )
            self._log_terminal_failure(
                seq,
                started,
                sent,
                device_id,
                function,
                disposition,
                exc,
                last_source,
                frame,
            )
            self._complete_request(seq, device_id, function, disposition)
            completed = True
            if sent is not None:
                self._taint_transport_epoch(disposition, loop.time())
            raise
        finally:
            if not completed:
                self._complete_request(seq, device_id, function, "error")

    async def _sendto(self, data: bytes, endpoint: tuple[str, int]) -> None:
        await asyncio.get_running_loop().sock_sendto(self._socket, data, endpoint)

    async def _recvfrom(self, _remaining: float) -> tuple[bytes, tuple[str, int]]:
        return await asyncio.get_running_loop().sock_recvfrom(self._socket, 260)

    def _drain_stale_datagrams(self, upcoming_seq: int, started: float) -> None:
        """Discard only packets already queued immediately before a new request."""
        if self._socket is None:
            return
        drained: list[tuple[bytes, tuple[str, int]]] = []
        for _ in range(_MAX_STALE_DATAGRAMS):
            try:
                drained.append(self._socket.recvfrom(260))
            except (BlockingIOError, InterruptedError):
                break
            except OSError as exc:
                raise ModbusException("Unable to drain stale UDP datagrams") from exc
        if drained:
            now = asyncio.get_running_loop().time()
            for index, (datagram, source) in enumerate(drained, start=1):
                metadata = self._datagram_metadata(datagram)
                _LOGGER.debug(
                    "RTU-over-UDP drain upcoming_seq=%s drained=%s index=%s "
                    "source=%s:%s slave=%s function=%s length=%s crc_valid=%s "
                    "relative_ms=%.3f",
                    upcoming_seq,
                    len(drained),
                    index,
                    source[0],
                    source[1],
                    metadata[0],
                    metadata[1],
                    len(datagram),
                    metadata[2],
                    (now - started) * 1000,
                )

    def _local_endpoint(self) -> tuple[str, int]:
        """Return the actual local endpoint when the socket exposes it."""
        if self._socket is not None:
            try:
                endpoint = self._socket.getsockname()
                return endpoint[0], endpoint[1]
            except (AttributeError, OSError):
                pass
        return self.local_bind_address, self.local_udp_port

    @staticmethod
    def _request_fields(
        function: int, payload: bytes, expected_count: int
    ) -> tuple[int | None, int | None, int | None]:
        """Decode non-sensitive request routing fields for diagnostics."""
        if len(payload) < 4:
            return None, expected_count, None
        address, second = struct.unpack(">HH", payload[:4])
        return (
            address,
            expected_count,
            second if function in (5, 6) else None,
        )

    @staticmethod
    def _datagram_metadata(datagram: bytes) -> tuple[int | None, int | None, bool | None]:
        """Return safe frame metadata without accepting or decoding the frame."""
        slave = datagram[0] if datagram else None
        function = datagram[1] if len(datagram) >= 2 else None
        crc_valid = None
        if len(datagram) >= 4:
            crc_valid = modbus_rtu_crc(datagram[:-2]) == struct.unpack(
                "<H", datagram[-2:]
            )[0]
        return slave, function, crc_valid

    def _log_response_candidate(
        self,
        seq: int,
        sent: float,
        source: tuple[str, int],
        datagram: bytes,
        expected_slave: int,
        expected_function: int,
    ) -> None:
        """Log one received UDP candidate before existing validation."""
        slave, function, crc_valid = self._datagram_metadata(datagram)
        exception = (
            datagram[2]
            if len(datagram) >= 3
            and function == (expected_function | 0x80)
            else None
        )
        _LOGGER.debug(
            "RTU-over-UDP candidate seq=%s disposition=received "
            "elapsed_ms=%.3f source=%s:%s "
            "slave=%s expected_slave=%s function=%s expected_function=%s "
            "length=%s crc_valid=%s exception=%s",
            seq,
            (asyncio.get_running_loop().time() - sent) * 1000,
            source[0],
            source[1],
            slave,
            expected_slave,
            function,
            expected_function,
            len(datagram),
            crc_valid,
            exception,
        )

    def _log_terminal_failure(
        self,
        seq: int,
        started: float,
        sent: float | None,
        expected_slave: int,
        expected_function: int,
        disposition: str,
        error: Exception | None,
        source: tuple[str, int] | None,
        frame: bytearray,
    ) -> None:
        """Log a terminal request outcome with adjacent-request history."""
        previous = self._previous_request
        now = asyncio.get_running_loop().time()
        received_slave, received_function, crc_valid = self._datagram_metadata(frame)
        _LOGGER.debug(
            "RTU-over-UDP response seq=%s disposition=%s elapsed_ms=%.3f "
            "source=%s:%s received_slave=%s expected_slave=%s "
            "received_function=%s expected_function=%s length=%s crc_valid=%s "
            "error=%s previous_seq=%s "
            "previous_slave=%s previous_function=%s previous_outcome=%s "
            "since_previous_ms=%s",
            seq,
            disposition,
            (now - (started if sent is None else sent)) * 1000,
            None if source is None else source[0],
            None if source is None else source[1],
            received_slave,
            expected_slave,
            received_function,
            expected_function,
            len(frame),
            crc_valid,
            error,
            None if previous is None else previous.seq,
            None if previous is None else previous.expected_slave,
            None if previous is None else previous.expected_function,
            None if previous is None else previous.outcome,
            None
            if previous is None
            else round((now - previous.completion_monotonic) * 1000, 3),
        )

    def _complete_request(
        self, seq: int, expected_slave: int, expected_function: int, outcome: str
    ) -> None:
        """Retain diagnostic history without influencing transport behavior."""
        self._previous_request = RtuOverUdpRequestDiagnostic(
            seq,
            expected_slave,
            expected_function,
            outcome,
            asyncio.get_running_loop().time(),
        )

    def _source_is_expected(self, source: tuple[str, int]) -> bool:
        """Return whether a candidate came from the configured UDP peer."""
        return source[0] == self._remote_ip and (
            not self.strict_source_port or source[1] == self.remote_port
        )

    def _log_rejected_source(
        self,
        seq: int,
        sent: float,
        source: tuple[str, int],
        datagram: bytes,
    ) -> None:
        """Record harmless foreign UDP noise without ending the request."""
        slave, function, crc_valid = self._datagram_metadata(datagram)
        _LOGGER.debug(
            "RTU-over-UDP candidate seq=%s disposition=rejected "
            "reason=unexpected-source elapsed_ms=%.3f source=%s:%s "
            "slave=%s function=%s length=%s crc_valid=%s",
            seq,
            (asyncio.get_running_loop().time() - sent) * 1000,
            source[0],
            source[1],
            slave,
            function,
            len(datagram),
            crc_valid,
        )

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
