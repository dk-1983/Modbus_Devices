"""Samsung Modbus interface equipment."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymodbus.exceptions import ModbusException

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.climate import HVACMode
from homeassistant.const import EntityCategory, Platform

from .category import EquipmentCategory
from ..modbus_validation import validate_fc06_response, validated_registers


def _signed_word(value: int) -> int:
    """Decode one big-endian Modbus word as signed INT16."""
    return value - 0x10000 if value & 0x8000 else value


def _validate_device_id(response: Any, expected: int, operation: str) -> None:
    """Validate response identity when pymodbus exposes it."""
    for attribute in ("dev_id", "device_id", "slave_id", "unit_id"):
        actual = getattr(response, attribute, None)
        if actual is not None and actual != expected:
            raise ModbusException(
                f"Wrong Modbus device id for {operation}: expected {expected}, got {actual}"
            )


class MIMB19N:
    """Samsung MIM-B19N/MIM-B19NT Modbus interface profile."""

    equipment_manufacturer = "Samsung"
    equipment_model = "MIM-B19N(T)"
    equipment_category = EquipmentCategory.CLIMATE_CONTROL
    subdevice_address_spec = {"min": 0, "max": 47, "default": 0}

    _MODE_TO_REGISTER = {
        HVACMode.AUTO: 0,
        HVACMode.COOL: 1,
        HVACMode.DRY: 2,
        HVACMode.FAN_ONLY: 3,
        HVACMode.HEAT: 4,
    }
    _REGISTER_TO_MODE = {value: key for key, value in _MODE_TO_REGISTER.items()}
    _FAN_TO_REGISTER = {"auto": 0, "low": 1, "medium": 2, "high": 3}
    _REGISTER_TO_FAN = {value: key for key, value in _FAN_TO_REGISTER.items()}
    _SWING_TO_REGISTER = {"off": 0, "vertical": 1}
    _REGISTER_TO_SWING = {value: key for key, value in _SWING_TO_REGISTER.items()}

    def __init__(self, client, device_id: int) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = self.equipment_manufacturer
        self.attr_model_name = self.equipment_model
        self.attr_description = "Samsung Modbus Interface Module"
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms = [
            Platform.CLIMATE,
            Platform.SENSOR,
            Platform.BINARY_SENSOR,
        ]
        self._subdevice_address = 0
        self._base_address = 50
        self.attr_device_metadata = {
            "protocol": "Modbus RTU; Samsung Control Layer Protocol R1/R2",
            "supported_models": "MIM-B19N / MIM-B19NT",
        }

    def configure_subdevice_address(self, address: int) -> None:
        """Select one of the 48 Samsung-side unit slots."""
        if type(address) is not int or not 0 <= address <= 47:
            raise ValueError("Samsung unit address must be 0..47")
        self._subdevice_address = address
        self._base_address = 50 + address * 50
        self.attr_serial_number = f"unit-{address}"

    async def data_init(self) -> bool:
        self.attr_init_time = datetime.now()
        return True

    def get_climate_description(self) -> dict[str, Any]:
        return {
            "hvac_modes": [HVACMode.OFF, *self._MODE_TO_REGISTER],
            "fan_modes": list(self._FAN_TO_REGISTER),
            "swing_modes": list(self._SWING_TO_REGISTER),
            "min_temp": 16,
            "max_temp": 30,
            "temperature_step": 0.5,
            "writes_are_readback_confirmed": True,
        }

    @staticmethod
    def get_numeric_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "gateway_error_code",
                "name": "Gateway error code",
                "translation_key": "samsung_gateway_error_code",
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:alert-circle-outline",
            },
            {
                "sensor_id": "outdoor_error_code",
                "name": "Outdoor unit error code",
                "translation_key": "samsung_outdoor_error_code",
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:alert-outline",
            },
            {
                "sensor_id": "unit_error_code",
                "name": "Samsung unit error code",
                "translation_key": "samsung_unit_error_code",
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:alert-outline",
            },
            {
                "sensor_id": "unit_type_code",
                "name": "Samsung unit type code",
                "translation_key": "samsung_unit_type_code",
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:identifier",
            },
        ]

    @staticmethod
    def get_binary_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "gateway_link",
                "name": "Samsung gateway link",
                "translation_key": "samsung_gateway_link",
                "device_class": BinarySensorDeviceClass.CONNECTIVITY,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "unit_link",
                "name": "Samsung unit link",
                "translation_key": "samsung_unit_link",
                "device_class": BinarySensorDeviceClass.CONNECTIVITY,
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "outdoor_defrost",
                "name": "Outdoor unit defrost",
                "translation_key": "samsung_outdoor_defrost",
                "device_class": None,
                "entity_category": None,
                "icon": "mdi:snowflake-melt",
            },
        ]

    async def async_get_snapshot(self) -> dict[str, Any]:
        global_response = await self.attr_client.read_input_registers(
            address=0, count=3, device_id=self.attr_device_id
        )
        global_registers = validated_registers(
            global_response, 3, "read MIM-B19N(T) gateway status", expected_function=4
        )
        _validate_device_id(global_response, self.attr_device_id, "read gateway status")

        unit_response = await self.attr_client.read_input_registers(
            address=self._base_address, count=31, device_id=self.attr_device_id
        )
        unit = validated_registers(
            unit_response, 31, "read MIM-B19N(T) unit status", expected_function=4
        )
        _validate_device_id(unit_response, self.attr_device_id, "read unit status")

        gateway_status, outdoor_error, outdoor_defrost = global_registers
        communication = unit[0]
        exists = bool(communication & 0x0001)
        type_valid = bool(communication & 0x0002)
        ready = bool(communication & 0x0004)
        communication_error = bool(communication & 0x0008)
        unit_link = exists and type_valid and ready and not communication_error
        gateway_link = not bool(gateway_status & 0x0007)

        power = unit[2] == 1
        mode = self._REGISTER_TO_MODE.get(unit[3]) if power else HVACMode.OFF
        current_temperature = _signed_word(unit[9]) / 10
        target_temperature = _signed_word(unit[8]) / 10
        if not unit_link:
            mode = None
            current_temperature = None
            target_temperature = None

        numeric = {
            "gateway_error_code": {
                "value": gateway_status,
                "raw_register": gateway_status,
                "register_address": 0,
            },
            "outdoor_error_code": {
                "value": outdoor_error,
                "raw_register": outdoor_error,
                "register_address": 1,
            },
            "unit_error_code": {
                "value": unit[13],
                "raw_register": unit[13],
                "register_address": self._base_address + 13,
            },
            "unit_type_code": {
                "value": unit[1],
                "raw_register": unit[1],
                "register_address": self._base_address + 1,
            },
        }
        return {
            "climate": {
                "hvac_mode": mode,
                "target_temperature": target_temperature,
                "current_temperature": current_temperature,
                "fan_mode": self._REGISTER_TO_FAN.get(unit[4]) if unit_link else None,
                "swing_mode": self._REGISTER_TO_SWING.get(unit[5])
                if unit_link
                else None,
                "diagnostics": {
                    "samsung_unit_address": self._subdevice_address,
                    "register_base": self._base_address,
                    "communication_status": communication,
                    "remote_control_restrictions": unit[14],
                },
            },
            "numeric_sensors": numeric,
            "binary_sensors": {
                "gateway_link": {"state": gateway_link},
                "unit_link": {"state": unit_link},
                "outdoor_defrost": {"state": outdoor_defrost not in (0, 0x00FF)},
            },
        }

    async def _write_register_on(
        self, client, offset: int, value: int, operation: str
    ) -> None:
        address = self._base_address + offset
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

    async def _write_register(self, offset: int, value: int, operation: str) -> None:
        await self._write_register_on(self.attr_client, offset, value, operation)

    async def async_set_hvac_mode(self, mode: HVACMode) -> dict[str, Any]:
        if mode == HVACMode.OFF:
            await self._write_register(2, 0, "turn off Samsung unit")
            return {"hvac_mode": HVACMode.OFF}
        if mode not in self._MODE_TO_REGISTER:
            raise ValueError(f"Unsupported Samsung HVAC mode: {mode}")

        async def set_mode_and_power(client) -> None:
            await self._write_register_on(
                client, 3, self._MODE_TO_REGISTER[mode], "set Samsung mode"
            )
            await self._write_register_on(client, 2, 1, "turn on Samsung unit")

        await self.attr_client.async_execute_serialized(set_mode_and_power)
        return {"hvac_mode": mode}

    async def async_set_target_temperature(self, temperature: float) -> float:
        value = round(float(temperature) * 10)
        if not 160 <= value <= 300 or abs(value / 10 - temperature) > 1e-9:
            raise ValueError("Samsung target temperature must be 16.0..30.0 °C")
        await self._write_register(8, value, "set Samsung target temperature")
        return value / 10

    async def async_set_fan_mode(self, fan_mode: str) -> str:
        if fan_mode not in self._FAN_TO_REGISTER:
            raise ValueError(f"Unsupported Samsung fan mode: {fan_mode}")
        await self._write_register(
            4, self._FAN_TO_REGISTER[fan_mode], "set Samsung fan"
        )
        return fan_mode

    async def async_set_swing_mode(self, swing_mode: str) -> str:
        if swing_mode not in self._SWING_TO_REGISTER:
            raise ValueError(f"Unsupported Samsung swing mode: {swing_mode}")
        await self._write_register(
            5, self._SWING_TO_REGISTER[swing_mode], "set Samsung vertical airflow"
        )
        return swing_mode


EQUIPMENT_CLASSES = (MIMB19N,)
