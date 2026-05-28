"""Config flow for Modbus Devices."""

from __future__ import annotations

import logging
from typing import Any

from logging import getLogger
import voluptuous as vol

from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
)

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import Config
from .equipment.equipment import (
    get_classes_from_files,
    get_serial_ports,
)
from .modbus_client import connect_modbus

_LOGGER = getLogger(__name__)


class ModbusDevicesConfigFlow(
    ConfigFlow,
    domain=Config.DOMAIN,
):
    """Handle config flow for Modbus Devices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""

        self._data: dict[str, Any] = {}

        self._device_classes: list[str] = []
        self._serial_ports: list[str] = []

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Handle initial step."""

        if not self._device_classes:
            self._device_classes = await get_classes_from_files()

        if not self._serial_ports:
            self._serial_ports = await get_serial_ports()

        if user_input is not None:
            self._data.update(user_input)

            mode = user_input[Config.CONF_MODBUS_MODE]

            if mode in (
                Config.MODBUS_TCP,
                Config.MODBUS_UDP,
            ):
                return await self.async_step_network()

            if mode == Config.MODBUS_SERIAL:
                return await self.async_step_serial()

        schema = vol.Schema(
            {
                vol.Required(
                    Config.CONF_MODBUS_MODE,
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [
                                Config.MODBUS_TCP,
                                Config.MODBUS_UDP,
                                Config.MODBUS_SERIAL,
                            ],
                        }
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )

    async def async_step_network(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Handle TCP/UDP setup."""

        errors: dict[str, str] = {}

        if user_input is not None:

            self._data.update(user_input)

            unique_id = (
                f"{self._data[CONF_HOST]}_"
                f"{self._data[CONF_PORT]}_"
                f"{self._data[CONF_DEVICE_ID]}"
            )

            await self.async_set_unique_id(unique_id)

            self._abort_if_unique_id_configured()

            try:
                client = await connect_modbus(self._data)

                if client is None or not client.connected:
                    errors["base"] = "cannot_connect"

                else:
                    client.close()

                    title = (
                        f"{self._data[Config.CONF_DEVICE_CLASS]} "
                        f"({self._data[CONF_HOST]})"
                    )

                    _LOGGER.info(
                        "Creating TCP/UDP config entry: %s",
                        title,
                    )

                    return self.async_create_entry(
                        title=title,
                        data=self._data,
                    )

            except ModbusException as exc:
                _LOGGER.error(
                    "Modbus connection error: %s",
                    exc,
                )
                errors["base"] = "cannot_connect"

            except Exception as exc:
                _LOGGER.exception(
                    "Unexpected error: %s",
                    exc,
                )
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default="10.0.2.13",
                ): cv.string,

                vol.Required(
                    CONF_PORT,
                    default=510,
                ): int,

                vol.Required(
                    CONF_DEVICE_ID,
                    default=1,
                ): int,

                vol.Required(
                    Config.CONF_DEVICE_CLASS,
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": self._device_classes,
                        }
                    }
                ),

                vol.Optional(
                    CONF_NAME,
                    default="Modbus Device",
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="network",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_serial(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        """Handle serial setup."""

        errors: dict[str, str] = {}

        if user_input is not None:

            self._data.update(user_input)

            unique_id = (
                f"{self._data[Config.CONF_COM_PORT]}_"
                f"{self._data[CONF_DEVICE_ID]}"
            )

            await self.async_set_unique_id(unique_id)

            self._abort_if_unique_id_configured()

            try:
                client = await connect_modbus(self._data)

                if client is None or not client.connected:
                    errors["base"] = "cannot_connect"

                else:
                    client.close()

                    title = (
                        f"{self._data[Config.CONF_DEVICE_CLASS]} "
                        f"({self._data[Config.CONF_COM_PORT]})"
                    )

                    _LOGGER.info(
                        "Creating SERIAL config entry: %s",
                        title,
                    )

                    return self.async_create_entry(
                        title=title,
                        data=self._data,
                    )

            except ModbusException as exc:
                _LOGGER.error(
                    "Modbus serial error: %s",
                    exc,
                )
                errors["base"] = "cannot_connect"

            except Exception as exc:
                _LOGGER.exception(
                    "Unexpected error: %s",
                    exc,
                )
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(
                    Config.CONF_DEVICE_CLASS,
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": self._device_classes,
                        }
                    }
                ),

                vol.Required(
                    CONF_DEVICE_ID,
                    default=1,
                ): int,

                vol.Required(
                    Config.CONF_COM_PORT,
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": self._serial_ports,
                        }
                    }
                ),

                vol.Required(
                    Config.CONF_BAUDRATE,
                    default="9600",
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [
                                "300",
                                "600",
                                "1200",
                                "2400",
                                "4800",
                                "9600",
                                "14400",
                                "19200",
                                "38400",
                                "56000",
                                "57600",
                                "115200",
                                "128000",
                                "153600",
                                "230400",
                                "256000",
                                "460800",
                                "921600",
                            ],
                        }
                    }
                ),

                vol.Required(
                    Config.CONF_BYTESIZE,
                    default="8",
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [
                                "7",
                                "8",
                            ],
                        }
                    }
                ),

                vol.Required(
                    Config.CONF_PARITY,
                    default="N",
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [
                                "N",
                                "E",
                                "O",
                            ],
                        }
                    }
                ),

                vol.Required(
                    Config.CONF_STOPBITS,
                    default="1",
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [
                                "0",
                                "1",
                                "2",
                            ],
                        }
                    }
                ),

                vol.Optional(
                    CONF_NAME,
                    default="Modbus Device",
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=schema,
            errors=errors,
        )
