"""Equipment models manufactured by Zuked."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from custom_components.modbus_devices.modbus_validation import validated_registers
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTime,
)


@dataclass(frozen=True, slots=True)
class U0Register:
    """One monitoring word documented by manual XM-H0127 V1.4."""

    parameter: str
    address: int
    name: str
    scale: float = 1.0
    unit: str | None = None
    exposed: bool = False
    category: EntityCategory | None = None


U0_REGISTERS = (
    U0Register("U0-00", 0x7000, "Running frequency", 0.01, UnitOfFrequency.HERTZ, True),
    U0Register("U0-01", 0x7001, "Set frequency", 0.01, UnitOfFrequency.HERTZ, True),
    U0Register("U0-02", 0x7002, "Bus voltage", 0.1, UnitOfElectricPotential.VOLT, True),
    U0Register(
        "U0-03", 0x7003, "Output voltage", 1, UnitOfElectricPotential.VOLT, True
    ),
    # The scan says "Output power (A)".  Its ampere unit, 0.01 A resolution,
    # and adjacent U0-05 power word make output current the only coherent reading.
    U0Register(
        "U0-04", 0x7004, "Output current", 0.01, UnitOfElectricCurrent.AMPERE, True
    ),
    U0Register("U0-05", 0x7005, "Output power", 0.1, UnitOfPower.KILO_WATT, True),
    U0Register("U0-06", 0x7006, "Output torque", 0.1, "%", True),
    U0Register("U0-07", 0x7007, "DI input status", category=EntityCategory.DIAGNOSTIC),
    U0Register("U0-08", 0x7008, "Retain"),
    U0Register("U0-09", 0x7009, "AI1 voltage/current", 0.01),
    U0Register("U0-10", 0x700A, "AI2 voltage", 0.01, UnitOfElectricPotential.VOLT),
    U0Register(
        "U0-11",
        0x700B,
        "AI3 keypad potentiometer voltage",
        0.01,
        UnitOfElectricPotential.VOLT,
    ),
    U0Register("U0-12", 0x700C, "Count"),
    U0Register("U0-13", 0x700D, "Length value"),
    U0Register("U0-14", 0x700E, "Load speed", 1, "rpm"),
    U0Register("U0-15", 0x700F, "PID setting"),
    U0Register("U0-16", 0x7010, "PID feedback value"),
    U0Register("U0-17", 0x7011, "PLC stage"),
    U0Register("U0-18", 0x7012, "Input pulse frequency", 0.01, UnitOfFrequency.HERTZ),
    U0Register("U0-19", 0x7013, "Feedback speed", 0.01, UnitOfFrequency.HERTZ),
    U0Register("U0-20", 0x7014, "Remaining running time", 0.1, UnitOfTime.MINUTES),
    U0Register("U0-21", 0x7015, "AI1 before correction", 0.001),
    U0Register(
        "U0-22", 0x7016, "AI2 before correction", 0.001, UnitOfElectricPotential.VOLT
    ),
    U0Register(
        "U0-23", 0x7017, "AI3 before correction", 0.001, UnitOfElectricPotential.VOLT
    ),
    U0Register("U0-24", 0x7018, "Linear speed", 1, "m/min"),
    U0Register(
        "U0-25",
        0x7019,
        "Current power-on time",
        1,
        UnitOfTime.MINUTES,
        True,
        EntityCategory.DIAGNOSTIC,
    ),
    U0Register(
        "U0-26",
        0x701A,
        "Current running time",
        0.1,
        UnitOfTime.MINUTES,
        True,
        EntityCategory.DIAGNOSTIC,
    ),
    U0Register("U0-27", 0x701B, "Input pulse frequency", 1, UnitOfFrequency.HERTZ),
    U0Register("U0-28", 0x701C, "Communication set value", 0.01, "%"),
    U0Register(
        "U0-30", 0x701E, "Primary frequency display", 0.01, UnitOfFrequency.HERTZ
    ),
    U0Register(
        "U0-31", 0x701F, "Auxiliary frequency display", 0.01, UnitOfFrequency.HERTZ
    ),
    U0Register("U0-32", 0x7020, "Memory address value"),
    U0Register("U0-35", 0x7023, "Target torque", 0.1, "%"),
    U0Register("U0-37", 0x7025, "Power factor angle", 0.1, "°"),
    U0Register("U0-39", 0x7027, "Retain"),
    U0Register("U0-40", 0x7028, "Retain"),
    U0Register("U0-41", 0x7029, "Intuitive DI input status"),
    U0Register("U0-42", 0x702A, "Retain"),
    U0Register("U0-43", 0x702B, "DI function status 1"),
    U0Register("U0-44", 0x702C, "DI function status 2"),
    U0Register(
        "U0-45",
        0x702D,
        "Fault information",
        exposed=True,
        category=EntityCategory.DIAGNOSTIC,
    ),
    U0Register("U0-59", 0x703B, "Set frequency", 0.01, "%"),
    U0Register("U0-60", 0x703C, "Running frequency", 0.01, "%"),
    U0Register("U0-61", 0x703D, "Drive status", exposed=True),
    U0Register(
        "U0-62",
        0x703E,
        "Current fault code",
        exposed=True,
        category=EntityCategory.DIAGNOSTIC,
    ),
    U0Register("U0-65", 0x7041, "Torque upper limit", 0.1, "%"),
)

U0_BY_PARAMETER = {register.parameter: register for register in U0_REGISTERS}

FAULTS = {
    2: "overcurrent_during_acceleration",
    3: "overcurrent_during_deceleration",
    4: "overcurrent_at_constant_speed",
    5: "overvoltage_during_acceleration",
    6: "overvoltage_during_deceleration",
    7: "overvoltage_at_constant_speed",
    8: "control_power_failure",
    9: "undervoltage",
    10: "drive_overload",
    11: "motor_overload",
    13: "output_phase_loss",
    14: "module_overheat",
    15: "external_equipment_fault",
    16: "communication_fault",
    17: "contactor_fault",
    18: "current_detection_fault",
    19: "motor_tuning_fault",
    21: "eeprom_read_write_fault",
    23: "short_circuit_to_ground",
    26: "cumulative_running_time_reached",
    27: "user_defined_fault_1",
    28: "user_defined_fault_2",
    29: "cumulative_power_on_time_reached",
    30: "load_drop_fault",
    31: "pid_feedback_loss_during_running",
    40: "cycle_by_cycle_current_limiting_fault",
    41: "motor_switching_fault_during_running",
    42: "speed_deviation_too_large",
    43: "motor_overspeed",
    55: "slave_fault_in_master_slave_control",
    64: "module_overcurrent_during_acceleration",
    65: "module_overcurrent_during_deceleration",
    66: "module_overcurrent_at_constant_speed",
}

NUMERIC_PARAMETERS = tuple(
    item.parameter
    for item in U0_REGISTERS
    if item.exposed and item.parameter not in {"U0-45", "U0-61", "U0-62"}
)


class Zuked3104S1:
    """Zuked 310-4.0S1 general-purpose AC drive."""

    equipment_manufacturer = "Zuked"
    equipment_model = "310-4.0S1"
    uses_stable_entry_identity = True
    documented_register_base = 0x7000
    monitoring_read_contract_verified = True

    def __init__(self, client, device_id) -> None:
        """Initialize a read-only drive model without polling or writing."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = self.equipment_manufacturer
        self.attr_model_name = self.equipment_model
        self.attr_description = "General-purpose AC drive"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms = [Platform.SENSOR]
        self.attr_unique_id_prefix = None
        self.attr_device_identifier = None
        self.attr_device_metadata = {
            "manual": "XM-H0127 V1.4 (2023-09-23)",
            "polling_contract": "FC03 direct PDU addresses; hardware verified",
            "writes": "not supported",
        }

    async def data_init(self) -> bool:
        """Initialize local metadata without touching the drive."""
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only runtime identity values actually available."""
        return {
            "device_type": None,
            "serial_number": None,
            "hardware_version": None,
            "software_version": None,
        }

    @staticmethod
    def get_numeric_sensor_descriptions() -> list[dict[str, Any]]:
        """Describe the selected useful U0 engineering values."""
        descriptions = []
        for parameter in NUMERIC_PARAMETERS:
            item = U0_BY_PARAMETER[parameter]
            device_class = None
            if item.unit == UnitOfFrequency.HERTZ:
                device_class = SensorDeviceClass.FREQUENCY
            elif item.unit == UnitOfElectricPotential.VOLT:
                device_class = SensorDeviceClass.VOLTAGE
            elif item.unit == UnitOfElectricCurrent.AMPERE:
                device_class = SensorDeviceClass.CURRENT
            elif item.unit == UnitOfPower.KILO_WATT:
                device_class = SensorDeviceClass.POWER
            elif item.unit == UnitOfTime.MINUTES:
                device_class = SensorDeviceClass.DURATION
            descriptions.append(
                {
                    "sensor_id": Zuked3104S1._sensor_id(item),
                    "name": item.name,
                    "device_class": device_class,
                    "state_class": SensorStateClass.MEASUREMENT,
                    "unit": item.unit,
                    "precision": Zuked3104S1._precision(item.scale),
                    "entity_category": item.category,
                    "icon": Zuked3104S1._numeric_icon(item),
                }
            )
        return descriptions

    @staticmethod
    def get_state_sensor_descriptions() -> list[dict[str, Any]]:
        """Describe lossless status and fault words."""
        return [
            {
                "sensor_id": "drive_status",
                "name": "Drive status",
                "icon": "mdi:engine",
                "unknown_state_icon": "mdi:help-circle-outline",
            },
            {
                "sensor_id": "fault_information",
                "name": "Fault information",
                "icon": "mdi:alert-circle-outline",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
            {
                "sensor_id": "current_fault_code",
                "name": "Current fault code",
                "icon": "mdi:alert-circle",
                "state_icons": dict.fromkeys(FAULTS.values(), "mdi:alert-circle"),
                "unknown_state_icon": "mdi:help-circle-outline",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read one conservative, hardware-verified U0 snapshot."""
        raw = await self._read_documented_words()
        return self.decode_documented_snapshot(raw)

    async def _read_documented_words(self) -> dict[str, int]:
        """Read the verified core block and three isolated diagnostic words."""
        core = await self._read_holding_words(0x7000, 7, "U0-00..U0-06")
        raw = {f"U0-{offset:02d}": value for offset, value in enumerate(core)}
        isolated = (
            *(parameter for parameter in NUMERIC_PARAMETERS if parameter not in raw),
            "U0-45",
            "U0-61",
            "U0-62",
        )
        for parameter in isolated:
            register = U0_BY_PARAMETER[parameter]
            raw[parameter] = (
                await self._read_holding_words(
                    register.address,
                    1,
                    parameter,
                )
            )[0]
        return raw

    async def _read_holding_words(
        self, address: int, count: int, operation: str
    ) -> list[int]:
        """Read and strictly validate documented FC03 holding registers."""
        response = await self.attr_client.read_holding_registers(
            address=address,
            count=count,
            device_id=self.attr_device_id,
        )
        return validated_registers(
            response,
            count,
            f"Zuked 310-4.0S1 {operation}",
            expected_function=3,
        )

    @classmethod
    def decode_documented_snapshot(cls, raw: dict[str, int]) -> dict[str, dict]:
        """Decode a complete synthetic or hardware-validated U0 snapshot."""
        required = {*NUMERIC_PARAMETERS, "U0-45", "U0-61", "U0-62"}
        if raw.keys() != required or any(
            type(value) is not int or not 0 <= value <= 0xFFFF for value in raw.values()
        ):
            raise ValueError(
                "Zuked snapshot must contain every exposed unsigned U0 word"
            )
        numeric = {}
        for parameter in NUMERIC_PARAMETERS:
            item = U0_BY_PARAMETER[parameter]
            numeric[cls._sensor_id(item)] = {
                "value": round(raw[parameter] * item.scale, cls._precision(item.scale)),
                "raw_register": raw[parameter],
                "register_address": item.address,
                "parameter_kind": parameter,
            }
        return {
            "numeric_sensors": numeric,
            "state_sensors": {
                "drive_status": cls._state(f"unknown_{raw['U0-61']}", raw["U0-61"]),
                "fault_information": cls._state(
                    f"fault_information_{raw['U0-45']}", raw["U0-45"]
                ),
                "current_fault_code": cls._state(
                    cls.decode_fault(raw["U0-62"]), raw["U0-62"]
                ),
            },
        }

    @staticmethod
    def decode_fault(code: int) -> str:
        """Decode only ErrXX values printed by XM-H0127 V1.4."""
        return FAULTS.get(code, f"unknown_fault_{code}")

    @staticmethod
    def _state(state: str, code: int) -> dict[str, Any]:
        return {
            "state": state,
            "primary_code": code,
            "expanded_codes": [],
            "expanded_states": [],
        }

    @staticmethod
    def _sensor_id(item: U0Register) -> str:
        return item.name.casefold().replace("-", "_").replace(" ", "_")

    @staticmethod
    def _precision(scale: float) -> int:
        return {1: 0, 0.1: 1, 0.01: 2, 0.001: 3}[scale]

    @staticmethod
    def _numeric_icon(item: U0Register) -> str | None:
        return {
            UnitOfFrequency.HERTZ: "mdi:sine-wave",
            UnitOfElectricPotential.VOLT: "mdi:flash",
            UnitOfElectricCurrent.AMPERE: "mdi:current-ac",
            UnitOfPower.KILO_WATT: "mdi:lightning-bolt",
            UnitOfTime.MINUTES: "mdi:timer-outline",
            "%": "mdi:gauge",
        }.get(item.unit)


EQUIPMENT_CLASSES = (Zuked3104S1,)
