"""Protocol and lifecycle tests for raw Modbus RTU over UDP."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.modbus_client import (
    SerializedModbusClient,
    connect_modbus,
)
from custom_components.modbus_devices.rtu_over_udp import (
    ModbusRtuOverUdpClient,
    append_modbus_rtu_crc,
    modbus_rtu_crc,
)


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.blocking = None
        self.bound = None
        self.stale = []

    def setblocking(self, value):
        self.blocking = value

    def bind(self, endpoint):
        self.bound = endpoint

    def recvfrom(self, _size):
        if self.stale:
            return self.stale.pop(0)
        raise BlockingIOError

    def close(self):
        self.closed = True

    def getsockname(self):
        return self.bound or ("0.0.0.0", 40000)


def response(payload: bytes) -> bytes:
    return append_modbus_rtu_crc(payload)


def prepared(*datagrams, timeout=0.05, strict_source_port=False):
    client = ModbusRtuOverUdpClient(
        "10.0.2.10",
        40000,
        local_udp_port=40000,
        timeout=timeout,
        strict_source_port=strict_source_port,
    )
    udp_socket = FakeSocket()
    client._socket = udp_socket
    client._remote_endpoint = ("10.0.2.10", 40000)
    client._remote_ip = "10.0.2.10"
    queue = list(datagrams)
    sent = []

    async def sendto(data, endpoint):
        sent.append((data, endpoint, client._socket))

    async def recvfrom(_remaining):
        if queue:
            item = queue.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        await asyncio.sleep(1)

    client._sendto = sendto
    client._recvfrom = recvfrom
    return client, udp_socket, sent


def peer(frame, port=40000):
    return frame, ("10.0.2.10", port)


def recovery_socket(monkeypatch, client):
    fresh = FakeSocket()
    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.socket.socket",
        lambda *_args: fresh,
    )
    client._quarantine_seconds = 0
    return fresh


def test_crc_known_vector_and_wire_byte_order():
    body = bytes.fromhex("01 03 00 00 00 0A")
    assert modbus_rtu_crc(body) == 0xCDC5
    assert append_modbus_rtu_crc(body) == bytes.fromhex("01 03 00 00 00 0A C5 CD")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "kwargs", "reply", "request_hex"),
    [
        ("read_coils", {"address": 0x0013, "count": 10}, "01 01 02 CD 01", "01 01 00 13 00 0A"),
        ("read_discrete_inputs", {"address": 0x00C4, "count": 8}, "01 02 01 AC", "01 02 00 C4 00 08"),
        ("read_holding_registers", {"address": 0x006B, "count": 3}, "01 03 06 02 2B 00 00 00 64", "01 03 00 6B 00 03"),
        ("read_input_registers", {"address": 0x0008, "count": 1}, "01 04 02 00 0A", "01 04 00 08 00 01"),
        ("write_coil", {"address": 0x00AC, "value": True}, "01 05 00 AC FF 00", "01 05 00 AC FF 00"),
        ("write_coil", {"address": 0x00AC, "value": False}, "01 05 00 AC 00 00", "01 05 00 AC 00 00"),
        ("write_register", {"address": 0x0001, "value": 3}, "01 06 00 01 00 03", "01 06 00 01 00 03"),
        ("write_registers", {"address": 0x0001, "values": [10, 258]}, "01 10 00 01 00 02", "01 10 00 01 00 02 04 00 0A 01 02"),
    ],
)
async def test_request_encoding_for_all_supported_functions(
    method, kwargs, reply, request_hex
):
    client, _socket, sent = prepared(peer(response(bytes.fromhex(reply))))
    await getattr(client, method)(device_id=1, **kwargs)
    assert sent == [
        (
            append_modbus_rtu_crc(bytes.fromhex(request_hex)),
            ("10.0.2.10", 40000),
            client._socket,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "kwargs", "reply", "attribute", "expected"),
    [
        ("read_coils", {"address": 0, "count": 10}, "01 01 02 CD 01", "bits", [True, False, True, True, False, False, True, True, True, False]),
        ("read_discrete_inputs", {"address": 0, "count": 8}, "01 02 01 AC", "bits", [False, False, True, True, False, True, False, True]),
        ("read_holding_registers", {"address": 0, "count": 3}, "01 03 06 02 2B 00 00 00 64", "registers", [555, 0, 100]),
        ("read_input_registers", {"address": 0, "count": 1}, "01 04 02 00 0A", "registers", [10]),
        ("write_coil", {"address": 172, "value": True}, "01 05 00 AC FF 00", "value", 0xFF00),
        ("write_register", {"address": 1, "value": 3}, "01 06 00 01 00 03", "value", 3),
        ("write_registers", {"address": 1, "values": [10, 258]}, "01 10 00 01 00 02", "count", 2),
    ],
)
async def test_response_decoding_is_compatible_with_common_validators(
    method, kwargs, reply, attribute, expected
):
    client, _socket, _sent = prepared(peer(response(bytes.fromhex(reply))))
    result = await getattr(client, method)(device_id=1, **kwargs)
    assert result.function_code == int(reply.split()[1], 16)
    assert result.dev_id == 1
    assert getattr(result, attribute) == expected
    assert result.isError() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("exception_code", [3, 4, 15])
async def test_valid_modbus_exception_does_not_taint_transport(exception_code):
    client, udp_socket, _sent = prepared(
        peer(response(bytes((1, 0x83, exception_code))))
    )
    result = await client.read_holding_registers(address=0, count=1, device_id=1)
    assert result.function_code == 0x83
    assert result.exception_code == exception_code
    assert result.isError() is True
    assert client.epoch_tainted is False
    assert client._socket is udp_socket


@pytest.mark.asyncio
async def test_captured_fc03_counter_exception_frame_and_dynamic_source_port():
    request = bytes.fromhex("01 03 B4 FC 00 03 E2 0B")
    exception = bytes.fromhex("01 83 03 01 31")
    assert modbus_rtu_crc(request[:-2]) == int.from_bytes(request[-2:], "little")
    assert modbus_rtu_crc(exception[:-2]) == int.from_bytes(exception[-2:], "little")

    client, _socket, sent = prepared(peer(exception, port=41723))
    result = await client.read_holding_registers(
        address=46332, count=3, device_id=1
    )

    assert sent[0][0] == request
    assert result.dev_id == 1
    assert result.function_code == 0x83
    assert result.exception_code == 3
    assert result.isError() is True


@pytest.mark.asyncio
async def test_response_can_be_accumulated_from_multiple_datagrams():
    frame = response(bytes.fromhex("01 03 04 00 0A 00 0B"))
    client, _socket, _sent = prepared(peer(frame[:3]), peer(frame[3:6]), peer(frame[6:]))
    result = await client.read_holding_registers(address=0, count=2, device_id=1)
    assert result.registers == [10, 11]


@pytest.mark.asyncio
async def test_two_complete_frames_are_not_accepted_as_one_response():
    frame = response(bytes.fromhex("01 03 02 00 01"))
    client, _socket, _sent = prepared(peer(frame + frame))
    with pytest.raises(ModbusException, match="trailing"):
        await client.read_holding_registers(address=0, count=1, device_id=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (bytes.fromhex("01 03 02 00 01 00 00"), "CRC"),
        (response(bytes.fromhex("02 03 02 00 01")), "device id"),
        (response(bytes.fromhex("01 04 02 00 01")), "function"),
        (response(bytes.fromhex("01 03 02 00 01")) + b"\x00", "trailing"),
        (response(bytes.fromhex("01 03 04 00 01 00 02")), "byte count"),
    ],
)
async def test_malformed_frames_are_rejected(frame, message):
    client, _socket, _sent = prepared(peer(frame))
    with pytest.raises(ModbusException, match=message):
        await client.read_holding_registers(address=0, count=1, device_id=1)


@pytest.mark.asyncio
async def test_partial_frame_uses_one_absolute_timeout():
    partial = bytes.fromhex("01 03 02 00")
    client, _socket, _sent = prepared(peer(partial), timeout=0.01)
    with pytest.raises(asyncio.TimeoutError):
        await client.read_holding_registers(address=0, count=1, device_id=1)


@pytest.mark.asyncio
async def test_foreign_source_is_ignored_before_valid_response(caplog):
    frame = response(bytes.fromhex("01 03 02 00 01"))
    client, udp_socket, _sent = prepared(
        (frame, ("10.0.2.99", 40000)), peer(frame)
    )
    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.modbus_devices.rtu_over_udp",
    ):
        result = await client.read_holding_registers(
            address=0, count=1, device_id=1
        )
    assert result.registers == [1]
    assert "disposition=rejected reason=unexpected-source" in caplog.text
    assert client.epoch_tainted is False
    assert client._socket is udp_socket

    compatible, _socket, _sent = prepared(peer(frame, port=41000))
    assert (
        await compatible.read_holding_registers(address=0, count=1, device_id=1)
    ).registers == [1]

    strict, _socket, _sent = prepared(
        peer(frame, port=41000), peer(frame), strict_source_port=True
    )
    assert (
        await strict.read_holding_registers(address=0, count=1, device_id=1)
    ).registers == [1]


@pytest.mark.asyncio
async def test_foreign_noise_preserves_absolute_deadline_then_timeout_taints():
    foreign = peer(
        response(bytes.fromhex("01 03 02 00 09")), port=40000
    )[0], ("10.0.2.99", 40000)
    client, old_socket, _sent = prepared(timeout=0.01)
    remaining_values = []
    calls = 0

    async def foreign_then_wait(remaining):
        nonlocal calls
        remaining_values.append(remaining)
        calls += 1
        if calls <= 3:
            return foreign
        await asyncio.sleep(1)

    client._recvfrom = foreign_then_wait
    with pytest.raises(TimeoutError):
        await client.read_holding_registers(address=0, count=1, device_id=1)

    assert len(remaining_values) >= 2
    assert remaining_values == sorted(remaining_values, reverse=True)
    assert client.epoch_tainted is True
    assert old_socket.closed is True


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [
        ("read_coils", {"address": 0, "count": 0, "device_id": 1}),
        ("read_discrete_inputs", {"address": 0, "count": 2001, "device_id": 1}),
        ("read_holding_registers", {"address": 0, "count": 126, "device_id": 1}),
        ("read_input_registers", {"address": 65535, "count": 2, "device_id": 1}),
        ("write_coil", {"address": 0, "value": 1, "device_id": 1}),
        ("write_register", {"address": -1, "value": 1, "device_id": 1}),
        ("write_register", {"address": 0, "value": 65536, "device_id": 1}),
        ("write_registers", {"address": 0, "values": [], "device_id": 1}),
        ("write_registers", {"address": 0, "values": [1] * 124, "device_id": 1}),
        ("read_coils", {"address": 0, "count": 1, "device_id": 248}),
    ],
)
def test_invalid_arguments_fail_before_network_send(method, kwargs):
    client, _socket, sent = prepared()
    with pytest.raises(ValueError):
        asyncio.run(getattr(client, method)(**kwargs))
    assert sent == []


@pytest.mark.asyncio
async def test_persistent_socket_is_reused_and_close_is_idempotent():
    first = response(bytes.fromhex("01 03 02 00 01"))
    second = response(bytes.fromhex("01 04 02 00 02"))
    client, udp_socket, sent = prepared(peer(first), peer(second))
    await client.read_holding_registers(address=0, count=1, device_id=1)
    await client.read_input_registers(address=0, count=1, device_id=1)
    assert {id(item[2]) for item in sent} == {id(udp_socket)}
    client.close()
    client.close()
    assert udp_socket.closed is True
    assert client.connected is False


@pytest.mark.asyncio
async def test_normal_success_has_no_quarantine_or_reconnect(monkeypatch):
    first = response(bytes.fromhex("01 03 02 00 01"))
    second = response(bytes.fromhex("01 04 02 00 02"))
    client, udp_socket, sent = prepared(peer(first), peer(second))
    sleep = AsyncMock()
    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.asyncio.sleep", sleep
    )

    await client.read_holding_registers(address=0, count=1, device_id=1)
    await client.read_input_registers(address=0, count=1, device_id=1)

    sleep.assert_not_awaited()
    assert client.epoch_tainted is False
    assert client._socket is udp_socket
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_stale_datagrams_queued_before_send_are_drained_boundedly(caplog):
    frame = response(bytes.fromhex("01 03 02 00 01"))
    client, udp_socket, _sent = prepared(peer(frame))
    udp_socket.stale.append((response(bytes.fromhex("02 03 02 00 09")), ("10.0.2.10", 40000)))
    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.modbus_devices.rtu_over_udp",
    ):
        result = await client.read_holding_registers(address=0, count=1, device_id=1)
    assert result.registers == [1]
    assert udp_socket.stale == []
    assert "drain upcoming_seq=1 drained=1" in caplog.text
    assert "slave=2 function=3 length=7 crc_valid=True" in caplog.text


@pytest.mark.asyncio
async def test_closed_socket_and_send_failures_are_explicit():
    disconnected = ModbusRtuOverUdpClient("10.0.2.10", 40000)
    with pytest.raises(ModbusException, match="not connected"):
        await disconnected.read_holding_registers(address=0, count=1, device_id=1)

    frame = response(bytes.fromhex("01 03 02 00 01"))
    client, _socket, _sent = prepared(peer(frame))

    async def failed_send(_data, _endpoint):
        raise OSError("network down")

    client._sendto = failed_send
    with pytest.raises(ModbusException, match="send"):
        await client.read_holding_registers(address=0, count=1, device_id=1)
    assert client.epoch_tainted is False


@pytest.mark.asyncio
async def test_connect_binds_persistent_source_port_and_close(monkeypatch):
    udp_socket = FakeSocket()
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(
        loop,
        "getaddrinfo",
        AsyncMock(return_value=[(2, 2, 17, "", ("10.0.2.10", 40000))]),
    )
    monkeypatch.setattr("custom_components.modbus_devices.rtu_over_udp.socket.socket", lambda *_args: udp_socket)
    client = ModbusRtuOverUdpClient("gateway", 40000)
    assert await client.connect() is True
    assert await client.connect() is True
    assert udp_socket.bound == ("0.0.0.0", 40000)
    assert client.connected is True
    client.close()
    assert udp_socket.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["resolve", "bind"])
async def test_connect_resolution_and_bind_failures_close_partial_socket(
    monkeypatch, failure
):
    udp_socket = FakeSocket()
    loop = asyncio.get_running_loop()
    if failure == "resolve":
        monkeypatch.setattr(loop, "getaddrinfo", AsyncMock(side_effect=OSError("dns")))
    else:
        monkeypatch.setattr(
            loop,
            "getaddrinfo",
            AsyncMock(return_value=[(2, 2, 17, "", ("10.0.2.10", 40000))]),
        )

        def fail_bind(_endpoint):
            raise OSError("in use")

        udp_socket.bind = fail_bind
    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.socket.socket",
        lambda *_args: udp_socket,
    )
    client = ModbusRtuOverUdpClient("gateway", 40000)
    with pytest.raises(ModbusException, match="prepare"):
        await client.connect()
    assert client.connected is False
    if failure == "bind":
        assert udp_socket.closed is True


@pytest.mark.asyncio
async def test_connect_modbus_returns_serialized_rtu_over_udp_client(monkeypatch):
    raw = AsyncMock()
    raw.local_udp_port = 40000
    raw.connect.return_value = True
    monkeypatch.setattr(
        "custom_components.modbus_devices.modbus_client.ModbusRtuOverUdpClient",
        lambda *args, **kwargs: raw,
    )
    client = await connect_modbus(
        {
            Config.CONF_MODBUS_MODE: Config.MODBUS_RTU_OVER_UDP,
            "host": "10.0.2.10",
            "port": 40000,
        }
    )
    assert isinstance(client, SerializedModbusClient)
    assert client._client is raw
    raw.connect.assert_awaited_once()


def test_adapter_has_no_internal_request_lock():
    client = ModbusRtuOverUdpClient("10.0.2.10", 40000)
    assert not hasattr(client, "request_lock")
    assert not hasattr(client, "_request_lock")


@pytest.mark.asyncio
async def test_request_sequences_and_normal_response_diagnostics(caplog):
    first = peer(response(bytes.fromhex("01 06 B4 63 00 3F")))
    second = peer(response(bytes.fromhex("01 03 02 00 0A")))
    client, _socket, _sent = prepared(first, second)

    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.modbus_devices.rtu_over_udp",
    ):
        await client.write_register(address=46179, value=63, device_id=1)
        await client.read_holding_registers(address=46328, count=1, device_id=1)

    assert "request start seq=1 epoch=0" in caplog.text
    assert "expected_function=6 address=46179 count=1 value=63" in caplog.text
    assert "request start seq=2 epoch=0" in caplog.text
    assert "expected_function=3 address=46328 count=1 value=None" in caplog.text
    assert "response seq=1 epoch=0 disposition=accepted" in caplog.text
    assert "response seq=2 epoch=0 disposition=accepted" in caplog.text
    assert "RTU-over-UDP drain" not in caplog.text
    assert all(record.levelno == logging.DEBUG for record in caplog.records)
    assert client.last_request_diagnostic.seq == 2
    assert client.last_request_diagnostic.outcome == "success"


@pytest.mark.asyncio
async def test_timeout_and_cancellation_record_diagnostic_history(caplog):
    timed_out, _socket, _sent = prepared(timeout=0.01)
    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.modbus_devices.rtu_over_udp",
    ):
        with pytest.raises(asyncio.TimeoutError):
            await timed_out.read_holding_registers(address=1, count=1, device_id=1)
    assert timed_out.last_request_diagnostic.outcome == "timeout"
    assert "seq=1 disposition=timeout" in caplog.text
    assert timed_out.epoch_tainted is True
    assert timed_out.connected is False

    cancelled, _socket, _sent = prepared(timeout=1)
    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.modbus_devices.rtu_over_udp",
    ):
        task = asyncio.create_task(
            cancelled.read_holding_registers(address=2, count=1, device_id=1)
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cancelled.last_request_diagnostic.outcome == "cancelled"
    assert "seq=1 disposition=cancelled" in caplog.text
    assert cancelled.epoch_tainted is True
    assert cancelled.connected is False


@pytest.mark.asyncio
async def test_cancellation_during_send_attempt_taints_epoch():
    client, udp_socket, _sent = prepared(timeout=1)
    entered_send = asyncio.Event()

    async def blocked_send(_data, _endpoint):
        entered_send.set()
        await asyncio.Event().wait()

    client._sendto = blocked_send
    task = asyncio.create_task(
        client.read_holding_registers(address=2, count=1, device_id=1)
    )
    await entered_send.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.epoch_tainted is True
    assert client._socket is None
    assert udp_socket.closed is True


@pytest.mark.asyncio
async def test_cancellation_before_send_attempt_does_not_taint_epoch(monkeypatch):
    client, udp_socket, sent = prepared(timeout=1)

    def cancel_before_send(_seq, _started):
        raise asyncio.CancelledError

    monkeypatch.setattr(client, "_drain_stale_datagrams", cancel_before_send)
    with pytest.raises(asyncio.CancelledError):
        await client.read_holding_registers(address=2, count=1, device_id=1)

    assert sent == []
    assert client.epoch_tainted is False
    assert client._socket is udp_socket
    assert udp_socket.closed is False


@pytest.mark.asyncio
async def test_post_send_programming_error_propagates_without_taint(monkeypatch):
    frame = response(bytes.fromhex("01 03 02 00 01"))
    client, udp_socket, _sent = prepared(peer(frame))
    monkeypatch.setattr(
        client,
        "_log_response_candidate",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("local defect")),
    )

    with pytest.raises(RuntimeError, match="local defect"):
        await client.read_holding_registers(address=0, count=1, device_id=1)

    assert client.epoch_tainted is False
    assert client._socket is udp_socket
    assert udp_socket.closed is False


@pytest.mark.asyncio
async def test_stale_datagram_queued_on_closed_epoch_is_discarded(
    monkeypatch, caplog
):
    stale_fc06 = response(bytes.fromhex("01 06 B4 63 00 05"))
    proper_fc03 = response(bytes.fromhex("01 03 02 00 0A"))
    client, udp_socket, _sent = prepared(peer(proper_fc03), timeout=0.01)

    with pytest.raises(asyncio.TimeoutError):
        client._recvfrom = AsyncMock(side_effect=asyncio.TimeoutError())
        await client.write_register(address=46179, value=5, device_id=1)
    assert udp_socket.closed is True
    udp_socket.stale.append(peer(stale_fc06))
    fresh_socket = recovery_socket(monkeypatch, client)
    client._recvfrom = AsyncMock(return_value=peer(proper_fc03))

    with caplog.at_level(
        logging.DEBUG,
        logger="custom_components.modbus_devices.rtu_over_udp",
    ):
        result = await client.read_holding_registers(
            address=46328, count=1, device_id=1
        )

    assert result.registers == [10]
    assert client._socket is fresh_socket
    assert fresh_socket.bound == ("0.0.0.0", 40000)
    assert udp_socket.stale == [peer(stale_fc06)]
    assert client.transport_epoch == 1
    assert client.epoch_tainted is False


@pytest.mark.asyncio
async def test_closing_tainted_epoch_discards_already_queued_datagram(monkeypatch):
    stale_fc06 = response(bytes.fromhex("01 06 B4 63 00 05"))
    proper_fc03 = response(bytes.fromhex("01 03 02 00 0A"))
    client, old_socket, _sent = prepared(timeout=0.01)

    async def timeout_after_queueing(_remaining):
        old_socket.stale.append(peer(stale_fc06))
        raise TimeoutError

    client._recvfrom = timeout_after_queueing
    with pytest.raises(TimeoutError):
        await client.write_register(address=46179, value=5, device_id=1)

    assert old_socket.closed is True
    fresh_socket = recovery_socket(monkeypatch, client)
    client._recvfrom = AsyncMock(return_value=peer(proper_fc03))
    result = await client.read_holding_registers(
        address=46328, count=1, device_id=1
    )

    assert result.registers == [10]
    assert client._socket is fresh_socket
    assert old_socket.stale == [peer(stale_fc06)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delayed_response",
    [
        response(bytes.fromhex("01 03 02 00 6F")),
        response(bytes((1, 0x83, 3))),
        response(bytes((1, 0x83, 4))),
    ],
    ids=["value", "exception-3", "exception-4"],
)
async def test_same_function_stale_fc03_isolated_during_quarantine(
    monkeypatch, delayed_response
):
    proper_fc03 = response(bytes.fromhex("01 03 02 00 0A"))
    client, old_socket, sent = prepared(timeout=0.01)

    with pytest.raises(asyncio.TimeoutError):
        await client.read_holding_registers(
            address=46328, count=1, device_id=1
        )

    release = asyncio.Event()
    sleep_started = asyncio.Event()

    async def controlled_sleep(_delay):
        sleep_started.set()
        await release.wait()

    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.asyncio.sleep",
        controlled_sleep,
    )
    client._quarantine_seconds = 5
    fresh_socket = FakeSocket()
    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.socket.socket",
        lambda *_args: fresh_socket,
    )
    client._recvfrom = AsyncMock(return_value=peer(proper_fc03))

    task = asyncio.create_task(
        client.read_holding_registers(address=46328, count=1, device_id=1)
    )
    await sleep_started.wait()
    assert len(sent) == 1
    assert old_socket.closed is True
    assert client.connected is False

    old_socket.stale.append(peer(delayed_response))
    assert len(sent) == 1
    release.set()
    result = await task

    assert result.registers == [10]
    assert client._socket is fresh_socket
    assert sent[-1][2] is fresh_socket
    assert old_socket.stale == [peer(delayed_response)]


def test_same_function_stale_frame_is_indistinguishable_from_frame_contents():
    stale_fc03 = response(bytes.fromhex("01 03 02 00 6F"))
    result = ModbusRtuOverUdpClient._decode_response(stale_fc03, 1, 3, 1)

    assert result.registers == [111]


@pytest.mark.parametrize("exception_code", [3, 4])
def test_same_function_stale_exception_is_indistinguishable_from_contents(
    exception_code,
):
    stale_exception = response(bytes((1, 0x83, exception_code)))
    result = ModbusRtuOverUdpClient._decode_response(stale_exception, 1, 3, 1)

    assert result.function_code == 0x83
    assert result.exception_code == exception_code
    assert result.isError() is True


@pytest.mark.asyncio
async def test_quarantine_blocks_send_until_fixed_port_recovery(monkeypatch):
    proper = response(bytes.fromhex("01 03 02 00 2A"))
    client, old_socket, sent = prepared(timeout=0.01)
    with pytest.raises(asyncio.TimeoutError):
        await client.read_holding_registers(address=100, count=1, device_id=1)

    release = asyncio.Event()
    sleep_started = asyncio.Event()

    async def controlled_sleep(_delay):
        sleep_started.set()
        await release.wait()

    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.asyncio.sleep",
        controlled_sleep,
    )
    client._quarantine_seconds = 5
    fresh_socket = FakeSocket()
    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.socket.socket",
        lambda *_args: fresh_socket,
    )
    client._recvfrom = AsyncMock(return_value=peer(proper))

    task = asyncio.create_task(
        client.read_holding_registers(address=200, count=1, device_id=1)
    )
    await sleep_started.wait()
    assert len(sent) == 1
    assert old_socket.closed is True
    assert client.connected is False

    release.set()
    result = await task
    assert result.registers == [42]
    assert len(sent) == 2
    assert sent[-1][2] is fresh_socket
    assert fresh_socket.bound == ("0.0.0.0", 40000)


@pytest.mark.asyncio
async def test_wrong_function_is_fatal_and_taints_next_epoch():
    wrong = response(bytes.fromhex("01 06 B4 63 00 05"))
    client, old_socket, _sent = prepared(peer(wrong))

    with pytest.raises(ModbusException, match="Wrong RTU-over-UDP response function"):
        await client.read_holding_registers(address=46328, count=1, device_id=1)

    assert client.epoch_tainted is True
    assert old_socket.closed is True
    assert client.last_request_diagnostic.outcome == "wrong-function"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_frame",
    [
        bytes.fromhex("01 03 02 00 01 00 00"),
        response(bytes.fromhex("01 03 02 00 01")) + b"\x00",
    ],
)
async def test_malformed_or_invalid_crc_taints_epoch(bad_frame):
    client, old_socket, _sent = prepared(peer(bad_frame))

    with pytest.raises(ModbusException):
        await client.read_holding_registers(address=0, count=1, device_id=1)

    assert client.epoch_tainted is True
    assert old_socket.closed is True


@pytest.mark.asyncio
async def test_recovery_bind_failure_starts_new_quarantine(monkeypatch):
    client, _old_socket, sent = prepared(timeout=0.01)
    with pytest.raises(asyncio.TimeoutError):
        await client.read_holding_registers(address=0, count=1, device_id=1)
    client._quarantine_seconds = 5
    sleep_entered = [asyncio.Event(), asyncio.Event()]
    sleep_release = [asyncio.Event(), asyncio.Event()]
    sleep_calls = []

    async def controlled_sleep(delay):
        index = len(sleep_calls)
        sleep_calls.append(delay)
        sleep_entered[index].set()
        await sleep_release[index].wait()

    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.asyncio.sleep",
        controlled_sleep,
    )
    failed_socket = FakeSocket()

    def fail_bind(_endpoint):
        raise OSError("still in use")

    failed_socket.bind = fail_bind
    fresh_socket = FakeSocket()
    sockets = iter((failed_socket, fresh_socket))
    bind_calls = []

    def socket_factory(*_args):
        bind_calls.append(len(bind_calls) + 1)
        return next(sockets)

    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.socket.socket",
        socket_factory,
    )

    first_recovery = asyncio.create_task(
        client.read_holding_registers(address=1, count=1, device_id=1)
    )
    await sleep_entered[0].wait()
    sleep_release[0].set()
    with pytest.raises(ModbusException, match="recover"):
        await first_recovery

    assert client.epoch_tainted is True
    assert client.connected is False
    assert len(sent) == 1
    assert bind_calls == [1]

    proper = response(bytes.fromhex("01 03 02 00 2A"))
    client._recvfrom = AsyncMock(return_value=peer(proper))
    second_recovery = asyncio.create_task(
        client.read_holding_registers(address=2, count=1, device_id=1)
    )
    await sleep_entered[1].wait()
    assert bind_calls == [1]
    assert len(sent) == 1

    sleep_release[1].set()
    result = await second_recovery
    assert result.registers == [42]
    assert bind_calls == [1, 2]
    assert client._socket is fresh_socket
    assert client.epoch_tainted is False


@pytest.mark.asyncio
async def test_close_during_quarantine_prevents_socket_resurrection(monkeypatch):
    client, _old_socket, sent = prepared(timeout=0.01)
    with pytest.raises(asyncio.TimeoutError):
        await client.read_holding_registers(address=0, count=1, device_id=1)

    release = asyncio.Event()
    sleep_started = asyncio.Event()

    async def controlled_sleep(_delay):
        sleep_started.set()
        await release.wait()

    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.asyncio.sleep",
        controlled_sleep,
    )
    client._quarantine_seconds = 5
    created = []
    monkeypatch.setattr(
        "custom_components.modbus_devices.rtu_over_udp.socket.socket",
        lambda *_args: created.append(FakeSocket()),
    )

    task = asyncio.create_task(
        client.read_holding_registers(address=1, count=1, device_id=1)
    )
    await sleep_started.wait()
    client.close()
    release.set()

    with pytest.raises(ModbusException, match="closed during recovery"):
        await task
    assert created == []
    assert client.connected is False
    assert len(sent) == 1
