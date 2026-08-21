"""Equipment models manufactured by Dyna Drive."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any

from ..modbus_validation import validate_fc06_response, validated_registers

from homeassistant.const import EntityCategory, Platform


class DN310Command(IntEnum):
    """Documented volatile commands for register 0x2000."""

    FORWARD_RUN = 0x0001
    REVERSE_RUN = 0x0002
    COAST_STOP = 0x0005
    DECELERATE_STOP = 0x0006
    FAULT_RESET = 0x0007


RUNNING_STATUS = {
    0x0001: "forward_run",
    0x0002: "reverse_run",
    0x0003: "stop",
}

FAULTS = {
    0x0000: "no_fault",
    0x0002: "overcurrent_during_acceleration",
    0x0003: "overcurrent_during_deceleration",
    0x0004: "overcurrent_at_constant_speed",
    0x0005: "overvoltage_during_acceleration",
    0x0006: "overvoltage_during_deceleration",
    0x0007: "overvoltage_at_constant_speed",
    0x0008: "buffer_resistor_overload",
    0x0009: "undervoltage",
    0x000A: "inverter_overload",
    0x000B: "motor_overload",
    0x000C: "power_input_phase_loss",
    0x000D: "power_output_phase_loss",
    0x000E: "igbt_overheat",
    0x000F: "external_fault",
    0x0010: "communication_fault",
    0x0011: "contactor_fault",
    0x0012: "current_detection_fault",
    0x0013: "motor_auto_tuning_fault",
    0x0014: "encoder_pg_card_fault",
    0x0015: "parameter_read_write_fault",
    0x0016: "inverter_hardware_fault",
    0x0017: "motor_short_to_ground",
    0x001A: "accumulated_running_time_reached",
    0x001B: "user_defined_fault_1",
    0x001C: "user_defined_fault_2",
    0x001D: "accumulated_power_on_time_reached",
    0x001E: "load_lost",
    0x001F: "pid_feedback_lost_during_running",
    0x0028: "fast_current_limit_timeout",
    0x0029: "motor_switchover_error_during_running",
    0x002A: "too_large_speed_deviation",
    0x002B: "motor_overspeed",
    0x005A: "incorrect_encoder_ppr_setting",
    0x005E: "speed_feedback_error",
}

RESERVED_FAULTS = frozenset({0x0001, 0x0018, 0x0019, 0x002D, 0x005B, 0x005C})

MONITORING_REGISTERS = (
    ("running_frequency_raw", "Running frequency (raw)", 0x1001),
    ("bus_voltage_raw", "Bus voltage (raw)", 0x1002),
    ("output_voltage_raw", "Output voltage (raw)", 0x1003),
    ("output_current_raw", "Output current (raw)", 0x1004),
    ("output_power_raw", "Output power (raw)", 0x1005),
    ("output_torque_raw", "Output torque (raw)", 0x1006),
    ("running_speed_raw", "Running speed (raw)", 0x1007),
)


class DN310:
    """Dyna Drive DN310 variable-frequency drive."""

    uses_stable_entry_identity = True
    protocol = "Modbus RTU slave; FC03/FC06 word operations"
    persistent_write_ranges = ((0xF000, 0xFEFF), (0xA000, 0xACFF))
    frequency_setpoint_limitation = (
        "DN310.pdf gives conflicting 0x1000 scales (-10000..10000 and "
        "-1000..1000); writable frequency control is intentionally disabled"
    )

    def __init__(self, client, device_id) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Dyna Drive"
        self.attr_model_name = "DN310"
        self.attr_description = "Variable-frequency drive"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms = [Platform.SENSOR, Platform.BUTTON]
        self.attr_unique_id_prefix = None
        self.attr_device_identifier = None
        self.attr_device_metadata = {
            "protocol": self.protocol,
            "frequency_setpoint": self.frequency_setpoint_limitation,
            "eeprom_writes": "not supported",
            "communication_control": "P0-02=2 must be configured on the drive",
        }

    async def data_init(self) -> bool:
        await self.async_get_snapshot()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_numeric_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Return raw monitoring words whose engineering scales are undocumented."""
        return [
            {
                "sensor_id": sensor_id,
                "name": name,
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
                "entity_category": EntityCategory.DIAGNOSTIC,
            }
            for sensor_id, name, _address in MONITORING_REGISTERS
        ]

    @staticmethod
    def get_state_sensor_descriptions() -> list[dict[str, Any]]:
        return [
            {"sensor_id": "running_status", "name": "Running status"},
            {
                "sensor_id": "inverter_fault",
                "name": "Inverter fault",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
        ]

    @staticmethod
    def get_button_descriptions() -> list[dict[str, Any]]:
        return [
            {
                "button_id": "forward_run",
                "name": "Forward run",
                "command": DN310Command.FORWARD_RUN,
            },
            {
                "button_id": "reverse_run",
                "name": "Reverse run",
                "command": DN310Command.REVERSE_RUN,
            },
            {
                "button_id": "coast_stop",
                "name": "Coast stop",
                "command": DN310Command.COAST_STOP,
            },
            {
                "button_id": "decelerate_stop",
                "name": "Decelerate stop",
                "command": DN310Command.DECELERATE_STOP,
            },
            {
                "button_id": "fault_reset",
                "name": "Fault reset",
                "command": DN310Command.FAULT_RESET,
                "entity_category": EntityCategory.CONFIG,
            },
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        monitoring = await self._read_words(0x1001, 7, "monitoring block")
        status_code = (await self._read_words(0x3000, 1, "running status"))[0]
        fault_code = (await self._read_words(0x8000, 1, "current fault"))[0]

        numeric_sensors = {
            sensor_id: {
                "value": monitoring[index],
                "raw_register": monitoring[index],
                "register_address": address,
                "parameter_kind": "dn310_raw_word",
            }
            for index, (sensor_id, _name, address) in enumerate(MONITORING_REGISTERS)
        }
        return {
            "numeric_sensors": numeric_sensors,
            "state_sensors": {
                "running_status": self._state_snapshot(
                    RUNNING_STATUS.get(status_code, f"unknown_{status_code}"),
                    status_code,
                ),
                "inverter_fault": self._state_snapshot(
                    self._decode_fault(fault_code), fault_code
                ),
            },
        }

    async def async_send_command(self, command: DN310Command | int) -> None:
        try:
            command = DN310Command(command)
        except ValueError as exc:
            raise ValueError(f"Unsupported DN310 command: {command!r}") from exc

        response = await self.attr_client.write_register(
            address=0x2000,
            value=int(command),
            device_id=self.attr_device_id,
        )
        validate_fc06_response(
            response,
            address=0x2000,
            value=int(command),
            device_id=self.attr_device_id,
            operation="send DN310 command",
        )

    async def _read_words(self, address: int, count: int, operation: str) -> list[int]:
        response = await self.attr_client.read_holding_registers(
            address=address,
            count=count,
            device_id=self.attr_device_id,
        )
        return validated_registers(
            response,
            count,
            f"DN310 {operation}",
            expected_function=3,
        )

    @staticmethod
    def _state_snapshot(state: str, code: int) -> dict[str, Any]:
        return {
            "state": state,
            "primary_code": code,
            "expanded_codes": [],
            "expanded_states": [],
        }

    @staticmethod
    def _decode_fault(code: int) -> str:
        if code in FAULTS:
            return FAULTS[code]
        if code in RESERVED_FAULTS:
            return f"reserved_0x{code:04x}"
        return f"unknown_{code}"
