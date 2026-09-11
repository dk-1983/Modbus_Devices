"""Daikin Modbus equipment."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, Platform, UnitOfTemperature

from ..modbus_validation import validate_fc06_response, validated_registers


def _signed_16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class RTDRA:
    """Daikin RTD-RA Modbus interface."""

    equipment_manufacturer = "Daikin"
    equipment_model = "RTD-RA"

    _MODE_TO_REGISTER = {
        HVACMode.AUTO: 0,
        HVACMode.HEAT: 1,
        HVACMode.FAN_ONLY: 2,
        HVACMode.COOL: 3,
        HVACMode.DRY: 4,
    }
    _REGISTER_TO_MODE = {value: key for key, value in _MODE_TO_REGISTER.items()}
    _FAN_TO_REGISTER = {
        "auto": 0,
        "speed_1": 1,
        "speed_2": 2,
        "speed_3": 3,
        "speed_4": 4,
        "speed_5": 5,
    }
    _REGISTER_TO_FAN = {value: key for key, value in _FAN_TO_REGISTER.items()}
    _SWING_TO_REGISTER = {"off": 0, "on": 1}
    _REGISTER_TO_SWING = {value: key for key, value in _SWING_TO_REGISTER.items()}

    def __init__(self, client, device_id: int) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = self.equipment_manufacturer
        self.attr_model_name = self.equipment_model
        self.attr_description = "Air-conditioner Modbus interface"
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms = [Platform.CLIMATE, Platform.SENSOR]

    async def data_init(self) -> bool:
        self.attr_init_time = datetime.now()
        return True

    def get_climate_description(self) -> dict[str, Any]:
        return {
            "hvac_modes": [HVACMode.OFF, *self._MODE_TO_REGISTER],
            "fan_modes": list(self._FAN_TO_REGISTER),
            "swing_modes": list(self._SWING_TO_REGISTER),
            "min_temp": 10,
            "max_temp": 32,
            "temperature_step": 1,
        }

    def get_numeric_sensor_descriptions(self) -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": "coil_inlet_temperature",
                "name": "Coil inlet temperature",
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfTemperature.CELSIUS,
                "precision": 2,
                "entity_category": EntityCategory.DIAGNOSTIC,
            }
        ]

    async def async_get_snapshot(self) -> dict[str, Any]:
        controls_response = await self.attr_client.read_holding_registers(
            address=0, count=5, device_id=self.attr_device_id
        )
        controls = validated_registers(
            controls_response, 5, "read RTD-RA controls", expected_function=3
        )
        status_response = await self.attr_client.read_input_registers(
            address=120, count=3, device_id=self.attr_device_id
        )
        status = validated_registers(
            status_response, 3, "read RTD-RA status", expected_function=4
        )
        thermo_response = await self.attr_client.read_input_registers(
            address=129, count=2, device_id=self.attr_device_id
        )
        thermo = validated_registers(
            thermo_response, 2, "read RTD-RA thermo status", expected_function=4
        )
        return {
            "climate": {
                "hvac_mode": (
                    self._REGISTER_TO_MODE.get(controls[2])
                    if controls[4]
                    else HVACMode.OFF
                ),
                "target_temperature": controls[0],
                "current_temperature": _signed_16(status[2]) / 100,
                "fan_mode": self._REGISTER_TO_FAN.get(controls[1]),
                "swing_mode": self._REGISTER_TO_SWING.get(controls[3]),
                "diagnostics": {
                    "fault_active": bool(status[0]),
                    "fault_code": self._decode_fault_code(status[1]),
                    "thermo_state": thermo[0],
                    "raw_mode": controls[2],
                },
            },
            "numeric_sensors": {
                "coil_inlet_temperature": {
                    "value": _signed_16(thermo[1]) / 100,
                    "raw_register": thermo[1],
                    "register_address": 130,
                    "parameter_kind": "coil_inlet_temperature",
                }
            },
        }

    @staticmethod
    def _decode_fault_code(value: int) -> str | None:
        if value == 255:
            return None
        if value == 0:
            return "waiting"
        return bytes((value >> 8, value & 0xFF)).decode("ascii", errors="replace")

    async def _write_register_on(
        self, client, address: int, value: int, operation: str
    ) -> None:
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

    async def _write_register(self, address: int, value: int, operation: str) -> None:
        await self._write_register_on(self.attr_client, address, value, operation)

    async def async_set_hvac_mode(self, mode: HVACMode) -> dict[str, Any]:
        if mode == HVACMode.OFF:
            await self._write_register(4, 0, "turn off RTD-RA")
            return {"hvac_mode": HVACMode.OFF}
        if mode not in self._MODE_TO_REGISTER:
            raise ValueError(f"Unsupported RTD-RA HVAC mode: {mode}")

        async def set_mode_and_power(client) -> None:
            await self._write_register_on(
                client, 2, self._MODE_TO_REGISTER[mode], "set RTD-RA mode"
            )
            await self._write_register_on(client, 4, 1, "turn on RTD-RA")

        await self.attr_client.async_execute_serialized(set_mode_and_power)
        return {"hvac_mode": mode}

    async def async_set_target_temperature(self, temperature: float) -> int:
        value = int(temperature)
        if value != temperature or not 10 <= value <= 32:
            raise ValueError("RTD-RA target temperature must be 10..32 °C")
        await self._write_register(0, value, "set RTD-RA target temperature")
        return value

    async def async_set_fan_mode(self, fan_mode: str) -> str:
        if fan_mode not in self._FAN_TO_REGISTER:
            raise ValueError(f"Unsupported RTD-RA fan mode: {fan_mode}")
        await self._write_register(
            1, self._FAN_TO_REGISTER[fan_mode], "set RTD-RA fan mode"
        )
        return fan_mode

    async def async_set_swing_mode(self, swing_mode: str) -> str:
        if swing_mode not in self._SWING_TO_REGISTER:
            raise ValueError(f"Unsupported RTD-RA swing mode: {swing_mode}")
        await self._write_register(
            3, self._SWING_TO_REGISTER[swing_mode], "set RTD-RA louvre mode"
        )
        return swing_mode


EQUIPMENT_CLASSES = (RTDRA,)
