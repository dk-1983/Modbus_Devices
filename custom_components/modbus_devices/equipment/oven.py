"""Классы описывают содержание каждого прибора компании OVEN."""

from datetime import datetime, timedelta, timezone
from typing import Any

from custom_components.modbus_devices.const import Config
from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusUdpClient,
)

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform, UnitOfTemperature


class TRM138:
    """OVEN TRM-138."""

    def __init__(self, client, device_id) -> None:
        """Inicialization variables."""
        self.attr_device_id: int = device_id
        self.attr_client: (
            AsyncModbusSerialClient | AsyncModbusTcpClient | AsyncModbusUdpClient | None
        ) = client
        self.attr_manufactures_name: str = "Oven"
        self.attr_model_name: str = "TRM-138"
        self.attr_device_type: int | None = None
        self.attr_serial_number: str | None = None
        self.attr_hardware_version: float | None = None
        self.attr_software_version: float | None = None
        self.attr_init_time: datetime | None = None
        self.attr_description: str = "Measuring regulator"
        self.attr_secret: str | None = None
        self.attr_clock_iter: list[int] = list(range(1, 2))
        self.attr_platforms: list[Platform] = [
            Platform.SENSOR,
        ]
        self.attr_ch1: dict[str, Any] = {
            "chanel_number": 1,
            "chanel_number_view": 1,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 0,
            "address_hex": hex(0x0000),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }
        self.attr_ch2: dict[str, Any] = {
            "chanel_number": 2,
            "chanel_number_view": 2,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 5,
            "address_hex": hex(0x0005),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }
        self.attr_ch3: dict[str, Any] = {
            "chanel_number": 3,
            "chanel_number_view": 3,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 10,
            "address_hex": hex(0x000A),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }
        self.attr_ch4: dict[str, Any] = {
            "chanel_number": 4,
            "chanel_number_view": 4,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 15,
            "address_hex": hex(0x000F),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }
        self.attr_ch5: dict[str, Any] = {
            "chanel_number": 5,
            "chanel_number_view": 5,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 20,
            "address_hex": hex(0x0014),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }
        self.attr_ch6: dict[str, Any] = {
            "chanel_number": 6,
            "chanel_number_view": 6,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 25,
            "address_hex": hex(0x0019),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }
        self.attr_ch7: dict[str, Any] = {
            "chanel_number": 7,
            "chanel_number_view": 7,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 30,
            "address_hex": hex(0x001E),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }
        self.attr_ch8: dict[str, Any] = {
            "chanel_number": 8,
            "chanel_number_view": 8,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": 35,
            "address_hex": hex(0x0023),
            "count": 5,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }

    async def data_init(self) -> bool:
        """Инициализирует все свойства класса."""
        await self.get_device_info()
        await self.get_chanels()
        return True

    async def get_device_info(self) -> list:
        """Получает информацию о текущем контроллере."""
        self.attr_init_time = (datetime.now()).replace(
            tzinfo=timezone(timedelta(hours=Config.TIME_ZONE)),
            microsecond=0,
        )
        self.attr_device_type = "Not supported"
        self.attr_software_version = "Not supported"
        self.attr_hardware_version = "Not supported"
        self.attr_serial_number = "Not supported"
        return True

    async def get_chanel(self, chanel: int) -> dict[str, Any]:
        """Получает аналоговые данные одного канала контроллера."""
        attr = getattr(self, f"attr_ch{chanel}")
        attr["value"] = (
            await self.attr_client.read_input_registers(
                address=attr["address"],
                count=attr["count"],
                device_id=self.attr_device_id,
            )
        ).registers
        setattr(self, f"attr_ch{chanel}", attr)
        return getattr(self, f"attr_ch{chanel}")

    async def get_chanels(
        self, chanels: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """Получает аналоговые данные всех или нескольких каналов контроллера."""
        data: list[dict[str, Any]] = []
        chanels = (chanels, (list(range(1, 9))))[chanels is None]
        for chanel in chanels:
            attr = getattr(self, f"attr_ch{chanel}")
            attr["value"] = (
                await self.attr_client.read_input_registers(
                    address=attr["address"],
                    count=attr["count"],
                    device_id=self.attr_device_id,
                )
            ).registers
            setattr(self, f"attr_ch{chanel}", attr)
            data.append(getattr(self, f"attr_ch{chanel}"))
        return data

    def __repr__(self) -> str:
        """Output representation information from Oven Class."""
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
            f"chanel 1: {self.attr_ch1['value']}, "
            f"chanel 2: {self.attr_ch2['value']}, "
            f"chanel 3: {self.attr_ch3['value']}, "
            f"chanel 4: {self.attr_ch4['value']}, "
            f"chanel 5: {self.attr_ch5['value']}, "
            f"chanel 6: {self.attr_ch6['value']}, "
            f"chanel 7: {self.attr_ch7['value']}, "
            f"chanel 8: {self.attr_ch8['value']}, "
            f"description: {self.attr_description}"
        )
