"""Modbus client connection."""

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

            return client

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

            return client

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

            return client

        raise ValueError(f"Unknown Modbus mode: {mode}")

    except ModbusException as exc:
        _LOGGER.error("Modbus connection error: %s", exc)
        return None

    except Exception as exc:
        _LOGGER.exception("Unexpected error: %s", exc)
        return None
