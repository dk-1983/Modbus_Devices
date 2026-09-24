"""Equipment models manufactured by ERMAN."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
import math
import time
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
    validate_fc06_response,
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


@dataclass(frozen=True, slots=True)
class NumberParameter:
    parameter: str
    name: str
    address: int
    scale: float
    minimum: float
    maximum: float
    unit: str | None = None
    dynamic_max_parameter: str | None = None


@dataclass(frozen=True, slots=True)
class SelectParameter:
    parameter: str
    name: str
    address: int
    options: tuple[str, ...]


RUNTIME_BASE_ADDRESS = 2000
RUNTIME_REGISTER_COUNT = 10
SETTINGS_REFRESH_INTERVAL = 30.0

NUMBER_PARAMETERS = (
    NumberParameter(
        "p001", "P001 Pressure setpoint", 1001, 0.01, 0, 16, "kgf/cm²", "p006"
    ),
    NumberParameter("p002", "P002 Proportional coefficient", 1002, 0.01, 0, 10),
    NumberParameter("p003", "P003 Integration time", 1003, 0.01, 0.1, 10, "s"),
    NumberParameter("p004", "P004 Start duration", 1004, 1, 0, 30, "s"),
    NumberParameter(
        "p005",
        "P005 Emergency pressure threshold",
        1005,
        0.01,
        0,
        16,
        "kgf/cm²",
        "p006",
    ),
    NumberParameter("p006", "P006 Pressure sensor limit", 1006, 0.01, 1, 16, "kgf/cm²"),
    NumberParameter("p101", "P101 Manual frequency", 1101, 0.1, 0, 50, "Hz", "p102"),
    NumberParameter("p102", "P102 Upper frequency limit", 1102, 0.1, 0, 50, "Hz"),
    NumberParameter(
        "p103", "P103 Lower frequency limit", 1103, 0.1, 0, 50, "Hz", "p102"
    ),
    NumberParameter("p104", "P104 Starting frequency", 1104, 0.1, 0, 60, "Hz"),
    NumberParameter("p105", "P105 Starting-frequency voltage", 1105, 1, 0, 100, "%"),
    NumberParameter("p106", "P106 Motor-start test frequency", 1106, 0.1, 0, 50, "Hz"),
    NumberParameter("p107", "P107 Motor-start wait time", 1107, 1, 0, 120, "s"),
    NumberParameter("p108", "P108 Leak-test period", 1108, 1, 0, 600, "s"),
    NumberParameter(
        "p109",
        "P109 Leak-detection pressure difference",
        1109,
        0.01,
        0,
        16,
        "kgf/cm²",
        "p006",
    ),
    NumberParameter("p110", "P110 Flow-test period", 1110, 1, 1, 600, "s"),
    NumberParameter(
        "p111",
        "P111 Flow-detection pressure difference",
        1111,
        0.01,
        0,
        16,
        "kgf/cm²",
        "p006",
    ),
    NumberParameter("p112", "P112 Test duration", 1112, 1, 10, 60, "s"),
    NumberParameter(
        "p113", "P113 Dry-run pressure threshold", 1113, 0.01, 0, 16, "kgf/cm²", "p006"
    ),
    NumberParameter("p114", "P114 Dry-run detection time", 1114, 1, 0, 600, "s"),
    NumberParameter(
        "p115", "P115 Start pressure difference", 1115, 0.01, 0, 16, "kgf/cm²", "p006"
    ),
    NumberParameter(
        "p116",
        "P116 Motor-start pressure difference",
        1116,
        0.01,
        0,
        16,
        "kgf/cm²",
        "p006",
    ),
    NumberParameter("p129", "P129 Current year", 1129, 1, 2001, 2101),
    NumberParameter("p133", "P133 Channel 1 duration", 1133, 1, 1, 600, "min"),
    NumberParameter("p136", "P136 Channel 2 duration", 1136, 1, 1, 600, "min"),
)

SELECT_PARAMETERS = (
    SelectParameter("p008", "P008 Main-menu mode", 1008, ("pressure", "frequency")),
    SelectParameter(
        "p100",
        "P100 Operating mode",
        1100,
        (
            "pressure_control",
            "manual_frequency",
            "rs485_frequency",
            "analog_input_frequency",
        ),
    ),
    SelectParameter(
        "p117", "P117 Start method", 1117, ("control_panel", "digital_input", "rs485")
    ),
    SelectParameter(
        "p118",
        "P118 Y1 function",
        1118,
        (
            "unused",
            "fault",
            "running",
            "set_frequency_reached",
            "modbus_control",
            "time_relay",
        ),
    ),
    SelectParameter(
        "p119", "P119 Y1 normal state", 1119, ("normally_open", "normally_closed")
    ),
    SelectParameter(
        "p120",
        "P120 Y2 function",
        1120,
        (
            "unused",
            "fault",
            "running",
            "set_frequency_reached",
            "modbus_control",
            "time_relay",
        ),
    ),
    SelectParameter(
        "p121", "P121 Y2 normal state", 1121, ("normally_open", "normally_closed")
    ),
    SelectParameter(
        "p124", "P124 Current input", 1124, ("automatic", "an1", "an2", "an1_and_an2")
    ),
    SelectParameter(
        "p125",
        "P125 Power-on state",
        1125,
        ("stopped", "restore_previous", "start_pump"),
    ),
    SelectParameter("p126", "P126 Sleep mode", 1126, ("enabled", "disabled")),
    SelectParameter("p130", "P130 Time relay", 1130, ("disabled", "enabled")),
    SelectParameter(
        "p131", "P131 Relay outputs on fault", 1131, ("keep_running", "turn_off")
    ),
)

NUMBER_BY_ID = {item.parameter: item for item in NUMBER_PARAMETERS}
SELECT_BY_ID = {item.parameter: item for item in SELECT_PARAMETERS}

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
        self.attr_platforms = [
            Platform.SENSOR,
            Platform.BUTTON,
            Platform.SWITCH,
            Platform.NUMBER,
            Platform.SELECT,
        ]
        self.attr_unique_id_prefix = None
        self.attr_device_identifier = None
        self._settings_cache: dict[str, dict] | None = None
        self._settings_refresh_at = 0.0
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

    @staticmethod
    def get_number_descriptions() -> list[dict[str, Any]]:
        """Describe protocol-scaled P parameters with manual-derived limits."""
        return [
            {
                "number_id": item.parameter,
                "name": item.name,
                "translation_key": f"erman_{item.parameter}",
                "native_min_value": item.minimum,
                "native_max_value": item.maximum,
                "native_step": item.scale,
                "native_unit_of_measurement": item.unit,
                "dynamic_max_id": item.dynamic_max_parameter,
                "icon": "mdi:tune-variant",
            }
            for item in NUMBER_PARAMETERS
        ]

    @staticmethod
    def get_select_descriptions() -> list[dict[str, Any]]:
        """Describe enumerated P parameters from the current ER-G manual."""
        return [
            {
                "select_id": item.parameter,
                "name": item.name,
                "translation_key": f"erman_{item.parameter}",
                "options": list(item.options),
                "entity_category": EntityCategory.CONFIG,
                "icon": "mdi:tune-variant",
            }
            for item in SELECT_PARAMETERS
        ]

    async def _async_get_snapshot_on(self, client) -> dict[str, dict]:
        """Read runtime and periodically refreshed configuration atomically."""
        response = await client.read_input_registers(
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
        outputs_response = await client.read_coils(
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
        if (
            self._settings_cache is None
            or time.monotonic() >= self._settings_refresh_at
        ):
            self._settings_cache = await self._read_settings_on(client)
            self._settings_refresh_at = time.monotonic() + SETTINGS_REFRESH_INTERVAL
        snapshot.update(self._settings_cache)
        return snapshot

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read one serialized ER-G snapshot."""
        executor = getattr(self.attr_client, "async_execute_serialized", None)
        if callable(executor):
            return await executor(self._async_get_snapshot_on)
        return await self._async_get_snapshot_on(self.attr_client)

    async def _read_settings_on(self, client) -> dict[str, dict]:
        blocks = ((1001, 8), (1100, 38))
        raw: dict[int, int] = {}
        for address, count in blocks:
            response = await client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.attr_device_id,
            )
            self._validate_response_device_id(response, "read ER-G-220-05 settings")
            registers = validated_registers(
                response,
                count,
                "read ER-G-220-05 settings",
                expected_function=3,
            )
            raw.update(
                (address + offset, value) for offset, value in enumerate(registers)
            )
        return {
            "numbers": {
                item.parameter: {
                    "value": round(raw[item.address] * item.scale, 2),
                    "raw_register": raw[item.address],
                }
                for item in NUMBER_PARAMETERS
            },
            "selects": {
                item.parameter: {
                    "state": (
                        item.options[raw[item.address]]
                        if raw[item.address] < len(item.options)
                        else None
                    ),
                    "raw_register": raw[item.address],
                }
                for item in SELECT_PARAMETERS
            },
        }

    async def async_set_number(self, number_id: str, value: float) -> float:
        """Write one scaled P parameter and require exact FC03 readback."""
        if number_id not in NUMBER_BY_ID:
            raise ValueError(f"Unknown ER-G-220-05 number: {number_id}")
        item = NUMBER_BY_ID[number_id]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{item.parameter.upper()} must be numeric")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"{item.parameter.upper()} must be finite")
        raw = round(value / item.scale)
        normalized = round(raw * item.scale, 2)
        if not math.isclose(value, normalized, abs_tol=item.scale / 100):
            raise ValueError(f"{item.parameter.upper()} must use step {item.scale}")

        async def execute(client) -> float:
            maximum = item.maximum
            if item.dynamic_max_parameter is not None:
                dependency = NUMBER_BY_ID[item.dynamic_max_parameter]
                response = await client.read_holding_registers(
                    address=dependency.address,
                    count=1,
                    device_id=self.attr_device_id,
                )
                self._validate_response_device_id(response, "read ER-G dependent limit")
                maximum = min(
                    maximum,
                    validated_registers(
                        response,
                        1,
                        "read ER-G dependent limit",
                        expected_function=3,
                    )[0]
                    * dependency.scale,
                )
            if not item.minimum <= normalized <= maximum:
                raise ValueError(
                    f"{item.parameter.upper()} must be {item.minimum}..{maximum}"
                )
            await self._write_register_confirmed_on(
                client, item.address, raw, item.parameter
            )
            return normalized

        return await self._execute_serialized(execute)

    async def async_set_select(self, select_id: str, option: str) -> str:
        """Write one enumerated P parameter with exact readback."""
        if select_id not in SELECT_BY_ID:
            raise ValueError(f"Unknown ER-G-220-05 select: {select_id}")
        item = SELECT_BY_ID[select_id]
        if option not in item.options:
            raise ValueError(f"Unsupported {item.parameter.upper()} option: {option}")
        raw = item.options.index(option)

        async def execute(client) -> str:
            await self._write_register_confirmed_on(
                client, item.address, raw, item.parameter
            )
            return option

        return await self._execute_serialized(execute)

    async def _write_register_confirmed_on(
        self, client, address: int, value: int, parameter: str
    ) -> None:
        response = await client.write_register(
            address=address,
            value=value,
            device_id=self.attr_device_id,
        )
        validate_fc06_response(
            response,
            address=address,
            value=value,
            operation=f"set ER-G-220-05 {parameter.upper()}",
            device_id=self.attr_device_id,
        )
        readback_response = await client.read_holding_registers(
            address=address,
            count=1,
            device_id=self.attr_device_id,
        )
        self._validate_response_device_id(readback_response, f"verify {parameter}")
        actual = validated_registers(
            readback_response,
            1,
            f"verify ER-G-220-05 {parameter.upper()}",
            expected_function=3,
        )[0]
        if actual != value:
            raise ModbusException(
                f"ER-G-220-05 {parameter.upper()} readback mismatch: "
                f"requested {value}, got {actual}"
            )
        self._settings_refresh_at = 0.0

    async def _execute_serialized(self, operation):
        executor = getattr(self.attr_client, "async_execute_serialized", None)
        if callable(executor):
            return await executor(operation)
        return await operation(self.attr_client)

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
