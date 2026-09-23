"""Haier Modbus equipment."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.climate import HVACMode
from homeassistant.const import Platform

from .category import EquipmentCategory
from ..modbus_validation import (
    validate_fc05_response,
    validate_fc06_response,
    validated_bits,
    validated_registers,
)


class YCJA002:
    """Haier YCJ-A002 air-conditioner Modbus interface."""

    equipment_manufacturer = "Haier"
    equipment_model = "YCJ-A002"
    equipment_category = EquipmentCategory.CLIMATE_CONTROL

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
        self.attr_platforms = [Platform.CLIMATE]

    async def data_init(self) -> bool:
        self.attr_init_time = datetime.now()
        return True

    def get_climate_description(self) -> dict[str, Any]:
        return {
            "hvac_modes": [HVACMode.OFF, *self._MODE_TO_REGISTER],
            "fan_modes": list(self._FAN_TO_REGISTER),
            "min_temp": 16,
            "max_temp": 30,
            "temperature_step": 1,
        }

    async def async_get_snapshot(self) -> dict[str, Any]:
        power_response = await self.attr_client.read_coils(
            address=0, count=1, device_id=self.attr_device_id
        )
        power = validated_bits(
            power_response, 1, "read YCJ-A002 power", expected_function=1
        )[0]
        holding_response = await self.attr_client.read_holding_registers(
            address=0, count=4, device_id=self.attr_device_id
        )
        holding = validated_registers(
            holding_response, 4, "read YCJ-A002 controls", expected_function=3
        )
        input_response = await self.attr_client.read_input_registers(
            address=0, count=3, device_id=self.attr_device_id
        )
        inputs = validated_registers(
            input_response, 3, "read YCJ-A002 status", expected_function=4
        )
        return {
            "climate": {
                "hvac_mode": (
                    self._REGISTER_TO_MODE.get(holding[1]) if power else HVACMode.OFF
                ),
                "target_temperature": holding[0],
                "current_temperature": inputs[0],
                "fan_mode": self._REGISTER_TO_FAN.get(holding[2]),
                "swing_mode": None,
                "diagnostics": {
                    "fault_code": inputs[1],
                    "lock_state": holding[3],
                    "compatibility_unit_number": inputs[2],
                    "raw_mode": holding[1],
                    "raw_fan": holding[2],
                },
            }
        }

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

    async def _write_power_on(self, client, value: bool) -> None:
        response = await client.write_coil(
            address=0, value=value, device_id=self.attr_device_id
        )
        validate_fc05_response(
            response,
            address=0,
            value=value,
            operation="set YCJ-A002 power",
            device_id=self.attr_device_id,
        )

    async def _write_power(self, value: bool) -> None:
        await self._write_power_on(self.attr_client, value)

    async def async_set_hvac_mode(self, mode: HVACMode) -> dict[str, Any]:
        if mode == HVACMode.OFF:
            await self._write_power(False)
            return {"hvac_mode": HVACMode.OFF}
        if mode not in self._MODE_TO_REGISTER:
            raise ValueError(f"Unsupported YCJ-A002 HVAC mode: {mode}")

        async def set_mode_and_power(client) -> None:
            await self._write_register_on(
                client, 1, self._MODE_TO_REGISTER[mode], "set YCJ-A002 mode"
            )
            await self._write_power_on(client, True)

        await self.attr_client.async_execute_serialized(set_mode_and_power)
        return {"hvac_mode": mode}

    async def async_set_target_temperature(self, temperature: float) -> int:
        value = int(temperature)
        if value != temperature or not 16 <= value <= 30:
            raise ValueError("YCJ-A002 target temperature must be 16..30 °C")
        await self._write_register(0, value, "set YCJ-A002 target temperature")
        return value

    async def async_set_fan_mode(self, fan_mode: str) -> str:
        if fan_mode not in self._FAN_TO_REGISTER:
            raise ValueError(f"Unsupported YCJ-A002 fan mode: {fan_mode}")
        await self._write_register(
            2, self._FAN_TO_REGISTER[fan_mode], "set YCJ-A002 fan mode"
        )
        return fan_mode


EQUIPMENT_CLASSES = (YCJA002,)
