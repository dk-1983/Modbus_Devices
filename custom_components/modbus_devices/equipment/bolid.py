"""Классы описывают содержание каждого прибора."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from logging import getLogger
from typing import Any

from custom_components.modbus_devices.const import Config
from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusUdpClient,
)
from pymodbus.exceptions import ModbusException

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform

from ..gateway import (
    CapabilityRequirement,
    GatewayCapabilitySpec,
    GatewayType,
    ModbusDataArea,
    ObjectKind,
    ResolvedDeviceMapping,
    ResolvedObjectMapping,
)
from ..s2000_pp import (
    S2000PPRuntimeReader,
    S2000PPZoneState,
    validated_bits,
    validated_registers,
)
from .equipment import validate_write_response

_LOGGER = getLogger(__name__)


class M3000BB1020:
    """Bolid M3000-BB-1020 hw: 1.00 sw: 1.00."""

    def __init__(self, client, device_id) -> None:
        """Inicialization variables."""
        self.attr_device_id: int = device_id
        self.attr_client: (
            AsyncModbusSerialClient | AsyncModbusTcpClient | AsyncModbusUdpClient | None
        ) = client
        self.attr_manufactures_name: str = "Bolid"
        self.attr_model_name: str = "M3000-BB-1020"
        self.attr_device_type: int | None = None
        self.attr_serial_number: str | None = None
        self.attr_hardware_version: float | None = None
        self.attr_software_version: float | None = None
        self.attr_init_time: datetime | None = None
        self.attr_description: str = "Programmable relay"
        self.attr_secret: str | None = None
        self.attr_clock_iter: list[int] = list(range(1, 2))
        self.attr_platforms: list[Platform] = [
            Platform.BINARY_SENSOR,
            Platform.DATETIME,
            Platform.SWITCH,
        ]
        self.attr_in1: dict[str, Any] = {
            "input_number": 1,
            "input_number_view": 1,
            "input_type": "24 volts",
            "data_type": "discrete_input",
            "address": 0,
            "address_hex": hex(0x0000),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in2: dict[str, Any] = {
            "input_number": 2,
            "input_number_view": 2,
            "input_type": "24 volts",
            "data_type": "discrete_input",
            "address": 128,
            "address_hex": hex(0x0080),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in3: dict[str, Any] = {
            "input_number": 3,
            "input_number_view": 3,
            "input_type": "24 volts",
            "data_type": "discrete_input",
            "address": 256,
            "address_hex": hex(0x0100),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in4: dict[str, Any] = {
            "input_number": 4,
            "input_number_view": 4,
            "input_type": "24 volts",
            "data_type": "discrete_input",
            "address": 384,
            "address_hex": hex(0x0180),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in5: dict[str, Any] = {
            "input_number": 5,
            "input_number_view": 5,
            "input_type": "24 volts",
            "data_type": "discrete_input",
            "address": 512,
            "address_hex": hex(0x0200),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in6: dict[str, Any] = {
            "input_number": 6,
            "input_number_view": 6,
            "input_type": "24 volts",
            "data_type": "discrete_input",
            "address": 640,
            "address_hex": hex(0x0280),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }

        self.attr_in7: dict[str, Any] = {
            "input_number": 7,
            "input_number_view": 1,
            "input_type": "220 volts",
            "data_type": "discrete_input",
            "address": 768,
            "address_hex": hex(0x0300),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in8: dict[str, Any] = {
            "input_number": 8,
            "input_number_view": 2,
            "input_type": "220 volts",
            "data_type": "discrete_input",
            "address": 896,
            "address_hex": hex(0x0380),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in9: dict[str, Any] = {
            "input_number": 9,
            "input_number_view": 3,
            "input_type": "220 volts",
            "data_type": "discrete_input",
            "address": 1024,
            "address_hex": hex(0x0400),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in10: dict[str, Any] = {
            "input_number": 10,
            "input_number_view": 4,
            "input_type": "220 volts",
            "data_type": "discrete_input",
            "address": 1152,
            "address_hex": hex(0x0480),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in11: dict[str, Any] = {
            "input_number": 11,
            "input_number_view": 5,
            "input_type": "220 volts",
            "data_type": "discrete_input",
            "address": 1280,
            "address_hex": hex(0x0500),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }
        self.attr_in12: dict[str, Any] = {
            "input_number": 12,
            "input_number_view": 6,
            "input_type": "220 volts",
            "data_type": "discrete_input",
            "address": 1408,
            "address_hex": hex(0x0580),
            "state": None,
            "func_mode": [2],
            "device_class": BinarySensorDeviceClass.POWER,
            "icon_on": "mdi:power-on",
            "icon_off": "mdi:power-off",
        }

        self.attr_out1: dict[str, Any] = {
            "out_number": 1,
            "out_number_view": 1,
            "out_type": "relay",
            "data_type": "coil_register",
            "address": 4096,
            "address_hex": hex(0x1000),
            "state": None,
            "func_mode": [1, 5, 15],
            "device_class": SwitchDeviceClass.SWITCH,
            "icon_on": "mdi:toggle-switch-variant",
            "icon_off": "mdi:toggle-switch-variant-off",
        }
        self.attr_out2: dict[str, Any] = {
            "out_number": 2,
            "out_number_view": 2,
            "out_type": "relay",
            "data_type": "coil_register",
            "address": 4224,
            "address_hex": hex(0x1080),
            "state": None,
            "func_mode": [1, 5, 15],
            "device_class": SwitchDeviceClass.SWITCH,
            "icon_on": "mdi:toggle-switch-variant",
            "icon_off": "mdi:toggle-switch-variant-off",
        }
        self.attr_out3: dict[str, Any] = {
            "out_number": 3,
            "out_number_view": 3,
            "out_type": "relay",
            "data_type": "coil_register",
            "address": 4352,
            "address_hex": hex(0x1100),
            "state": None,
            "func_mode": [1, 5, 15],
            "device_class": SwitchDeviceClass.SWITCH,
            "icon_on": "mdi:toggle-switch-variant",
            "icon_off": "mdi:toggle-switch-variant-off",
        }
        self.attr_out4: dict[str, Any] = {
            "out_number": 4,
            "out_number_view": 4,
            "out_type": "relay",
            "data_type": "coil_register",
            "address": 4480,
            "address_hex": hex(0x1180),
            "state": None,
            "func_mode": [1, 5, 15],
            "device_class": SwitchDeviceClass.SWITCH,
            "icon_on": "mdi:toggle-switch-variant",
            "icon_off": "mdi:toggle-switch-variant-off",
        }
        self.attr_out5: dict[str, Any] = {
            "out_number": 5,
            "out_number_view": 5,
            "out_type": "relay",
            "data_type": "coil_register",
            "address": 4608,
            "address_hex": hex(0x1200),
            "state": None,
            "func_mode": [1, 5, 15],
            "device_class": SwitchDeviceClass.SWITCH,
            "icon_on": "mdi:toggle-switch-variant",
            "icon_off": "mdi:toggle-switch-variant-off",
        }
        self.attr_out6: dict[str, Any] = {
            "out_number": 6,
            "out_number_view": 6,
            "out_type": "relay",
            "data_type": "coil_register",
            "address": 4736,
            "address_hex": hex(0x1280),
            "state": None,
            "func_mode": [1, 5, 15],
            "device_class": SwitchDeviceClass.SWITCH,
            "icon_on": "mdi:toggle-switch-variant",
            "icon_off": "mdi:toggle-switch-variant-off",
        }

    async def data_init(self) -> bool:
        """Инициализирует все свойства класса."""
        await self.get_device_info()
        await self.set_time()
        await self.get_inputs()
        await self.get_outputs()
        return True

    async def get_device_info(self) -> list:
        """Получает информацию о текущем контроллере."""
        init = (
            await self.attr_client.read_holding_registers(
                address=60001, count=6, device_id=self.attr_device_id
            )
        ).registers
        self.attr_device_type = init[0]
        self.attr_software_version = init[1]
        self.attr_hardware_version = init[2]
        self.attr_serial_number = hex(init[3])[2:] + hex(init[4])[2:] + hex(init[5])[2:]
        return init

    async def set_time(self, value: datetime | None = None) -> datetime:
        """Устанавливает дату и время в контроллер."""
        time_values: list = []
        value = value or datetime.now()
        for num in range(6):
            time_values.append(value.timetuple()[num])
        response = await self.attr_client.write_registers(
            address=60007, values=time_values, device_id=self.attr_device_id
        )
        validate_write_response(response, "set M3000-BB-1020 time")
        self.attr_init_time = value
        return self.attr_init_time

    async def get_time(self) -> datetime:
        """Получает дату и время установленные в контроллере."""
        responce = await self.attr_client.read_holding_registers(
            address=60007, count=6, device_id=self.attr_device_id
        )
        return datetime(*responce.registers).replace(
            tzinfo=timezone(timedelta(hours=Config.TIME_ZONE)), microsecond=0
        )

    async def get_input(self, input: int) -> dict[str, Any]:
        """Получает состояние одного входа контроллера."""
        attr = getattr(self, f"attr_in{input}")
        attr["state"] = (
            await self.attr_client.read_discrete_inputs(
                address=attr["address"], count=1, device_id=self.attr_device_id
            )
        ).bits[0]
        setattr(self, f"attr_in{input}", attr)
        return getattr(self, f"attr_in{input}")

    async def get_inputs(self, inputs: list[int] | None = None) -> list[dict[str, Any]]:
        """Получает состояние всех или нескольких входов контроллера."""
        data: list[dict[str, Any]] = []
        inputs = (inputs, (list(range(1, 13))))[inputs is None]
        for in_put in inputs:
            attr = getattr(self, f"attr_in{in_put}")
            attr["state"] = (
                await self.attr_client.read_discrete_inputs(
                    address=attr["address"], count=1, device_id=self.attr_device_id
                )
            ).bits[0]
            setattr(self, f"attr_in{in_put}", attr)
            data.append(getattr(self, f"attr_in{in_put}"))
        return data

    async def get_output(self, out: int) -> dict[str, Any]:
        """Получает состояние одного выхода номер 1-6."""
        attr = getattr(self, f"attr_out{out}")
        attr["state"] = (
            await self.attr_client.read_coils(
                address=attr["address"], count=1, device_id=self.attr_device_id
            )
        ).bits[0]
        setattr(self, f"attr_out{out}", attr)
        return getattr(self, f"attr_out{out}")

    async def get_outputs(self, outputs: list | None = None):
        """Получение нескольких или всех состояний выходов контроллера."""
        data: list[dict[str, Any]] = []
        outputs = (outputs, (list(range(1, 7))))[outputs is None]
        for output in outputs:
            attr = getattr(self, f"attr_out{output}")
            attr["state"] = (
                await self.attr_client.read_coils(
                    address=attr["address"], count=1, device_id=self.attr_device_id
                )
            ).bits[0]
            setattr(self, f"attr_out{output}", attr)
            data.append(getattr(self, f"attr_out{output}"))
        return data

    async def set_output(self, output: int, value: bool) -> dict[str, Any]:
        """Устанавливает состояние одного выхода номер 1-6."""
        attr = getattr(self, f"attr_out{output}")
        response = await self.attr_client.write_coil(
            address=attr["address"], value=value, device_id=self.attr_device_id
        )
        validate_write_response(response, f"set M3000-BB-1020 output {output}")
        attr["state"] = bool(value)
        setattr(self, f"attr_out{output}", attr)
        return getattr(self, f"attr_out{output}")

    async def set_outputs(
        self, outputs: list[int] | None = None, values: list[bool] | None = None
    ):
        """Устанавливает все или некоторые выходы контроллера в состояние values."""
        if values is None:
            return False
        data: list[dict[str, Any]] = []
        outputs = (outputs, (list(range(1, 7))))[outputs is None]
        for output, index in zip(outputs, range(len(outputs))):
            try:
                if not isinstance(values[index], (bool, int)):
                    raise TypeError
                attr = getattr(self, f"attr_out{output}")
                response = await self.attr_client.write_coil(
                    address=attr["address"],
                    value=values[index],
                    device_id=self.attr_device_id,
                )
                validate_write_response(
                    response,
                    f"set M3000-BB-1020 output {output}",
                )
                attr["state"] = bool(values[index])
                setattr(self, f"attr_out{output}", attr)
                data.append(getattr(self, f"attr_out{output}"))
            except IndexError:
                break
        return data

    def __repr__(self) -> str:
        """Representation info of object."""
        cls = self.__class__.__name__
        return (
            f"class: {cls}, "
            f"init_time: {self.attr_init_time}, "
            f"device_id: {self.attr_device_id}, "
            f"manufactures_name: {self.attr_manufactures_name}, "
            f"device_type: {self.attr_device_type}, "
            f"model_name: {self.attr_model_name}, "
            f"serial_number: {self.attr_serial_number}, "
            f"hardware_version: {self.attr_hardware_version}, "
            f"software_version: {self.attr_software_version}, "
            f"secret: {self.attr_secret}, "
            f"in1: {self.attr_in1['state']}, "
            f"in2: {self.attr_in2['state']}, "
            f"in3: {self.attr_in3['state']}, "
            f"in4: {self.attr_in4['state']}, "
            f"in5: {self.attr_in5['state']}, "
            f"in6: {self.attr_in6['state']}, "
            f"in7: {self.attr_in7['state']}, "
            f"in8: {self.attr_in8['state']}, "
            f"in9: {self.attr_in9['state']}, "
            f"in10: {self.attr_in10['state']}, "
            f"in11: {self.attr_in11['state']}, "
            f"in12: {self.attr_in12['state']}, "
            f"out1: {self.attr_out1['state']}, "
            f"out2: {self.attr_out2['state']}, "
            f"out3: {self.attr_out3['state']}, "
            f"out4: {self.attr_out4['state']}, "
            f"out5: {self.attr_out5['state']}, "
            f"out6: {self.attr_out6['state']}, "
            f"description: {self.attr_description}"
        )


class S2000PP:
    """Bolid С2000-ПП protocol converter, firmware 3.xx."""

    SERVICE_INFO_ADDRESS = 46152
    DEVICE_TYPE = 36
    DIAGNOSTIC_START_ADDRESS = 8

    def __init__(self, client, device_id) -> None:
        """Initialize documented gateway metadata and diagnostics."""
        self.attr_device_id: int = device_id
        self.attr_client: (
            AsyncModbusSerialClient
            | AsyncModbusTcpClient
            | AsyncModbusUdpClient
            | None
        ) = client
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "С2000-ПП"
        self.attr_description = "Orion to Modbus protocol converter"
        self.attr_device_type: int | None = None
        self.attr_serial_number: str | None = None
        self.attr_hardware_version: str | None = None
        self.attr_software_version: str | None = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms: list[Platform] = [Platform.BINARY_SENSOR]

        diagnostics = (
            (
                1,
                "Orion master mode",
                None,
                "mdi:server-network",
                "mdi:server-network-off",
            ),
            (
                2,
                "Orion master communication",
                BinarySensorDeviceClass.CONNECTIVITY,
                "mdi:lan-connect",
                "mdi:lan-disconnect",
            ),
            (
                3,
                "Enclosure tamper",
                BinarySensorDeviceClass.TAMPER,
                "mdi:shield-lock-open",
                "mdi:shield-lock",
            ),
            (
                4,
                "Power fault",
                BinarySensorDeviceClass.PROBLEM,
                "mdi:power-plug-off",
                "mdi:power-plug",
            ),
        )
        for number, name, device_class, icon_on, icon_off in diagnostics:
            setattr(
                self,
                f"attr_in{number}",
                {
                    "input_number": number,
                    "input_number_view": number,
                    "input_type": name,
                    "data_type": "discrete_input",
                    "address": self.DIAGNOSTIC_START_ADDRESS + number - 1,
                    "state": None,
                    "func_mode": [2],
                    "device_class": device_class,
                    "icon_on": icon_on,
                    "icon_off": icon_off,
                },
            )

    async def data_init(self) -> bool:
        """Read documented service information and diagnostics."""
        await self.get_device_info()
        await self.get_inputs()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, int | str | None]:
        """Read documented type and firmware version via FC03."""
        response = await self.attr_client.read_holding_registers(
            address=self.SERVICE_INFO_ADDRESS,
            count=2,
            device_id=self.attr_device_id,
        )
        registers = validated_registers(
            response,
            2,
            "read S2000-PP type and firmware version",
        )
        if registers[0] != self.DEVICE_TYPE:
            raise ModbusException(
                f"Unexpected device type at S2000-PP endpoint: {registers[0]}"
            )
        self.attr_device_type = registers[0]
        self.attr_software_version = (
            f"{registers[1] // 100}.{registers[1] % 100:02d}"
        )
        return {
            "device_type": self.attr_device_type,
            "software_version": self.attr_software_version,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
        }

    async def get_inputs(self) -> list[dict[str, Any]]:
        """Read all four documented gateway diagnostics in one FC02 request."""
        response = await self.attr_client.read_discrete_inputs(
            address=self.DIAGNOSTIC_START_ADDRESS,
            count=4,
            device_id=self.attr_device_id,
        )
        states = validated_bits(
            response,
            4,
            "read S2000-PP diagnostics",
        )
        result = []
        for number, state in enumerate(states, start=1):
            item = getattr(self, f"attr_in{number}")
            item["state"] = state
            result.append(item)
        return result


class C2000KPB:
    """Bolid C2000-KPB described by the version 3.04 documentation."""

    required_gateway = GatewayType.S2000_PP

    capability_requirements = tuple(
        GatewayCapabilitySpec(
            key=f"output_{number}",
            name=f"Output {number}",
            object_kind=ObjectKind.RELAY,
            local_object_number=number,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        )
        for number in range(1, 7)
    ) + tuple(
        GatewayCapabilitySpec(
            key=f"output_{number}_circuit",
            name=f"Output {number} circuit state",
            object_kind=ObjectKind.ZONE,
            local_object_number=number,
            zone_type=2,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        )
        for number in range(1, 7)
    ) + tuple(
        GatewayCapabilitySpec(
            key=f"technological_input_{number}",
            name=f"Technological input {number}",
            object_kind=ObjectKind.ZONE,
            local_object_number=number,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        )
        for number in range(1, 3)
    ) + (
        GatewayCapabilitySpec(
            key="device_state",
            name="Device state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            zone_type=3,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
    )

    STATE_NAMES = {
        1: "mains_restored",
        2: "mains_fault",
        17: "arming_failed",
        22: "control_restored",
        24: "armed",
        35: "technological_input_restored",
        36: "technological_input_violated",
        38: "technological_input_violated_2",
        39: "equipment_normal",
        41: "equipment_fault",
        45: "input_open_circuit",
        71: "level_low",
        72: "level_normal",
        74: "level_high",
        75: "level_critical_high",
        76: "temperature_high",
        77: "level_critical_low",
        78: "temperature_normal",
        82: "temperature_sensor_fault",
        83: "temperature_sensor_restored",
        109: "disarmed",
        111: "input_control_enabled",
        112: "input_control_disabled",
        113: "output_control_enabled",
        114: "output_control_disabled",
        117: "disarmed_input_restored",
        118: "input_alarm",
        119: "disarmed_input_violated",
        121: "output_open_circuit",
        122: "output_short_circuit",
        123: "output_circuit_restored",
        126: "output_communication_lost",
        127: "output_communication_restored",
        128: "output_state_changed",
        130: "pump_enabled",
        131: "pump_disabled",
        135: "automatic_test_failed",
        138: "activation_failed",
        140: "internal_test_started",
        149: "enclosure_tamper",
        152: "enclosure_tamper_restored",
        165: "input_parameter_error",
        187: "input_communication_lost",
        188: "input_communication_restored",
        194: "power_overload",
        195: "power_overload_restored",
        198: "power_fault",
        199: "power_restored",
        200: "battery_restored",
        202: "battery_fault",
        203: "device_restarted",
        204: "maintenance_required",
        206: "temperature_low",
        211: "battery_low",
        212: "reserve_battery_low",
        213: "reserve_battery_restored",
        214: "input_short_circuit",
        250: "device_communication_lost",
        251: "device_communication_restored",
    }

    def __init__(self, client, device_id) -> None:
        """Initialization variables."""

        self.attr_device_id: int = device_id

        self.attr_client: (
            AsyncModbusSerialClient
            | AsyncModbusTcpClient
            | AsyncModbusUdpClient
            | None
        ) = client

        self.attr_manufactures_name: str = "Bolid"
        self.attr_model_name: str = "С2000-КПБ"

        self.attr_device_type: int | None = None
        self.attr_serial_number: str | None = None
        self.attr_hardware_version: str | None = None
        self.attr_software_version: str | None = None

        self.attr_init_time: datetime | None = None

        self.attr_output_amount: int = 6
        self.attr_input_amount: int = 2

        self.attr_description: str = "Control and launch unit"

        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self._relay_mappings: dict[int, ResolvedObjectMapping] = {}
        self._zone_mappings: dict[str, ResolvedObjectMapping] = {}

        #
        # Outputs
        #

        for num in range(1, 7):

            setattr(
                self,
                f"attr_out{num}",
                {
                    "out_number": num,
                    "out_number_view": num,
                    "out_type": "Output",
                    "data_type": "coil_register",
                    "address": None,
                    "address_hex": None,
                    "state": None,
                    "func_mode": [1, 5, 15],
                    "device_class": SwitchDeviceClass.SWITCH,
                    "icon_on": "mdi:toggle-switch-variant",
                    "icon_off": "mdi:toggle-switch-variant-off",
                },
            )

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return the complete model capability declaration."""
        return cls.capability_requirements

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply the configured subset of model capabilities."""
        if mapping.identity.model != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000-KPB")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000-KPB")

        self.attr_gateway_mapping = mapping
        specs = {
            (spec.object_kind, spec.local_object_number, spec.zone_type): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.object_kind, item.local_object_number, zone_type))
            if spec is None:
                raise ValueError("Mapping contains an unsupported C2000-KPB object")
            expected_area = (
                ModbusDataArea.COIL
                if item.object_kind is ObjectKind.RELAY
                else ModbusDataArea.HOLDING_REGISTER
            )
            if item.data_area is not expected_area:
                raise ValueError("C2000-KPB mapping uses an invalid Modbus data area")
            if spec.key in resolved:
                raise ValueError("Duplicate C2000-KPB capability mapping")
            resolved[spec.key] = item

        missing_required = {
            spec.key
            for spec in self.capability_requirements
            if spec.requirement is CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION
            and spec.key not in resolved
        }
        if missing_required:
            raise ValueError(f"Missing required C2000-KPB mappings: {missing_required}")

        self.attr_device_identifier = mapping.identity.stable_id
        self.attr_unique_id_prefix = mapping.identity.stable_id
        self._relay_mappings = {
            item.local_object_number: item
            for key, item in resolved.items()
            if key.startswith("output_") and not key.endswith("_circuit")
        }
        self._zone_mappings = {
            key: item for key, item in resolved.items() if item.object_kind is ObjectKind.ZONE
        }

        for number, item in self._relay_mappings.items():
            output = getattr(self, f"attr_out{number}")
            output["address"] = item.modbus_address
            output["address_hex"] = hex(item.modbus_address)
        if self._relay_mappings:
            self.attr_platforms.append(Platform.SWITCH)
        if self._zone_mappings:
            self.attr_platforms.append(Platform.SENSOR)

    async def data_init(self) -> bool:
        """Initialize device data."""
        if self.attr_gateway_mapping is None:
            raise ValueError("C2000-KPB requires a validated S2000-PP mapping")
        await self.get_device_info()
        await self.async_get_snapshot()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only service fields available through the documented path."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_output_descriptions(self) -> list[dict[str, Any]]:
        """Return descriptions only for relays configured in this gateway."""
        return [getattr(self, f"attr_out{number}") for number in self._relay_mappings]

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Return descriptions for the configured zone capability subset."""
        descriptions = []
        specs = {spec.key: spec for spec in self.capability_requirements}
        for key in self._zone_mappings:
            descriptions.append(
                {
                    "sensor_id": key,
                    "name": specs[key].name,
                    "device_class": None,
                    "icon": "mdi:state-machine",
                }
            )
        return descriptions

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read all configured runtime capabilities into one atomic snapshot."""
        reader = S2000PPRuntimeReader(self.attr_client, self.attr_device_id)
        snapshot: dict[str, dict] = {}
        if self._relay_mappings:
            states = await reader.async_read_coils(
                item.modbus_address for item in self._relay_mappings.values()
            )
            outputs = {}
            for number, mapping in self._relay_mappings.items():
                output = dict(getattr(self, f"attr_out{number}"))
                output["state"] = states[mapping.modbus_address]
                setattr(self, f"attr_out{number}", output)
                outputs[number] = output
            snapshot["outputs"] = outputs
        if self._zone_mappings:
            states = await reader.async_read_zone_states(self._zone_mappings.values())
            snapshot["state_sensors"] = {
                key: self._state_sensor_value(key, states[item.gateway_object_number])
                for key, item in self._zone_mappings.items()
            }
        return snapshot

    def _state_sensor_value(
        self,
        key: str,
        state: S2000PPZoneState,
    ) -> dict[str, Any]:
        expanded_codes = state.expanded_states
        active_codes = tuple(code for code in expanded_codes if code != 0)
        return {
            "sensor_id": key,
            "state": self._state_name(state.primary_state),
            "primary_code": state.primary_state,
            "expanded_codes": expanded_codes,
            "expanded_states": tuple(self._state_name(code) for code in active_codes),
        }

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")

    async def get_output(
        self,
        output: int,
    ) -> dict[str, Any]:
        """Get one relay state."""

        if output not in self._relay_mappings:
            raise ValueError(f"C2000-KPB output {output} is not configured in S2000-PP")
        attr = getattr(self, f"attr_out{output}")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_coils((attr["address"],))
        attr["state"] = states[attr["address"]]

        setattr(
            self,
            f"attr_out{output}",
            attr,
        )

        return attr

    async def get_outputs(
        self,
        outputs: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get all or selected outputs."""

        data: list[dict[str, Any]] = []

        selected = outputs or list(self._relay_mappings)
        unknown = set(selected) - set(self._relay_mappings)
        if unknown:
            raise ValueError(f"C2000-KPB outputs are not configured: {sorted(unknown)}")
        reader = S2000PPRuntimeReader(self.attr_client, self.attr_device_id)
        states = await reader.async_read_coils(
            self._relay_mappings[number].modbus_address for number in selected
        )
        for output in selected:
            attr = dict(getattr(self, f"attr_out{output}"))
            attr["state"] = states[self._relay_mappings[output].modbus_address]
            setattr(self, f"attr_out{output}", attr)
            data.append(attr)

        return data

    async def set_output(
        self,
        output: int,
        value: bool,
    ) -> dict[str, Any]:
        """Set one relay state."""

        if output not in self._relay_mappings:
            raise ValueError(f"C2000-KPB output {output} is not configured in S2000-PP")
        attr = getattr(self, f"attr_out{output}")

        #
        # FC05
        #

        response = await self.attr_client.write_coil(
            address=attr["address"],
            value=value,
            device_id=self.attr_device_id,
        )
        validate_write_response(response, f"set C2000-KPB output {output}")
        attr["state"] = bool(value)
        setattr(self, f"attr_out{output}", attr)
        return attr

    async def set_outputs(
        self,
        outputs: list[int] | None = None,
        values: list[bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Set multiple outputs."""

        if values is None:
            return []

        data: list[dict[str, Any]] = []

        outputs = outputs or list(self._relay_mappings)

        for output, value in zip(outputs, values):

            result = await self.set_output(
                output,
                value,
            )

            data.append(result)

        return data

    def __repr__(self) -> str:
        """Representation info."""

        cls = self.__class__.__name__

        return (
            f"class: {cls}, "
            f"device_id: {self.attr_device_id}, "
            f"manufactures_name: {self.attr_manufactures_name}, "
            f"model_name: {self.attr_model_name}, "
            f"serial_number: {self.attr_serial_number}, "
            f"software_version: {self.attr_software_version}, "
            f"description: {self.attr_description}"
        )


class C2000SP4:
    """Bolid C2000-SP4 family equipment.

    Supported variants: С2000-СП4/24, С2000-СП4/24 исп.01,
    С2000-СП4/220 and С2000-СП4/220 исп.01.
    С2000-СП4/220 исп.02 is explicitly not supported.
    """

    required_gateway = GatewayType.S2000_PP
    uses_dpls_identity = True
    dpls_address_count = 5

    class Variant(str, Enum):
        SP4_24 = "sp4_24"
        SP4_24_01 = "sp4_24_01"
        SP4_220 = "sp4_220"
        SP4_220_01 = "sp4_220_01"

    @dataclass(frozen=True, slots=True)
    class VariantMetadata:
        display_name: str
        nominal_power: str
        maximum_output_current: str
        integrated_dpls_isolator: bool
        output_circuit_supervision: str

    variants = {
        Variant.SP4_24: VariantMetadata(
            "С2000-СП4/24", "10.2–28.4 V DC / 12–24 V AC", "3 A", False,
            "open circuit and short circuit",
        ),
        Variant.SP4_24_01: VariantMetadata(
            "С2000-СП4/24 исп.01", "10.2–28.4 V DC / 12–24 V AC", "3 A", True,
            "open circuit and short circuit",
        ),
        Variant.SP4_220: VariantMetadata(
            "С2000-СП4/220", "230 V AC ±10%", "3 A", False,
            "open circuit and short circuit",
        ),
        Variant.SP4_220_01: VariantMetadata(
            "С2000-СП4/220 исп.01", "230 V AC ±10%", "3 A", True,
            "open circuit and short circuit",
        ),
    }
    unsupported_variants = {"sp4_220_02": "С2000-СП4/220 исп.02 (not supported)"}

    capability_requirements = (
        GatewayCapabilitySpec(
            key="actuator_control", name="Working position",
            object_kind=ObjectKind.RELAY, local_object_number=0,
            local_object_offset=0,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="actuator_state", name="Actuator state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=0, zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="working_output_circuit", name="Working output circuit",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=1, zone_type=2,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="initial_output_circuit", name="Initial output circuit",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=2, zone_type=2,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="working_limit_switch", name="Working-position limit switch",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=3, zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="initial_limit_switch", name="Initial-position limit switch",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=4, zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
    )

    STATE_NAMES = {
        **C2000KPB.STATE_NAMES,
        153: "actuator_working_position",
        154: "actuator_initial_position",
        155: "actuator_failure",
        156: "actuator_error",
    }
    ACTUATOR_STATE_NAMES = {
        44: "actuator_error",
        45: "actuator_failure",
        53: "actuator_initial_position",
        54: "actuator_working_position",
    }

    def __init__(self, client, device_id) -> None:
        """Inicialization variables."""

        self.attr_device_id: int = device_id

        self.attr_client: (
            AsyncModbusSerialClient
            | AsyncModbusTcpClient
            | AsyncModbusUdpClient
            | None
        ) = client

        self.attr_manufactures_name: str = "Bolid"
        self.attr_model_name: str = "С2000-СП4/24(220)"
        self.attr_device_type: int | None = None
        self.attr_serial_number: str | None = None
        self.attr_hardware_version: str | None = None
        self.attr_software_version: str | None = None
        self.attr_init_time: datetime | None = None

        self.attr_output_amount = 1
        self.attr_input_amount = 0
        self.attr_description = "Addressable valve control unit"
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._relay_mapping: ResolvedObjectMapping | None = None
        self._zone_mappings: dict[str, ResolvedObjectMapping] = {}

        self.attr_out1: dict[str, Any] = {
            "out_number": 1,
            "out_number_view": "Working position",
            "out_type": "Actuator",
            "data_type": "coil_register",
            "address": None,
            "address_hex": None,
            "state": None,
            "func_mode": [1, 5, 15],
            "device_class": SwitchDeviceClass.SWITCH,
            "icon_on": "mdi:toggle-switch-variant",
            "icon_off": "mdi:toggle-switch-variant-off",
        }

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        return cls.capability_requirements

    @classmethod
    def get_variant_options(cls) -> dict[str, str]:
        """Return supported variants plus an explicit rejected option for the UI."""
        return {
            **{variant.value: metadata.display_name for variant, metadata in cls.variants.items()},
            **cls.unsupported_variants,
        }

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply the configured subset of the five DPLS addresses."""
        if mapping.identity.model != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000-SP4")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000-SP4")

        identity = mapping.identity
        if identity.dpls is None or identity.dpls.address_count != self.dpls_address_count:
            raise ValueError("C2000-SP4 requires a five-address DPLS identity")
        try:
            variant = self.Variant(identity.metadata.variant)
        except (TypeError, ValueError) as exc:
            raise ValueError("Unsupported or missing C2000-SP4 variant") from exc
        metadata = self.variants[variant]
        specs = {
            (spec.object_kind,
             spec.resolved_local_object_number(identity.dpls.base_address),
             spec.zone_type): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.object_kind, item.local_object_number, zone_type))
            if spec is None:
                raise ValueError("Mapping contains an unsupported C2000-SP4 object")
            expected = ModbusDataArea.COIL if item.object_kind is ObjectKind.RELAY else ModbusDataArea.HOLDING_REGISTER
            if item.data_area is not expected:
                raise ValueError("C2000-SP4 mapping uses an invalid Modbus data area")
            if spec.key in resolved:
                raise ValueError("Duplicate C2000-SP4 capability mapping")
            resolved[spec.key] = item
        if not resolved:
            raise ValueError("C2000-SP4 mapping must configure at least one capability")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = identity.stable_id
        self.attr_unique_id_prefix = identity.stable_id
        self.attr_model_name = metadata.display_name
        self.attr_device_metadata = {
            "variant": metadata.display_name,
            "nominal_power": metadata.nominal_power,
            "maximum_output_current": metadata.maximum_output_current,
            "integrated_dpls_isolator": metadata.integrated_dpls_isolator,
            "output_circuit_supervision": metadata.output_circuit_supervision,
            "kdl_orion_address": identity.orion_address,
            "dpls_base_address": identity.dpls.base_address,
        }
        self._relay_mapping = resolved.get("actuator_control")
        self._zone_mappings = {
            key: item for key, item in resolved.items() if item.object_kind is ObjectKind.ZONE
        }
        if self._relay_mapping is not None:
            self.attr_out1["address"] = self._relay_mapping.modbus_address
            self.attr_out1["address_hex"] = hex(self._relay_mapping.modbus_address)
            self.attr_platforms.append(Platform.SWITCH)
        if self._zone_mappings:
            self.attr_platforms.append(Platform.SENSOR)

    async def data_init(self) -> bool:
        """Initialize device."""
        if self.attr_gateway_mapping is None:
            raise ValueError("C2000-SP4 requires a validated S2000-PP mapping")
        await self.get_device_info()
        await self.async_get_snapshot()
        self.attr_init_time = datetime.now()

        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only service information available through this transport path."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_output_descriptions(self) -> list[dict[str, Any]]:
        return [] if self._relay_mapping is None else [self.attr_out1]

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        specs = {spec.key: spec for spec in self.capability_requirements}
        return [
            {"sensor_id": key, "name": specs[key].name, "device_class": None,
             "icon": "mdi:state-machine"}
            for key in self._zone_mappings
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        reader = S2000PPRuntimeReader(self.attr_client, self.attr_device_id)
        snapshot: dict[str, dict] = {}
        if self._relay_mapping is not None:
            states = await reader.async_read_coils((self._relay_mapping.modbus_address,))
            output = dict(self.attr_out1)
            output["state"] = states[self._relay_mapping.modbus_address]
            self.attr_out1 = output
            snapshot["outputs"] = {1: output}
        if self._zone_mappings:
            states = await reader.async_read_zone_states(self._zone_mappings.values())
            snapshot["state_sensors"] = {
                key: self._state_sensor_value(key, states[item.gateway_object_number])
                for key, item in self._zone_mappings.items()
            }
        return snapshot

    def _state_sensor_value(
        self, key: str, state: S2000PPZoneState
    ) -> dict[str, Any]:
        active = tuple(code for code in state.expanded_states if code != 0)
        names = (
            {**self.STATE_NAMES, **self.ACTUATOR_STATE_NAMES}
            if key == "actuator_state"
            else self.STATE_NAMES
        )
        return {
            "state": names.get(state.primary_state, f"unknown_{state.primary_state}"),
            "primary_code": state.primary_state,
            "expanded_codes": state.expanded_states,
            "expanded_states": tuple(
                names.get(code, f"unknown_{code}") for code in active
            ),
        }

    async def get_output(
        self,
        out: int = 1,
    ) -> dict[str, Any]:
        """Get output state."""

        if out != 1 or self._relay_mapping is None:
            raise ValueError("C2000-SP4 actuator control is not configured")
        states = await S2000PPRuntimeReader(self.attr_client, self.attr_device_id).async_read_coils((self._relay_mapping.modbus_address,))
        self.attr_out1["state"] = states[self._relay_mapping.modbus_address]
        return self.attr_out1

    async def get_outputs(
        self,
        outputs: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Get outputs state."""

        selected = outputs or ([1] if self._relay_mapping is not None else [])
        if set(selected) - {1} or (selected and self._relay_mapping is None):
            raise ValueError("C2000-SP4 actuator control is not configured")
        return [await self.get_output(1)] if selected else []

    async def set_output(
        self,
        output: int = 1,
        value: bool = False,
    ) -> dict[str, Any]:
        """Set output state."""

        if output != 1 or self._relay_mapping is None:
            raise ValueError("C2000-SP4 actuator control is not configured")
        attr = self.attr_out1

        result = await self.attr_client.write_coil(
            address=attr["address"],
            value=value,
            device_id=self.attr_device_id,
        )
        validate_write_response(result, f"set C2000-SP4 output {output}")

        attr["state"] = bool(value)

        self.attr_out1 = attr
        return attr

    async def set_outputs(
        self,
        outputs: list[int] | None = None,
        values: list[bool] | None = None,
    ):
        """Set outputs state."""

        if values is None:
            return []
        selected = outputs or [1]
        return [await self.set_output(output, value) for output, value in zip(selected, values)]

    def __repr__(self) -> str:
        """Representation info of object."""

        cls = self.__class__.__name__

        return (
            f"class: {cls}, "
            f"init_time: {self.attr_init_time}, "
            f"device_id: {self.attr_device_id}, "
            f"manufactures_name: "
            f"{self.attr_manufactures_name}, "
            f"device_type: {self.attr_device_type}, "
            f"model_name: {self.attr_model_name}, "
            f"serial_number: {self.attr_serial_number}, "
            f"hardware_version: "
            f"{self.attr_hardware_version}, "
            f"software_version: "
            f"{self.attr_software_version}, "
            f"out1: {self.attr_out1['state']}, "
            f"description: {self.attr_description}"
        )
