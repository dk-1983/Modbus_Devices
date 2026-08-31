"""Классы описывают содержание каждого прибора."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from logging import getLogger
from typing import Any

from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusUdpClient,
)
from pymodbus.exceptions import ModbusException

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from ..gateway import (
    CapabilityRequirement,
    GatewayCapabilitySpec,
    GatewayType,
    ModbusDataArea,
    ObjectKind,
    ResolvedDeviceMapping,
    ResolvedObjectMapping,
)
from ..modbus_validation import (
    validate_fc05_response,
    validate_fc16_response,
    validated_bits,
    validated_registers,
)
from ..s2000_pp import (
    NumericParameterKind,
    NumericResultStatus,
    S2000_PP_NUMERIC_RESULT,
    S2000PPConfiguration,
    S2000PPCounterValueReader,
    S2000PPNumericValueReader,
    S2000PPRuntimeReader,
    S2000PPZoneState,
    resolve_zone_row,
)
from .equipment import canonical_equipment_class_name

_LOGGER = getLogger(__name__)



def _handle_optional_numeric_protocol_error(
    device,
    channel: str,
    item: ResolvedObjectMapping,
    result,
) -> None:
    """Isolate only a typed exception returned by the numeric result read."""
    if (
        getattr(result, "operation", None) != "read numeric result"
        or getattr(result, "exception_code", None) is None
    ):
        raise ModbusException(result.message or "numeric protocol error")
    mapping = device.attr_gateway_mapping
    identity = mapping.identity
    dpls = identity.dpls
    _LOGGER.warning(
        "Optional S2000-PP numeric protocol error model=%s class=%s "
        "orion=%s dpls=%s channel=%s pp_row=%s selector_register=%s "
        "selector_value=%s result_register=%s result_count=%s owner=%s "
        "generation=%s response_function=%s exception=%s operation=%s error=%s",
        device.attr_model_name,
        device.__class__.__name__,
        identity.orion_address,
        None if dpls is None else dpls.base_address,
        channel,
        item.gateway_object_number,
        getattr(result, "selector_register", None),
        item.gateway_object_number,
        getattr(result, "result_register", S2000_PP_NUMERIC_RESULT),
        getattr(result, "result_count", 1),
        getattr(result, "session_owner", None),
        getattr(result, "session_generation", None),
        getattr(result, "response_function_code", None),
        getattr(result, "exception_code", None),
        getattr(result, "operation", None),
        result.message,
    )


class InvalidM3000ClockPayload(ModbusException):
    """A successful M3000 RTC register read containing invalid calendar fields."""


class M3000BB1020:
    """Bolid M3000-BB-1020 hw: 1.00 sw: 1.00."""

    equipment_manufacturer = "Bolid"
    equipment_model = "M3000-BB-1020"

    CLOCK_SYNC_MAX_DRIFT_SECONDS = 10
    CLOCK_SYNC_RETRY_COOLDOWN_SECONDS = 60
    RUNTIME_HEADER_ADDRESS = 60001
    RUNTIME_HEADER_REGISTER_COUNT = 12
    DEVICE_INFO_REGISTER_COUNT = 6
    CLOCK_ADDRESS = 60007
    CLOCK_REGISTER_COUNT = 6

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
        self.attr_has_device_time_sensor = True
        self.attr_platforms: list[Platform] = [
            Platform.BINARY_SENSOR,
            Platform.SENSOR,
            Platform.SWITCH,
        ]
        self._clock_write_lock = asyncio.Lock()
        self._last_failed_clock_sync_attempt: float | None = None
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
        """Initialize local metadata without device I/O."""
        self.attr_init_time = datetime.now()
        return True

    async def async_get_snapshot(self) -> dict[str, Any]:
        """Read one authoritative runtime snapshot for the coordinator."""
        inputs = await self.get_inputs()
        outputs = await self.get_outputs()
        comparison_time = self._local_now()
        device_time = None
        try:
            device_time = await self._get_runtime_header()
        except InvalidM3000ClockPayload:
            _LOGGER.warning(
                "M3000-BB-1020 returned invalid device clock fields; "
                "attempting backend-time correction",
                exc_info=True,
            )
            await self._async_attempt_clock_sync()
        except ModbusException:
            _LOGGER.warning(
                "Unable to read M3000-BB-1020 device clock; correction skipped",
                exc_info=True,
            )
        else:
            await self._async_correct_clock(device_time, comparison_time)
        return {
            "inputs": {item["input_number"]: item for item in inputs},
            "outputs": {item["out_number"]: item for item in outputs},
            "time": device_time,
        }

    async def _async_correct_clock(
        self,
        device_time: datetime,
        comparison_time: datetime,
    ) -> bool:
        """Correct a valid device wall clock only when drift exceeds tolerance."""
        device_wall_time = device_time.replace(tzinfo=None, microsecond=0)
        backend_wall_time = comparison_time.replace(tzinfo=None, microsecond=0)
        drift = abs((device_wall_time - backend_wall_time).total_seconds())
        if drift <= self.CLOCK_SYNC_MAX_DRIFT_SECONDS:
            return False
        return await self._async_attempt_clock_sync(drift=drift)

    async def _async_attempt_clock_sync(self, *, drift: float | None = None) -> bool:
        """Write backend time unless a previous failed write is cooling down."""
        monotonic_now = self._monotonic_now()
        if (
            self._last_failed_clock_sync_attempt is not None
            and monotonic_now - self._last_failed_clock_sync_attempt
            < self.CLOCK_SYNC_RETRY_COOLDOWN_SECONDS
        ):
            return False
        try:
            await self.set_time()
        except (ModbusException, OSError, TimeoutError):
            self._last_failed_clock_sync_attempt = self._monotonic_now()
            _LOGGER.warning(
                "Unable to synchronize M3000-BB-1020 device clock%s; "
                "retry suppressed for %s seconds",
                "" if drift is None else f" (drift {drift:.0f} seconds)",
                self.CLOCK_SYNC_RETRY_COOLDOWN_SECONDS,
                exc_info=True,
            )
            return False
        self._last_failed_clock_sync_attempt = None
        return True

    @staticmethod
    def _monotonic_now() -> float:
        """Return event-loop monotonic time for failed-write cooldowns."""
        return asyncio.get_running_loop().time()

    @staticmethod
    def _local_now() -> datetime:
        """Return Home Assistant's configured local wall-clock time."""
        return dt_util.now()

    async def get_device_info(self) -> list:
        """Получает информацию о текущем контроллере."""
        registers = await self._read_holding_registers(
            self.RUNTIME_HEADER_ADDRESS,
            self.DEVICE_INFO_REGISTER_COUNT,
            "read M3000-BB-1020 device info",
        )
        self._apply_device_info(registers)
        return registers

    async def _get_runtime_header(self) -> datetime:
        """Read documented contiguous device-info and RTC registers once."""
        registers = await self._read_holding_registers(
            self.RUNTIME_HEADER_ADDRESS,
            self.RUNTIME_HEADER_REGISTER_COUNT,
            "read M3000-BB-1020 runtime header",
        )
        self._apply_device_info(registers[: self.DEVICE_INFO_REGISTER_COUNT])
        return self._decode_time(registers[self.DEVICE_INFO_REGISTER_COUNT :])

    async def _read_holding_registers(
        self,
        address: int,
        count: int,
        operation: str,
    ) -> list[int]:
        """Read and validate one M3000 holding-register block."""
        response = await self.attr_client.read_holding_registers(
            address=address,
            count=count,
            device_id=self.attr_device_id,
        )
        return validated_registers(
            response,
            count,
            operation,
            expected_function=3,
        )

    def _apply_device_info(self, registers: list[int]) -> None:
        """Apply the documented six-register M3000 identity block."""
        self.attr_device_type = registers[0]
        self.attr_software_version = registers[1]
        self.attr_hardware_version = registers[2]
        self.attr_serial_number = "".join(hex(value)[2:] for value in registers[3:6])

    async def set_time(self, value: datetime | None = None) -> datetime:
        """Устанавливает дату и время в контроллер."""
        async with self._clock_write_lock:
            value = value or self._local_now()
            time_values = list(value.timetuple()[:6])
            response = await self.attr_client.write_registers(
                address=self.CLOCK_ADDRESS,
                values=time_values,
                device_id=self.attr_device_id,
            )
            validate_fc16_response(
                response,
                address=self.CLOCK_ADDRESS,
                count=len(time_values),
                device_id=self.attr_device_id,
                operation="set M3000-BB-1020 time",
            )
            self.attr_init_time = value
            return self.attr_init_time

    async def get_time(self) -> datetime:
        """Получает дату и время установленные в контроллере."""
        registers = await self._read_holding_registers(
            self.CLOCK_ADDRESS,
            self.CLOCK_REGISTER_COUNT,
            "read M3000-BB-1020 time",
        )
        return self._decode_time(registers)

    @staticmethod
    def _decode_time(registers: list[int]) -> datetime:
        """Decode six timezone-less M3000 wall-clock fields."""
        try:
            return datetime(*registers, microsecond=0)
        except ValueError as exc:
            raise InvalidM3000ClockPayload(
                "Invalid M3000-BB-1020 clock payload"
            ) from exc

    async def get_input(self, input: int) -> dict[str, Any]:
        """Получает состояние одного входа контроллера."""
        attr = getattr(self, f"attr_in{input}")
        response = await self.attr_client.read_discrete_inputs(
            address=attr["address"], count=1, device_id=self.attr_device_id
        )
        attr["state"] = validated_bits(
            response, 1, f"read M3000-BB-1020 input {input}", expected_function=2
        )[0]
        setattr(self, f"attr_in{input}", attr)
        return getattr(self, f"attr_in{input}")

    async def get_inputs(self, inputs: list[int] | None = None) -> list[dict[str, Any]]:
        """Получает состояние всех или нескольких входов контроллера."""
        selected = range(1, 13) if inputs is None else inputs
        return [await self.get_input(input_number) for input_number in selected]

    async def get_output(self, out: int) -> dict[str, Any]:
        """Получает состояние одного выхода номер 1-6."""
        attr = getattr(self, f"attr_out{out}")
        response = await self.attr_client.read_coils(
            address=attr["address"], count=1, device_id=self.attr_device_id
        )
        attr["state"] = validated_bits(
            response, 1, f"read M3000-BB-1020 output {out}", expected_function=1
        )[0]
        setattr(self, f"attr_out{out}", attr)
        return getattr(self, f"attr_out{out}")

    async def get_outputs(self, outputs: list | None = None):
        """Получение нескольких или всех состояний выходов контроллера."""
        selected = range(1, 7) if outputs is None else outputs
        return [await self.get_output(output_number) for output_number in selected]

    async def set_output(self, output: int, value: bool) -> dict[str, Any]:
        """Устанавливает состояние одного выхода номер 1-6."""
        attr = getattr(self, f"attr_out{output}")
        response = await self.attr_client.write_coil(
            address=attr["address"], value=value, device_id=self.attr_device_id
        )
        validate_fc05_response(
            response,
            address=attr["address"],
            value=bool(value),
            device_id=self.attr_device_id,
            operation=f"set M3000-BB-1020 output {output}",
        )
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
        selected = range(1, 7) if outputs is None else outputs
        for output, value in zip(selected, values, strict=False):
            if not isinstance(value, (bool, int)):
                raise TypeError
            data.append(await self.set_output(output, value))
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

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-ПП"

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
        """Initialize local metadata without polling the gateway."""
        self.attr_init_time = datetime.now()
        return True

    async def async_get_snapshot(self) -> dict[str, Any]:
        """Read diagnostics and cache service metadata on the first snapshot."""
        if self.attr_device_type is None:
            await self.get_device_info()
        inputs = await self.get_inputs()
        return {"inputs": {item["input_number"]: item for item in inputs}}

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
            expected_function=3,
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
            expected_function=2,
        )
        result = []
        for number, state in enumerate(states, start=1):
            item = getattr(self, f"attr_in{number}")
            item["state"] = state
            result.append(item)
        return result


class C2000KPB:
    """Bolid C2000-KPB described by the version 3.04 documentation."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-КПБ"

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
        3: "intrusion_alarm",
        4: "interference",
        6: "interference_restored",
        17: "arming_failed",
        19: "test",
        20: "test_mode_started",
        21: "test_mode_finished",
        22: "control_restored",
        24: "armed",
        14: "code_guessing_detected",
        15: "door_opened",
        18: "duress_code_presented",
        25: "access_closed",
        26: "access_rejected_unknown_code",
        27: "door_forced",
        28: "access_granted",
        29: "access_denied",
        30: "access_restored",
        31: "door_closed",
        32: "passage_registered",
        33: "door_held_open",
        34: "identification",
        35: "technological_input_restored",
        36: "technological_input_violated",
        37: "fire",
        38: "technological_input_violated_2",
        39: "equipment_normal",
        41: "equipment_fault",
        43: "warning",
        44: "attention",
        45: "input_open_circuit",
        46: "dpls_open_circuit",
        47: "dpls_restored",
        58: "silent_alarm",
        61: "configuration_reset",
        62: "configuration_changed",
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
        110: "alarm_reset",
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
        164: "sabotage",
        165: "input_parameter_error",
        186: "battery_replacement_required",
        187: "input_communication_lost",
        188: "input_communication_restored",
        192: "output_voltage_disconnected",
        193: "output_voltage_connected",
        194: "power_overload",
        195: "power_overload_restored",
        196: "charger_fault",
        197: "charger_restored",
        198: "power_fault",
        199: "power_restored",
        200: "battery_restored",
        202: "battery_fault",
        203: "device_restarted",
        204: "maintenance_required",
        205: "battery_test_failed",
        206: "temperature_low",
        211: "battery_low",
        212: "reserve_battery_low",
        213: "reserve_battery_restored",
        214: "input_short_circuit",
        224: "invalid_dpls_response",
        225: "unstable_dpls_response",
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
        validate_fc05_response(
            response,
            address=attr["address"],
            value=bool(value),
            device_id=self.attr_device_id,
            operation=f"set C2000-KPB output {output}",
        )
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


class C20002:
    """Bolid C2000-2 direct Orion state model behind S2000-PP."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-2"
    required_gateway = GatewayType.S2000_PP
    documented_firmware = "2.75"
    capability_requirements = (
        GatewayCapabilitySpec(
            key="device_state",
            name="Device state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            zone_type=3,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="access_input_1_state",
            name="Access/Input 1 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=1,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="access_input_2_state",
            name="Access/Input 2 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=2,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="input_3_state",
            name="Input 3 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=3,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="input_4_state",
            name="Input 4 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=4,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
    )
    STATE_NAMES = C2000KPB.STATE_NAMES

    def __init__(self, client, device_id) -> None:
        """Initialize the direct Orion state model."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "С2000-2"
        self.attr_description = "Access controller"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {
            "documented_firmware": self.documented_firmware,
            "documented_orion_state_objects": 5,
            "gateway_transport_limitation": (
                "S2000-PP exposes configured Orion zone states, not the card "
                "database, credentials, access log, or safe generic door-control commands"
            ),
        }
        self._state_mappings: dict[str, ResolvedObjectMapping] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return the exact optional S2000-PP state capabilities."""
        return cls.capability_requirements

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply the configured Orion state subset."""
        if canonical_equipment_class_name(mapping.identity.model) != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000-2")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000-2")
        if mapping.identity.dpls is not None:
            raise ValueError("C2000-2 identity must not contain DPLS identity")

        specs = {
            (spec.object_kind, spec.local_object_number, spec.zone_type): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.object_kind, item.local_object_number, zone_type))
            if spec is None:
                raise ValueError("Mapping contains an unsupported C2000-2 object")
            if item.data_area is not ModbusDataArea.HOLDING_REGISTER:
                raise ValueError("C2000-2 state mapping must use holding registers")
            if spec.key in resolved:
                raise ValueError("Duplicate C2000-2 capability mapping")
            resolved[spec.key] = item
        if not resolved:
            raise ValueError("C2000-2 mapping must configure at least one state object")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = mapping.identity.stable_id
        self.attr_unique_id_prefix = mapping.identity.stable_id
        self._state_mappings = resolved
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        """Initialize local metadata; coordinator owns runtime polling."""
        await self.get_device_info()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only service fields visible through this transport."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe the configured authoritative Orion state objects."""
        specs = {spec.key: spec for spec in self.capability_requirements}
        return [
            {
                "sensor_id": key,
                "name": specs[key].name,
                "device_class": None,
                "icon": "mdi:state-machine",
                "entity_category": (
                    EntityCategory.DIAGNOSTIC if key == "device_state" else None
                ),
            }
            for key in self._state_mappings
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read all configured state objects into one atomic snapshot."""
        if not self._state_mappings:
            raise ValueError("C2000-2 requires a validated S2000-PP mapping")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states(self._state_mappings.values())
        return {
            "state_sensors": {
                key: self._state_sensor_value(states[item.gateway_object_number])
                for key, item in self._state_mappings.items()
            }
        }

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")

    @classmethod
    def _state_sensor_value(cls, state: S2000PPZoneState) -> dict[str, Any]:
        expanded_codes = state.expanded_states
        return {
            "state": cls._state_name(state.primary_state),
            "primary_code": state.primary_state,
            "expanded_codes": expanded_codes,
            "expanded_states": tuple(
                cls._state_name(code) for code in expanded_codes if code != 0
            ),
        }


class C20004:
    """Bolid C2000-4 direct Orion state model behind S2000-PP."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-4"
    required_gateway = GatewayType.S2000_PP
    documented_firmware = "3.85"
    capability_requirements = (
        GatewayCapabilitySpec(
            key="device_state",
            name="Device state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            zone_type=3,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="input_1_state",
            name="Input 1 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=1,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="input_2_state",
            name="Input 2 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=2,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="input_3_state",
            name="Input 3 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=3,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="input_4_state",
            name="Input 4 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=4,
            zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
    )
    STATE_NAMES = C2000KPB.STATE_NAMES

    def __init__(self, client, device_id) -> None:
        """Initialize the direct Orion state model."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "С2000-4"
        self.attr_description = "Intrusion and fire alarm control panel"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {
            "documented_firmware": self.documented_firmware,
            "documented_orion_state_objects": 5,
            "gateway_transport_limitation": (
                "S2000-PP exposes configured Orion zone states; relay control is not "
                "published because safe ownership depends on device and S2000M tactics"
            ),
        }
        self._state_mappings: dict[str, ResolvedObjectMapping] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return the exact optional S2000-PP state capabilities."""
        return cls.capability_requirements

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply the configured Orion state subset."""
        if canonical_equipment_class_name(mapping.identity.model) != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000-4")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000-4")
        if mapping.identity.dpls is not None:
            raise ValueError("C2000-4 identity must not contain DPLS identity")

        specs = {
            (spec.object_kind, spec.local_object_number, spec.zone_type): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.object_kind, item.local_object_number, zone_type))
            if spec is None:
                raise ValueError("Mapping contains an unsupported C2000-4 object")
            if item.data_area is not ModbusDataArea.HOLDING_REGISTER:
                raise ValueError("C2000-4 state mapping must use holding registers")
            if spec.key in resolved:
                raise ValueError("Duplicate C2000-4 capability mapping")
            resolved[spec.key] = item
        if not resolved:
            raise ValueError("C2000-4 mapping must configure at least one state object")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = mapping.identity.stable_id
        self.attr_unique_id_prefix = mapping.identity.stable_id
        self._state_mappings = resolved
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        """Initialize local metadata; coordinator owns runtime polling."""
        await self.get_device_info()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only service fields visible through this transport."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe the configured authoritative Orion state objects."""
        specs = {spec.key: spec for spec in self.capability_requirements}
        return [
            {
                "sensor_id": key,
                "name": specs[key].name,
                "device_class": None,
                "icon": "mdi:state-machine",
                "entity_category": (
                    EntityCategory.DIAGNOSTIC if key == "device_state" else None
                ),
            }
            for key in self._state_mappings
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read all configured state objects into one atomic snapshot."""
        if not self._state_mappings:
            raise ValueError("C2000-4 requires a validated S2000-PP mapping")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states(self._state_mappings.values())
        return {
            "state_sensors": {
                key: self._state_sensor_value(states[item.gateway_object_number])
                for key, item in self._state_mappings.items()
            }
        }

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")

    @classmethod
    def _state_sensor_value(cls, state: S2000PPZoneState) -> dict[str, Any]:
        expanded_codes = state.expanded_states
        return {
            "state": cls._state_name(state.primary_state),
            "primary_code": state.primary_state,
            "expanded_codes": expanded_codes,
            "expanded_states": tuple(
                cls._state_name(code) for code in expanded_codes if code != 0
            ),
        }


class C2000BKI:
    """Bolid C2000-BKI direct Orion device state behind S2000-PP."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-БКИ"
    required_gateway = GatewayType.S2000_PP
    documented_firmware = "2.45"
    capability_requirements = (
        GatewayCapabilitySpec(
            key="device_state",
            name="Device state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            zone_type=3,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    STATE_NAMES = C2000KPB.STATE_NAMES

    def __init__(self, client, device_id) -> None:
        """Initialize the direct Orion device-state model."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "С2000-БКИ"
        self.attr_description = "Display and control unit"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {
            "documented_firmware": self.documented_firmware,
            "documented_orion_state_objects": 1,
            "gateway_transport_limitation": (
                "S2000-PP exposes the BKI device state; its 60 indicators and keys "
                "represent external Orion partitions or actuators and are not BKI objects"
            ),
        }
        self._state_mappings: dict[str, ResolvedObjectMapping] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return the exact optional S2000-PP device-state capability."""
        return cls.capability_requirements

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply the configured Orion device-state mapping."""
        if canonical_equipment_class_name(mapping.identity.model) != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000-BKI")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000-BKI")
        if mapping.identity.dpls is not None:
            raise ValueError("C2000-BKI identity must not contain DPLS identity")

        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            if (
                item.object_kind is not ObjectKind.ZONE
                or item.local_object_number != 0
                or zone_type != 3
            ):
                raise ValueError("Mapping contains an unsupported C2000-BKI object")
            if item.data_area is not ModbusDataArea.HOLDING_REGISTER:
                raise ValueError("C2000-BKI state mapping must use holding registers")
            if "device_state" in resolved:
                raise ValueError("Duplicate C2000-BKI capability mapping")
            resolved["device_state"] = item
        if not resolved:
            raise ValueError("C2000-BKI mapping must configure its device state")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = mapping.identity.stable_id
        self.attr_unique_id_prefix = mapping.identity.stable_id
        self._state_mappings = resolved
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        """Initialize local metadata; coordinator owns runtime polling."""
        await self.get_device_info()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only service fields visible through this transport."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe the authoritative BKI device-state object."""
        if not self._state_mappings:
            return []
        return [
            {
                "sensor_id": "device_state",
                "name": "Device state",
                "device_class": None,
                "icon": "mdi:state-machine",
                "entity_category": EntityCategory.DIAGNOSTIC,
            }
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read the BKI device state into one coordinator snapshot."""
        if not self._state_mappings:
            raise ValueError("C2000-BKI requires a validated S2000-PP mapping")
        item = self._state_mappings["device_state"]
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states((item,))
        return {
            "state_sensors": {
                "device_state": self._state_sensor_value(
                    states[item.gateway_object_number]
                )
            }
        }

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")

    @classmethod
    def _state_sensor_value(cls, state: S2000PPZoneState) -> dict[str, Any]:
        expanded_codes = state.expanded_states
        return {
            "state": cls._state_name(state.primary_state),
            "primary_code": state.primary_state,
            "expanded_codes": expanded_codes,
            "expanded_states": tuple(
                cls._state_name(code) for code in expanded_codes if code != 0
            ),
        }


class Signal20M:
    """Bolid Signal-20M direct Orion state model behind S2000-PP."""

    equipment_manufacturer = "Bolid"
    equipment_model = "Сигнал-20М"
    required_gateway = GatewayType.S2000_PP
    documented_firmware = "2.13"
    capability_requirements = (
        GatewayCapabilitySpec(
            key="device_state",
            name="Device state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            zone_type=3,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        *tuple(
            GatewayCapabilitySpec(
                key=f"input_{number}_state",
                name=f"Input {number} state",
                object_kind=ObjectKind.ZONE,
                local_object_number=number,
                zone_type=1,
                requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
            )
            for number in range(1, 21)
        ),
    )
    STATE_NAMES = C2000KPB.STATE_NAMES

    def __init__(self, client, device_id) -> None:
        """Initialize the direct Orion state model."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "Сигнал-20М"
        self.attr_description = "Intrusion and fire alarm control panel"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {
            "documented_firmware": self.documented_firmware,
            "documented_orion_state_objects": 21,
            "physical_outputs": 7,
            "gateway_transport_limitation": (
                "S2000-PP exposes configured Orion zone states; relay control is not "
                "published because safe ownership depends on device and S2000M tactics"
            ),
        }
        self._state_mappings: dict[str, ResolvedObjectMapping] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return exact optional S2000-PP state capabilities."""
        return cls.capability_requirements

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply the configured Orion state subset."""
        if canonical_equipment_class_name(mapping.identity.model) != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match Signal-20M")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match Signal-20M")
        if mapping.identity.dpls is not None:
            raise ValueError("Signal-20M identity must not contain DPLS identity")

        specs = {
            (spec.object_kind, spec.local_object_number, spec.zone_type): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.object_kind, item.local_object_number, zone_type))
            if spec is None:
                raise ValueError("Mapping contains an unsupported Signal-20M object")
            if item.data_area is not ModbusDataArea.HOLDING_REGISTER:
                raise ValueError("Signal-20M state mapping must use holding registers")
            if spec.key in resolved:
                raise ValueError("Duplicate Signal-20M capability mapping")
            resolved[spec.key] = item
        if not resolved:
            raise ValueError("Signal-20M mapping must configure at least one state object")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = mapping.identity.stable_id
        self.attr_unique_id_prefix = mapping.identity.stable_id
        self._state_mappings = resolved
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        """Initialize local metadata; coordinator owns runtime polling."""
        await self.get_device_info()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only service fields visible through this transport."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe the configured authoritative Orion state objects."""
        specs = {spec.key: spec for spec in self.capability_requirements}
        return [
            {
                "sensor_id": key,
                "name": specs[key].name,
                "device_class": None,
                "icon": "mdi:state-machine",
                "entity_category": (
                    EntityCategory.DIAGNOSTIC if key == "device_state" else None
                ),
            }
            for key in self._state_mappings
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read configured state objects into one coordinator snapshot."""
        if not self._state_mappings:
            raise ValueError("Signal-20M requires a validated S2000-PP mapping")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states(self._state_mappings.values())
        return {
            "state_sensors": {
                key: self._state_sensor_value(states[item.gateway_object_number])
                for key, item in self._state_mappings.items()
            }
        }

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")

    @classmethod
    def _state_sensor_value(cls, state: S2000PPZoneState) -> dict[str, Any]:
        expanded_codes = state.expanded_states
        return {
            "state": cls._state_name(state.primary_state),
            "primary_code": state.primary_state,
            "expanded_codes": expanded_codes,
            "expanded_states": tuple(
                cls._state_name(code) for code in expanded_codes if code != 0
            ),
        }


class MIP24Isp20:
    """Bolid MIP-24 isp.20 direct Orion state model behind S2000-PP."""

    equipment_manufacturer = "Bolid"
    equipment_model = "МИП-24 исп.20"
    required_gateway = GatewayType.S2000_PP
    full_designation = "МИП-24-2/П5-Р-RS"
    documented_target_firmware = "5.10"
    physical_numeric_capabilities = (
        "output_voltage",
        "output_current",
        "battery_voltage",
        "battery_charge",
        "mains_voltage",
        "temperature",
    )
    gateway_transport_limitation = (
        "S2000-PP exposes input 0 as the type-3 global/tamper state row and "
        "inputs 1-5 as type-8 state/numeric rows; "
        "runtime service information and autonomous alarm-output control are "
        "unavailable through this transport"
    )
    capability_requirements = (
        GatewayCapabilitySpec(
            key="device_state",
            name="Device state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            zone_type=3,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="output_power_state",
            name="Output power state",
            object_kind=ObjectKind.ZONE,
            local_object_number=1,
            zone_type=8,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="output_load_state",
            name="Output load state",
            object_kind=ObjectKind.ZONE,
            local_object_number=2,
            zone_type=8,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="battery_state",
            name="Battery state",
            object_kind=ObjectKind.ZONE,
            local_object_number=3,
            zone_type=8,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="charger_state",
            name="Charger state",
            object_kind=ObjectKind.ZONE,
            local_object_number=4,
            zone_type=8,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="mains_state",
            name="Mains state",
            object_kind=ObjectKind.ZONE,
            local_object_number=5,
            zone_type=8,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    STATE_NAMES = C2000KPB.STATE_NAMES
    _STATE_PRESENTATION = {
        "device_state": ("mdi:state-machine", EntityCategory.DIAGNOSTIC),
        "output_power_state": ("mdi:power-plug", None),
        "output_load_state": ("mdi:current-ac", None),
        "battery_state": ("mdi:battery", None),
        "charger_state": ("mdi:battery-charging", EntityCategory.DIAGNOSTIC),
        "mains_state": ("mdi:transmission-tower", None),
    }
    _NUMERIC_KINDS = {
        "output_voltage": NumericParameterKind.OUTPUT_VOLTAGE,
        "output_current": NumericParameterKind.OUTPUT_CURRENT,
        "battery_voltage": NumericParameterKind.BATTERY_VOLTAGE,
        "battery_charge": NumericParameterKind.BATTERY_CHARGE,
        "mains_voltage": NumericParameterKind.MAINS_VOLTAGE,
    }
    _NUMERIC_METADATA = {
        "output_voltage": (
            "Output voltage",
            SensorDeviceClass.VOLTAGE,
            UnitOfElectricPotential.VOLT,
            2,
        ),
        "output_current": (
            "Output current",
            SensorDeviceClass.CURRENT,
            UnitOfElectricCurrent.AMPERE,
            2,
        ),
        "battery_voltage": (
            "Battery voltage",
            SensorDeviceClass.VOLTAGE,
            UnitOfElectricPotential.VOLT,
            2,
        ),
        "battery_charge": (
            "Battery charge",
            SensorDeviceClass.BATTERY,
            PERCENTAGE,
            0,
        ),
        "mains_voltage": (
            "Mains voltage",
            SensorDeviceClass.VOLTAGE,
            UnitOfElectricPotential.VOLT,
            0,
        ),
    }
    _NUMERIC_STATE_KEYS = {
        "output_power_state": "output_voltage",
        "output_load_state": "output_current",
        "battery_state": "battery_voltage",
        "charger_state": "battery_charge",
        "mains_state": "mains_voltage",
    }

    def __init__(self, client, device_id) -> None:
        """Initialize the six-row state and numeric equipment model."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "МИП-24 исп.20"
        self.attr_description = "Power supply module"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {
            "full_designation": self.full_designation,
            "documented_target_firmware": self.documented_target_firmware,
            "documented_orion_state_objects": 6,
            "validated_s2000_pp_rows": 6,
            "physical_numeric_capabilities": self.physical_numeric_capabilities,
            "gateway_transport_limitation": self.gateway_transport_limitation,
        }
        self._state_mappings: dict[str, ResolvedObjectMapping] = {}
        self._numeric_mappings: dict[str, ResolvedObjectMapping] = {}
        self._numeric_values: dict[str, dict[str, Any]] = {}
        self._numeric_cursor = 0

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return required and optional exact S2000-PP capabilities."""
        return cls.capability_requirements

    @classmethod
    def reconcile_gateway_mapping(
        cls,
        mapping: ResolvedDeviceMapping,
        configuration: S2000PPConfiguration,
    ) -> ResolvedDeviceMapping:
        """Validate persisted rows against the live PP table and repair drift."""
        rows = configuration.zones_for_device(mapping.identity.orion_address)
        canonical_rows = []
        for spec in cls.capability_requirements:
            matches = [
                row
                for row in rows
                if row.local_zone_number == spec.local_object_number
                and row.zone_type == spec.zone_type
            ]
            if len(matches) != 1:
                canonical_rows = []
                break
            canonical_rows.append(matches[0])

        if canonical_rows:
            canonical = ResolvedDeviceMapping(
                identity=mapping.identity,
                source=mapping.source,
                objects=tuple(
                    resolve_zone_row(
                        row,
                        configuration.partition_id(row.partition_number),
                    )
                    for row in canonical_rows
                ),
            )
            return canonical

        if cls._is_exact_legacy_mapping(mapping, configuration):
            return mapping

        raise ValueError(
            "MIP-24 isp.20 mapping does not match one unambiguous current "
            "S2000-PP Input 0-5 footprint"
        )

    @classmethod
    def _is_exact_legacy_mapping(
        cls,
        mapping: ResolvedDeviceMapping,
        configuration: S2000PPConfiguration,
    ) -> bool:
        """Accept a semantically exact pre-type-8 footprint without guessing."""
        if len(mapping.objects) != 6:
            return False
        actual_rows = {row.table_number: row for row in configuration.zones}
        expected_types = {0: 3, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1}
        seen_inputs: set[int] = set()
        for item in mapping.objects:
            row = actual_rows.get(item.gateway_object_number)
            if (
                row is None
                or row.device_address != mapping.identity.orion_address
                or row.local_zone_number != item.local_object_number
                or row.zone_type != expected_types.get(item.local_object_number)
            ):
                return False
            expected = resolve_zone_row(
                row,
                configuration.partition_id(row.partition_number),
            )
            if item != expected:
                return False
            seen_inputs.add(item.local_object_number)
        return seen_inputs == set(expected_types)

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply the configured Orion object subset."""
        if canonical_equipment_class_name(mapping.identity.model) != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match MIP-24 isp.20")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match MIP-24 isp.20")
        if mapping.identity.dpls is not None:
            raise ValueError("MIP-24 isp.20 identity must not contain DPLS identity")

        specs = {
            (spec.object_kind, spec.local_object_number, spec.zone_type): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.object_kind, item.local_object_number, zone_type))
            if spec is None and zone_type == 1 and 1 <= item.local_object_number <= 5:
                # Preserve already-stored mappings created by the pre-type-8 model.
                spec = next(
                    candidate
                    for candidate in self.capability_requirements
                    if candidate.local_object_number == item.local_object_number
                )
            if spec is None:
                raise ValueError("Mapping contains an unsupported MIP-24 isp.20 object")
            if item.data_area is not ModbusDataArea.HOLDING_REGISTER:
                raise ValueError("MIP-24 isp.20 state mapping must use holding registers")
            if spec.key in resolved:
                raise ValueError("Duplicate MIP-24 isp.20 capability mapping")
            resolved[spec.key] = item

        canonical_keys = {"device_state", *self._NUMERIC_STATE_KEYS}
        if not canonical_keys.issubset(resolved):
            raise ValueError("MIP-24 isp.20 requires input 0 and all five input rows")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = mapping.identity.stable_id
        self.attr_unique_id_prefix = mapping.identity.stable_id
        self._state_mappings = resolved
        self._numeric_mappings = {
            numeric_key: resolved[state_key]
            for state_key, numeric_key in self._NUMERIC_STATE_KEYS.items()
            if state_key in resolved
            for item in (resolved[state_key],)
            if item.zone_details is not None
            and item.zone_details.zone_type == 8
        }
        self._numeric_values = {}
        self._numeric_cursor = 0
        self.attr_platforms = [Platform.SENSOR, Platform.BINARY_SENSOR]

    async def get_device_info(self) -> dict[str, Any]:
        """Return only runtime service fields exposed by the transport."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe only state objects configured in S2000-PP."""
        specs = {spec.key: spec for spec in self.capability_requirements}
        return [
            {
                "sensor_id": key,
                "name": specs[key].name,
                "device_class": None,
                "icon": self._STATE_PRESENTATION[key][0],
                "entity_category": self._STATE_PRESENTATION[key][1],
            }
            for key in self._state_mappings
        ]

    def get_numeric_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe numeric values of configured type-8 PP rows."""
        return [
            {
                "sensor_id": key,
                "name": self._NUMERIC_METADATA[key][0],
                "device_class": self._NUMERIC_METADATA[key][1],
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": self._NUMERIC_METADATA[key][2],
                "precision": self._NUMERIC_METADATA[key][3],
            }
            for key in self._numeric_mappings
        ]

    def get_binary_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe the documented enclosure tamper derived from input 0."""
        return [{
            "sensor_id": "tamper",
            "name": "Enclosure tamper",
            "device_class": BinarySensorDeviceClass.TAMPER,
            "entity_category": EntityCategory.DIAGNOSTIC,
            "icon": "mdi:shield-lock-open",
        }]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read all mapped state objects into one atomic snapshot."""
        if not self._state_mappings:
            raise ValueError("MIP-24 isp.20 requires a validated S2000-PP mapping")
        mapping = self.attr_gateway_mapping
        numeric_reader = S2000PPNumericValueReader(
            self.attr_client,
            self.attr_device_id,
            mapping.identity.gateway.stable_id,
        )
        numeric_items = tuple(self._numeric_mappings.items())
        if numeric_items:
            key, item = numeric_items[self._numeric_cursor]
            result = await numeric_reader.async_read(
                item.gateway_object_number, self._NUMERIC_KINDS[key]
            )
            if result.status is NumericResultStatus.READY:
                self._numeric_values[key] = {
                    "value": result.value,
                    "raw_register": result.raw_register,
                    "parameter_kind": result.parameter_kind.value,
                }
                self._numeric_cursor = (self._numeric_cursor + 1) % len(numeric_items)
            elif result.status is NumericResultStatus.PROTOCOL_ERROR:
                _handle_optional_numeric_protocol_error(self, key, item, result)

        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states(self._state_mappings.values())
        state_snapshot = {
            key: self._state_sensor_value(key, states[item.gateway_object_number])
            for key, item in self._state_mappings.items()
        }
        device_state = states[self._state_mappings["device_state"].gateway_object_number]
        return {
            "numeric_sensors": {
                key: dict(value) for key, value in self._numeric_values.items()
            },
            "state_sensors": state_snapshot,
            "binary_sensors": {"tamper": {
                "state": self._tamper_state(device_state),
                "primary_code": device_state.primary_state,
                "expanded_codes": device_state.expanded_states,
            }},
        }

    async def data_init(self) -> bool:
        """Initialize local metadata; the coordinator owns runtime polling."""
        await self.get_device_info()
        self.attr_init_time = datetime.now()
        return True

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")

    @classmethod
    def _state_sensor_value(
        cls, key: str, state: S2000PPZoneState
    ) -> dict[str, Any]:
        expanded_codes = state.expanded_states
        return {
            "sensor_id": key,
            "state": cls._state_name(state.primary_state),
            "primary_code": state.primary_state,
            "expanded_codes": expanded_codes,
            "expanded_states": tuple(
                cls._state_name(code) for code in expanded_codes if code != 0
            ),
        }

    @staticmethod
    def _tamper_state(state: S2000PPZoneState) -> bool | None:
        """Derive case-open semantics from documented input-0 state codes."""
        for code in (state.primary_state, *state.expanded_states):
            if code == 149:
                return True
            if code == 152:
                return False
        return None


class C2000KDL:
    """Classic Bolid C2000-KDL through an S2000-PP gateway.

    The documented S2000-PP transport exposes the controller itself only as
    zone type 3, local object 0. Rows for other local objects belong to DPLS
    devices and are deliberately outside this equipment model.
    """

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-КДЛ"
    required_gateway = GatewayType.S2000_PP
    gateway_transport_limitation = (
        "S2000-PP does not expose documented Modbus requests for C2000-KDL "
        "serial, firmware, hardware revision, product cipher, DPLS catalog, "
        "or DPLS electrical measurements"
    )
    capability_requirements = (
        GatewayCapabilitySpec(
            key="device_state",
            name="Device state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            zone_type=3,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    STATE_NAMES = {
        **C2000KPB.STATE_NAMES,
        46: "dpls_open_circuit",
        215: "dpls_short_circuit",
        217: "dpls_branch_communication_lost",
        218: "dpls_branch_communication_restored",
        222: "dpls_voltage_high",
    }

    def __init__(self, client, device_id) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "С2000-КДЛ"
        self.attr_description = "DPLS line controller"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._device_state_mapping: ResolvedObjectMapping | None = None

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return the one controller-owned S2000-PP object."""
        return cls.capability_requirements

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Accept only the exact device-level type-3/local-0 zone."""
        if mapping.identity.model != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000-KDL")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000-KDL")
        if mapping.identity.dpls is not None:
            raise ValueError("C2000-KDL identity must not contain a DPLS subidentity")
        if len(mapping.objects) != 1:
            raise ValueError("C2000-KDL requires exactly one device-state mapping")

        device_state = mapping.objects[0]
        if (
            device_state.object_kind is not ObjectKind.ZONE
            or device_state.local_object_number != 0
            or device_state.zone_details is None
            or device_state.zone_details.zone_type != 3
            or device_state.data_area is not ModbusDataArea.HOLDING_REGISTER
        ):
            raise ValueError(
                "C2000-KDL requires S2000-PP zone type 3, local object 0"
            )

        identity = mapping.identity
        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = identity.stable_id
        self.attr_unique_id_prefix = identity.stable_id
        self.attr_device_metadata = {
            "orion_address": identity.orion_address,
            "gateway_identity": identity.gateway.stable_id,
            "maximum_dpls_addresses": 127,
            "maximum_dpls_output_current": "120 mA",
            "maximum_dpls_device_current": "84 mA",
            "recommended_dpls_device_current": "64 mA",
            "dpls_topologies": "ring, tree, mixed",
            "transport_limitation": self.gateway_transport_limitation,
        }
        self._device_state_mapping = device_state
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        """Initialize the required aggregate state without service guesses."""
        if self._device_state_mapping is None:
            raise ValueError(
                "C2000-KDL requires zone type 3, local object 0 in S2000-PP"
            )
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return only service information available through this transport."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Return one aggregate multistate diagnostic entity."""
        if self._device_state_mapping is None:
            return []
        return [
            {
                "sensor_id": "device_state",
                "name": "Device state",
                "device_class": None,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "icon": "mdi:state-machine",
            }
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read primary and expanded state as one atomic snapshot."""
        if self._device_state_mapping is None:
            raise ValueError("C2000-KDL device-state mapping is not configured")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states((self._device_state_mapping,))
        state = states[self._device_state_mapping.gateway_object_number]
        active_codes = tuple(code for code in state.expanded_states if code != 0)
        return {
            "state_sensors": {
                "device_state": {
                    "sensor_id": "device_state",
                    "state": self._state_name(state.primary_state),
                    "primary_code": state.primary_state,
                    "expanded_codes": state.expanded_states,
                    "expanded_states": tuple(
                        self._state_name(code) for code in active_codes
                    ),
                }
            }
        }

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")


class C2000RARR125:
    """Bolid C2000R-ARR125 radio expander behind a C2000-KDL.

    The expander owns exactly one DPLS input object. Radio devices enrolled in
    it have independent DPLS identities and are deliberately outside this
    model. KDL input types 5 and 6 are model metadata: the documented
    S2000-PP configuration table does not expose that KDL setting.
    """

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-АРР125"
    required_gateway = GatewayType.S2000_PP
    uses_dpls_identity = True
    dpls_address_count = 1
    variant_optional = True
    documented_target_firmware = "1.31"
    supported_kdl_input_types = (5, 6)
    gateway_transport_limitation = (
        "S2000-PP does not expose the configured KDL input type, serial, "
        "actual firmware, hardware revision, product cipher, radio identifier, "
        "protocol version, enrolled-device catalog, RSSI, radio route, channel, "
        "or ARR125 electrical measurements"
    )

    class Variant(str, Enum):
        HARDWARE_1_0 = "hardware_1_0"
        HARDWARE_14_0 = "hardware_14_0"

    @dataclass(frozen=True, slots=True)
    class VariantMetadata:
        display_name: str
        dpls_current: str
        external_power_current: str
        power_behavior: str

        @property
        def device_metadata(self) -> dict[str, Any]:
            return {
                "hardware_variant": self.display_name,
                "dpls_current": self.dpls_current,
                "external_power_current": self.external_power_current,
                "power_behavior": self.power_behavior,
            }

    variants = {
        Variant.HARDWARE_1_0: VariantMetadata(
            "1.0",
            "up to 21 mA; emergency mode up to 5.7 mA",
            "15 mA nominal at 12 V",
            "configurable DPLS/external supply; emergency DPLS operation with radio off",
        ),
        Variant.HARDWARE_14_0: VariantMetadata(
            "14.0",
            "up to 27 mA",
            "27 mA at 12 V; 15 mA at 24 V",
            "hardware-selected DPLS supply; stops if all permitted sources fail",
        ),
    }
    variant_dpls_address_counts = {
        Variant.HARDWARE_1_0.value: 1,
        Variant.HARDWARE_14_0.value: 1,
    }
    capability_requirements = (
        GatewayCapabilitySpec(
            key="device_state",
            name="ARR125 state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            local_object_offset=0,
            zone_type=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    STATE_NAMES = C2000KPB.STATE_NAMES

    def __init__(self, client, device_id) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "С2000Р-АРР125"
        self.attr_description = "Addressable radio expander"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._device_state_mapping: ResolvedObjectMapping | None = None

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        return cls.capability_requirements

    @classmethod
    def get_variant_options(cls) -> dict[str, str]:
        return {
            variant.value: metadata.display_name
            for variant, metadata in cls.variants.items()
        }

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        if mapping.identity.model != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000RARR125")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000RARR125")
        dpls = mapping.identity.dpls
        if dpls is None or dpls.address_count != 1:
            raise ValueError("C2000RARR125 requires one DPLS address")
        if len(mapping.objects) != 1:
            raise ValueError("C2000RARR125 requires exactly one own zone mapping")

        device_state = mapping.objects[0]
        if (
            device_state.object_kind is not ObjectKind.ZONE
            or device_state.local_object_number != dpls.base_address
            or device_state.zone_details is None
            or device_state.zone_details.zone_type != 1
            or device_state.data_area is not ModbusDataArea.HOLDING_REGISTER
        ):
            raise ValueError(
                "C2000RARR125 requires its own type-1 zone at the configured DPLS address"
            )

        variant = mapping.identity.metadata.variant
        if variant is not None and variant not in self.get_variant_options():
            raise ValueError("C2000RARR125 requires hardware variant 1.0 or 14.0")
        variant_metadata = (
            None if variant is None else self.variants[self.Variant(variant)]
        )
        identity = mapping.identity
        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = identity.stable_id
        self.attr_unique_id_prefix = identity.stable_id
        self.attr_device_metadata = {
            **({} if variant_metadata is None else variant_metadata.device_metadata),
            "orion_address": identity.orion_address,
            "gateway_identity": identity.gateway.stable_id,
            "dpls_address": dpls.base_address,
            "dpls_address_count": 1,
            "supported_kdl_input_types": self.supported_kdl_input_types,
            "maximum_radio_devices": 125,
            "maximum_repeaters": 32,
            "maximum_repeater_depth": 8,
            "radio_channels": 10,
            "radio_bands_mhz": "866.0–868.0, 868.0–868.2, 868.7–869.2",
            "transport_limitation": self.gateway_transport_limitation,
        }
        self._device_state_mapping = device_state
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        if self._device_state_mapping is None:
            raise ValueError("C2000RARR125 own zone mapping is not configured")
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        if self._device_state_mapping is None:
            return []
        return [{
            "sensor_id": "device_state",
            "name": "ARR125 state",
            "device_class": None,
            "entity_category": EntityCategory.DIAGNOSTIC,
            "icon": "mdi:radio-tower",
        }]

    async def async_get_snapshot(self) -> dict[str, dict]:
        if self._device_state_mapping is None:
            raise ValueError("C2000RARR125 own zone mapping is not configured")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states((self._device_state_mapping,))
        state = states[self._device_state_mapping.gateway_object_number]
        active_codes = tuple(code for code in state.expanded_states if code != 0)
        return {"state_sensors": {"device_state": {
            "sensor_id": "device_state",
            "state": self._state_name(state.primary_state),
            "primary_code": state.primary_state,
            "expanded_codes": state.expanded_states,
            "expanded_states": tuple(self._state_name(code) for code in active_codes),
        }}}

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")


class BolidDPLSDetectorBase:
    """Shared exact-zone state mechanics for distinct DPLS detectors."""

    required_gateway = GatewayType.S2000_PP
    uses_dpls_identity = True
    dpls_address_count = 1
    variant_optional = True
    variants: dict = {}
    topologies: dict[str, str] = {}
    topology_dpls_address_counts: dict[str, int] = {}
    capability_requirements: tuple[GatewayCapabilitySpec, ...] = ()
    state_sensor_definitions: dict[str, tuple[str, str, str]] = {}
    state_entity_category: EntityCategory | None = None
    STATE_NAMES = C2000KPB.STATE_NAMES
    detector_model = ""
    detector_description = "Addressable fire detector"
    supported_kdl_input_types: tuple[int, ...] = ()
    documented_target_firmware: str | None = None
    physical_capabilities: tuple[str, ...] = ()
    gateway_transport_limitation = (
        "S2000-PP does not expose the configured KDL input type, serial, actual "
        "firmware, hardware revision, product cipher, DPLS protocol version, or "
        "detector service/configuration values"
    )

    def __init__(self, client, device_id) -> None:
        if self.__class__ is BolidDPLSDetectorBase:
            raise TypeError("BolidDPLSDetectorBase is not equipment")
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = self.detector_model
        self.attr_description = self.detector_description
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._state_mapping: ResolvedObjectMapping | None = None
        self._state_mappings: dict[str, ResolvedObjectMapping] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        return cls.capability_requirements

    @classmethod
    def get_variant_options(cls) -> dict[str, str]:
        return dict(cls.variants)

    @classmethod
    def get_gateway_capabilities_for_metadata(
        cls, metadata
    ) -> tuple[GatewayCapabilitySpec, ...]:
        """Return the exact capability set selected by typed topology metadata."""
        return cls.capability_requirements

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        if canonical_equipment_class_name(mapping.identity.model) != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match detector")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match detector")
        dpls = mapping.identity.dpls
        if dpls is None:
            raise ValueError("DPLS detector requires a DPLS identity")
        metadata = mapping.identity.metadata
        expected_count = self.topology_dpls_address_counts.get(
            metadata.topology, self.dpls_address_count
        )
        if dpls.address_count != expected_count:
            raise ValueError("DPLS detector address count does not match its topology")
        capabilities = self.get_gateway_capabilities_for_metadata(metadata)
        accepted = {
            (
                spec.resolved_local_object_number(dpls.base_address),
                spec.zone_type,
            ): spec
            for spec in capabilities
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for state_mapping in mapping.objects:
            spec = None
            if state_mapping.zone_details is not None:
                spec = accepted.get(
                    (state_mapping.local_object_number, state_mapping.zone_details.zone_type)
                )
            if (
                state_mapping.object_kind is not ObjectKind.ZONE
                or spec is None
                or state_mapping.data_area is not ModbusDataArea.HOLDING_REGISTER
                or spec.key in resolved
            ):
                raise ValueError(
                    "Detector mapping must contain only exact configured DPLS zones"
                )
            resolved[spec.key] = state_mapping

        required = {
            spec.key for spec in capabilities
            if spec.requirement is CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION
            and spec.alternative_group is None
        }
        if not required.issubset(resolved):
            raise ValueError("Detector mapping is missing a required own zone")
        for group in {
            spec.alternative_group for spec in capabilities
            if spec.alternative_group is not None
        }:
            matches = [
                spec.key for spec in capabilities
                if spec.alternative_group == group and spec.key in resolved
            ]
            if len(matches) != 1:
                raise ValueError("Detector mapping must select exactly one alternative")

        identity = mapping.identity
        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = identity.stable_id
        self.attr_unique_id_prefix = identity.stable_id
        self.attr_device_metadata = {
            "kdl_orion_address": identity.orion_address,
            "gateway_identity": identity.gateway.stable_id,
            "dpls_address": dpls.base_address,
            "dpls_address_count": dpls.address_count,
            "supported_kdl_input_types": self.supported_kdl_input_types,
            "documented_target_firmware": self.documented_target_firmware,
            "physical_capabilities": self.physical_capabilities,
            "transport_limitation": self.gateway_transport_limitation,
        }
        if metadata.variant is not None:
            self.attr_device_metadata["hardware_variant"] = metadata.variant
        if metadata.topology is not None:
            self.attr_device_metadata["topology"] = metadata.topology
        self._state_mappings = resolved
        self._state_mapping = next(iter(resolved.values()), None)
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        if self._state_mapping is None:
            raise ValueError("Detector zone mapping is not configured")
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        if not self._state_mappings:
            return []
        descriptions = []
        for capability_key in self._state_mappings:
            sensor_id, name, icon = self.state_sensor_definitions.get(
                capability_key,
                ("detector_state", "Detector state", "mdi:smoke-detector"),
            )
            description = {
                "sensor_id": sensor_id,
                "name": name,
                "device_class": None,
                "icon": icon,
            }
            if self.state_entity_category is not None:
                description["entity_category"] = self.state_entity_category
            descriptions.append(description)
        return descriptions

    async def async_get_snapshot(self) -> dict[str, dict]:
        if self._state_mapping is None:
            raise ValueError("Detector zone mapping is not configured")
        mappings = tuple(self._state_mappings.values())
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states(mappings)
        snapshot = {}
        for capability_key, state_mapping in self._state_mappings.items():
            sensor_id, _, _ = self.state_sensor_definitions.get(
                capability_key,
                ("detector_state", "Detector state", "mdi:smoke-detector"),
            )
            state = states[state_mapping.gateway_object_number]
            active = tuple(code for code in state.expanded_states if code != 0)
            snapshot[sensor_id] = {
                "sensor_id": sensor_id,
                "state": self._state_name(state.primary_state),
                "primary_code": state.primary_state,
                "expanded_codes": state.expanded_states,
                "expanded_states": tuple(self._state_name(code) for code in active),
            }
        return {"state_sensors": snapshot}

    @classmethod
    def _state_name(cls, code: int) -> str:
        return cls.STATE_NAMES.get(code, f"unknown_{code}")


class DIP34A05(BolidDPLSDetectorBase):
    """Current wired optical smoke detector ДИП-34А-05."""

    equipment_manufacturer = "Bolid"
    equipment_model = "ДИП-34А-05"
    detector_model = "ДИП-34А-05"
    documented_variant = "dip_34a_05"
    documented_target_firmware = "1.22"
    supported_kdl_input_types = (6, 21)
    physical_capabilities = ("smoke_detection", "dust_compensation", "test")
    capability_requirements = (
        GatewayCapabilitySpec(
            key="detector_state", name="Detector state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=0, zone_type=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Return the one lossless state entity with DIP-specific icon semantics."""
        descriptions = super().get_state_sensor_descriptions()
        for description in descriptions:
            if description["sensor_id"] != "detector_state":
                continue
            description["state_icons"] = {
                "equipment_normal": "mdi:smoke-detector",
                "fire": "mdi:smoke-detector-alert",
                "warning": "mdi:smoke-detector-alert",
                "attention": "mdi:smoke-detector-alert",
                "equipment_fault": "mdi:alert-circle",
                "maintenance_required": "mdi:alert-circle",
                "input_communication_lost": "mdi:alert-circle",
                "device_communication_lost": "mdi:alert-circle",
            }
            description["unknown_state_icon"] = "mdi:help-circle-outline"
        return descriptions


class BolidRadioDetectorDiagnosticsMixin:
    """Shared truthful diagnostics for one-row radio detectors."""

    detector_state_icons: dict[str, str] = {}
    _MAIN_BATTERY_CODES = frozenset((200, 202, 211))
    _RESERVE_BATTERY_CODES = frozenset((212, 213))
    battery_state_channels: tuple[tuple[str, str, frozenset[int]], ...] = (
        ("main_battery_state", "Main battery state", _MAIN_BATTERY_CODES),
        ("reserve_battery_state", "Reserve battery state", _RESERVE_BATTERY_CODES),
    )

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        # Absence of transient event codes is not evidence of a closed case.
        # Only the explicit canonical 149/152 lifecycle establishes state.
        self._enclosure_tamper_state: bool | None = None

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Keep one projected DPLS row and enable its semantic diagnostics."""
        super().apply_gateway_mapping(mapping)
        self.attr_platforms = [Platform.SENSOR, Platform.BINARY_SENSOR]

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe the lossless detector state and documented battery channels."""
        descriptions = super().get_state_sensor_descriptions()
        descriptions[0]["state_icons"] = dict(self.detector_state_icons)
        descriptions[0]["unknown_state_icon"] = "mdi:help-circle-outline"
        for sensor_id, name, _ in self.battery_state_channels:
            descriptions.append({
                "sensor_id": sensor_id,
                "name": name,
                "device_class": None,
                "icon": "mdi:battery",
                "entity_category": EntityCategory.DIAGNOSTIC,
                "state_icons": {
                    "battery_restored": "mdi:battery-check",
                    "battery_low": "mdi:battery-alert",
                    "battery_fault": "mdi:battery-alert",
                    "reserve_battery_restored": "mdi:battery-check",
                    "reserve_battery_low": "mdi:battery-alert",
                },
                "unknown_state_icon": "mdi:help-circle-outline",
            })
        return descriptions

    def get_binary_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Expose documented tamper without treating code absence as restored."""
        return [] if self._state_mapping is None else [{
            "sensor_id": "enclosure_tamper",
            "name": "Enclosure tamper",
            "device_class": BinarySensorDeviceClass.TAMPER,
            "entity_category": EntityCategory.DIAGNOSTIC,
            "enabled_default": True,
            "icon": "mdi:shield-question",
            "icon_on": "mdi:shield-lock-open",
            "icon_off": "mdi:shield-check",
            "unknown_icon": "mdi:shield-question",
        }]

    @classmethod
    def _battery_state(
        cls, active: tuple[int, ...], codes: frozenset[int]
    ) -> tuple[int | None, str | None]:
        """Decode one channel only when its expanded evidence is unambiguous."""
        matched = {code for code in active if code in codes}
        if len(matched) != 1:
            return None, None
        code = matched.pop()
        return code, cls._state_name(code)

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Add conservative radio diagnostics to the lossless row snapshot."""
        snapshot = await super().async_get_snapshot()
        capability_key = next(iter(self._state_mappings))
        sensor_id = self.state_sensor_definitions.get(
            capability_key, ("detector_state", "", "")
        )[0]
        detector = snapshot["state_sensors"][sensor_id]
        expanded_codes = detector["expanded_codes"]
        active = tuple(code for code in expanded_codes if code != 0)

        tamper_codes = {code for code in active if code in {149, 152}}
        if tamper_codes == {149}:
            self._enclosure_tamper_state = True
        elif tamper_codes == {152}:
            self._enclosure_tamper_state = False

        for sensor_id, _, codes in self.battery_state_channels:
            code, state = self._battery_state(active, codes)
            snapshot["state_sensors"][sensor_id] = {
                "sensor_id": sensor_id,
                "state": state,
                "primary_code": detector["primary_code"],
                "expanded_codes": expanded_codes,
                "expanded_states": detector["expanded_states"],
                "battery_code": code,
            }

        snapshot["binary_sensors"] = {"enclosure_tamper": {
            "state": self._enclosure_tamper_state,
            "primary_code": detector["primary_code"],
            "expanded_codes": expanded_codes,
        }}
        return snapshot


class BolidRadioFireDetectorBase(
    BolidRadioDetectorDiagnosticsMixin, BolidDPLSDetectorBase
):
    """Shared physical contract for one-row radio fire detectors."""

    gateway_transport_limitation = (
        BolidDPLSDetectorBase.gateway_transport_limitation
        + "; RSSI, channel, repeater route, radio identifier, and battery voltage "
        "are not exposed"
    )
    capability_requirements = DIP34A05.capability_requirements


class C2000RDIP(BolidRadioFireDetectorBase):
    """Radio optical smoke detector represented as its own DPLS object."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-ДИП"
    detector_model = "С2000Р-ДИП"
    documented_target_firmware = "1.29"
    supported_kdl_input_types = (1, 6, 8, 21)
    physical_capabilities = (
        "smoke_detection", "dust_compensation", "radio_supervision",
        "main_and_reserve_battery", "tamper", "test",
    )
    capability_requirements = DIP34A05.capability_requirements
    detector_state_icons = {
        "armed": "mdi:smoke-detector",
        "equipment_normal": "mdi:smoke-detector",
        "fire": "mdi:smoke-detector-alert",
        "warning": "mdi:smoke-detector-alert",
        "attention": "mdi:smoke-detector-alert",
        "equipment_fault": "mdi:alert-circle",
        "maintenance_required": "mdi:alert-circle",
        "input_communication_lost": "mdi:alert-circle",
        "device_communication_lost": "mdi:alert-circle",
    }


class C2000IP03(BolidDPLSDetectorBase):
    """Wired temperature detector С2000-ИП-03 with two PP mapping modes."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-ИП-03"
    detector_model = "С2000-ИП-03"
    documented_variant = "s2000_ip_03"
    documented_target_firmware = "1.15"
    supported_kdl_input_types = (6, 21)
    physical_capabilities = ("temperature_measurement", "fire_detection", "test")
    capability_requirements = (
        GatewayCapabilitySpec(
            key="state_only", name="Detector state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=0, zone_type=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
            alternative_group="detector_mapping",
        ),
        GatewayCapabilitySpec(
            key="state_and_temperature", name="Detector state + temperature",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=0, zone_type=6,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
            alternative_group="detector_mapping",
        ),
    )

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        self._temperature_enabled = False
        self._temperature_value: dict[str, Any] | None = None

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        super().apply_gateway_mapping(mapping)
        self._temperature_enabled = self._state_mapping.zone_details.zone_type == 6
        self.attr_device_metadata["mapping_mode"] = (
            "state_and_temperature" if self._temperature_enabled else "state_only"
        )

    def get_numeric_sensor_descriptions(self) -> list[dict[str, Any]]:
        if not self._temperature_enabled:
            return []
        return [{
            "sensor_id": "temperature",
            "name": "Temperature",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "unit": UnitOfTemperature.CELSIUS,
            "precision": 2,
        }]

    async def async_get_snapshot(self) -> dict[str, dict]:
        snapshot = await super().async_get_snapshot()
        if not self._temperature_enabled:
            return snapshot
        mapping = self.attr_gateway_mapping
        result = await S2000PPNumericValueReader(
            self.attr_client,
            self.attr_device_id,
            mapping.identity.gateway.stable_id,
        ).async_read(
            self._state_mapping.gateway_object_number,
            NumericParameterKind.TEMPERATURE,
        )
        if result.status is NumericResultStatus.READY:
            self._temperature_value = {
                "value": result.value,
                "raw_register": result.raw_register,
                "parameter_kind": result.parameter_kind.value,
            }
        elif result.status is NumericResultStatus.PROTOCOL_ERROR:
            _handle_optional_numeric_protocol_error(
                self,
                "temperature",
                self._state_mapping,
                result,
            )
        snapshot["numeric_sensors"] = (
            {} if self._temperature_value is None
            else {"temperature": dict(self._temperature_value)}
        )
        return snapshot


class C2000RIP(BolidRadioFireDetectorBase):
    """Radio heat detector with one lossless S2000-PP state projection."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-ИП"
    detector_model = "С2000Р-ИП"
    documented_target_firmware = "1.30"
    supported_kdl_input_types = (3, 6, 9, 10, 21)
    physical_capabilities = (
        "temperature_measurement", "fire_detection", "radio_supervision",
        "main_and_reserve_battery", "tamper", "test",
    )
    gateway_transport_limitation = (
        BolidDPLSDetectorBase.gateway_transport_limitation
        + "; numeric temperature through S2000-PP is not confirmed; RSSI, channel, "
        "repeater route, radio identifier, and battery voltage are not exposed"
    )
    capability_requirements = DIP34A05.capability_requirements
    detector_state_icons = {
        "armed": "mdi:thermometer",
        "equipment_normal": "mdi:thermometer",
        "temperature_normal": "mdi:thermometer",
        "fire": "mdi:fire-alert",
        "warning": "mdi:fire-alert",
        "attention": "mdi:fire-alert",
        "temperature_high": "mdi:fire-alert",
        "equipment_fault": "mdi:alert-circle",
        "temperature_sensor_fault": "mdi:alert-circle",
        "input_communication_lost": "mdi:alert-circle",
        "device_communication_lost": "mdi:alert-circle",
    }

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        self._measurement_fault_state: bool | None = None

    def get_binary_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Expose independently restored enclosure and measuring-part faults."""
        descriptions = super().get_binary_sensor_descriptions()
        if self._state_mapping is not None:
            descriptions.append({
                "sensor_id": "measurement_fault",
                "name": "Temperature measurement fault",
                "device_class": BinarySensorDeviceClass.PROBLEM,
                "entity_category": EntityCategory.DIAGNOSTIC,
                "enabled_default": True,
                "icon": "mdi:thermometer-question",
                "icon_on": "mdi:thermometer-alert",
                "icon_off": "mdi:thermometer-check",
                "unknown_icon": "mdi:thermometer-question",
            })
        return descriptions

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Project the canonical 82/83 measuring-part lifecycle losslessly."""
        snapshot = await super().async_get_snapshot()
        detector = snapshot["state_sensors"]["detector_state"]
        active = {code for code in detector["expanded_codes"] if code != 0}
        measurement_codes = active & {82, 83}
        if measurement_codes == {82}:
            self._measurement_fault_state = True
        elif measurement_codes == {83}:
            self._measurement_fault_state = False
        snapshot["binary_sensors"]["measurement_fault"] = {
            "state": self._measurement_fault_state,
            "primary_code": detector["primary_code"],
            "expanded_codes": detector["expanded_codes"],
        }
        return snapshot


class C2000RST01(BolidRadioDetectorDiagnosticsMixin, BolidDPLSDetectorBase):
    """Radio glass-break detector С2000Р-СТ исп.01."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-СТ исп.01"
    detector_model = "С2000Р-СТ исп.01"
    detector_description = "Radio glass-break detector"
    documented_target_firmware = "1.03"
    supported_kdl_input_types = (5,)
    physical_capabilities = (
        "glass_break_detection", "tamper", "radio_supervision", "battery", "test",
    )
    gateway_transport_limitation = (
        BolidDPLSDetectorBase.gateway_transport_limitation
        + "; RSSI, channel, repeater route, radio identifier, battery voltage, "
        "sensitivity, acoustic level, and detector-local commands are not exposed"
    )
    capability_requirements = (
        GatewayCapabilitySpec(
            key="glass_break_state", name="Glass break detector state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=0, zone_type=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    state_sensor_definitions = {
        "glass_break_state": (
            "glass_break_state", "Glass break detector state", "mdi:glass-fragile"
        ),
    }
    battery_state_channels = (
        (
            "main_battery_state",
            "Battery state",
            BolidRadioDetectorDiagnosticsMixin._MAIN_BATTERY_CODES,
        ),
    )
    detector_state_icons = {
        "armed": "mdi:glass-fragile",
        "control_restored": "mdi:glass-fragile",
        "intrusion_alarm": "mdi:alarm-light",
        "interference": "mdi:alert-circle",
        "equipment_fault": "mdi:alert-circle",
        "input_communication_lost": "mdi:alert-circle",
        "device_communication_lost": "mdi:alert-circle",
    }

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        self._glass_break_state: bool | None = None

    def get_binary_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Expose alarm and the shared explicit enclosure lifecycle."""
        descriptions = super().get_binary_sensor_descriptions()
        if self._state_mapping is not None:
            descriptions.insert(0, {
                "sensor_id": "glass_break",
                "name": "Glass break",
                "device_class": BinarySensorDeviceClass.SOUND,
                "enabled_default": True,
                "icon": "mdi:help-circle-outline",
                "icon_on": "mdi:alarm-light",
                "icon_off": "mdi:glass-fragile",
                "unknown_icon": "mdi:help-circle-outline",
            })
        return descriptions

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Project explicit alarm/restore evidence without hiding raw states."""
        snapshot = await super().async_get_snapshot()
        detector = snapshot["state_sensors"]["glass_break_state"]
        active = {code for code in detector["expanded_codes"] if code != 0}
        primary = detector["primary_code"]
        if primary == 3 or (3 in active and not active & {24, 110}):
            self._glass_break_state = True
        elif primary in {24, 110} or (active & {24, 110} and 3 not in active):
            self._glass_break_state = False
        snapshot["binary_sensors"]["glass_break"] = {
            "state": self._glass_break_state,
            "primary_code": primary,
            "expanded_codes": detector["expanded_codes"],
        }
        return snapshot


class C2000ST04(BolidDPLSDetectorBase):
    """Wired DPLS glass-break detector С2000-СТ исп.04."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-СТ исп.04"
    detector_model = "С2000-СТ исп.04"
    detector_description = "DPLS glass-break detector"
    documented_target_firmware = "1.22"
    supported_kdl_input_types = (5,)
    physical_capabilities = (
        "glass_break_detection", "tamper", "anti_masking", "test",
        "dpls_service_voltage",
    )
    gateway_transport_limitation = (
        BolidDPLSDetectorBase.gateway_transport_limitation
        + "; DPLS service voltage, sensitivity, acoustic level, and detector-local "
        "commands are not exposed through S2000-PP"
    )
    capability_requirements = C2000RST01.capability_requirements
    state_sensor_definitions = C2000RST01.state_sensor_definitions


def _reconcile_smk_gateway_mapping(
    detector_class,
    mapping: ResolvedDeviceMapping,
    configuration: S2000PPConfiguration,
) -> ResolvedDeviceMapping:
    """Resolve the exact SMK type-1 footprint without using partition identity."""
    identity = mapping.identity
    dpls = identity.dpls
    if dpls is None:
        raise ValueError("SMK mapping requires a DPLS identity")
    capabilities = detector_class.get_gateway_capabilities_for_metadata(
        identity.metadata
    )
    expected_count = detector_class.topology_dpls_address_counts.get(
        identity.metadata.topology, detector_class.dpls_address_count
    )
    if dpls.address_count != expected_count:
        raise ValueError("SMK DPLS footprint does not match its topology")

    resolved = []
    for capability in capabilities:
        local_address = capability.resolved_local_object_number(dpls.base_address)
        matches = [
            row
            for row in configuration.zones_for_device(identity.orion_address)
            if row.local_zone_number == local_address and row.zone_type == 1
        ]
        if len(matches) != 1:
            raise ValueError(
                "SMK mapping does not match one unambiguous zone-type-1 row "
                f"for DPLS address {local_address}"
            )
        row = matches[0]
        resolved.append(
            resolve_zone_row(row, configuration.partition_id(row.partition_number))
        )
    return ResolvedDeviceMapping(identity, mapping.source, tuple(resolved))


class C2000RSMK(BolidDPLSDetectorBase):
    """Radio magnetic-contact detector with an optional external circuit."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-СМК"
    detector_model = "С2000Р-СМК"
    detector_description = "Radio magnetic-contact detector"
    state_entity_category = EntityCategory.DIAGNOSTIC
    dpls_address_count = 1
    variants = {
        "hardware_1_0": "Hardware 1.0",
        "hardware_2_0": "Hardware 2.0",
    }
    topologies = {
        "contact_only": "Magnetic contact only",
        "contact_and_external_input": "Magnetic contact + external input",
    }
    topology_dpls_address_counts = {
        "contact_only": 1,
        "contact_and_external_input": 2,
    }
    documented_target_firmware = None
    documented_firmware_family = (
        "1.04", "1.05", "1.06", "1.07", "1.12", "1.13"
    )
    supported_kdl_input_types = (4, 5, 6, 7, 11)
    external_input_kdl_types = (4, 5, 6, 7, 11, 17, 22)
    physical_capabilities = (
        "magnetic_contact", "optional_external_dry_contact", "tamper",
        "anti_sabotage", "radio_supervision", "battery", "test",
    )
    gateway_transport_limitation = (
        BolidDPLSDetectorBase.gateway_transport_limitation
        + "; external-circuit ADC/resistance, RSSI, channel, repeater route, radio "
        "identifier, battery voltage, and detector-local commands are not exposed"
    )
    capability_requirements = (
        GatewayCapabilitySpec(
            key="opening_state", name="Opening state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=0, zone_type=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="external_input_state", name="External input state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=1, zone_type=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    state_sensor_definitions = {
        "opening_state": ("opening_state", "Opening state", "mdi:door"),
        "external_input_state": (
            "external_input_state", "External input state", "mdi:electric-switch"
        ),
    }
    battery_state_codes = (200, 202, 211)

    @classmethod
    def reconcile_gateway_mapping(
        cls,
        mapping: ResolvedDeviceMapping,
        configuration: S2000PPConfiguration,
    ) -> ResolvedDeviceMapping:
        """Reconcile the configured radio-contact footprint with current PP rows."""
        return _reconcile_smk_gateway_mapping(cls, mapping, configuration)

    @classmethod
    def get_gateway_capabilities_for_metadata(
        cls, metadata
    ) -> tuple[GatewayCapabilitySpec, ...]:
        if metadata.topology == "contact_only":
            return cls.capability_requirements[:1]
        if metadata.topology == "contact_and_external_input":
            return cls.capability_requirements
        raise ValueError("C2000RSMK requires a supported topology")

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        variant = mapping.identity.metadata.variant
        if variant is not None and variant not in self.variants:
            raise ValueError("C2000RSMK hardware variant is not supported")
        super().apply_gateway_mapping(mapping)
        self.attr_device_metadata["external_input_kdl_types"] = (
            self.external_input_kdl_types
        )
        self.attr_device_metadata["documented_firmware_family"] = (
            self.documented_firmware_family
        )
        self.attr_device_metadata["battery_topology"] = "single_er14505m"

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe raw contact rows plus the confirmed battery state."""
        descriptions = super().get_state_sensor_descriptions()
        if self._state_mappings:
            descriptions.append({
                "sensor_id": "battery_state",
                "name": "Battery state",
                "device_class": None,
                "icon": "mdi:battery",
            })
        return descriptions

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Add a single-battery semantic without inventing terminal behavior."""
        snapshot = await super().async_get_snapshot()
        opening = snapshot["state_sensors"]["opening_state"]
        active = tuple(code for code in opening["expanded_codes"] if code != 0)
        code = next((item for item in active if item in self.battery_state_codes), None)
        snapshot["state_sensors"]["battery_state"] = {
            "state": None if code is None else self._state_name(code),
            "primary_code": opening["primary_code"],
            "expanded_codes": opening["expanded_codes"],
            "expanded_states": opening["expanded_states"],
        }
        return snapshot


class C2000SMK(BolidDPLSDetectorBase):
    """Wired one-address magnetic-contact detector С2000-СМК исп.04."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-СМК исп.04"
    detector_model = "С2000-СМК исп.04"
    detector_description = "DPLS magnetic-contact detector"
    documented_target_firmware = None
    documented_firmware_family = ("1.10", "1.11")
    supported_kdl_input_types = (4, 5, 6, 7, 11)
    state_entity_category = EntityCategory.DIAGNOSTIC
    physical_capabilities = (
        "magnetic_contact", "magnetic_test", "dpls_service_voltage",
    )
    gateway_transport_limitation = (
        BolidDPLSDetectorBase.gateway_transport_limitation
        + "; DPLS service voltage and address-programming operations are not exposed "
        "through S2000-PP"
    )
    capability_requirements = C2000RSMK.capability_requirements[:1]
    state_sensor_definitions = {
        "opening_state": ("opening_state", "Opening state", "mdi:door"),
    }

    @classmethod
    def reconcile_gateway_mapping(
        cls,
        mapping: ResolvedDeviceMapping,
        configuration: S2000PPConfiguration,
    ) -> ResolvedDeviceMapping:
        """Reconcile the configured wired-contact row with current PP data."""
        return _reconcile_smk_gateway_mapping(cls, mapping, configuration)

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Attach execution-specific documentation without runtime version claims."""
        super().apply_gateway_mapping(mapping)
        self.attr_device_metadata["documented_firmware_family"] = (
            self.documented_firmware_family
        )


class BolidDPLSWaterMeterBase(BolidDPLSDetectorBase):
    """Shared state and unscaled S2000-PP counter mechanics for water meters."""

    detector_description = "DPLS water meter"
    supported_kdl_input_types = (13,)
    dpls_address_count = 1
    pulse_volume_m3 = 0.001
    automatic_counter_polling_enabled = True
    optional_counter_result_exceptions: frozenset[int] = frozenset()
    physical_capabilities = (
        "cumulative_water_consumption",
        "initial_reading",
        "serial_number",
        "magnetic_influence_detection",
        "battery_supervision",
    )
    gateway_transport_limitation = (
        "S2000-PP exposes the current pulse total and Orion states, but not the "
        "initial reading, meter serial number, actual firmware, hardware revision, "
        "battery voltage, percentage, DPLS voltage, or registrar service data"
    )
    capability_requirements = (
        GatewayCapabilitySpec(
            key="meter_state",
            name="Meter state",
            object_kind=ObjectKind.ZONE,
            local_object_number=0,
            local_object_offset=0,
            zone_type=7,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    state_sensor_definitions = {
        "meter_state": ("meter_state", "Meter state", "mdi:counter"),
    }

    def __init__(self, client, device_id) -> None:
        if self.__class__ is BolidDPLSWaterMeterBase:
            raise TypeError("BolidDPLSWaterMeterBase is not equipment")
        super().__init__(client, device_id)
        self._water_value: dict[str, Any] | None = None

    def get_numeric_sensor_descriptions(self) -> list[dict[str, Any]]:
        return [{
            "sensor_id": "water_consumption",
            "name": "Water consumption",
            "device_class": SensorDeviceClass.WATER,
            "state_class": SensorStateClass.TOTAL_INCREASING,
            "unit": UnitOfVolume.CUBIC_METERS,
            "precision": 3,
        }]

    async def async_get_snapshot(self) -> dict[str, dict]:
        snapshot = await super().async_get_snapshot()
        mapping = self.attr_gateway_mapping
        if mapping is None or self._state_mapping is None:
            raise ValueError("Water meter counter mapping is not configured")
        if not self.automatic_counter_polling_enabled:
            snapshot["numeric_sensors"] = (
                {} if self._water_value is None
                else {"water_consumption": dict(self._water_value)}
            )
            return snapshot
        result = await S2000PPCounterValueReader(
            self.attr_client,
            self.attr_device_id,
            mapping.identity.gateway.stable_id,
        ).async_read(self._state_mapping.gateway_object_number)
        if result.status is NumericResultStatus.READY:
            self._water_value = {
                "value": result.raw_count * self.pulse_volume_m3,
                "raw_count": result.raw_count,
            }
        elif (
            result.status is NumericResultStatus.PROTOCOL_ERROR
            and result.result_register_read
            and result.exception_code in self.optional_counter_result_exceptions
        ):
            self._water_value = None
        elif result.status is NumericResultStatus.PROTOCOL_ERROR:
            raise ModbusException(result.message or "counter protocol error")
        snapshot["numeric_sensors"] = (
            {} if self._water_value is None
            else {"water_consumption": dict(self._water_value)}
        )
        return snapshot

class SVK15_3_8_1_B3(BolidDPLSWaterMeterBase):
    """Radio water meter with integrated С2000Р-АСР1 исп.01."""

    equipment_manufacturer = "Bolid"
    equipment_model = "СВК15-3-8-1-Б3"
    detector_model = "СВК15-3-8-1-Б3"
    detector_description = "Radio DPLS-visible water meter"
    documented_target_firmware = "1.07"
    # A single automatic counter acquisition was hardware-proven to make
    # unrelated DPLS detectors report communication loss through S2000-PP.
    # Keep the entity and protocol implementation, but do not initiate this
    # optional transaction until the device-side cause is understood.
    automatic_counter_polling_enabled = False
    optional_counter_result_exceptions = frozenset({3})
    physical_capabilities = BolidDPLSWaterMeterBase.physical_capabilities + (
        "radio_supervision",
        "radio_signal_quality",
        "replaceable_er14505_battery",
    )
    gateway_transport_limitation = (
        BolidDPLSWaterMeterBase.gateway_transport_limitation
        + "; ARR125 is not part of stable identity; ARR32 transport, RSSI, RF channel, "
        "repeater route, and radio identifier are not exposed"
    )


class SVK15_3_2_B(BolidDPLSWaterMeterBase):
    """Wired DPLS water meter with integrated С2000-АСР1."""

    equipment_manufacturer = "Bolid"
    equipment_model = "СВК15-3-2-Б"
    detector_model = "СВК15-3-2-Б"
    detector_description = "Wired DPLS water meter"
    physical_capabilities = BolidDPLSWaterMeterBase.physical_capabilities + (
        "dpls_line_supervision",
        "cr2032_reserve_power",
    )


class BolidDPLSOutputBase:
    """Shared exact-mapping and output lifecycle for DPLS radio outputs."""

    required_gateway = GatewayType.S2000_PP
    uses_dpls_identity = True
    variant_optional = True
    variants: dict = {}
    topologies: dict[str, str] = {}
    topology_dpls_address_counts: dict[str, int] = {}
    capability_requirements: tuple[GatewayCapabilitySpec, ...] = ()
    output_specs: dict[str, tuple[int, str, str]] = {}
    STATE_NAMES = C2000KPB.STATE_NAMES
    gateway_transport_limitation = (
        "S2000-PP exposes configured relay/zone rows but not radio identifier, "
        "RSSI, channel, route, actual firmware, hardware revision, battery "
        "voltage, enrollment, test, or output program configuration"
    )

    def __init__(self, client, device_id) -> None:
        if self.__class__ is BolidDPLSOutputBase:
            raise TypeError("BolidDPLSOutputBase is not equipment")
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = self.model_name
        self.attr_description = self.description
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._relay_mappings: dict[int, ResolvedObjectMapping] = {}
        self._zone_mappings: dict[str, ResolvedObjectMapping] = {}
        self._outputs: dict[int, dict[str, Any]] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        return cls.capability_requirements

    @classmethod
    def get_variant_options(cls) -> dict[str, str]:
        return dict(cls.variants)

    def _validate_identity(self, mapping: ResolvedDeviceMapping) -> None:
        if mapping.identity.model != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match output device")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match output device")

    def _validate_configuration(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate model-specific variant and topology metadata."""

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        self._validate_identity(mapping)
        identity = mapping.identity
        dpls = identity.dpls
        if dpls is None:
            raise ValueError("DPLS output device requires a DPLS identity")
        self._validate_configuration(mapping)
        specs = {
            (
                spec.object_kind,
                spec.resolved_local_object_number(dpls.base_address),
                spec.zone_type,
            ): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.object_kind, item.local_object_number, zone_type))
            if spec is None:
                raise ValueError("Mapping contains an unsupported output-device object")
            expected = (
                ModbusDataArea.COIL
                if item.object_kind is ObjectKind.RELAY
                else ModbusDataArea.HOLDING_REGISTER
            )
            if item.data_area is not expected:
                raise ValueError("Output-device mapping uses an invalid data area")
            if spec.key in resolved:
                raise ValueError("Duplicate output-device capability mapping")
            resolved[spec.key] = item
        required = {
            spec.key for spec in self.capability_requirements
            if spec.requirement is CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION
        }
        if not required <= resolved.keys():
            raise ValueError("Output-device mapping is missing a required object")
        self._validate_resolved_capabilities(mapping, resolved)

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = identity.stable_id
        self.attr_unique_id_prefix = identity.stable_id
        self.attr_device_metadata = self._device_metadata(mapping)
        self._relay_mappings = {}
        self._zone_mappings = {}
        self._outputs = {}
        for key, item in resolved.items():
            if item.object_kind is ObjectKind.RELAY:
                number, label, output_type = self.output_specs[key]
                self._relay_mappings[number] = item
                self._outputs[number] = {
                    "out_number": number,
                    "out_number_view": label,
                    "out_type": output_type,
                    "data_type": "coil_register",
                    "address": item.modbus_address,
                    "address_hex": hex(item.modbus_address),
                    "state": None,
                    "func_mode": [1, 5, 15],
                    "device_class": SwitchDeviceClass.SWITCH,
                    "icon_on": "mdi:toggle-switch-variant",
                    "icon_off": "mdi:toggle-switch-variant-off",
                }
            else:
                self._zone_mappings[key] = item
        self.attr_platforms = [Platform.SWITCH]
        if self._zone_mappings:
            self.attr_platforms.append(Platform.SENSOR)

    def _validate_resolved_capabilities(
        self,
        mapping: ResolvedDeviceMapping,
        resolved: dict[str, ResolvedObjectMapping],
    ) -> None:
        """Validate model-specific capability combinations."""

    def _device_metadata(self, mapping: ResolvedDeviceMapping) -> dict[str, Any]:
        identity = mapping.identity
        return {
            "kdl_orion_address": identity.orion_address,
            "gateway_identity": identity.gateway.stable_id,
            "dpls_base_address": identity.dpls.base_address,
            "dpls_address_count": identity.dpls.address_count,
            "transport_limitation": self.gateway_transport_limitation,
        }

    async def data_init(self) -> bool:
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_output_descriptions(self) -> list[dict[str, Any]]:
        return [self._outputs[number] for number in sorted(self._outputs)]

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        names = {spec.key: spec.name for spec in self.capability_requirements}
        return [
            {"sensor_id": key, "name": names[key], "device_class": None,
             "icon": "mdi:state-machine"}
            for key in self._zone_mappings
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        if not self._relay_mappings:
            raise ValueError("Output mappings are not configured")
        reader = S2000PPRuntimeReader(self.attr_client, self.attr_device_id)
        states = await reader.async_read_coils(
            tuple(item.modbus_address for item in self._relay_mappings.values())
        )
        outputs = {}
        for number, item in self._relay_mappings.items():
            output = dict(self._outputs[number])
            output["state"] = states[item.modbus_address]
            self._outputs[number] = output
            outputs[number] = output
        snapshot: dict[str, dict] = {"outputs": outputs}
        if self._zone_mappings:
            zone_states = await reader.async_read_zone_states(
                self._zone_mappings.values()
            )
            snapshot["state_sensors"] = {
                key: self._state_value(zone_states[item.gateway_object_number])
                for key, item in self._zone_mappings.items()
            }
        return snapshot

    @classmethod
    def _state_value(cls, state: S2000PPZoneState) -> dict[str, Any]:
        active = tuple(code for code in state.expanded_states if code != 0)
        return {
            "state": cls.STATE_NAMES.get(
                state.primary_state, f"unknown_{state.primary_state}"
            ),
            "primary_code": state.primary_state,
            "expanded_codes": state.expanded_states,
            "expanded_states": tuple(
                cls.STATE_NAMES.get(code, f"unknown_{code}") for code in active
            ),
        }

    async def get_output(self, out: int = 1) -> dict[str, Any]:
        if out not in self._relay_mappings:
            raise ValueError("Output is not configured")
        item = self._relay_mappings[out]
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_coils((item.modbus_address,))
        output = dict(self._outputs[out])
        output["state"] = states[item.modbus_address]
        self._outputs[out] = output
        return output

    async def get_outputs(self, outputs: list[int] | None = None) -> list[dict[str, Any]]:
        selected = outputs or sorted(self._relay_mappings)
        if set(selected) - self._relay_mappings.keys():
            raise ValueError("Output is not configured")
        return [await self.get_output(number) for number in selected]

    async def set_output(self, output: int = 1, value: bool = False) -> dict[str, Any]:
        if output not in self._relay_mappings:
            raise ValueError("Output is not configured")
        address = self._relay_mappings[output].modbus_address
        response = await self.attr_client.write_coil(
            address=address, value=value, device_id=self.attr_device_id
        )
        validate_fc05_response(
            response,
            address=address,
            value=bool(value),
            device_id=self.attr_device_id,
            operation=f"set {self.__class__.__name__} output {output}",
        )
        if getattr(response, "address", None) != address:
            raise ModbusException("FC05 response does not echo the requested address")
        echoed = getattr(response, "value", None)
        accepted_values = ({True, 0xFF00} if value else {False, 0x0000})
        if echoed not in accepted_values:
            raise ModbusException("FC05 response does not echo the requested value")
        updated = dict(self._outputs[output])
        updated["state"] = bool(value)
        self._outputs[output] = updated
        return updated

    async def set_outputs(
        self,
        outputs: list[int] | None = None,
        values: list[bool] | None = None,
    ) -> list[dict[str, Any]]:
        if values is None:
            return []
        selected = outputs or sorted(self._relay_mappings)
        return [
            await self.set_output(number, value)
            for number, value in zip(selected, values)
        ]


class C2000RRM(BolidDPLSOutputBase):
    """Two-output radio relay module С2000Р-РМ and исп.01."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-РМ"
    model_name = "С2000Р-РМ"
    description = "Radio relay module"
    dpls_address_count = 2
    variant_optional = False
    variants = {"standard": "С2000Р-РМ", "isp_01": "С2000Р-РМ исп.01"}
    topologies = {
        "outputs_only": "Two relay outputs",
        "outputs_and_input": "Two relay outputs + controlled circuit",
    }
    topology_dpls_address_counts = {"outputs_only": 2, "outputs_and_input": 3}
    supported_controlled_circuit_kdl_input_types = (
        1, 2, 3, 4, 5, 6, 7, 11, 16, 17, 18, 21, 22
    )
    capability_requirements = (
        GatewayCapabilitySpec(
            key="relay_1", name="Relay 1", object_kind=ObjectKind.RELAY,
            local_object_number=0, local_object_offset=0,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="relay_2", name="Relay 2", object_kind=ObjectKind.RELAY,
            local_object_number=0, local_object_offset=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="controlled_circuit", name="Controlled circuit state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=2, zone_type=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
    )
    output_specs = {
        "relay_1": (1, "Relay 1", "Relay"),
        "relay_2": (2, "Relay 2", "Relay"),
    }

    @classmethod
    def get_gateway_capabilities_for_metadata(
        cls, metadata: Any
    ) -> tuple[GatewayCapabilitySpec, ...]:
        """Expose only the objects owned by the selected topology."""
        if metadata.topology == "outputs_and_input":
            return cls.capability_requirements
        return cls.capability_requirements[:2]

    def _validate_configuration(self, mapping: ResolvedDeviceMapping) -> None:
        variant = mapping.identity.metadata.variant
        topology = mapping.identity.metadata.topology
        if variant not in self.variants or topology not in self.topologies:
            raise ValueError("C2000RRM requires a supported variant and topology")
        if variant == "isp_01" and topology != "outputs_only":
            raise ValueError("С2000Р-РМ исп.01 does not support a controlled circuit")
        expected = self.topology_dpls_address_counts[topology]
        if mapping.identity.dpls.address_count != expected:
            raise ValueError("C2000RRM DPLS range does not match its topology")

    def _validate_resolved_capabilities(
        self, mapping: ResolvedDeviceMapping, resolved: dict[str, ResolvedObjectMapping]
    ) -> None:
        wants_input = mapping.identity.metadata.topology == "outputs_and_input"
        if ("controlled_circuit" in resolved) != wants_input:
            raise ValueError("C2000RRM controlled-circuit mapping does not match topology")

    def _device_metadata(self, mapping: ResolvedDeviceMapping) -> dict[str, Any]:
        return {
            **super()._device_metadata(mapping),
            "variant": self.variants[mapping.identity.metadata.variant],
            "topology": mapping.identity.metadata.topology,
            "supported_controlled_circuit_kdl_input_types": (
                self.supported_controlled_circuit_kdl_input_types
            ),
        }


class C2000RSirena(BolidDPLSOutputBase):
    """Independent light and sound outputs of С2000Р-Сирена."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-Сирена"
    model_name = "С2000Р-Сирена"
    description = "Radio light and sound annunciator"
    dpls_address_count = 2
    capability_requirements = (
        GatewayCapabilitySpec(
            key="light", name="Light", object_kind=ObjectKind.RELAY,
            local_object_number=0, local_object_offset=0,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="sound", name="Sound", object_kind=ObjectKind.RELAY,
            local_object_number=0, local_object_offset=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    output_specs = {
        "light": (1, "Light", "Output"),
        "sound": (2, "Sound", "Output"),
    }

    def _validate_configuration(self, mapping: ResolvedDeviceMapping) -> None:
        if mapping.identity.dpls.address_count != 2:
            raise ValueError("C2000RSirena requires two DPLS addresses")


class BolidDPLSWaterDetectorBase:
    """Shared one-row S2000-PP mechanics for distinct water detectors."""

    required_gateway = GatewayType.S2000_PP
    uses_dpls_identity = True
    dpls_address_count = 1
    variants: dict[str, str] = {}
    variant_metadata: dict[str, dict[str, Any]] = {}
    STATE_NAMES = {**C2000KPB.STATE_NAMES, 79: "water_alarm", 80: "water_alarm_restored"}
    capability_requirements = (
        GatewayCapabilitySpec(
            key="water_leak_state", name="Water leak state",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=0, zone_type=1,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    gateway_transport_limitation = (
        "S2000-PP does not expose configured KDL input type, DPLS voltage, ADC, "
        "serial, actual firmware, hardware revision, or address programming"
    )
    description = "Addressable water leak detector"
    battery_state_groups: dict[str, tuple[int, ...]] = {}

    def __init__(self, client, device_id) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = self.equipment_model
        self.attr_description = self.description
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._state_mapping: ResolvedObjectMapping | None = None

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        return cls.capability_requirements

    @classmethod
    def get_variant_options(cls) -> dict[str, str]:
        return dict(cls.variants)

    @classmethod
    def reconcile_gateway_mapping(
        cls,
        mapping: ResolvedDeviceMapping,
        configuration: S2000PPConfiguration,
    ) -> ResolvedDeviceMapping:
        """Resolve one exact DPLS row without using its partition as identity."""
        identity = mapping.identity
        dpls = identity.dpls
        if dpls is None or dpls.address_count != 1:
            raise ValueError("Water detector requires one DPLS address")
        matches = [
            row
            for row in configuration.zones_for_device(identity.orion_address)
            if row.local_zone_number == dpls.base_address and row.zone_type == 1
        ]
        if len(matches) != 1:
            raise ValueError(
                "Water detector mapping does not match one unambiguous zone-type-1 row"
            )
        row = matches[0]
        return ResolvedDeviceMapping(
            identity,
            mapping.source,
            (
                resolve_zone_row(
                    row,
                    configuration.partition_id(row.partition_number),
                ),
            ),
        )

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        identity = mapping.identity
        if identity.model != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match water detector")
        if identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match water detector")
        dpls = identity.dpls
        if dpls is None or dpls.address_count != 1:
            raise ValueError("Water detector requires exactly one DPLS address")
        if identity.metadata.variant not in {None, *self.variants}:
            raise ValueError("Unsupported water-detector variant")
        if len(mapping.objects) != 1:
            raise ValueError("Water detector requires exactly one own zone mapping")
        item = mapping.objects[0]
        if (
            item.object_kind is not ObjectKind.ZONE
            or item.local_object_number != dpls.base_address
            or item.zone_details is None
            or item.zone_details.zone_type != 1
            or item.data_area is not ModbusDataArea.HOLDING_REGISTER
        ):
            raise ValueError(
                "Water detector mapping must be zone type 1 at its DPLS address"
            )
        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = identity.stable_id
        self.attr_unique_id_prefix = identity.stable_id
        metadata = self.variant_metadata.get(identity.metadata.variant, {})
        self.attr_device_metadata = {
            "variant": identity.metadata.variant,
            **metadata,
            "kdl_orion_address": identity.orion_address,
            "gateway_identity": identity.gateway.stable_id,
            "dpls_address": dpls.base_address,
            "transport_limitation": self.gateway_transport_limitation,
        }
        self._state_mapping = item
        self.attr_platforms = [Platform.SENSOR, Platform.BINARY_SENSOR]

    async def data_init(self) -> bool:
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        if self._state_mapping is None:
            return []
        descriptions = [{
            "sensor_id": "water_leak_state", "name": "Water leak state",
            "device_class": None, "icon": "mdi:water-alert",
            "entity_category": EntityCategory.DIAGNOSTIC,
        }]
        for key in self.battery_state_groups:
            descriptions.append({
                "sensor_id": key,
                "name": key.replace("_", " ").title(),
                "device_class": None,
                "icon": "mdi:battery-check",
            })
        return descriptions

    def get_binary_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Expose only the documented water alarm/restored binary semantic."""
        return [] if self._state_mapping is None else [{
            "sensor_id": "water_leak",
            "name": "Water leak",
            "device_class": BinarySensorDeviceClass.MOISTURE,
        }]

    async def async_get_snapshot(self) -> dict[str, dict]:
        if self._state_mapping is None:
            raise ValueError("Water-detector zone mapping is not configured")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states((self._state_mapping,))
        state = states[self._state_mapping.gateway_object_number]
        active = tuple(code for code in state.expanded_states if code != 0)
        raw_state = {
            "state": self.STATE_NAMES.get(
                state.primary_state, f"unknown_{state.primary_state}"
            ),
            "primary_code": state.primary_state,
            "expanded_codes": state.expanded_states,
            "expanded_states": tuple(
                self.STATE_NAMES.get(code, f"unknown_{code}") for code in active
            ),
        }
        state_sensors = {"water_leak_state": raw_state}
        for key, codes in self.battery_state_groups.items():
            code = next((item for item in active if item in codes), None)
            state_sensors[key] = {
                "state": None if code is None else self.STATE_NAMES.get(
                    code, f"unknown_{code}"
                ),
                "primary_code": state.primary_state,
                "expanded_codes": state.expanded_states,
                "expanded_states": raw_state["expanded_states"],
            }
        water_state = (
            True if state.primary_state == 79
            else False if state.primary_state == 80
            else None
        )
        return {
            "state_sensors": state_sensors,
            "binary_sensors": {"water_leak": {
                "state": water_state,
                "primary_code": state.primary_state,
                "expanded_codes": state.expanded_states,
            }},
        }


class C2000DZ(BolidDPLSWaterDetectorBase):
    """One-address wired water-leak detector С2000-ДЗ."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-ДЗ"
    variant_optional = True
    variants = {
        "v1_06": "С2000-ДЗ 1.06",
        "v1_10": "С2000-ДЗ 1.10",
        "v1_13": "С2000-ДЗ 1.13",
    }
    variant_metadata = {
        "v1_06": {"dpls_current": "≤0.5 mA", "galvanic_isolation": False},
        "v1_10": {"dpls_current": "≤1 mA", "galvanic_isolation": True},
        "v1_13": {"dpls_current": "≤0.5 mA", "galvanic_isolation": True},
    }
    supported_kdl_input_types = (6, 17)
    documented_classic_kdl_minimum = "2.10"

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Keep wired-only static metadata without adding radio capabilities."""
        super().apply_gateway_mapping(mapping)
        self.attr_device_metadata.update({
            "supported_kdl_input_types": self.supported_kdl_input_types,
            "documented_classic_kdl_minimum": self.documented_classic_kdl_minimum,
        })


class C2000RDZ(BolidDPLSWaterDetectorBase):
    """Ordinary two-battery radio water-leak detector С2000Р-ДЗ."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-ДЗ"
    description = "Radio water leak detector"
    documented_firmware_family = (
        "1.00", "1.01", "1.02", "1.03", "1.04", "1.05", "1.06"
    )
    battery_state_groups = {
        "main_battery_state": (200, 211, 202),
        "reserve_battery_state": (213, 212),
    }

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Attach documented metadata without guessing actual runtime versions."""
        super().apply_gateway_mapping(mapping)
        self.attr_device_metadata.update({
            "battery_topology": "main_and_reserve_cr2450",
            "documented_firmware_family": self.documented_firmware_family,
            "tamper_capability": "documented_pp_routing_deferred",
            "radio_supervision": "documented_product_specific_routing_deferred",
        })


class BolidDPLSNumericDeviceBase:
    """Shared mechanics for distinct DPLS devices exposing numeric zones.

    The generic snapshot contract treats numeric protocol errors as fatal. A
    concrete family may isolate optional numeric result exceptions only in an
    override that explicitly invokes ``_handle_optional_numeric_protocol_error``.
    """

    required_gateway = GatewayType.S2000_PP
    uses_dpls_identity = True
    gateway_transport_supported = True
    capability_requirements: tuple[GatewayCapabilitySpec, ...] = ()
    numeric_kinds: dict[str, NumericParameterKind] = {}
    numeric_metadata: dict[str, tuple[Any, str, int]] = {}
    variants: dict = {}
    variant_dpls_address_counts: dict[str, int] = {}
    STATE_NAMES = C2000KPB.STATE_NAMES

    def __init__(self, client, device_id) -> None:
        if self.__class__ is BolidDPLSNumericDeviceBase:
            raise TypeError("BolidDPLSNumericDeviceBase is not equipment")
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = self.__class__.__name__
        self.attr_description = "DPLS numeric device"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._numeric_mappings: dict[str, ResolvedObjectMapping] = {}
        self._numeric_values: dict[str, dict[str, Any]] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        return cls.capability_requirements

    @classmethod
    def get_variant_options(cls) -> dict[str, str]:
        return {
            variant.value: metadata.display_name
            for variant, metadata in cls.variants.items()
        }

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        if not self.gateway_transport_supported:
            raise ValueError(self.gateway_transport_limitation)
        if mapping.identity.model != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match equipment")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match equipment")
        identity = mapping.identity
        if identity.dpls is None:
            raise ValueError("Numeric DPLS equipment requires nested DPLS identity")
        try:
            variant = self.Variant(identity.metadata.variant)
            metadata = self.variants[variant]
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError("Unsupported or missing equipment variant") from exc
        expected_count = self.variant_dpls_address_counts[variant.value]
        if identity.dpls.address_count != expected_count:
            raise ValueError("DPLS address count does not match equipment variant")

        specs = {
            (
                spec.resolved_local_object_number(identity.dpls.base_address),
                spec.zone_type,
            ): spec
            for spec in self.capability_requirements
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            zone_type = None if item.zone_details is None else item.zone_details.zone_type
            spec = specs.get((item.local_object_number, zone_type))
            if (
                spec is None
                or item.object_kind is not ObjectKind.ZONE
                or item.data_area is not ModbusDataArea.HOLDING_REGISTER
            ):
                raise ValueError("Mapping contains an unsupported numeric DPLS object")
            if spec.key in resolved:
                raise ValueError("Duplicate numeric capability mapping")
            resolved[spec.key] = item
        if not resolved:
            raise ValueError("Numeric DPLS mapping must configure at least one capability")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = identity.stable_id
        self.attr_unique_id_prefix = identity.stable_id
        self.attr_model_name = metadata.display_name
        self.attr_device_metadata = {
            **metadata.device_metadata,
            "kdl_orion_address": identity.orion_address,
            "dpls_base_address": identity.dpls.base_address,
        }
        self._numeric_mappings = resolved
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        if self.attr_gateway_mapping is None:
            raise ValueError("Equipment requires a validated S2000-PP mapping")
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
        descriptions = []
        for key in self._numeric_mappings:
            device_class, unit, precision = self.numeric_metadata[key]
            descriptions.append(
                {
                    "sensor_id": key,
                    "name": self._capability(key).name,
                    "device_class": device_class,
                    "state_class": SensorStateClass.MEASUREMENT,
                    "unit": unit,
                    "precision": precision,
                }
            )
        return descriptions

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        return [
            {
                "sensor_id": f"{key}_state",
                "name": f"{self._capability(key).name} state",
                "device_class": None,
                "icon": "mdi:state-machine",
                "entity_category": EntityCategory.DIAGNOSTIC,
            }
            for key in self._numeric_mappings
        ]

    def _capability(self, key: str) -> GatewayCapabilitySpec:
        return next(item for item in self.capability_requirements if item.key == key)

    async def async_get_snapshot(self) -> dict[str, dict]:
        mapping = self.attr_gateway_mapping
        reader = S2000PPNumericValueReader(
            self.attr_client,
            self.attr_device_id,
            mapping.identity.gateway.stable_id,
        )
        for key, item in self._numeric_mappings.items():
            result = await reader.async_read(
                item.gateway_object_number, self.numeric_kinds[key]
            )
            if result.status is NumericResultStatus.READY:
                self._numeric_values[key] = {
                    "value": result.value,
                    "raw_register": result.raw_register,
                    "parameter_kind": result.parameter_kind.value,
                }
            elif result.status is NumericResultStatus.PROTOCOL_ERROR:
                raise ModbusException(result.message or "numeric protocol error")

        zone_states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states(self._numeric_mappings.values())
        return {
            "numeric_sensors": {
                key: dict(value) for key, value in self._numeric_values.items()
            },
            "state_sensors": {
                f"{key}_state": self._state_sensor_value(
                    zone_states[item.gateway_object_number]
                )
                for key, item in self._numeric_mappings.items()
            },
        }

    def _state_sensor_value(self, state: S2000PPZoneState) -> dict[str, Any]:
        active = tuple(code for code in state.expanded_states if code != 0)
        return {
            "state": self.STATE_NAMES.get(
                state.primary_state, f"unknown_{state.primary_state}"
            ),
            "primary_code": state.primary_state,
            "expanded_codes": state.expanded_states,
            "expanded_states": tuple(
                self.STATE_NAMES.get(code, f"unknown_{code}") for code in active
            ),
        }


class BolidDPLSThermohygrometerBase(BolidDPLSNumericDeviceBase):
    """Shared two-zone S2000-PP mechanics for distinct thermohygrometers."""

    capability_requirements = (
        GatewayCapabilitySpec(
            key="temperature", name="Temperature", object_kind=ObjectKind.ZONE,
            local_object_number=0, local_object_offset=0,
            zone_type=6,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
        GatewayCapabilitySpec(
            key="humidity", name="Humidity", object_kind=ObjectKind.ZONE,
            local_object_number=0, local_object_offset=1,
            zone_type=6,
            requirement=CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        ),
    )
    numeric_kinds = {
        "temperature": NumericParameterKind.TEMPERATURE,
        "humidity": NumericParameterKind.RELATIVE_HUMIDITY,
    }
    numeric_metadata = {
        "temperature": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 1),
        "humidity": (SensorDeviceClass.HUMIDITY, PERCENTAGE, 0),
    }

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        self._numeric_cursor = 0

    @classmethod
    def reconcile_gateway_mapping(
        cls,
        mapping: ResolvedDeviceMapping,
        configuration: S2000PPConfiguration,
    ) -> ResolvedDeviceMapping:
        """Repair a partial VT mapping only from its exact two-address footprint."""
        identity = mapping.identity
        dpls = identity.dpls
        if dpls is None or dpls.address_count != 2:
            raise ValueError("Thermohygrometer requires one two-address DPLS identity")
        rows = configuration.zones_for_device(identity.orion_address)
        resolved = []
        for address in (dpls.base_address, dpls.base_address + 1):
            matches = [
                row for row in rows
                if row.local_zone_number == address and row.zone_type == 6
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Thermohygrometer mapping does not match one unambiguous adjacent "
                    "temperature/humidity footprint"
                )
            row = matches[0]
            resolved.append(
                resolve_zone_row(
                    row,
                    configuration.partition_id(row.partition_number),
                )
            )
        return ResolvedDeviceMapping(identity, mapping.source, tuple(resolved))

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Require both logical channels of one physical thermohygrometer."""
        super().apply_gateway_mapping(mapping)
        if set(self._numeric_mappings) != {"temperature", "humidity"}:
            raise ValueError(
                "Thermohygrometer requires both temperature and humidity channels"
            )

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Poll grouped states and one numeric channel per coordinator refresh."""
        mapping = self.attr_gateway_mapping
        if mapping is None:
            raise ValueError("Equipment requires a validated S2000-PP mapping")
        zone_states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_zone_states(self._numeric_mappings.values())

        keys = ("temperature", "humidity")
        key = keys[self._numeric_cursor]
        item = self._numeric_mappings[key]
        _LOGGER.debug(
            "%s numeric poll channel=%s PP-row=%s cursor=%s",
            self.__class__.__name__,
            key,
            item.gateway_object_number,
            self._numeric_cursor,
        )
        result = await S2000PPNumericValueReader(
            self.attr_client,
            self.attr_device_id,
            mapping.identity.gateway.stable_id,
        ).async_read(item.gateway_object_number, self.numeric_kinds[key])
        _LOGGER.debug(
            "%s numeric result channel=%s PP-row=%s status=%s "
            "exception=%s raw=%s decoded=%s",
            self.__class__.__name__,
            key,
            item.gateway_object_number,
            result.status.value,
            result.exception_code,
            result.raw_register,
            result.value,
        )
        if result.status is NumericResultStatus.READY:
            self._numeric_values[key] = {
                "value": result.value,
                "raw_register": result.raw_register,
                "parameter_kind": result.parameter_kind.value,
            }
            self._numeric_cursor = (self._numeric_cursor + 1) % len(keys)
            _LOGGER.debug(
                "%s numeric cursor advanced channel=%s next=%s",
                self.__class__.__name__,
                key,
                keys[self._numeric_cursor],
            )
        elif result.status is NumericResultStatus.PROTOCOL_ERROR:
            _handle_optional_numeric_protocol_error(self, key, item, result)

        return {
            "numeric_sensors": {
                sensor_id: dict(value)
                for sensor_id, value in self._numeric_values.items()
            },
            "state_sensors": {
                f"{sensor_id}_state": self._state_sensor_value(
                    zone_states[channel.gateway_object_number]
                )
                for sensor_id, channel in self._numeric_mappings.items()
            },
        }


class C2000VT(BolidDPLSThermohygrometerBase):
    """Bolid С2000-ВТ and С2000-ВТ исп.01 DPLS thermohygrometers."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-ВТ"
    dpls_address_count = 2

    class Variant(str, Enum):
        VT = "vt"
        VT_01 = "vt_01"

    @dataclass(frozen=True, slots=True)
    class VariantMetadata:
        display_name: str
        temperature_accuracy: str
        humidity_accuracy: str

        @property
        def device_metadata(self) -> dict[str, Any]:
            return {
                "variant": self.display_name,
                "temperature_range": "-30…+55 °C",
                "temperature_accuracy": self.temperature_accuracy,
                "temperature_resolution": "0.1 °C",
                "humidity_range": "0…100 %",
                "humidity_accuracy": self.humidity_accuracy,
                "humidity_resolution": "1 %",
            }

    variants = {
        Variant.VT: VariantMetadata("С2000-ВТ", "±0.5 °C", "±5 %"),
        Variant.VT_01: VariantMetadata("С2000-ВТ исп.01", "±0.4 °C", "±3 %"),
    }
    variant_dpls_address_counts = {"vt": 2, "vt_01": 2}

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        self.attr_model_name = "С2000-ВТ"
        self.attr_description = "Addressable temperature and humidity sensor"


class C2000VTI(C2000VT):
    """Bolid С2000-ВТИ and С2000-ВТИ исп.01 display thermohygrometers."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-ВТИ"
    dpls_address_count = 3
    unsupported_variants = {
        "vti_01": "С2000-ВТИ исп.01 CO channel is not hardware validated"
    }

    class Variant(str, Enum):
        VTI = "vti"
        VTI_01 = "vti_01"

    @dataclass(frozen=True, slots=True)
    class VariantMetadata:
        display_name: str
        has_co_sensor: bool
        has_local_sounder: bool

        @property
        def device_metadata(self) -> dict[str, Any]:
            return {
                "variant": self.display_name,
                "temperature_range": "-10…+55 °C",
                "temperature_accuracy": "±0.4 °C",
                "temperature_resolution": "0.1 °C",
                "humidity_range": "0…100 %",
                "humidity_accuracy": "±3 %",
                "humidity_resolution": "0.1 %",
                "local_lcd": True,
                "co_sensor": self.has_co_sensor,
                "local_sounder": self.has_local_sounder,
                "remote_sounder_control": False,
            }

    variants = {
        Variant.VTI: VariantMetadata("С2000-ВТИ", False, False),
        Variant.VTI_01: VariantMetadata("С2000-ВТИ исп.01", True, True),
    }
    variant_dpls_address_counts = {"vti": 2, "vti_01": 3}
    capability_requirements = C2000VT.capability_requirements + (
        GatewayCapabilitySpec(
            key="co_concentration", name="CO concentration",
            object_kind=ObjectKind.ZONE, local_object_number=0,
            local_object_offset=2, zone_type=6,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
    )
    numeric_kinds = {
        **C2000VT.numeric_kinds,
        "co_concentration": NumericParameterKind.CO_CONCENTRATION,
    }
    numeric_metadata = {
        **C2000VT.numeric_metadata,
        "co_concentration": (None, "ppm", 0),
    }

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        self.attr_model_name = "С2000-ВТИ"
        self.attr_description = "Addressable display thermohygrometer"

    @classmethod
    def reconcile_gateway_mapping(
        cls,
        mapping: ResolvedDeviceMapping,
        configuration: S2000PPConfiguration,
    ) -> ResolvedDeviceMapping:
        """Reconcile only the hardware-confirmed two-channel VTI variant."""
        if mapping.identity.metadata.variant != cls.Variant.VTI.value:
            raise ValueError("C2000-VTI isp.01 requires separate CO validation")
        return super().reconcile_gateway_mapping(mapping, configuration)

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Apply the shared VT contract only to ordinary C2000-VTI."""
        if mapping.identity.metadata.variant != self.Variant.VTI.value:
            raise ValueError("C2000-VTI isp.01 requires separate CO validation")
        super().apply_gateway_mapping(mapping)


class C2000RVTI(BolidDPLSThermohygrometerBase):
    """Bolid С2000Р-ВТИ two-zone radio thermohygrometer.

    The wired and radio products share only the documented S2000-PP
    temperature/humidity acquisition mechanics.  Their registry identity,
    metadata, and radio-only battery capability remain separate.
    """

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000Р-ВТИ"
    dpls_address_count = 2

    class Variant(str, Enum):
        RVTI = "rvti"

    @dataclass(frozen=True, slots=True)
    class VariantMetadata:
        display_name: str

        @property
        def device_metadata(self) -> dict[str, Any]:
            return {
                "variant": self.display_name,
                "temperature_range": "-10…+55 °C",
                "temperature_resolution": "0.1 °C",
                "humidity_indication_range": "0…100 %",
                "humidity_measurement_range": "20…80 %",
                "humidity_resolution": "0.1 %",
                "battery_topology": "one_er14505_3_6_v",
                "radio_supervision": "documented_pp_routing_deferred",
                "tamper_capability": "pp_routing_not_validated",
            }

    variants = {
        Variant.RVTI: VariantMetadata("С2000Р-ВТИ"),
    }
    variant_dpls_address_counts = {"rvti": 2}
    capability_requirements = BolidDPLSThermohygrometerBase.capability_requirements
    numeric_kinds = BolidDPLSThermohygrometerBase.numeric_kinds
    numeric_metadata = {
        "temperature": (
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            1,
        ),
        "humidity": (SensorDeviceClass.HUMIDITY, PERCENTAGE, 1),
    }
    battery_state_codes = frozenset((200, 202, 211))

    def __init__(self, client, device_id) -> None:
        super().__init__(client, device_id)
        self.attr_model_name = "С2000Р-ВТИ"
        self.attr_description = "Radio display thermohygrometer"

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Apply the two-zone contract with a product-specific new identity."""
        super().apply_gateway_mapping(mapping)
        identity = f"{mapping.identity.stable_id}:model:{self.__class__.__name__}"
        self.attr_device_identifier = identity
        self.attr_unique_id_prefix = identity

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Expose two zone states and one physical main-battery state."""
        return [
            *super().get_state_sensor_descriptions(),
            {
                "sensor_id": "main_battery_state",
                "name": "Main battery state",
                "device_class": None,
                "icon": "mdi:battery-check",
                "entity_category": EntityCategory.DIAGNOSTIC,
            },
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Aggregate the duplicated radio battery state into one entity."""
        snapshot = await super().async_get_snapshot()
        channel_states = snapshot["state_sensors"]
        expanded_codes = tuple(
            code
            for key in ("temperature_state", "humidity_state")
            for code in channel_states[key]["expanded_codes"]
            if code != 0
        )
        battery_codes = tuple(
            dict.fromkeys(
                code for code in expanded_codes if code in self.battery_state_codes
            )
        )
        battery_code = battery_codes[0] if len(battery_codes) == 1 else None
        expanded_states = tuple(
            self.STATE_NAMES.get(code, f"unknown_{code}")
            for code in dict.fromkeys(expanded_codes)
        )
        channel_states["main_battery_state"] = {
            "state": (
                None
                if battery_code is None
                else self.STATE_NAMES.get(
                    battery_code, f"unknown_{battery_code}"
                )
            ),
            "primary_code": battery_code,
            "expanded_codes": expanded_codes,
            "expanded_states": expanded_states,
        }
        return snapshot


class C2000SP2:
    """Bolid C2000-SP2 DPLS relay-state equipment."""

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-СП2"
    required_gateway = GatewayType.S2000_PP
    uses_dpls_identity = True
    dpls_address_count = 2
    variant_optional = True
    documented_firmware = "1.21"
    topologies = {
        "one_output": "One relay output",
        "two_outputs": "Two relay outputs",
    }
    topology_dpls_address_counts = {"one_output": 1, "two_outputs": 2}
    capability_requirements = (
        GatewayCapabilitySpec(
            key="relay_1",
            name="Relay 1 state",
            object_kind=ObjectKind.RELAY,
            local_object_number=0,
            local_object_offset=0,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
        GatewayCapabilitySpec(
            key="relay_2",
            name="Relay 2 state",
            object_kind=ObjectKind.RELAY,
            local_object_number=0,
            local_object_offset=1,
            requirement=CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        ),
    )

    def __init__(self, client, device_id) -> None:
        """Initialize the read-only DPLS relay-state model."""
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "Bolid"
        self.attr_model_name = "С2000-СП2"
        self.attr_description = "Addressable two-relay signal/start unit"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time: datetime | None = None
        self.attr_platforms: list[Platform] = []
        self.attr_gateway_mapping: ResolvedDeviceMapping | None = None
        self.attr_device_identifier: str | None = None
        self.attr_unique_id_prefix: str | None = None
        self.attr_device_metadata: dict[str, Any] = {}
        self._relay_mappings: dict[str, ResolvedObjectMapping] = {}

    @classmethod
    def get_gateway_capabilities(cls) -> tuple[GatewayCapabilitySpec, ...]:
        """Return both relay-state capabilities."""
        return cls.capability_requirements

    @classmethod
    def get_gateway_capabilities_for_metadata(
        cls, metadata: Any
    ) -> tuple[GatewayCapabilitySpec, ...]:
        """Return relay states owned by the selected address topology."""
        if metadata.topology == "one_output":
            return cls.capability_requirements[:1]
        if metadata.topology == "two_outputs":
            return cls.capability_requirements
        raise ValueError("C2000-SP2 requires a supported topology")

    def apply_gateway_mapping(self, mapping: ResolvedDeviceMapping) -> None:
        """Validate and apply exact DPLS relay ownership."""
        if canonical_equipment_class_name(mapping.identity.model) != self.__class__.__name__:
            raise ValueError("Gateway mapping model does not match C2000-SP2")
        if mapping.identity.gateway.gateway_type is not self.required_gateway:
            raise ValueError("Gateway mapping type does not match C2000-SP2")
        dpls = mapping.identity.dpls
        if dpls is None:
            raise ValueError("C2000-SP2 requires a DPLS identity")
        metadata = mapping.identity.metadata
        expected_count = self.topology_dpls_address_counts.get(metadata.topology)
        if expected_count is None or dpls.address_count != expected_count:
            raise ValueError("C2000-SP2 DPLS range does not match its topology")

        capabilities = self.get_gateway_capabilities_for_metadata(metadata)
        accepted = {
            spec.resolved_local_object_number(dpls.base_address): spec
            for spec in capabilities
        }
        resolved: dict[str, ResolvedObjectMapping] = {}
        for item in mapping.objects:
            spec = accepted.get(item.local_object_number)
            if (
                item.object_kind is not ObjectKind.RELAY
                or spec is None
                or item.data_area is not ModbusDataArea.COIL
            ):
                raise ValueError("Mapping contains an unsupported C2000-SP2 object")
            if spec.key in resolved:
                raise ValueError("Duplicate C2000-SP2 capability mapping")
            resolved[spec.key] = item
        if not resolved:
            raise ValueError("C2000-SP2 mapping requires at least one relay state")

        self.attr_gateway_mapping = mapping
        self.attr_device_identifier = mapping.identity.stable_id
        self.attr_unique_id_prefix = mapping.identity.stable_id
        self.attr_device_metadata = {
            "documented_firmware": self.documented_firmware,
            "kdl_orion_address": mapping.identity.orion_address,
            "gateway_identity": mapping.identity.gateway.stable_id,
            "dpls_base_address": dpls.base_address,
            "dpls_address_count": dpls.address_count,
            "topology": metadata.topology,
            "control_limitation": (
                "Relay control is not exposed because S2000-PP permits control only "
                "when outputs are not owned by internal tactics or S2000M scenarios"
            ),
        }
        self._relay_mappings = resolved
        self.attr_platforms = [Platform.SENSOR]

    async def data_init(self) -> bool:
        """Initialize local metadata; coordinator owns runtime polling."""
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return service fields visible through this transport."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_state_sensor_descriptions(self) -> list[dict[str, Any]]:
        """Describe configured authoritative relay states."""
        names = {spec.key: spec.name for spec in self.capability_requirements}
        return [
            {
                "sensor_id": key,
                "name": names[key],
                "device_class": None,
                "icon": "mdi:electric-switch",
            }
            for key in self._relay_mappings
        ]

    async def async_get_snapshot(self) -> dict[str, dict]:
        """Read configured relay states into one coordinator snapshot."""
        if not self._relay_mappings:
            raise ValueError("C2000-SP2 requires a validated S2000-PP mapping")
        states = await S2000PPRuntimeReader(
            self.attr_client, self.attr_device_id
        ).async_read_coils(
            tuple(item.modbus_address for item in self._relay_mappings.values())
        )
        return {
            "state_sensors": {
                key: {
                    "state": "on" if states[item.modbus_address] else "off",
                    "primary_code": 1 if states[item.modbus_address] else 0,
                    "expanded_codes": (),
                    "expanded_states": (),
                }
                for key, item in self._relay_mappings.items()
            }
        }


class C2000SP4:
    """Bolid C2000-SP4 family equipment.

    Supported variants: С2000-СП4/24, С2000-СП4/24 исп.01,
    С2000-СП4/220 and С2000-СП4/220 исп.01.
    С2000-СП4/220 исп.02 is explicitly not supported.
    """

    equipment_manufacturer = "Bolid"
    equipment_model = "С2000-СП4/24(220)"
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
        validate_fc05_response(
            result,
            address=attr["address"],
            value=bool(value),
            device_id=self.attr_device_id,
            operation=f"set C2000-SP4 output {output}",
        )

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


EQUIPMENT_CLASSES = (
    C20002,
    C20004,
    C2000BKI,
    C2000DZ,
    C2000IP03,
    C2000KDL,
    C2000KPB,
    C2000RARR125,
    C2000RDZ,
    C2000RDIP,
    C2000RIP,
    C2000RRM,
    C2000RSMK,
    C2000RST01,
    C2000RSirena,
    C2000RVTI,
    C2000SMK,
    C2000SP2,
    C2000SP4,
    C2000ST04,
    C2000VT,
    C2000VTI,
    DIP34A05,
    M3000BB1020,
    MIP24Isp20,
    Signal20M,
    S2000PP,
    SVK15_3_2_B,
    SVK15_3_8_1_B3,
)
