"""APC Smart-UPS Modbus monitoring equipment."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    Platform,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
    UnitOfTime,
)

from .category import EquipmentCategory

from ..modbus_validation import validated_registers


class SmartUPS3000RMXL:
    """Read-only APC Smart-UPS 3000 RM XL monitoring profile."""

    equipment_manufacturer = "APC"
    equipment_model = "Smart-UPS 3000 RM XL"
    equipment_category = EquipmentCategory.POWER_AND_BACKUP
    STATUS_WORD_3_ADDRESS = 0x0003
    PRIMARY_MEASUREMENTS_ADDRESS = 0x0005
    PRIMARY_MEASUREMENTS_COUNT = 10
    INPUT_VOLTAGE_ADDRESS = 0x0011
    INPUT_MEASUREMENTS_COUNT = 2
    _ONLINE_BIT = 3
    _ON_BATTERY_BIT = 4
    _OVERLOAD_BIT = 5
    _LOW_BATTERY_BIT = 6
    _REPLACE_BATTERY_BIT = 7
    _CALIBRATION_BIT = 0
    _AVR_TRIM_BIT = 1
    _AVR_BOOST_BIT = 2

    def __init__(self, client, device_id: int) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = self.equipment_manufacturer
        self.attr_model_name = self.equipment_model
        self.attr_description = "APC Smart-UPS 3000 RM XL"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms = [Platform.SENSOR, Platform.BINARY_SENSOR]
        self.attr_device_metadata = {
            "protocol": "Modbus TCP; FC03 read-only monitoring",
            "register_map": "Schneider Electric 990-5702A-EN",
        }

    async def data_init(self) -> bool:
        """Initialize local metadata without polling or writing the UPS."""
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return metadata exposed through the common equipment contract."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    @staticmethod
    def get_binary_sensor_descriptions() -> list[dict[str, Any]]:
        """Return semantic states decoded from Status Word 3."""
        return [
            {
                "sensor_id": "online",
                "name": "Online",
                "device_class": BinarySensorDeviceClass.POWER,
                "icon": "mdi:transmission-tower",
            },
            {
                "sensor_id": "on_battery",
                "name": "On battery",
                "device_class": BinarySensorDeviceClass.PROBLEM,
                "icon": "mdi:battery-alert",
            },
            {
                "sensor_id": "low_battery",
                "name": "Low battery",
                "device_class": BinarySensorDeviceClass.BATTERY,
                "icon": "mdi:battery-low",
            },
            {
                "sensor_id": "replace_battery",
                "name": "Replace battery",
                "device_class": BinarySensorDeviceClass.PROBLEM,
                "icon": "mdi:battery-sync",
            },
            {
                "sensor_id": "overload",
                "name": "Overload",
                "device_class": BinarySensorDeviceClass.PROBLEM,
                "icon": "mdi:alert",
            },
            {
                "sensor_id": "battery_calibration",
                "name": "Battery calibration",
                "device_class": BinarySensorDeviceClass.RUNNING,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:battery-sync",
            },
            {
                "sensor_id": "avr_boost",
                "name": "AVR boost",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:transmission-tower-export",
            },
            {
                "sensor_id": "avr_trim",
                "name": "AVR trim",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:transmission-tower-import",
            },
        ]

    @staticmethod
    def get_numeric_sensor_descriptions() -> list[dict[str, Any]]:
        """Return field-verified numeric and raw diagnostic registers."""
        return [
            {
                "sensor_id": "battery_charge",
                "name": "Battery charge",
                "device_class": SensorDeviceClass.BATTERY,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": PERCENTAGE,
                "precision": 0,
            },
            {
                "sensor_id": "runtime_remaining",
                "name": "Runtime remaining",
                "device_class": SensorDeviceClass.DURATION,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfTime.MINUTES,
                "precision": 0,
            },
            {
                "sensor_id": "battery_voltage",
                "name": "Battery voltage",
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfElectricPotential.VOLT,
                "precision": 0,
            },
            {
                "sensor_id": "internal_temperature",
                "name": "Internal temperature",
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfTemperature.CELSIUS,
                "precision": 0,
            },
            {
                "sensor_id": "battery_pack_count",
                "name": "Battery pack count",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:battery-outline",
            },
            {
                "sensor_id": "output_load",
                "name": "Output load",
                "device_class": None,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": PERCENTAGE,
                "precision": 0,
                "icon": "mdi:gauge",
            },
            {
                "sensor_id": "output_voltage",
                "name": "Output voltage",
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfElectricPotential.VOLT,
                "precision": 0,
            },
            {
                "sensor_id": "input_voltage",
                "name": "Input voltage",
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfElectricPotential.VOLT,
                "precision": 0,
            },
            {
                "sensor_id": "input_frequency",
                "name": "Input frequency",
                "device_class": SensorDeviceClass.FREQUENCY,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfFrequency.HERTZ,
                "precision": 0,
            },
            {
                "sensor_id": "status_word_3",
                "name": "Status word 3",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:code-braces",
            },
        ]

    async def async_get_snapshot(self) -> dict[str, dict[str, Any]]:
        """Read only field-verified registers without touching min/max values."""
        status_word = (
            await self._read_words(
                self.STATUS_WORD_3_ADDRESS, "read Smart-UPS Status Word 3"
            )
        )[0]
        primary = await self._read_words(
            self.PRIMARY_MEASUREMENTS_ADDRESS,
            "read Smart-UPS primary measurements",
            count=self.PRIMARY_MEASUREMENTS_COUNT,
        )
        input_measurements = await self._read_words(
            self.INPUT_VOLTAGE_ADDRESS,
            "read Smart-UPS input measurements",
            count=self.INPUT_MEASUREMENTS_COUNT,
        )
        return {
            "binary_sensors": {
                "online": self._binary_state(status_word, self._ONLINE_BIT),
                "on_battery": self._binary_state(status_word, self._ON_BATTERY_BIT),
                "low_battery": self._binary_state(status_word, self._LOW_BATTERY_BIT),
                "replace_battery": self._binary_state(
                    status_word, self._REPLACE_BATTERY_BIT
                ),
                "overload": self._binary_state(status_word, self._OVERLOAD_BIT),
                "battery_calibration": self._binary_state(
                    status_word, self._CALIBRATION_BIT
                ),
                "avr_boost": self._binary_state(status_word, self._AVR_BOOST_BIT),
                "avr_trim": self._binary_state(status_word, self._AVR_TRIM_BIT),
            },
            "numeric_sensors": {
                "battery_charge": self._numeric_state(primary[0], 0x0005, "apc_uint16"),
                "runtime_remaining": self._numeric_state(
                    primary[1], 0x0006, "apc_uint16"
                ),
                "battery_voltage": self._numeric_state(
                    primary[2], 0x0007, "apc_uint16"
                ),
                "internal_temperature": self._numeric_state(
                    primary[3], 0x0008, "apc_uint16"
                ),
                "battery_pack_count": self._numeric_state(
                    primary[6], 0x000B, "apc_uint16"
                ),
                "output_load": self._numeric_state(primary[7], 0x000C, "apc_uint16"),
                "output_voltage": self._numeric_state(primary[9], 0x000E, "apc_uint16"),
                "input_voltage": self._numeric_state(
                    input_measurements[0],
                    self.INPUT_VOLTAGE_ADDRESS,
                    "apc_uint16",
                ),
                "input_frequency": self._numeric_state(
                    input_measurements[1], 0x0012, "apc_uint16"
                ),
                "status_word_3": self._numeric_state(
                    status_word, self.STATUS_WORD_3_ADDRESS, "apc_status_word"
                ),
            },
        }

    async def _read_words(
        self, address: int, operation: str, *, count: int = 1
    ) -> list[int]:
        response = await self.attr_client.read_holding_registers(
            address=address, count=count, device_id=self.attr_device_id
        )
        return validated_registers(response, count, operation, expected_function=3)

    @staticmethod
    def _binary_state(status_word: int, bit: int) -> dict[str, Any]:
        return {
            "state": bool(status_word & (1 << bit)),
            "primary_code": status_word,
            "expanded_codes": [],
        }

    @staticmethod
    def _numeric_state(value: int, address: int, parameter_kind: str) -> dict[str, Any]:
        return {
            "value": value,
            "raw_register": value,
            "register_address": address,
            "parameter_kind": parameter_kind,
        }


EQUIPMENT_CLASSES = (SmartUPS3000RMXL,)
