"""Equipment models manufactured by Owen."""

from datetime import datetime, timedelta, timezone
import struct
from typing import Any

from custom_components.modbus_devices.const import Config
from pymodbus.client import (
    AsyncModbusSerialClient,
    AsyncModbusTcpClient,
    AsyncModbusUdpClient,
)
from pymodbus.exceptions import ModbusException

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform, UnitOfTemperature

from ..modbus_validation import (
    validate_fc05_response,
    validated_bits,
    validated_registers,
)


class TRM138:
    """Owen TRM-138."""

    equipment_manufacturer = "Owen"
    equipment_model = "TRM-138"
    CHANNEL_COUNT = 8
    REGISTERS_PER_CHANNEL = 5
    REGISTER_COUNT = CHANNEL_COUNT * REGISTERS_PER_CHANNEL
    VALID_DECIMAL_POINTS = frozenset(range(4))
    STATUS_DESCRIPTIONS = {
        0: "ok",
        1: "input_below_range",
        2: "lba_alarm",
        3: "internal_error",
        4: "cold_junction_compensation_error",
        5: "input_above_range",
        6: "rtd_below_range",
        7: "cold_junction_compensation_error",
        8: "thermocouple_below_range",
        9: "thermocouple_above_range",
        10: "processing_sequence_error",
        11: "sensor_line_break",
        12: "invalid_configuration",
        13: "corrected_value_below_range",
        14: "corrected_value_above_range",
        15: "critical_device_error",
        16: "rtd_above_range",
        57: "invalid_configuration",
    }

    def __init__(self, client, device_id) -> None:
        """Initialize the device and its documented FC04 channel map."""
        self.attr_device_id: int = device_id
        self.attr_client: (
            AsyncModbusSerialClient | AsyncModbusTcpClient | AsyncModbusUdpClient | None
        ) = client
        self.attr_manufactures_name: str = "Owen"
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
        self._channels = {
            number: self._channel_description(number)
            for number in range(1, self.CHANNEL_COUNT + 1)
        }
        for number, channel in self._channels.items():
            setattr(self, f"attr_ch{number}", channel)

    @classmethod
    def _channel_description(cls, number: int) -> dict[str, Any]:
        address = (number - 1) * cls.REGISTERS_PER_CHANNEL
        return {
            "chanel_number": number,
            "chanel_number_view": number,
            "chanel_type": "Temperature",
            "data_type": "input_registers",
            "address": address,
            "address_hex": hex(address),
            "count": cls.REGISTERS_PER_CHANNEL,
            "value": None,
            "func_mode": [4],
            "device_class": SensorDeviceClass.TEMPERATURE,
            "state_class": SensorStateClass.MEASUREMENT,
            "icon_c": "mdi:temperature-celsius",
            "icon_f": "mdi:temperature-fahrenheit",
            "icon_k": "mdi:temperature-kelvin",
            "unit_of_temperature_c": UnitOfTemperature.CELSIUS,
            # Keep misspelled legacy keys because entities/configurations may use them.
            "unut_of_temperature_f": UnitOfTemperature.FAHRENHEIT,
            "unut_of_temperature_k": UnitOfTemperature.KELVIN,
        }

    async def data_init(self) -> bool:
        """Инициализирует все свойства класса."""
        await self.get_device_info()
        return True

    async def get_device_info(self) -> bool:
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
        attr = self._get_channel(chanel)
        response = await self.attr_client.read_input_registers(
            address=attr["address"],
            count=attr["count"],
            device_id=self.attr_device_id,
        )
        registers = validated_registers(
            response,
            attr["count"],
            f"read TRM-138 channel {chanel}",
            expected_function=4,
        )
        return self._update_channel(chanel, registers)

    async def get_chanels(
        self, chanels: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """Получает аналоговые данные всех или нескольких каналов контроллера."""
        selected = list(self._channels) if chanels is None else list(chanels)
        self._validate_channels(selected)
        if not selected:
            return []

        if selected == list(self._channels):
            response = await self.attr_client.read_input_registers(
                address=0,
                count=self.REGISTER_COUNT,
                device_id=self.attr_device_id,
            )
            registers = validated_registers(
                response,
                self.REGISTER_COUNT,
                "read TRM-138 channels",
                expected_function=4,
            )
            return [
                self._update_channel(
                    number,
                    registers[start : start + self.REGISTERS_PER_CHANNEL],
                )
                for number in selected
                for start in [(number - 1) * self.REGISTERS_PER_CHANNEL]
            ]

        return [await self.get_chanel(number) for number in selected]

    async def async_get_snapshot(self) -> dict[str, dict[int, dict[str, Any]]]:
        """Read one coherent FC04 snapshot of all measurement channels."""
        channels = await self.get_chanels()
        return {"chanels": {item["chanel_number"]: item for item in channels}}

    def _get_channel(self, number: int) -> dict[str, Any]:
        self._validate_channels([number])
        return self._channels[number]

    def _validate_channels(self, channels: list[int]) -> None:
        unknown = [number for number in channels if number not in self._channels]
        if unknown:
            raise ValueError(f"Unknown TRM-138 channels: {unknown}")

    def _update_channel(
        self, number: int, registers: list[int]
    ) -> dict[str, Any]:
        if len(registers) != self.REGISTERS_PER_CHANNEL:
            raise ModbusException(
                f"Invalid TRM-138 channel {number} block length: "
                f"expected {self.REGISTERS_PER_CHANNEL}, got {len(registers)}"
            )
        decoded = list(registers)
        decimal_point = decoded[0]
        if decimal_point not in self.VALID_DECIMAL_POINTS:
            raise ModbusException(
                f"Invalid TRM-138 channel {number} decimal point: {decimal_point}"
            )
        integer_value = AsyncModbusSerialClient.convert_from_registers(
            [decoded[1]], data_type=AsyncModbusSerialClient.DATATYPE.INT16
        )
        decoded[1] = integer_value
        status_code = decoded[2]
        float_value = struct.unpack(">f", struct.pack(">HH", decoded[3], decoded[4]))[0]
        channel = {
            **self._channels[number],
            # ``value`` is the established entity contract: decimal point, signed
            # integer, status, then the documented IEEE-754 high/low words.
            "value": decoded,
            "raw_registers": list(registers),
            "decimal_point": decimal_point,
            "measurement": integer_value / (10**decimal_point),
            "float_value": float_value,
            "status_code": status_code,
            "status": self.STATUS_DESCRIPTIONS.get(status_code, "unknown"),
            "valid": status_code == 0,
        }
        self._channels[number] = channel
        setattr(self, f"attr_ch{number}", channel)
        return channel

    def __repr__(self) -> str:
        """Output representation information from Owen class."""
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
    """Owen ПЛК110-24.60.К-М with a user-program-defined Modbus slave map."""

    equipment_manufacturer = "Owen"
    equipment_model = "ПЛК110-24.60.К-М"
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
        self.attr_manufactures_name = "Owen"
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
        validate_fc05_response(
            response,
            address=current["address"],
            value=bool(value),
            device_id=self.attr_device_id,
            operation=f"set PLC110 output {output}",
        )
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
            bits = validated_bits(
                response,
                count,
                f"read PLC110 {data_area} at {start}",
                expected_function=2 if data_area == "discrete_input" else 1,
            )
            result.update(
                {start + offset: state for offset, state in enumerate(bits)}
            )
        return result


EQUIPMENT_CLASSES = (
    PLC110_24_60_K_M,
    TRM138,
)
