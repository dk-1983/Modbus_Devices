"""4VRS-developed Modbus equipment."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from pymodbus.exceptions import ModbusException

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.climate import HVACMode
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    Platform,
    UnitOfTemperature,
    UnitOfTime,
)

from .category import EquipmentCategory

from ..modbus_validation import (
    validate_fc05_response,
    validate_fc06_response,
    validate_fc16_response,
    validated_bits,
    validated_registers,
)


def _validate_device_id(response: Any, device_id: int, operation: str) -> None:
    """Validate a response identity when the transport exposes one."""
    for attribute in ("dev_id", "device_id", "slave_id", "unit_id"):
        actual = getattr(response, attribute, None)
        if actual is not None and actual != device_id:
            raise ModbusException(
                f"Wrong Modbus device id for {operation}: "
                f"expected {device_id}, got {actual}"
            )


def _is_correlated_exception(
    response: Any,
    *,
    function: int,
    exception_code: int,
    device_id: int,
) -> bool:
    """Return whether an exception belongs to this exact request."""
    is_error = getattr(response, "isError", None)
    if not callable(is_error) or not is_error():
        return False
    if getattr(response, "function_code", None) != function | 0x80:
        return False
    if getattr(response, "exception_code", None) != exception_code:
        return False
    try:
        _validate_device_id(response, device_id, "classify Haier-ESP32 exception")
    except ModbusException:
        return False
    return True


class HaierESP32:
    """4VRS Haier-ESP32-Modbus air-conditioner controller."""

    equipment_manufacturer = "4VRS"
    equipment_model = "Haier-ESP32"
    equipment_category = EquipmentCategory.CLIMATE_CONTROL

    COMMAND_CONFIRM_TIMEOUT = 30.0
    COMMAND_POLL_INTERVAL = 0.25

    _MODE_TO_REGISTER = {
        HVACMode.COOL: 1,
        HVACMode.HEAT: 2,
        HVACMode.DRY: 3,
        HVACMode.FAN_ONLY: 4,
        HVACMode.AUTO: 5,
    }
    _REGISTER_TO_MODE = {value: key for key, value in _MODE_TO_REGISTER.items()}
    _FAN_TO_REGISTER = {"low": 1, "medium": 2, "high": 3, "auto": 4}
    _REGISTER_TO_FAN = {value: key for key, value in _FAN_TO_REGISTER.items()}
    _SWING_TO_REGISTER = {
        "off": 0,
        "vertical": 1,
        "horizontal": 2,
        "both": 3,
    }
    _REGISTER_TO_SWING = {value: key for key, value in _SWING_TO_REGISTER.items()}
    _PRESET_TO_REGISTER = {"none": 0, "boost": 1, "sleep": 2}
    _REGISTER_TO_PRESET = {value: key for key, value in _PRESET_TO_REGISTER.items()}
    _VERTICAL_TO_REGISTER = {
        "health_up": 1,
        "max_up": 2,
        "health_down": 3,
        "up": 4,
        "center": 6,
        "down": 8,
    }
    _REGISTER_TO_VERTICAL = {
        1: "health_up",
        2: "max_up",
        3: "health_down",
        4: "up",
        6: "center",
        8: "down",
        10: "max_down",
        12: "auto",
        14: "auto_special",
    }
    _HORIZONTAL_TO_REGISTER = {
        "center": 0,
        "max_left": 3,
        "left": 4,
        "right": 5,
        "max_right": 6,
    }
    _REGISTER_TO_HORIZONTAL = {
        0: "center",
        3: "max_left",
        4: "left",
        5: "right",
        6: "max_right",
        7: "auto",
    }
    _COMMAND_STATES = {
        0: "idle",
        1: "pending",
        2: "confirmed",
        3: "timeout",
    }

    def __init__(self, client, device_id: int) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = self.equipment_manufacturer
        self.attr_model_name = self.equipment_model
        self.attr_description = "4VRS Haier ESP32 Modbus controller"
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms = [
            Platform.CLIMATE,
            Platform.SWITCH,
            Platform.SELECT,
            Platform.SENSOR,
            Platform.BINARY_SENSOR,
        ]
        self.attr_device_metadata = {
            "register_map": (
                "https://github.com/dk-1983/Haier-ESP32-Modbus/"
                "blob/main/docs/REGISTERS.md"
            ),
            "protocol": "Modbus RTU or Modbus TCP",
        }

    async def data_init(self) -> bool:
        self.attr_init_time = datetime.now()
        return True

    def get_climate_description(self) -> dict[str, Any]:
        return {
            "hvac_modes": [HVACMode.OFF, *self._MODE_TO_REGISTER],
            "fan_modes": list(self._FAN_TO_REGISTER),
            "swing_modes": list(self._SWING_TO_REGISTER),
            "preset_modes": list(self._PRESET_TO_REGISTER),
            "min_temp": 16,
            "max_temp": 30,
            "temperature_step": 1,
            "writes_are_readback_confirmed": True,
        }

    @staticmethod
    def get_switch_descriptions() -> list[dict[str, Any]]:
        return [
            {"switch_id": "quiet", "name": "Quiet", "icon": "mdi:volume-low"},
            {
                "switch_id": "display",
                "name": "Display",
                "icon": "mdi:television-ambient-light",
            },
        ]

    @classmethod
    def get_select_descriptions(cls) -> list[dict[str, Any]]:
        return [
            {
                "select_id": "vertical_position",
                "name": "Vertical position",
                "options": list(cls._VERTICAL_TO_REGISTER),
                "icon": "mdi:arrow-up-down",
            },
            {
                "select_id": "horizontal_position",
                "name": "Horizontal position",
                "options": list(cls._HORIZONTAL_TO_REGISTER),
                "icon": "mdi:arrow-left-right",
            },
        ]

    @staticmethod
    def get_numeric_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "status_age_seconds",
                "name": "Status age",
                "device_class": SensorDeviceClass.DURATION,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfTime.SECONDS,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "status_count",
                "name": "Status packet count",
                "device_class": None,
                "state_class": SensorStateClass.TOTAL_INCREASING,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:counter",
            },
            {
                "sensor_id": "link_flags",
                "name": "Link flags",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:code-braces",
            },
        ]

    @staticmethod
    def get_state_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "command_status",
                "name": "Command status",
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:progress-clock",
            }
        ]

    @staticmethod
    def get_binary_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "fresh_link",
                "name": "Fresh Haier link",
                "device_class": BinarySensorDeviceClass.CONNECTIVITY,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "rtu_enabled",
                "name": "Modbus RTU enabled",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:serial-port",
            },
            {
                "sensor_id": "tcp_enabled",
                "name": "Modbus TCP enabled",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:ethernet",
            },
        ]

    def _diagnostic_snapshot(self, registers: list[int]) -> dict[str, Any]:
        age, count_low, count_high, command_code, flags = registers
        count = (count_high << 16) | count_low
        command_state = self._COMMAND_STATES.get(
            command_code, f"unknown_{command_code}"
        )
        numeric = {
            "status_age_seconds": {
                "value": age,
                "raw_register": age,
                "register_address": 4,
                "parameter_kind": "uint16_seconds",
            },
            "status_count": {
                "value": count,
                "raw_count": [count_low, count_high],
                "register_address": 5,
                "parameter_kind": "uint32_low_word_first",
            },
            "link_flags": {
                "value": flags,
                "raw_register": flags,
                "register_address": 8,
                "parameter_kind": "bitmask",
            },
        }
        return {
            "numeric_sensors": numeric,
            "state_sensors": {
                "command_status": {
                    "state": command_state,
                    "primary_code": command_code,
                    "expanded_codes": [],
                    "expanded_states": [],
                }
            },
            "binary_sensors": {
                "fresh_link": {"state": bool(flags & 0x0001)},
                "rtu_enabled": {"state": bool(flags & 0x0002)},
                "tcp_enabled": {"state": bool(flags & 0x0004)},
            },
        }

    def _unavailable_primary(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        return {
            **diagnostics,
            "climate": {
                "hvac_mode": None,
                "target_temperature": None,
                "current_temperature": None,
                "fan_mode": None,
                "swing_mode": None,
                "preset_mode": None,
                "diagnostics": {"fresh_telemetry": False},
            },
            "switches": {
                "quiet": {"state": None},
                "display": {"state": None},
            },
            "selects": {
                "vertical_position": {"state": None},
                "horizontal_position": {"state": None},
            },
        }

    async def _async_get_snapshot_on(self, client) -> dict[str, Any]:
        diagnostic_response = await client.read_input_registers(
            address=4, count=5, device_id=self.attr_device_id
        )
        diagnostics_registers = validated_registers(
            diagnostic_response,
            5,
            "read Haier-ESP32 diagnostics",
            expected_function=4,
        )
        _validate_device_id(
            diagnostic_response, self.attr_device_id, "read Haier-ESP32 diagnostics"
        )
        diagnostics = self._diagnostic_snapshot(diagnostics_registers)

        power_response = await client.read_coils(
            address=0, count=3, device_id=self.attr_device_id
        )
        if _is_correlated_exception(
            power_response,
            function=1,
            exception_code=0x0B,
            device_id=self.attr_device_id,
        ):
            return self._unavailable_primary(diagnostics)
        coils = validated_bits(
            power_response, 3, "read Haier-ESP32 coils", expected_function=1
        )
        _validate_device_id(
            power_response, self.attr_device_id, "read Haier-ESP32 coils"
        )

        holding_response = await client.read_holding_registers(
            address=0, count=8, device_id=self.attr_device_id
        )
        if _is_correlated_exception(
            holding_response,
            function=3,
            exception_code=0x0B,
            device_id=self.attr_device_id,
        ):
            return self._unavailable_primary(diagnostics)
        holding = validated_registers(
            holding_response,
            8,
            "read Haier-ESP32 controls",
            expected_function=3,
        )
        _validate_device_id(
            holding_response, self.attr_device_id, "read Haier-ESP32 controls"
        )

        input_response = await client.read_input_registers(
            address=0, count=4, device_id=self.attr_device_id
        )
        if _is_correlated_exception(
            input_response,
            function=4,
            exception_code=0x0B,
            device_id=self.attr_device_id,
        ):
            return self._unavailable_primary(diagnostics)
        inputs = validated_registers(
            input_response,
            4,
            "read Haier-ESP32 telemetry",
            expected_function=4,
        )
        _validate_device_id(
            input_response, self.attr_device_id, "read Haier-ESP32 telemetry"
        )

        return {
            **diagnostics,
            "climate": {
                "hvac_mode": (
                    self._REGISTER_TO_MODE.get(holding[1]) if coils[0] else HVACMode.OFF
                ),
                "target_temperature": holding[0],
                "current_temperature": inputs[3] / 10,
                "fan_mode": self._REGISTER_TO_FAN.get(holding[2]),
                "swing_mode": self._REGISTER_TO_SWING.get(holding[4]),
                "preset_mode": self._REGISTER_TO_PRESET.get(holding[5]),
                "diagnostics": {
                    "fault_code": inputs[1],
                    "lock_state": holding[3],
                    "compatibility_unit_number": inputs[2],
                    "legacy_room_temperature": inputs[0],
                    "raw_mode": holding[1],
                    "raw_fan": holding[2],
                    "raw_vertical_position": holding[6],
                    "raw_horizontal_position": holding[7],
                    "fresh_telemetry": True,
                },
            },
            "switches": {
                "quiet": {"state": coils[1]},
                "display": {"state": coils[2]},
            },
            "selects": {
                "vertical_position": {
                    "state": self._REGISTER_TO_VERTICAL.get(
                        holding[6], f"unknown_{holding[6]}"
                    )
                },
                "horizontal_position": {
                    "state": self._REGISTER_TO_HORIZONTAL.get(
                        holding[7], f"unknown_{holding[7]}"
                    )
                },
            },
        }

    async def async_get_snapshot(self) -> dict[str, Any]:
        return await self.attr_client.async_execute_serialized(
            self._async_get_snapshot_on
        )

    async def _wait_for_confirmation_on(self, client) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.COMMAND_CONFIRM_TIMEOUT
        while True:
            response = await client.read_input_registers(
                address=7, count=1, device_id=self.attr_device_id
            )
            status = validated_registers(
                response,
                1,
                "wait for Haier-ESP32 command confirmation",
                expected_function=4,
            )[0]
            _validate_device_id(
                response,
                self.attr_device_id,
                "wait for Haier-ESP32 command confirmation",
            )
            if status == 2:
                return
            if status == 3:
                raise ModbusException("Haier-ESP32 command confirmation timed out")
            if status != 1:
                raise ModbusException(
                    f"Unexpected Haier-ESP32 command status: {status}"
                )
            if loop.time() >= deadline:
                raise ModbusException("Haier-ESP32 command confirmation timed out")
            await asyncio.sleep(self.COMMAND_POLL_INTERVAL)

    async def _write_register_confirmed_on(
        self, client, address: int, value: int, operation: str
    ) -> int:
        response = await client.write_register(
            address=address, value=value, device_id=self.attr_device_id
        )
        validate_fc06_response(
            response,
            address=address,
            value=value,
            operation=operation,
            device_id=self.attr_device_id,
        )
        await self._wait_for_confirmation_on(client)
        readback_response = await client.read_holding_registers(
            address=address, count=1, device_id=self.attr_device_id
        )
        actual = validated_registers(
            readback_response,
            1,
            f"{operation} readback",
            expected_function=3,
        )[0]
        _validate_device_id(
            readback_response, self.attr_device_id, f"{operation} readback"
        )
        if actual != value:
            raise ModbusException(
                f"Haier-ESP32 readback mismatch for {operation}: "
                f"requested {value}, got {actual}"
            )
        return actual

    async def _write_coil_confirmed_on(
        self, client, address: int, value: bool, operation: str
    ) -> bool:
        response = await client.write_coil(
            address=address, value=value, device_id=self.attr_device_id
        )
        validate_fc05_response(
            response,
            address=address,
            value=value,
            operation=operation,
            device_id=self.attr_device_id,
        )
        await self._wait_for_confirmation_on(client)
        readback_response = await client.read_coils(
            address=address, count=1, device_id=self.attr_device_id
        )
        actual = validated_bits(
            readback_response,
            1,
            f"{operation} readback",
            expected_function=1,
        )[0]
        _validate_device_id(
            readback_response, self.attr_device_id, f"{operation} readback"
        )
        if actual is not value:
            raise ModbusException(
                f"Haier-ESP32 readback mismatch for {operation}: "
                f"requested {value}, got {actual}"
            )
        return actual

    async def _write_register_confirmed(
        self, address: int, value: int, operation: str
    ) -> int:
        async def execute(client):
            return await self._write_register_confirmed_on(
                client, address, value, operation
            )

        return await self.attr_client.async_execute_serialized(execute)

    async def _write_coil_confirmed(
        self, address: int, value: bool, operation: str
    ) -> bool:
        async def execute(client):
            return await self._write_coil_confirmed_on(
                client, address, value, operation
            )

        return await self.attr_client.async_execute_serialized(execute)

    async def async_set_hvac_mode(self, mode: HVACMode) -> dict[str, Any]:
        if mode == HVACMode.OFF:
            await self._write_coil_confirmed(0, False, "turn off Haier-ESP32")
            return {"hvac_mode": HVACMode.OFF}
        if mode not in self._MODE_TO_REGISTER:
            raise ValueError(f"Unsupported Haier-ESP32 HVAC mode: {mode}")

        async def set_mode_and_power(client):
            await self._write_register_confirmed_on(
                client,
                1,
                self._MODE_TO_REGISTER[mode],
                "set Haier-ESP32 mode",
            )
            await self._write_coil_confirmed_on(client, 0, True, "turn on Haier-ESP32")

        await self.attr_client.async_execute_serialized(set_mode_and_power)
        return {"hvac_mode": mode}

    async def async_set_target_temperature(self, temperature: float) -> int:
        value = int(temperature)
        if value != temperature or not 16 <= value <= 30:
            raise ValueError("Haier-ESP32 target temperature must be 16..30 °C")
        return await self._write_register_confirmed(
            0, value, "set Haier-ESP32 target temperature"
        )

    async def async_set_fan_mode(self, fan_mode: str) -> str:
        if fan_mode not in self._FAN_TO_REGISTER:
            raise ValueError(f"Unsupported Haier-ESP32 fan mode: {fan_mode}")
        value = self._FAN_TO_REGISTER[fan_mode]
        actual = await self._write_register_confirmed(
            2, value, "set Haier-ESP32 fan mode"
        )
        return self._REGISTER_TO_FAN[actual]

    async def async_set_swing_mode(self, swing_mode: str) -> str:
        if swing_mode not in self._SWING_TO_REGISTER:
            raise ValueError(f"Unsupported Haier-ESP32 swing mode: {swing_mode}")
        value = self._SWING_TO_REGISTER[swing_mode]
        actual = await self._write_register_confirmed(
            4, value, "set Haier-ESP32 swing mode"
        )
        return self._REGISTER_TO_SWING[actual]

    async def async_set_preset_mode(self, preset_mode: str) -> str:
        if preset_mode not in self._PRESET_TO_REGISTER:
            raise ValueError(f"Unsupported Haier-ESP32 preset: {preset_mode}")
        value = self._PRESET_TO_REGISTER[preset_mode]
        actual = await self._write_register_confirmed(
            5, value, "set Haier-ESP32 preset"
        )
        return self._REGISTER_TO_PRESET[actual]

    async def async_set_switch(self, switch_id: str, value: bool) -> bool:
        addresses = {"quiet": 1, "display": 2}
        if switch_id not in addresses:
            raise ValueError(f"Unsupported Haier-ESP32 switch: {switch_id}")
        return await self._write_coil_confirmed(
            addresses[switch_id],
            value,
            f"set Haier-ESP32 {switch_id}",
        )

    async def async_set_select(self, select_id: str, option: str) -> str:
        if select_id == "vertical_position":
            mapping = self._VERTICAL_TO_REGISTER
            reverse = self._REGISTER_TO_VERTICAL
            address = 6
        elif select_id == "horizontal_position":
            mapping = self._HORIZONTAL_TO_REGISTER
            reverse = self._REGISTER_TO_HORIZONTAL
            address = 7
        else:
            raise ValueError(f"Unsupported Haier-ESP32 select: {select_id}")
        if option not in mapping:
            raise ValueError(
                f"Haier-ESP32 {select_id} value is read-only or unsupported: {option}"
            )
        actual = await self._write_register_confirmed(
            address, mapping[option], f"set Haier-ESP32 {select_id}"
        )
        return reverse[actual]


class SamsungESP32Modbus:
    """4VRS Samsung ESP32 UART-to-Modbus air-conditioner controller."""

    equipment_manufacturer = "4VRS"
    equipment_model = "Samsung-ESP32-Modbus"
    equipment_category = EquipmentCategory.CLIMATE_CONTROL

    COMMAND_CONFIRM_TIMEOUT = 12.0
    COMMAND_POLL_INTERVAL = 1.0

    _MODE_TO_REGISTER = {
        HVACMode.AUTO: 0,
        HVACMode.COOL: 1,
        HVACMode.DRY: 2,
        HVACMode.FAN_ONLY: 3,
        HVACMode.HEAT: 4,
    }
    _REGISTER_TO_MODE = {value: key for key, value in _MODE_TO_REGISTER.items()}
    _FAN_TO_REGISTER = {"low": 1, "medium": 2, "high": 3, "auto": 4, "turbo": 5}
    _REGISTER_TO_FAN = {value: key for key, value in _FAN_TO_REGISTER.items()}
    _SWING_TO_REGISTER = {
        "off": 0,
        "vertical": 1,
        "horizontal": 2,
        "both": 3,
    }
    _REGISTER_TO_SWING = {value: key for key, value in _SWING_TO_REGISTER.items()}
    _PRESET_TO_REGISTER = {
        "none": 0,
        "boost": 1,
        "sleep": 2,
        "quiet": 3,
        "legacy_smart": 4,
        "legacy_soft_cool": 5,
        "legacy_wind_1": 6,
        "legacy_wind_2": 7,
        "legacy_wind_3": 8,
    }
    _REGISTER_TO_PRESET = {value: key for key, value in _PRESET_TO_REGISTER.items()}
    _RESULT_STATES = {
        0: "idle",
        1: "pending",
        2: "confirmed",
        3: "timeout_unconfirmed",
        4: "cancelled",
        5: "acknowledged_unverified",
    }
    _LINK_STATES = {0: "not_ready", 7: "ready", 11: "partially_fresh"}
    _EXTENDED_NAMES = (
        "Sleep flag legacy",
        "Auto clean",
        "Ionizer SPI legacy",
        "Energy setting raw",
        "Reset filter reminder",
        "Filter interval legacy",
        "Reset usage counters",
        "Beep raw",
        "Error bytes",
        "Outdoor temperature raw",
        "Cooling capability raw",
        "Heating capability raw",
        "Power raw",
        "Energy raw",
        "Runtime raw",
        "Filter usage raw",
        "Main version",
        "Panel version",
        "Outdoor version",
        "Model code",
        "Option code",
        "Control enable raw",
        "WiFi status raw",
        "Internet status raw",
        "Airflow direction legacy",
    )
    _FILTER_OPTIONS = {"0": 0, "180": 1, "300": 2, "500": 3, "700": 4}
    _AIRFLOW_OPTIONS = {
        "off": 18,
        "indirect": 33,
        "direct": 49,
        "center": 65,
        "wide": 81,
        "left": 97,
        "right": 113,
        "long": 129,
        "legacy_vertical_82": 130,
        "vertical": 146,
        "horizontal": 162,
        "both": 178,
        "fixed": 194,
    }

    def __init__(self, client, device_id: int) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = self.equipment_manufacturer
        self.attr_model_name = self.equipment_model
        self.attr_description = "4VRS Samsung ESP32 Modbus controller"
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms = [
            Platform.CLIMATE,
            Platform.SWITCH,
            Platform.SELECT,
            Platform.NUMBER,
            Platform.SENSOR,
            Platform.BINARY_SENSOR,
            Platform.BUTTON,
        ]
        self.attr_device_metadata = {
            "project": "https://github.com/dk-1983/Samsung-ESP32-MQTT-Modbus",
            "register_map_version": "0.3.0",
            "protocol": "Modbus RTU or Modbus TCP",
            "tested_firmware": "0.4.2",
        }
        self._extended_values: dict[int, int | None] = dict.fromkeys(range(25))
        self._extended_payloads: dict[int, bytes | None] = dict.fromkeys(range(25))
        self._extended_ages: dict[int, int] = dict.fromkeys(range(25), 0xFFFF)
        self._extended_cursor = 0

    async def data_init(self) -> bool:
        self.attr_init_time = datetime.now()
        return True

    def get_climate_description(self) -> dict[str, Any]:
        return {
            "hvac_modes": [HVACMode.OFF, *self._MODE_TO_REGISTER],
            "fan_modes": list(self._FAN_TO_REGISTER),
            "swing_modes": list(self._SWING_TO_REGISTER),
            "preset_modes": list(self._PRESET_TO_REGISTER),
            "min_temp": 16,
            "max_temp": 30,
            "temperature_step": 1,
            "writes_are_readback_confirmed": True,
        }

    @staticmethod
    def get_switch_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "switch_id": "quiet",
                "name": "Quiet",
                "translation_key": "samsung_esp32_quiet",
                "icon": "mdi:volume-low",
            },
            {
                "switch_id": "extended_sleep",
                "name": "Sleep flag legacy",
                "icon": "mdi:sleep",
            },
            {
                "switch_id": "extended_auto_clean",
                "name": "Auto clean",
                "icon": "mdi:air-filter",
            },
            {
                "switch_id": "extended_ionizer",
                "name": "Ionizer SPI legacy",
                "icon": "mdi:creation",
            },
        ]

    @classmethod
    def get_select_descriptions(cls) -> list[dict[str, Any]]:
        return [
            {
                "select_id": "extended_filter_interval",
                "name": "Filter interval legacy",
                "options": list(cls._FILTER_OPTIONS),
                "entity_category": EntityCategory.CONFIG,
            },
            {
                "select_id": "extended_airflow_direction",
                "name": "Airflow direction legacy",
                "options": list(cls._AIRFLOW_OPTIONS),
                "entity_category": EntityCategory.CONFIG,
            },
        ]

    @staticmethod
    def get_number_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "number_id": "extended_energy_setting_raw",
                "name": "Energy setting raw",
                "native_min_value": 0,
                "native_max_value": 255,
                "native_step": 1,
                "native_unit_of_measurement": None,
                "icon": "mdi:code-braces",
            }
        ]

    @staticmethod
    def get_button_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "button_id": "reset_filter_reminder",
                "name": "Reset filter reminder",
                "translation_key": "samsung_esp32_reset_filter",
                "command": "reset_filter_reminder",
                "entity_category": EntityCategory.CONFIG,
            },
            {
                "button_id": "reset_usage_counters",
                "name": "Reset usage counters",
                "command": "reset_usage_counters",
                "entity_category": EntityCategory.CONFIG,
            },
        ]

    @staticmethod
    def get_numeric_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "core_status_age",
                "name": "Core status age",
                "translation_key": "samsung_esp32_core_status_age",
                "device_class": SensorDeviceClass.DURATION,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfTime.SECONDS,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "core_status_count",
                "name": "Core status count",
                "translation_key": "samsung_esp32_core_status_count",
                "device_class": None,
                "state_class": SensorStateClass.TOTAL_INCREASING,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:counter",
            },
            {
                "sensor_id": "link_flags",
                "name": "Link flags",
                "translation_key": "samsung_esp32_link_flags",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:code-braces",
            },
            {
                "sensor_id": "extended_last_index",
                "name": "Extended last index",
                "translation_key": "samsung_esp32_extended_last_index",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "extended_catalog_size",
                "name": "Extended catalog size",
                "translation_key": "samsung_esp32_extended_catalog_size",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            *(
                {
                    "sensor_id": f"extended_age_{index}",
                    "name": f"Extended age {index}",
                    "device_class": SensorDeviceClass.DURATION,
                    "state_class": SensorStateClass.MEASUREMENT,
                    "unit": UnitOfTime.SECONDS,
                    "precision": 0,
                    "entity_category": EntityCategory.DIAGNOSTIC,
                }
                for index in range(25)
            ),
        ]

    @staticmethod
    def get_state_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "link_state",
                "name": "Samsung link state",
                "translation_key": "samsung_esp32_link_state",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "command_result",
                "name": "Command result",
                "translation_key": "samsung_esp32_command_result",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "extended_result",
                "name": "Extended command result",
                "translation_key": "samsung_esp32_extended_result",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            *(
                {
                    "sensor_id": f"extended_raw_{index}",
                    "name": f"Extended raw {index} - {name}",
                    "entity_category": EntityCategory.DIAGNOSTIC,
                    "icon": "mdi:code-braces",
                }
                for index, name in enumerate(SamsungESP32Modbus._EXTENDED_NAMES)
            ),
        ]

    @staticmethod
    def get_binary_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "core_fresh",
                "name": "Core data fresh",
                "translation_key": "samsung_esp32_core_fresh",
                "device_class": BinarySensorDeviceClass.CONNECTIVITY,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "rtu_enabled",
                "name": "Modbus RTU enabled",
                "translation_key": "samsung_esp32_rtu_enabled",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:serial-port",
            },
            {
                "sensor_id": "tcp_enabled",
                "name": "Modbus TCP enabled",
                "translation_key": "samsung_esp32_tcp_enabled",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:ethernet",
            },
            {
                "sensor_id": "uart_tx_enabled",
                "name": "UART TX enabled",
                "translation_key": "samsung_esp32_uart_enabled",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:serial-port",
            },
        ]

    @staticmethod
    def _signed_word(value: int) -> int:
        return value - 0x10000 if value & 0x8000 else value

    @classmethod
    def _state(cls, value: int, states: dict[int, str]) -> dict[str, Any]:
        return {
            "state": states.get(value, f"unknown_{value}"),
            "primary_code": value,
            "expanded_codes": [],
            "expanded_states": [],
        }

    async def _read_registers_on(
        self, client, address: int, count: int, operation: str
    ) -> list[int]:
        response = await client.read_holding_registers(
            address=address, count=count, device_id=self.attr_device_id
        )
        registers = validated_registers(response, count, operation, expected_function=3)
        _validate_device_id(response, self.attr_device_id, operation)
        return registers

    async def _read_optional_on(
        self, client, address: int, operation: str
    ) -> int | None:
        response = await client.read_holding_registers(
            address=address, count=1, device_id=self.attr_device_id
        )
        if _is_correlated_exception(
            response, function=3, exception_code=0x0B, device_id=self.attr_device_id
        ):
            return None
        value = validated_registers(response, 1, operation, expected_function=3)[0]
        _validate_device_id(response, self.attr_device_id, operation)
        return value

    async def _read_extended_payload_on(
        self, client, index: int
    ) -> tuple[bytes | None, int]:
        base = 2500 + 18 * index
        age = (
            await self._read_registers_on(
                client, base + 17, 1, f"read Samsung-ESP32 extended age {index}"
            )
        )[0]
        if age == 0xFFFF:
            return None, age
        response = await client.read_holding_registers(
            address=base, count=17, device_id=self.attr_device_id
        )
        if _is_correlated_exception(
            response, function=3, exception_code=0x0B, device_id=self.attr_device_id
        ):
            return None, age
        words = validated_registers(
            response,
            17,
            f"read Samsung-ESP32 extended payload {index}",
            expected_function=3,
        )
        _validate_device_id(
            response,
            self.attr_device_id,
            f"read Samsung-ESP32 extended payload {index}",
        )
        length = words[0]
        if length > 32:
            raise ModbusException(
                f"Invalid Samsung-ESP32 extended payload length {length} at index {index}"
            )
        payload = bytes(
            byte for word in words[1:17] for byte in ((word >> 8) & 0xFF, word & 0xFF)
        )
        return payload[:length], age

    def _diagnostics(self, registers: list[int]) -> dict[str, Any]:
        age, count_low, count_high, result, flags, uart, ext_result, ext_index, size = (
            registers
        )
        return {
            "numeric_sensors": {
                "core_status_age": {"value": age},
                "core_status_count": {"value": count_low + (count_high << 16)},
                "link_flags": {"value": flags},
                "extended_last_index": {"value": ext_index},
                "extended_catalog_size": {"value": size},
            },
            "state_sensors": {
                "command_result": self._state(result, self._RESULT_STATES),
                "extended_result": self._state(ext_result, self._RESULT_STATES),
            },
            "binary_sensors": {
                "core_fresh": {"state": bool(flags & 0x0001)},
                "rtu_enabled": {"state": bool(flags & 0x0002)},
                "tcp_enabled": {"state": bool(flags & 0x0004)},
                "uart_tx_enabled": {"state": bool(flags & 0x0008) and bool(uart)},
            },
        }

    async def _async_get_snapshot_on(self, client) -> dict[str, Any]:
        diagnostic_words = await self._read_registers_on(
            client, 2475, 9, "read Samsung-ESP32 diagnostics"
        )
        snapshot = self._diagnostics(diagnostic_words)
        for _ in range(5):
            index = self._extended_cursor
            payload, age = await self._read_extended_payload_on(client, index)
            self._extended_payloads[index] = payload
            self._extended_ages[index] = age
            self._extended_values[index] = (
                payload[0] if payload is not None and len(payload) == 1 else None
            )
            self._extended_cursor = (index + 1) % 25
            await asyncio.sleep(0.01)
        for index, payload in self._extended_payloads.items():
            snapshot["state_sensors"][f"extended_raw_{index}"] = {
                "state": None if payload is None else payload.hex(" ").upper(),
                "primary_code": None,
                "expanded_codes": [],
                "expanded_states": [],
            }
            snapshot["numeric_sensors"][f"extended_age_{index}"] = {
                "value": self._extended_ages[index]
            }
        snapshot["numbers"] = {
            "extended_energy_setting_raw": {"value": self._extended_values[3]}
        }
        reverse_filter = {value: key for key, value in self._FILTER_OPTIONS.items()}
        reverse_airflow = {value: key for key, value in self._AIRFLOW_OPTIONS.items()}
        snapshot["selects"] = {
            "extended_filter_interval": {
                "state": reverse_filter.get(self._extended_values[5])
            },
            "extended_airflow_direction": {
                "state": reverse_airflow.get(self._extended_values[24])
            },
        }
        try:
            core = await self._read_registers_on(
                client, 50, 4, "read Samsung-ESP32 core state"
            )
            temperature = await self._read_registers_on(
                client, 58, 2, "read Samsung-ESP32 temperatures"
            )
            fan = await self._read_registers_on(
                client, 2486, 1, "read Samsung-ESP32 fan"
            )
        except ModbusException:
            snapshot.update(
                {
                    "climate": {
                        "hvac_mode": None,
                        "target_temperature": None,
                        "current_temperature": None,
                        "fan_mode": None,
                        "swing_mode": None,
                        "preset_mode": None,
                        "diagnostics": {"fresh_core": False},
                    },
                    "switches": {"quiet": {"state": None}},
                }
            )
            snapshot["state_sensors"]["link_state"] = self._state(0, self._LINK_STATES)
            return snapshot

        swing = await self._read_optional_on(client, 2484, "read Samsung-ESP32 swing")
        preset = await self._read_optional_on(client, 2485, "read Samsung-ESP32 preset")
        quiet = await self._read_optional_on(client, 2487, "read Samsung-ESP32 quiet")
        link, _unit_type, power, mode = core
        snapshot["state_sensors"]["link_state"] = self._state(link, self._LINK_STATES)
        snapshot.update(
            {
                "climate": {
                    "hvac_mode": (
                        self._REGISTER_TO_MODE.get(mode) if power else HVACMode.OFF
                    ),
                    "target_temperature": temperature[0] / 10,
                    "current_temperature": self._signed_word(temperature[1]) / 10,
                    "fan_mode": self._REGISTER_TO_FAN.get(fan[0]),
                    "swing_mode": (
                        None if swing is None else self._REGISTER_TO_SWING.get(swing)
                    ),
                    "preset_mode": (
                        None if preset is None else self._REGISTER_TO_PRESET.get(preset)
                    ),
                    "diagnostics": {
                        "fresh_core": True,
                        "raw_link_state": link,
                        "raw_unit_type": core[1],
                        "raw_power": power,
                        "raw_mode": mode,
                        "raw_fan": fan[0],
                    },
                },
                "switches": {
                    "quiet": {"state": None if quiet is None else bool(quiet)},
                    "extended_sleep": {
                        "state": None
                        if self._extended_values[0] is None
                        else self._extended_values[0] == 0
                    },
                    "extended_auto_clean": {
                        "state": None
                        if self._extended_values[1] is None
                        else self._extended_values[1] == 34
                    },
                    "extended_ionizer": {
                        "state": None
                        if self._extended_values[2] is None
                        else self._extended_values[2] == 15
                    },
                },
            }
        )
        return snapshot

    async def async_get_snapshot(self) -> dict[str, Any]:
        return await self.attr_client.async_execute_serialized(
            self._async_get_snapshot_on
        )

    async def _wait_for_new_result_on(
        self, client, *, result_address: int, allow_acknowledged: bool = False
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.COMMAND_CONFIRM_TIMEOUT
        saw_pending = False
        while True:
            status = (
                await self._read_registers_on(
                    client,
                    result_address,
                    1,
                    "wait for Samsung-ESP32 command result",
                )
            )[0]
            if status == 1:
                saw_pending = True
            elif status == 2 and saw_pending:
                return
            elif status == 5 and saw_pending and allow_acknowledged:
                return
            elif status in (3, 4):
                raise ModbusException(
                    f"Samsung-ESP32 command failed with result {status}"
                )
            if loop.time() >= deadline:
                raise ModbusException("Samsung-ESP32 command confirmation timed out")
            await asyncio.sleep(self.COMMAND_POLL_INTERVAL)

    async def _write_register_on(
        self,
        client,
        address: int,
        value: int,
        operation: str,
        *,
        result_address: int = 2478,
        readback: bool = True,
        allow_acknowledged: bool = False,
    ) -> int:
        response = await client.write_register(
            address=address, value=value, device_id=self.attr_device_id
        )
        validate_fc06_response(
            response,
            address=address,
            value=value,
            operation=operation,
            device_id=self.attr_device_id,
        )
        await self._wait_for_new_result_on(
            client,
            result_address=result_address,
            allow_acknowledged=allow_acknowledged,
        )
        if not readback:
            return value
        actual = (await self._read_registers_on(client, address, 1, operation))[0]
        if actual != value:
            raise ModbusException(
                f"Samsung-ESP32 readback mismatch for {operation}: "
                f"requested {value}, got {actual}"
            )
        return actual

    async def _write_register(self, address: int, value: int, operation: str) -> int:
        async def execute(client):
            return await self._write_register_on(client, address, value, operation)

        return await self.attr_client.async_execute_serialized(execute)

    async def async_set_hvac_mode(self, mode: HVACMode) -> dict[str, Any]:
        if mode == HVACMode.OFF:
            await self._write_register(52, 0, "turn off Samsung-ESP32")
            return {"hvac_mode": HVACMode.OFF}
        if mode not in self._MODE_TO_REGISTER:
            raise ValueError(f"Unsupported Samsung-ESP32 HVAC mode: {mode}")
        mode_value = self._MODE_TO_REGISTER[mode]

        async def execute(client):
            response = await client.write_registers(
                address=52, values=[1, mode_value], device_id=self.attr_device_id
            )
            validate_fc16_response(
                response,
                address=52,
                count=2,
                operation="set Samsung-ESP32 power and mode",
                device_id=self.attr_device_id,
            )
            await self._wait_for_new_result_on(client, result_address=2478)
            actual = await self._read_registers_on(
                client, 52, 2, "read Samsung-ESP32 power and mode"
            )
            if actual != [1, mode_value]:
                raise ModbusException(
                    "Samsung-ESP32 power/mode readback mismatch: "
                    f"requested {[1, mode_value]}, got {actual}"
                )

        await self.attr_client.async_execute_serialized(execute)
        return {"hvac_mode": mode}

    async def async_set_target_temperature(self, temperature: float) -> float:
        if isinstance(temperature, bool) or not 16 <= temperature <= 30:
            raise ValueError("Samsung-ESP32 target temperature must be 16..30 °C")
        if float(temperature).is_integer() is False:
            raise ValueError("Samsung-ESP32 target temperature must use a 1 °C step")
        await self._write_register(
            58, int(temperature) * 10, "set Samsung-ESP32 target temperature"
        )
        return float(temperature)

    async def async_set_fan_mode(self, fan_mode: str) -> str:
        if fan_mode not in self._FAN_TO_REGISTER:
            raise ValueError(f"Unsupported Samsung-ESP32 fan mode: {fan_mode}")
        await self._write_register(
            2486, self._FAN_TO_REGISTER[fan_mode], "set Samsung-ESP32 fan mode"
        )
        return fan_mode

    async def async_set_swing_mode(self, swing_mode: str) -> str:
        if swing_mode not in self._SWING_TO_REGISTER:
            raise ValueError(f"Unsupported Samsung-ESP32 swing mode: {swing_mode}")
        await self._write_register(
            2484,
            self._SWING_TO_REGISTER[swing_mode],
            "set Samsung-ESP32 swing mode",
        )
        return swing_mode

    async def async_set_preset_mode(self, preset_mode: str) -> str:
        if preset_mode not in self._PRESET_TO_REGISTER:
            raise ValueError(f"Unsupported Samsung-ESP32 preset: {preset_mode}")
        await self._write_register(
            2485,
            self._PRESET_TO_REGISTER[preset_mode],
            "set Samsung-ESP32 preset",
        )
        return preset_mode

    async def async_set_switch(self, switch_id: str, value: bool) -> bool:
        mapping = {
            "quiet": (2487, int(value), 2478),
            "extended_sleep": (2450, 0 if value else 255, 2481),
            "extended_auto_clean": (2451, 34 if value else 35, 2481),
            "extended_ionizer": (2452, 15 if value else 240, 2481),
        }
        if switch_id not in mapping:
            raise ValueError(f"Unknown Samsung-ESP32 switch: {switch_id}")
        address, raw, result_address = mapping[switch_id]

        async def execute(client):
            await self._write_register_on(
                client,
                address,
                raw,
                f"set Samsung-ESP32 {switch_id}",
                result_address=result_address,
            )

        await self.attr_client.async_execute_serialized(execute)
        return value

    async def async_set_select(self, select_id: str, option: str) -> str:
        selections = {
            "extended_filter_interval": (2455, self._FILTER_OPTIONS),
            "extended_airflow_direction": (2474, self._AIRFLOW_OPTIONS),
        }
        if select_id not in selections or option not in selections[select_id][1]:
            raise ValueError(f"Unknown Samsung-ESP32 selection: {select_id}={option}")
        address, options = selections[select_id]

        async def execute(client):
            await self._write_register_on(
                client,
                address,
                options[option],
                f"set Samsung-ESP32 {select_id}",
                result_address=2481,
            )

        await self.attr_client.async_execute_serialized(execute)
        return option

    async def async_set_number(self, number_id: str, value: float) -> float:
        if number_id != "extended_energy_setting_raw":
            raise ValueError(f"Unknown Samsung-ESP32 number: {number_id}")
        if (
            isinstance(value, bool)
            or not float(value).is_integer()
            or not 0 <= value <= 255
        ):
            raise ValueError(
                "Samsung-ESP32 raw energy setting must be an integer 0..255"
            )

        async def execute(client):
            await self._write_register_on(
                client,
                2453,
                int(value),
                "set Samsung-ESP32 raw energy setting",
                result_address=2481,
            )

        await self.attr_client.async_execute_serialized(execute)
        return float(value)

    async def async_send_command(self, command: str) -> None:
        if command not in ("reset_filter_reminder", "reset_usage_counters"):
            raise ValueError(f"Unknown Samsung-ESP32 command: {command}")

        address, value, result_address, allow_ack = (
            (57, 1, 2478, False)
            if command == "reset_filter_reminder"
            else (2456, 1, 2481, True)
        )

        async def execute(client):
            await self._write_register_on(
                client,
                address,
                value,
                f"execute Samsung-ESP32 {command}",
                result_address=result_address,
                readback=False,
                allow_acknowledged=allow_ack,
            )

        await self.attr_client.async_execute_serialized(execute)


EQUIPMENT_CLASSES = (HaierESP32, SamsungESP32Modbus)
