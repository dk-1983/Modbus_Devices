"""Equipment models manufactured by ERMAN."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Any

from pymodbus.exceptions import ModbusException

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)

from .category import EquipmentCategory

from ..modbus_validation import (
    validate_fc05_response,
    validated_bits,
    validated_registers,
)


@dataclass(frozen=True, slots=True)
class RuntimeRegister:
    """One documented ER-G-220-05 FC04 runtime register."""

    sensor_id: str
    name: str
    offset: int
    scale: float
    unit: str | None
    device_class: SensorDeviceClass | None
    precision: int
    icon: str


RUNTIME_BASE_ADDRESS = 2000
RUNTIME_REGISTER_COUNT = 10

NUMERIC_REGISTERS = (
    RuntimeRegister(
        "output_frequency",
        "Output frequency",
        0,
        0.1,
        UnitOfFrequency.HERTZ,
        SensorDeviceClass.FREQUENCY,
        1,
        "mdi:sine-wave",
    ),
    RuntimeRegister(
        "motor_current",
        "Motor current",
        1,
        0.1,
        UnitOfElectricCurrent.AMPERE,
        SensorDeviceClass.CURRENT,
        1,
        "mdi:current-ac",
    ),
    RuntimeRegister(
        "input_voltage",
        "Input voltage",
        2,
        1,
        UnitOfElectricPotential.VOLT,
        SensorDeviceClass.VOLTAGE,
        0,
        "mdi:flash",
    ),
    RuntimeRegister(
        "drive_temperature",
        "Drive temperature",
        3,
        1,
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        0,
        "mdi:thermometer",
    ),
    RuntimeRegister(
        "current_pressure",
        "Current pressure",
        6,
        0.01,
        "atm",
        None,
        2,
        "mdi:gauge",
    ),
    RuntimeRegister(
        "analog_input_1",
        "Analog input A1",
        8,
        1,
        "%",
        None,
        0,
        "mdi:percent",
    ),
    RuntimeRegister(
        "analog_input_2",
        "Analog input A2",
        9,
        1,
        "%",
        None,
        0,
        "mdi:percent",
    ),
)

DRIVE_STATES = {
    0: "initializing",
    1: "off",
    2: "motor_starting",
    3: "moving_to_setpoint",
    4: "maintaining_setpoint",
    5: "detecting_flow",
    6: "sleep",
    7: "stopping",
    8: "running_at_set_frequency",
    9: "fault",
    10: "start_delay",
    11: "relay_test_before_start",
}

FAULTS = {
    0: "no_fault",
    4: "err1",
    5: "e_p1",
    6: "e_fa",
    7: "e_th",
    8: "e_c1",
    9: "e_c2",
    10: "e_ul",
    11: "e_er",
    12: "e_uh",
    13: "e_u3",
    14: "e_u4",
    15: "e_u5",
    16: "e_u6",
    17: "e_u7",
    18: "e_u8",
    19: "e_u9",
    20: "e_s1",
    21: "e_sh",
    24: "e_s2",
    25: "e_rf",
    26: "e_c3",
    27: "e_af",
    28: "e_cf",
}


class ERGCommand(IntEnum):
    """Documented ER-G command-coil addresses."""

    START = 0
    STOP = 1
    EMERGENCY_STOP = 2
    SAVE_PARAMETERS = 5
    LOAD_PARAMETERS = 7
    RESET_FAULT = 9


class ERG22005:
    """ERMAN ER-G-220-05 variable-frequency drive."""

    equipment_manufacturer = "ERMAN"
    equipment_model = "ER-G-220-05"
    equipment_category = EquipmentCategory.VARIABLE_FREQUENCY_DRIVES
    uses_stable_entry_identity = True
    attr_poll_interval = timedelta(seconds=1)

    def __init__(self, client, device_id) -> None:
        """Initialize a document-derived equipment profile."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = self.equipment_manufacturer
        self.attr_model_name = self.equipment_model
        self.attr_description = "Variable-frequency drive"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms = [Platform.SENSOR, Platform.BUTTON, Platform.SWITCH]
        self.attr_unique_id_prefix = None
        self.attr_device_identifier = None
        self.attr_device_metadata = {
            "protocol_document": "MODBUS protocol v1.2 (2025-01-17)",
            "documented_software_version": "01.25",
            "serial_defaults": "9600 8N1; slave address 1",
            "validation": "document-derived; hardware feedback pending",
            "writes": "documented FC05 commands exposed; hardware feedback pending",
        }

    async def data_init(self) -> bool:
        """Initialize local metadata without performing device I/O."""
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only identity values actually known at runtime."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    @staticmethod
    def get_numeric_sensor_descriptions() -> list[dict[str, Any]]:
        """Describe the useful engineering values from FC04 registers 2000-2009."""
        return [
            {
                "sensor_id": item.sensor_id,
                "name": item.name,
                "device_class": item.device_class,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": item.unit,
                "precision": item.precision,
                "icon": item.icon,
                "translation_key": f"erman_{item.sensor_id}",
            }
            for item in NUMERIC_REGISTERS
        ]

    @staticmethod
    def get_state_sensor_descriptions() -> list[dict[str, Any]]:
        """Describe lossless runtime status, fault, and software-version states."""
        return [
            {
                "sensor_id": "drive_state",
                "name": "Drive state",
                "translation_key": "erman_drive_state",
                "device_class": SensorDeviceClass.ENUM,
                "options": list(DRIVE_STATES.values()),
                "icon": "mdi:engine",
                "unknown_state_icon": "mdi:help-circle-outline",
            },
            {
                "sensor_id": "fault_code",
                "name": "Fault code",
                "translation_key": "erman_fault_code",
                "device_class": SensorDeviceClass.ENUM,
                "options": [
                    "no_fault",
                    "reserved_fault_1",
                    "reserved_fault_2",
                    "reserved_fault_3",
                    *[FAULTS[code] for code in sorted(FAULTS) if code != 0],
                ],
                "icon": "mdi:alert-circle-outline",
                "unknown_state_icon": "mdi:help-circle-outline",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "software_version",
                "name": "Software version",
                "translation_key": "erman_software_version",
                "icon": "mdi:chip",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
        ]

    @staticmethod
    def get_button_descriptions() -> list[dict[str, Any]]:
        """Describe only non-reserved command coils from the manual."""
        return [
            {
                "button_id": "start",
                "name": "Start",
                "translation_key": "erman_start",
                "command": ERGCommand.START,
            },
            {
                "button_id": "stop",
                "name": "Stop",
                "translation_key": "erman_stop",
                "command": ERGCommand.STOP,
            },
            {
                "button_id": "emergency_stop",
                "name": "Emergency stop",
                "translation_key": "erman_emergency_stop",
                "command": ERGCommand.EMERGENCY_STOP,
            },
            {
                "button_id": "save_parameters",
                "name": "Save parameters to EEPROM",
                "translation_key": "erman_save_parameters",
                "command": ERGCommand.SAVE_PARAMETERS,
                "entity_category": EntityCategory.CONFIG,
            },
            {
                "button_id": "load_parameters",
                "name": "Load parameters from EEPROM",
                "translation_key": "erman_load_parameters",
                "command": ERGCommand.LOAD_PARAMETERS,
                "entity_category": EntityCategory.CONFIG,
            },
            {
                "button_id": "reset_fault",
                "name": "Reset fault",
                "translation_key": "erman_reset_fault",
                "command": ERGCommand.RESET_FAULT,
                "entity_category": EntityCategory.CONFIG,
            },
        ]

    @staticmethod
    def get_switch_descriptions() -> list[dict[str, Any]]:
        """Describe the two documented Y1/Y2 state-command coils."""
        return [
            {
                "switch_id": "output_y1",
                "name": "State / command - Y1",
                "translation_key": "erman_output_y1",
                "icon": "mdi:electric-switch",
            },
            {
                "switch_id": "output_y2",
                "name": "State / command - Y2",
                "translation_key": "erman_output_y2",
                "icon": "mdi:electric-switch",
            },
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read and decode one exact FC04 runtime block."""
        response = await self.attr_client.read_input_registers(
            address=RUNTIME_BASE_ADDRESS,
            count=RUNTIME_REGISTER_COUNT,
            device_id=self.attr_device_id,
        )
        self._validate_response_device_id(response, "read ER-G-220-05 runtime")
        registers = validated_registers(
            response,
            RUNTIME_REGISTER_COUNT,
            "read ER-G-220-05 runtime",
            expected_function=4,
        )
        outputs_response = await self.attr_client.read_coils(
            address=13,
            count=2,
            device_id=self.attr_device_id,
        )
        self._validate_response_device_id(
            outputs_response,
            "read ER-G-220-05 Y1/Y2 states",
        )
        outputs = validated_bits(
            outputs_response,
            2,
            "read ER-G-220-05 Y1/Y2 states",
            expected_function=1,
        )
        snapshot = self.decode_runtime(registers)
        snapshot["switches"] = {
            "output_y1": {"state": outputs[0]},
            "output_y2": {"state": outputs[1]},
        }
        return snapshot

    async def async_send_command(self, command: ERGCommand | int) -> None:
        """Send one documented non-reserved command through strict FC05."""
        try:
            command = ERGCommand(command)
        except ValueError as exc:
            raise ValueError(f"Unsupported ER-G-220-05 command: {command!r}") from exc

        response = await self.attr_client.write_coil(
            address=int(command),
            value=True,
            device_id=self.attr_device_id,
        )
        validate_fc05_response(
            response,
            address=int(command),
            value=True,
            device_id=self.attr_device_id,
            operation=f"send ER-G-220-05 {command.name.casefold()} command",
        )

    async def async_set_switch(self, switch_id: str, value: bool) -> bool:
        """Set Y1/Y2 only when its documented function parameter equals four."""
        mapping = {
            "output_y1": (13, 1118, "P118"),
            "output_y2": (14, 1120, "P120"),
        }
        if switch_id not in mapping:
            raise ValueError(f"Unknown ER-G-220-05 switch: {switch_id}")
        if type(value) is not bool:
            raise ValueError("ER-G-220-05 output state must be boolean")
        coil_address, function_address, parameter = mapping[switch_id]

        async def execute(client) -> bool:
            function_response = await client.read_holding_registers(
                address=function_address,
                count=1,
                device_id=self.attr_device_id,
            )
            self._validate_response_device_id(
                function_response,
                f"check ER-G-220-05 {parameter}",
            )
            function = validated_registers(
                function_response,
                1,
                f"check ER-G-220-05 {parameter}",
                expected_function=3,
            )[0]
            if function != 4:
                raise ModbusException(
                    f"Cannot manually control ER-G-220-05 {switch_id}: "
                    f"{parameter} must equal 4, got {function}"
                )

            response = await client.write_coil(
                address=coil_address,
                value=value,
                device_id=self.attr_device_id,
            )
            validate_fc05_response(
                response,
                address=coil_address,
                value=value,
                device_id=self.attr_device_id,
                operation=f"set ER-G-220-05 {switch_id}",
            )

            readback_response = await client.read_coils(
                address=coil_address,
                count=1,
                device_id=self.attr_device_id,
            )
            self._validate_response_device_id(
                readback_response,
                f"verify ER-G-220-05 {switch_id}",
            )
            readback = validated_bits(
                readback_response,
                1,
                f"verify ER-G-220-05 {switch_id}",
                expected_function=1,
            )[0]
            if readback != value:
                raise ModbusException(
                    f"ER-G-220-05 {switch_id} readback mismatch: "
                    f"requested {value}, got {readback}"
                )
            return readback

        serialized_executor = getattr(
            self.attr_client, "async_execute_serialized", None
        )
        if callable(serialized_executor):
            return await serialized_executor(execute)
        return await execute(self.attr_client)

    @classmethod
    def decode_runtime(cls, registers: list[int]) -> dict[str, dict]:
        """Decode one complete synthetic or physical runtime block."""
        if len(registers) != RUNTIME_REGISTER_COUNT or any(
            type(value) is not int or not 0 <= value <= 0xFFFF for value in registers
        ):
            raise ValueError(
                "ER-G-220-05 runtime must contain ten unsigned 16-bit registers"
            )

        numeric = {
            item.sensor_id: {
                "value": round(
                    registers[item.offset] * item.scale,
                    item.precision,
                ),
                "raw_register": registers[item.offset],
                "register_address": RUNTIME_BASE_ADDRESS + item.offset,
            }
            for item in NUMERIC_REGISTERS
        }
        drive_code = registers[4]
        fault_code = registers[5]
        software_word = registers[7]
        software_version = cls.decode_software_version(software_word)

        return {
            "numeric_sensors": numeric,
            "state_sensors": {
                "drive_state": cls._state(
                    DRIVE_STATES.get(drive_code, f"unknown_state_{drive_code}"),
                    drive_code,
                ),
                "fault_code": cls._state(
                    cls.decode_fault(fault_code),
                    fault_code,
                ),
                "software_version": cls._state(
                    software_version,
                    software_word,
                ),
            },
        }

    @staticmethod
    def decode_fault(code: int) -> str:
        """Decode documented faults while preserving reserved and unknown codes."""
        if code in range(1, 4):
            return f"reserved_fault_{code}"
        return FAULTS.get(code, f"unknown_fault_{code}")

    @staticmethod
    def decode_software_version(value: int) -> str:
        """Decode the documented decimal MM:YY software-version value."""
        month, year = divmod(value, 100)
        if 1 <= month <= 12:
            return f"{month:02d}.{year:02d}"
        return f"raw_0x{value:04X}"

    @staticmethod
    def _state(state: str, code: int) -> dict[str, Any]:
        return {
            "state": state,
            "primary_code": code,
            "expanded_codes": [],
            "expanded_states": [],
        }

    def _validate_response_device_id(self, response: Any, operation: str) -> None:
        for attribute in ("dev_id", "device_id", "slave_id", "unit_id"):
            actual = getattr(response, attribute, None)
            if actual is not None and actual != self.attr_device_id:
                raise ModbusException(
                    f"Wrong Modbus device id for {operation}: "
                    f"expected {self.attr_device_id}, got {actual}"
                )


EQUIPMENT_CLASSES = (ERG22005,)
