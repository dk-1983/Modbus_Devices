"""Config flow for Modbus Devices."""

from __future__ import annotations

from logging import getLogger
from typing import Any

from pymodbus.exceptions import ModbusException
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME, CONF_PORT
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import Config
from .equipment.equipment import get_classes_from_files, get_serial_ports
from .modbus_client import connect_modbus

_LOGGER = getLogger(__name__)


class ModbusDevicesConfigFlow(ConfigFlow, domain=Config.DOMAIN):
    """Handle config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

        self._device_classes: dict[str, list[str]] = {}

        self._serial_ports: list[str] = []
        self._selected_manufacturer: str = ""
        self._manufacturer_devices: list[str] = []

    # ---------------------------------------------------------
    # STEP 1 - MODE
    # ---------------------------------------------------------
    async def async_step_user(self, user_input=None):
        """Select connection type."""

        if not self._device_classes:
            self._device_classes = await self.hass.async_add_executor_job(
                get_classes_from_files
            )

        if not self._serial_ports:
            self._serial_ports = await self.hass.async_add_executor_job(
                get_serial_ports
            )

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_manufacturer()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_MODBUS_MODE): selector(
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
                )
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    # ---------------------------------------------------------
    # STEP 2 - MANUFACTURER
    # ---------------------------------------------------------
    async def async_step_manufacturer(self, user_input=None):
        """Select manufacturer."""

        if not self._device_classes:
            return self.async_abort(reason="no_devices")

        if user_input is not None:
            self._selected_manufacturer = user_input[Config.CONF_MANUFACTURER]

            self._manufacturer_devices = self._device_classes.get(
                self._selected_manufacturer, []
            )

            return await self.async_step_device()

        manufacturers = sorted(self._device_classes.keys())

        if not manufacturers:
            return self.async_abort(reason="no_manufacturers")

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_MANUFACTURER): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": manufacturers,
                        }
                    }
                )
            }
        )

        return self.async_show_form(
            step_id="manufacturer",
            data_schema=schema,
        )

    # ---------------------------------------------------------
    # STEP 3 - DEVICE
    # ---------------------------------------------------------
    async def async_step_device(self, user_input=None):
        """Select device."""

        if user_input is not None:
            device_name = user_input[Config.CONF_DEVICE_CLASS]

            # FIX: сохраняем ВСЁ что нужно дальше
            self._data[Config.CONF_MANUFACTURER] = self._selected_manufacturer
            self._data[Config.CONF_DEVICE_CLASS] = device_name

            return await self._next_step()

        devices = list(self._manufacturer_devices)

        if not devices:
            return self.async_abort(reason="no_devices_for_manufacturer")

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_DEVICE_CLASS): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": sorted(devices),
                        }
                    }
                )
            }
        )

        return self.async_show_form(step_id="device", data_schema=schema)

    # ---------------------------------------------------------
    # ROUTER
    # ---------------------------------------------------------
    async def _next_step(self):
        mode = self._data.get(Config.CONF_MODBUS_MODE)

        if mode in (Config.MODBUS_TCP, Config.MODBUS_UDP):
            return await self.async_step_network()

        return await self.async_step_serial()

    # ---------------------------------------------------------
    # STEP 4 - NETWORK (TCP/UDP)
    # ---------------------------------------------------------
    async def async_step_network(self, user_input=None):
        """TCP/UDP setup."""

        errors = {}

        if user_input is not None:
            self._data.update(user_input)

            self._data.setdefault(CONF_DEVICE_ID, 1)

            try:
                client = await connect_modbus(self._data)

                if not client or not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    client.close()

                    unique_id = (
                        f"{self._data.get(CONF_HOST)}_"
                        f"{self._data.get(CONF_PORT)}_"
                        f"{self._data.get(CONF_DEVICE_ID)}_"
                        f"{self._selected_manufacturer}_"
                        f"{self._data.get(Config.CONF_DEVICE_CLASS)}"
                    )

                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"{self._selected_manufacturer} {self._data[Config.CONF_DEVICE_CLASS]}",
                        data=self._data,
                    )

            except ModbusException:
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default="10.0.2.13"): cv.string,
                vol.Required(CONF_PORT, default=510): int,
                vol.Required(CONF_DEVICE_ID, default=1): int,
                vol.Optional(CONF_NAME, default="Modbus Device"): cv.string,
            }
        )

        return self.async_show_form(
            step_id="network",
            data_schema=schema,
            errors=errors,
        )

    # ---------------------------------------------------------
    # STEP 5 - SERIAL (FULL SETTINGS RESTORED)
    # ---------------------------------------------------------
    async def async_step_serial(self, user_input=None):
        """Serial setup."""

        errors = {}

        if user_input is not None:
            self._data.update(user_input)

            self._data.setdefault(CONF_DEVICE_ID, 1)

            try:
                client = await connect_modbus(self._data)

                if not client or not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    client.close()

                    unique_id = (
                        f"{self._data.get(Config.CONF_COM_PORT)}_"
                        f"{self._data.get(CONF_DEVICE_ID)}_"
                        f"{self._selected_manufacturer}_"
                        f"{self._data.get(Config.CONF_DEVICE_CLASS)}"
                    )

                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"{self._selected_manufacturer} {self._data[Config.CONF_DEVICE_CLASS]}",
                        data=self._data,
                    )

            except ModbusException:
                errors["base"] = "cannot_connect"

        # -------------------------
        # FULL SERIAL CONFIG
        # -------------------------
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID, default=1): int,
                vol.Required(Config.CONF_COM_PORT): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": self._serial_ports,
                        }
                    }
                ),
                vol.Required(Config.CONF_BAUDRATE, default="9600"): selector(
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
                vol.Required(Config.CONF_BYTESIZE, default="8"): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": ["7", "8"],
                        }
                    }
                ),
                vol.Required(Config.CONF_PARITY, default="N"): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": ["N", "E", "O"],
                        }
                    }
                ),
                vol.Required(Config.CONF_STOPBITS, default="1"): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": ["1", "2"],
                        }
                    }
                ),
                vol.Optional(CONF_NAME, default="Modbus Device"): cv.string,
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=schema,
            errors=errors,
        )
