"""Protocol and lifecycle tests for raw Modbus RTU over UDP."""

from __future__ import annotations

import asyncio
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
async def test_remote_modbus_exception_is_returned_for_common_validation():
    client, _socket, _sent = prepared(peer(response(bytes.fromhex("01 83 02"))))
    result = await client.read_holding_registers(address=0, count=1, device_id=1)
    assert result.function_code == 0x83
    assert result.exception_code == 2
    assert result.isError() is True


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
async def test_wrong_source_ip_is_rejected_and_port_policy_is_explicit():
    frame = response(bytes.fromhex("01 03 02 00 01"))
    wrong_ip, _socket, _sent = prepared((frame, ("10.0.2.99", 40000)))
    with pytest.raises(ModbusException, match="unexpected IP"):
        await wrong_ip.read_holding_registers(address=0, count=1, device_id=1)

    compatible, _socket, _sent = prepared(peer(frame, port=41000))
    assert (
        await compatible.read_holding_registers(address=0, count=1, device_id=1)
    ).registers == [1]

    strict, _socket, _sent = prepared(peer(frame, port=41000), strict_source_port=True)
    with pytest.raises(ModbusException, match="unexpected port"):
        await strict.read_holding_registers(address=0, count=1, device_id=1)


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
async def test_stale_datagrams_queued_before_send_are_drained_boundedly():
    frame = response(bytes.fromhex("01 03 02 00 01"))
    client, udp_socket, _sent = prepared(peer(frame))
    udp_socket.stale.append((response(bytes.fromhex("02 03 02 00 09")), ("10.0.2.10", 40000)))
    result = await client.read_holding_registers(address=0, count=1, device_id=1)
    assert result.registers == [1]
    assert udp_socket.stale == []


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
