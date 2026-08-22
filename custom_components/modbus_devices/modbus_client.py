"""Modbus client connection and per-client request serialization."""

import asyncio
from functools import wraps
import logging
from pathlib import Path
import sys
from typing import Any

from pymodbus import ModbusException
from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusUdpClient,
)
from serial.tools import list_ports

from .const import Config
from .rtu_over_udp import ModbusRtuOverUdpClient

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
)

_LOGGER = logging.getLogger(__name__)


def get_serial_ports() -> list[str]:
    """Return available serial ports."""
    result: set[str] = set()

    try:
        for port in list_ports.comports():
            result.add(port.device)
    except Exception:
        _LOGGER.debug("Unable to enumerate serial ports with pyserial", exc_info=True)

    if sys.platform.startswith(("linux", "cygwin")):
        for pattern in ("ttyUSB*", "ttyACM*", "ttyS*"):
            for device in Path("/dev").glob(pattern):
                result.add(str(device))

    elif sys.platform.startswith("darwin"):
        for device in Path("/dev").glob("tty.*"):
            result.add(str(device))

    elif sys.platform.startswith("win"):
        for number in range(1, 33):
            result.add(f"COM{number}")

    ports = sorted(result)
    return ports or ["Not Found"]


class SerializedModbusClient:
    """Serialize every physical Modbus request for one client lifecycle."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._request_lock = asyncio.Lock()

    @property
    def request_lock(self) -> asyncio.Lock:
        """Expose the physical-request boundary for protocol-level tests."""
        return self._request_lock

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._client, name)
        if not callable(attribute) or not name.startswith(("read_", "write_")):
            return attribute

        @wraps(attribute)
        async def serialized_request(*args, **kwargs):
            async with self._request_lock:
                return await attribute(*args, **kwargs)

        return serialized_request


def ensure_serialized_client(client: Any) -> SerializedModbusClient | None:
    """Return one idempotent serialized logical client contract."""
    if client is None or isinstance(client, SerializedModbusClient):
        return client
    return SerializedModbusClient(client)


async def connect_modbus(data: dict[str, Any]):
    """Unified Modbus connection factory."""

    mode = data[Config.CONF_MODBUS_MODE]

    try:
        # -------------------------
        # SERIAL
        # -------------------------
        if mode == Config.MODBUS_SERIAL:
            client = AsyncModbusSerialClient(
                port=data[Config.CONF_COM_PORT],
                baudrate=int(data[Config.CONF_BAUDRATE]),
                bytesize=int(data[Config.CONF_BYTESIZE]),
                parity=data[Config.CONF_PARITY],
                stopbits=int(data[Config.CONF_STOPBITS]),
            )

            await client.connect()

            _LOGGER.info(
                "Connected SERIAL: %s",
                data[Config.CONF_COM_PORT],
            )

            return ensure_serialized_client(client)

        # -------------------------
        # TCP
        # -------------------------
        if mode == Config.MODBUS_TCP:
            client = AsyncModbusTcpClient(
                host=data[CONF_HOST],
                port=data[CONF_PORT],
            )

            await client.connect()

            _LOGGER.info(
                "Connected TCP: %s:%s",
                data[CONF_HOST],
                data[CONF_PORT],
            )

            return ensure_serialized_client(client)

        # -------------------------
        # UDP
        # -------------------------
        if mode == Config.MODBUS_UDP:
            client = AsyncModbusUdpClient(
                host=data[CONF_HOST],
                port=data[CONF_PORT],
            )

            await client.connect()

            _LOGGER.info(
                "Connected UDP: %s:%s",
                data[CONF_HOST],
                data[CONF_PORT],
            )

            return ensure_serialized_client(client)

        # -------------------------
        # RAW MODBUS RTU OVER UDP
        # -------------------------
        if mode == Config.MODBUS_RTU_OVER_UDP:
            remote_port = int(
                data[Config.CONF_REMOTE_PORT]
                if Config.CONF_REMOTE_PORT in data
                else data[CONF_PORT]
            )
            client = ModbusRtuOverUdpClient(
                host=data[CONF_HOST],
                remote_port=remote_port,
                local_udp_port=int(
                    data.get(Config.CONF_LOCAL_UDP_PORT, remote_port)
                ),
                timeout=float(data.get(Config.CONF_TIMEOUT, 3.0)),
                local_bind_address=data.get(Config.CONF_LOCAL_BIND_ADDRESS),
            )
            await client.connect()
            _LOGGER.info(
                "Prepared RTU over UDP: %s:%s (local UDP port %s)",
                data[CONF_HOST],
                remote_port,
                client.local_udp_port,
            )
            return ensure_serialized_client(client)

        raise ValueError(f"Unknown Modbus mode: {mode}")

    except ModbusException as exc:
        _LOGGER.error("Modbus connection error: %s", exc)
        return None
