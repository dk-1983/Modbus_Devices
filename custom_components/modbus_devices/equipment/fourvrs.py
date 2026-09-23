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


EQUIPMENT_CLASSES = (HaierESP32,)
