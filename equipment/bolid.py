"""Классы описывают содержание каждого прибора."""

from datetime import datetime, timedelta, timezone
from logging import getLogger
from typing import Any

from custom_components.modbus_devices.const import Config
from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusUdpClient,
)

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform

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

    async def set_time(self) -> datetime:
        """Устанавливает дату и время в контроллер."""
        time_values: list = []
        for num in range(6):
            value = datetime.now().timetuple()
            time_values.append(value[num])
        await self.attr_client.write_registers(
            address=60007, values=time_values, device_id=self.attr_device_id
        )
        self.attr_init_time = await self.get_time()
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
        attr["state"] = (
            await self.attr_client.write_coil(
                address=attr["address"], value=value, device_id=self.attr_device_id
            )
        ).bits[0]
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
                attr["state"] = (
                    await self.attr_client.write_coil(
                        address=attr["address"],
                        value=values[index],
                        device_id=self.attr_device_id,
                    )
                ).bits[0]
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
