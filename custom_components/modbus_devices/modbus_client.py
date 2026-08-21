"""Modbus client connection and per-client request serialization."""

import asyncio
from functools import wraps
import logging
from typing import Any

from pymodbus import ModbusException
from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusUdpClient,
)

from .const import Config

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
)

_LOGGER = logging.getLogger(__name__)


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

        raise ValueError(f"Unknown Modbus mode: {mode}")

    except ModbusException as exc:
        _LOGGER.error("Modbus connection error: %s", exc)
        return None

    except Exception as exc:
        _LOGGER.exception("Unexpected error: %s", exc)
        return None
