"""RAW TCP wire regressions, including the YCJ-A002 equipment contract."""

import asyncio
from contextlib import asynccontextmanager
import struct

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.modbus_client import (
    SerializedModbusClient,
    connect_modbus,
)
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.rtu_over_tcp import (
    ModbusRtuOverTcpClient,
    append_modbus_rtu_crc as adu,
    modbus_rtu_crc,
)


@asynccontextmanager
async def gateway(handler, *, timeout=0.2):
    tasks = set()
    errors = []

    async def serve(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            await handler(reader, writer)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        except Exception as exc:
            errors.append(exc)
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = ModbusRtuOverTcpClient("127.0.0.1", port, timeout=timeout)
    await client.connect()
    try:
        yield client
    finally:
        client.close()
        server.close()
        await server.wait_closed()
        pending = list(tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        assert not errors


def test_crc_known_wire_vector():
    assert adu(bytes.fromhex("01030000000a")) == bytes.fromhex("01030000000ac5cd")


@pytest.mark.asyncio
@pytest.mark.parametrize("split", range(1, 9))
async def test_every_response_split_and_raw_request_without_mbap(split):
    reply = adu(bytes.fromhex("07030400170018"))

    async def serve(reader, writer):
        assert await reader.readexactly(8) == adu(bytes.fromhex("070300000002"))
        writer.write(reply[:split])
        await writer.drain()
        await asyncio.sleep(0.002)
        writer.write(reply[split:])
        await writer.drain()
        await reader.read()

    async with gateway(serve) as raw:
        result = await raw.read_holding_registers(address=0, count=2, device_id=7)
        assert result.registers == [23, 24]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [
        adu(bytes.fromhex("0803020017")),  # wrong slave
        adu(bytes.fromhex("0704020017")),  # wrong function
        adu(bytes.fromhex("07030400170018")),  # wrong byte count
        bytes.fromhex("07030200170000"),  # bad CRC
        adu(bytes.fromhex("0703020017")) + b"\x00",  # trailing data
        adu(bytes.fromhex("0703020017")) * 2,  # coalesced duplicate ADUs
        bytes.fromhex("0001000000050703020017"),  # MBAP
        b"\x07\x03\xff" + b"\x00" * 300,  # bounded overflow
    ],
)
async def test_malformed_response_closes_stream(reply):
    async def serve(reader, writer):
        await reader.readexactly(8)
        writer.write(reply)
        await writer.drain()
        await reader.read()

    async with gateway(serve) as raw:
        with pytest.raises(ModbusException):
            await raw.read_holding_registers(address=0, count=1, device_id=7)
        assert not raw.connected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "function,method,kwargs",
    [
        (5, "write_coil", {"value": True}),
        (6, "write_register", {"value": 23}),
        (16, "write_registers", {"values": [23, 24]}),
    ],
)
@pytest.mark.parametrize("mismatch", [None, "address", "value"])
async def test_write_echo_validation(function, method, kwargs, mismatch):
    async def serve(reader, writer):
        request = await reader.readexactly(13 if function == 16 else 8)
        assert request[:2] == bytes([7, function])
        assert modbus_rtu_crc(request[:-2]) == int.from_bytes(request[-2:], "little")
        reply = bytearray(request[:6])
        if mismatch:
            reply[3 if mismatch == "address" else 5] ^= 1
        writer.write(adu(reply))
        await writer.drain()
        await reader.read()

    async with gateway(serve) as raw:
        call = getattr(raw, method)(address=0, device_id=7, **kwargs)
        if mismatch:
            with pytest.raises(ModbusException):
                await call
            assert not raw.connected
        else:
            assert not (await call).isError()


@pytest.mark.asyncio
async def test_exception_response_preserves_healthy_connection():
    async def serve(reader, writer):
        for _ in range(2):
            await reader.readexactly(8)
            writer.write(adu(bytes.fromhex("078302")))
            await writer.drain()
        await reader.read()

    async with gateway(serve) as raw:
        for _ in range(2):
            reply = await raw.read_holding_registers(address=0, count=1, device_id=7)
            assert reply.isError() and reply.exception_code == 2
            assert raw.connected


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "partial", "eof", "cancel"])
@pytest.mark.parametrize("write", [False, True])
async def test_failure_drops_old_connection_next_request_reconnects(failure, write):
    connections = 0
    sent = asyncio.Event()

    async def serve(reader, writer):
        nonlocal connections
        connections += 1
        number = connections
        await reader.readexactly(8)
        sent.set()
        if number == 1:
            if failure == "eof":
                return
            if failure == "partial":
                writer.write(b"\x07\x06\x00" if write else b"\x07\x03\x02\x00")
                await writer.drain()
            assert await reader.read() == b""  # no retries on this stream
        else:
            writer.write(adu(bytes.fromhex("0703020018")))
            await writer.drain()
            await reader.read()

    async with gateway(serve, timeout=0.05) as raw:
        task = asyncio.create_task(
            raw.write_register(address=0, value=23, device_id=7)
            if write
            else raw.read_holding_registers(address=0, count=1, device_id=7)
        )
        await sent.wait()
        if failure == "cancel":
            task.cancel()
        error = {"eof": ModbusException, "cancel": asyncio.CancelledError}.get(
            failure, TimeoutError
        )
        with pytest.raises(error):
            await task
        assert not raw.connected
        assert connections == 1
        reply = await raw.read_holding_registers(address=0, count=1, device_id=7)
        assert reply.registers == [24]
        assert connections == 2


@pytest.mark.asyncio
async def test_ycj_a002_snapshot_and_controls_through_factory():
    from homeassistant.components.climate import HVACMode
    from custom_components.modbus_devices.equipment.haier import YCJA002

    requests = []

    async def serve(reader, writer):
        while True:
            request = await reader.readexactly(8)
            assert modbus_rtu_crc(request[:-2]) == int.from_bytes(
                request[-2:], "little"
            )
            requests.append(request[:-2].hex())
            function = request[1]
            data = {
                1: b"\x01\x01",
                3: struct.pack(">B4H", 8, 23, 1, 4, 1),
                4: struct.pack(">B3H", 6, 24, 0, 0),
            }.get(function, request[2:6])
            reply = adu(request[:2] + data)
            for octet in reply:
                writer.write(bytes([octet]))
                await writer.drain()
                await asyncio.sleep(0)

    async with gateway(serve, timeout=1) as raw:
        client = await connect_modbus(
            {
                Config.CONF_MODBUS_MODE: Config.MODBUS_RTU_OVER_TCP,
                "host": raw.host,
                "port": raw.port,
            }
        )
        assert isinstance(client, SerializedModbusClient)
        try:
            device = YCJA002(client, 7)
            snapshot = await device.async_get_snapshot()
            assert snapshot["climate"]["hvac_mode"] == HVACMode.COOL
            assert snapshot["climate"]["target_temperature"] == 23
            assert snapshot["climate"]["current_temperature"] == 24
            await device.async_set_hvac_mode(HVACMode.HEAT)
            assert requests == [
                "070100000001",
                "070300000004",
                "070400000003",
                "070600010002",
                "07050000ff00",
            ]
        finally:
            client.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"host": ""},
        {"port": 0},
        {"port": 65536},
        {"port": True},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"timeout": True},
    ],
)
def test_invalid_endpoint(kwargs):
    with pytest.raises(ValueError):
        ModbusRtuOverTcpClient(**({"host": "localhost", "port": 502} | kwargs))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "function,method,count,data,expected",
    [
        (1, "read_coils", 9, b"\x81\x01", [True] + [False] * 6 + [True, True]),
        (
            2,
            "read_discrete_inputs",
            9,
            b"\x81\x01",
            [True] + [False] * 6 + [True, True],
        ),
        (3, "read_holding_registers", 125, b"\x12\x34" * 125, [0x1234] * 125),
        (4, "read_input_registers", 125, b"\x12\x34" * 125, [0x1234] * 125),
    ],
)
async def test_read_function_boundaries(function, method, count, data, expected):
    async def serve(reader, writer):
        assert await reader.readexactly(8) == adu(
            struct.pack(">BBHH", 7, function, 0, count)
        )
        writer.write(adu(bytes([7, function, len(data)]) + data))
        await writer.drain()
        await reader.read()

    async with gateway(serve) as raw:
        reply = await getattr(raw, method)(address=0, count=count, device_id=7)
        assert (reply.bits if function < 3 else reply.registers) == expected


@pytest.mark.asyncio
async def test_serialized_tcp_requests_cannot_overlap():
    first_received = asyncio.Event()
    release = asyncio.Event()
    requests = []

    async def serve(reader, writer):
        requests.append(await reader.readexactly(8))
        first_received.set()
        await release.wait()
        writer.write(adu(bytes.fromhex("0703020017")))
        await writer.drain()
        requests.append(await reader.readexactly(8))
        writer.write(requests[-1])
        await writer.drain()
        await reader.read()

    async with gateway(serve, timeout=1) as raw:
        client = SerializedModbusClient(raw)
        read = asyncio.create_task(
            client.read_holding_registers(address=0, count=1, device_id=7)
        )
        await first_received.wait()
        write = asyncio.create_task(
            client.write_register(address=1, value=2, device_id=7)
        )
        await asyncio.sleep(0)
        assert not write.done() and len(requests) == 1
        release.set()
        await asyncio.gather(read, write)
        assert requests == [
            adu(bytes.fromhex("070300000001")),
            adu(bytes.fromhex("070600010002")),
        ]


@pytest.mark.asyncio
async def test_unsolicited_idle_data_is_rejected_before_next_send():
    late_sent = asyncio.Event()
    received = []

    async def serve(reader, writer):
        received.append(await reader.readexactly(8))
        writer.write(adu(bytes.fromhex("0703020017")))
        await writer.drain()
        await late_sent.wait()
        writer.write(adu(bytes.fromhex("0703020017")))
        await writer.drain()
        received.append(await reader.read())

    async with gateway(serve) as raw:
        await raw.read_holding_registers(address=0, count=1, device_id=7)
        late_sent.set()
        await asyncio.wait_for(raw._protocol.changed.wait(), 1)
        with pytest.raises(ModbusException, match="Unsolicited"):
            await raw.read_holding_registers(address=1, count=1, device_id=7)
        assert not raw.connected
        await asyncio.sleep(0.01)
        assert received[1] == b""


@pytest.mark.asyncio
async def test_close_interrupts_wait_and_requires_explicit_reconnect():
    received = asyncio.Event()

    async def serve(reader, writer):
        await reader.readexactly(8)
        received.set()
        await reader.read()

    async with gateway(serve, timeout=1) as raw:
        request = asyncio.create_task(
            raw.read_holding_registers(address=0, count=1, device_id=7)
        )
        await received.wait()
        raw.close()
        raw.close()
        with pytest.raises(ModbusException, match="closed"):
            await request
        with pytest.raises(ModbusException, match="closed"):
            await raw.read_holding_registers(address=0, count=1, device_id=7)
        assert await raw.connect()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("read_coils", {"count": 2001}),
        ("read_holding_registers", {"count": 126}),
        ("read_input_registers", {"count": 0}),
        ("read_discrete_inputs", {"count": -1}),
        ("read_holding_registers", {"count": 2, "address": 65535}),
        ("read_holding_registers", {"count": 1, "device_id": 0}),
        ("write_register", {"value": 65536}),
        ("write_register", {"value": True}),
        ("write_coil", {"value": 1}),
        ("write_registers", {"values": []}),
        ("write_registers", {"values": [0] * 124}),
    ],
)
async def test_invalid_request_never_connects(method, kwargs):
    raw = ModbusRtuOverTcpClient("127.0.0.1", 1)
    with pytest.raises(ValueError):
        await getattr(raw, method)(**({"address": 0, "device_id": 7} | kwargs))
    assert not raw.connected


@pytest.mark.asyncio
async def test_slow_fragments_do_not_extend_request_deadline():
    async def serve(reader, writer):
        await reader.readexactly(8)
        for octet in adu(bytes.fromhex("0703020017")):
            await asyncio.sleep(0.02)
            writer.write(bytes([octet]))
            await writer.drain()

    async with gateway(serve, timeout=0.05) as raw:
        with pytest.raises(TimeoutError):
            await raw.read_holding_registers(address=0, count=1, device_id=7)
        assert not raw.connected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply,method",
    [
        (adu(bytes.fromhex("078300")), "read_holding_registers"),
        (adu(bytes.fromhex("07010181")), "read_coils"),
    ],
)
async def test_invalid_exception_code_and_bit_padding(reply, method):
    async def serve(reader, writer):
        await reader.readexactly(8)
        writer.write(reply)
        await writer.drain()
        await reader.read()

    async with gateway(serve) as raw:
        with pytest.raises(ModbusException):
            await getattr(raw, method)(address=0, count=1, device_id=7)
        assert not raw.connected
