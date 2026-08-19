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
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform, UnitOfTemperature

from ..s2000_pp import validated_bits
from .equipment import validate_write_response


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


class PLC110_24_60_K_M:
    """OWEN ПЛК110-24.60.К-М with a user-program-defined Modbus slave map."""

    uses_stable_entry_identity = True
    input_count = 36
    output_count = 24
    fast_input_numbers = frozenset(range(1, 5))
    fast_output_numbers = frozenset(range(1, 5))
    manual_io_mapping_spec = {
        "di_data_areas": ("discrete_input", "coil"),
        "do_data_area": "coil",
        "input_count": input_count,
        "output_count": output_count,
    }

    def __init__(self, client, device_id) -> None:
        self.attr_client = client
        self.attr_device_id = device_id
        self.attr_manufactures_name = "OWEN"
        self.attr_model_name = "ПЛК110-24.60.К-М"
        self.attr_description = "Programmable logic controller"
        self.attr_device_type = None
        self.attr_serial_number = None
        self.attr_hardware_version = None
        self.attr_software_version = None
        self.attr_init_time = None
        self.attr_platforms = [Platform.BINARY_SENSOR, Platform.SWITCH]
        self.attr_unique_id_prefix = None
        self.attr_device_identifier = None
        self.attr_device_metadata = {
            "supply": "24 V DC",
            "total_io_points": 60,
            "digital_inputs": 36,
            "high_speed_inputs": "DI1…DI4",
            "digital_outputs": 24,
            "output_type": "NPN open collector transistor",
            "high_speed_outputs": "DO1…DO4",
            "maximum_output_current": "400 mA",
            "interfaces": "Ethernet/Modbus TCP; RS-485/Modbus RTU/ASCII",
            "modbus_map": "user-defined in CODESYS PLC Configuration",
        }
        self._io_mapping: dict[str, Any] | None = None
        self._inputs: dict[int, dict[str, Any]] = {}
        self._outputs: dict[int, dict[str, Any]] = {}

    def apply_io_mapping(self, mapping: dict[str, Any]) -> None:
        """Apply and validate the compact CODESYS-published bit layout."""
        try:
            di_area = str(mapping[Config.CONF_DI_DATA_AREA])
            di_base = int(mapping[Config.CONF_DI_BASE_ADDRESS])
            di_stride = int(mapping[Config.CONF_DI_ADDRESS_STRIDE])
            do_base = int(mapping[Config.CONF_DO_BASE_ADDRESS])
            do_stride = int(mapping[Config.CONF_DO_ADDRESS_STRIDE])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Incomplete PLC110 Modbus I/O mapping") from exc
        if di_area not in self.manual_io_mapping_spec["di_data_areas"]:
            raise ValueError("PLC110 DI area must be discrete_input or coil")
        if min(di_base, do_base) < 0 or min(di_stride, do_stride) < 1:
            raise ValueError("PLC110 bases must be non-negative and strides positive")
        di_addresses = tuple(di_base + index * di_stride for index in range(36))
        do_addresses = tuple(do_base + index * do_stride for index in range(24))
        if max((*di_addresses, *do_addresses)) > 65535:
            raise ValueError("PLC110 mapped bit address exceeds Modbus range")
        if di_area == "coil" and set(di_addresses) & set(do_addresses):
            raise ValueError("PLC110 DI and DO coil mappings must not overlap")

        self._io_mapping = {
            Config.CONF_DI_DATA_AREA: di_area,
            Config.CONF_DI_BASE_ADDRESS: di_base,
            Config.CONF_DI_ADDRESS_STRIDE: di_stride,
            Config.CONF_DO_BASE_ADDRESS: do_base,
            Config.CONF_DO_ADDRESS_STRIDE: do_stride,
        }
        self._inputs = {
            number: {
                "input_number": number,
                "input_number_view": number,
                "input_type": "DI",
                "data_type": di_area,
                "address": address,
                "address_hex": hex(address),
                "state": None,
                "func_mode": [2] if di_area == "discrete_input" else [1],
                "device_class": None,
                "icon_on": "mdi:electric-switch-closed",
                "icon_off": "mdi:electric-switch",
                "high_speed": number in self.fast_input_numbers,
            }
            for number, address in enumerate(di_addresses, start=1)
        }
        self._outputs = {
            number: {
                "out_number": number,
                "out_number_view": number,
                "out_type": "DO",
                "data_type": "coil",
                "address": address,
                "address_hex": hex(address),
                "state": None,
                "func_mode": [1, 5],
                "device_class": SwitchDeviceClass.SWITCH,
                "icon_on": "mdi:toggle-switch-variant",
                "icon_off": "mdi:toggle-switch-variant-off",
                "high_speed": number in self.fast_output_numbers,
            }
            for number, address in enumerate(do_addresses, start=1)
        }

    async def data_init(self) -> bool:
        if self._io_mapping is None:
            raise ValueError("PLC110 requires its user-defined Modbus I/O mapping")
        await self.async_get_snapshot()
        self.attr_init_time = datetime.now()
        return True

    async def get_device_info(self) -> dict[str, Any]:
        """Return no invented service information."""
        return {
            "device_type": self.attr_device_type,
            "serial_number": self.attr_serial_number,
            "hardware_version": self.attr_hardware_version,
            "software_version": self.attr_software_version,
        }

    def get_output_descriptions(self) -> list[dict[str, Any]]:
        return list(self._outputs.values())

    async def async_get_snapshot(self) -> dict[str, dict]:
        input_states = await self._read_mapped_bits(
            (item["address"] for item in self._inputs.values()),
            self._io_mapping[Config.CONF_DI_DATA_AREA],
        )
        output_states = await self._read_mapped_bits(
            (item["address"] for item in self._outputs.values()), "coil"
        )
        inputs = {}
        for number, current in self._inputs.items():
            updated = dict(current)
            updated["state"] = input_states[current["address"]]
            self._inputs[number] = updated
            inputs[number] = updated
        outputs = {}
        for number, current in self._outputs.items():
            updated = dict(current)
            updated["state"] = output_states[current["address"]]
            self._outputs[number] = updated
            outputs[number] = updated
        return {"inputs": inputs, "outputs": outputs}

    async def get_inputs(self, inputs: list[int] | None = None) -> list[dict[str, Any]]:
        selected = list(self._inputs) if inputs is None else inputs
        unknown = set(selected) - set(self._inputs)
        if unknown:
            raise ValueError(f"Unknown PLC110 inputs: {sorted(unknown)}")
        states = await self._read_mapped_bits(
            (self._inputs[number]["address"] for number in selected),
            self._io_mapping[Config.CONF_DI_DATA_AREA],
        )
        result = []
        for number in selected:
            updated = dict(self._inputs[number])
            updated["state"] = states[updated["address"]]
            self._inputs[number] = updated
            result.append(updated)
        return result

    async def get_outputs(self, outputs: list[int] | None = None) -> list[dict[str, Any]]:
        selected = list(self._outputs) if outputs is None else outputs
        unknown = set(selected) - set(self._outputs)
        if unknown:
            raise ValueError(f"Unknown PLC110 outputs: {sorted(unknown)}")
        states = await self._read_mapped_bits(
            (self._outputs[number]["address"] for number in selected), "coil"
        )
        result = []
        for number in selected:
            updated = dict(self._outputs[number])
            updated["state"] = states[updated["address"]]
            self._outputs[number] = updated
            result.append(updated)
        return result

    async def set_output(self, output: int, value: bool) -> dict[str, Any]:
        if output not in self._outputs:
            raise ValueError(f"Unknown PLC110 output: {output}")
        current = dict(self._outputs[output])
        response = await self.attr_client.write_coil(
            address=current["address"],
            value=bool(value),
            device_id=self.attr_device_id,
        )
        validate_write_response(response, f"set PLC110 output {output}")
        current["state"] = bool(value)
        self._outputs[output] = current
        return current

    async def _read_mapped_bits(self, addresses, data_area: str) -> dict[int, bool]:
        ordered = sorted(set(addresses))
        result: dict[int, bool] = {}
        index = 0
        while index < len(ordered):
            start = ordered[index]
            end = start
            index += 1
            while index < len(ordered) and ordered[index] == end + 1:
                end = ordered[index]
                index += 1
            count = end - start + 1
            reader = (
                self.attr_client.read_discrete_inputs
                if data_area == "discrete_input"
                else self.attr_client.read_coils
            )
            response = await reader(
                address=start, count=count, device_id=self.attr_device_id
            )
            bits = validated_bits(response, count, f"read PLC110 {data_area} at {start}")
            result.update(
                {start + offset: state for offset, state in enumerate(bits)}
            )
        return result
