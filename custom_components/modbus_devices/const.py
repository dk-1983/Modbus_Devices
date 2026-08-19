"""Constants for the modbus_devices integration."""

from typing import Any

from homeassistant.const import Platform


class Config:
    """Settings constants params."""

    DOMAIN: str = "modbus_devices"
    NAME: str = "Modbus Devices"

    WORD: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    WORD_LENGTH: int = 26

    TIME_FORMAT: str = "%d:%m:%Y %H:%M:%S"  # TODO Do not used!
    TIME_ZONE: int = 7  # in hours timezone integer
    TIME_DELTA: int = 1  # in hours timedelta for clock update.

    PLATFORMS: list[Platform] = [
        Platform.BINARY_SENSOR,
        Platform.DATETIME,
        Platform.SWITCH,
    ]

    CONF_MODBUS_MODE: str = "modbus_mode"
    CONF_DEVICE_CLASS: str = "device_class"
    CONF_GATEWAY_MAPPING: str = "gateway_mapping"
    CONF_GATEWAY_ID: str = "gateway_id"
    CONF_GATEWAY_SELECTION: str = "gateway_selection"
    CONF_MAPPING_SOURCE: str = "mapping_source"
    CONF_ORION_ADDRESS: str = "orion_address"
    CONF_OBJECT_KIND: str = "object_kind"
    CONF_DATA_AREA: str = "data_area"
    CONF_LOCAL_OBJECT_NUMBER: str = "local_object_number"
    CONF_GATEWAY_OBJECT_NUMBER: str = "gateway_object_number"
    CONF_RESOLVED_MODBUS_ADDRESS: str = "resolved_modbus_address"
    CONF_ADD_ANOTHER_OBJECT: str = "add_another_object"
    CONF_ZONE_TYPE: str = "zone_type"
    CONF_PARTITION_NUMBER: str = "partition_number"
    CONF_PARTITION_ID: str = "partition_id"
    CONF_CAPABILITY_KEY: str = "capability_key"
    CONF_DEVICE_VARIANT: str = "device_variant"
    CONF_DEVICE_TOPOLOGY: str = "device_topology"
    CONF_DPLS_BASE_ADDRESS: str = "dpls_base_address"
    CONF_IO_MAPPING: str = "io_mapping"
    CONF_DI_DATA_AREA: str = "di_data_area"
    CONF_DI_BASE_ADDRESS: str = "di_base_address"
    CONF_DI_ADDRESS_STRIDE: str = "di_address_stride"
    CONF_DO_BASE_ADDRESS: str = "do_base_address"
    CONF_DO_ADDRESS_STRIDE: str = "do_address_stride"

    CONF_MANUFACTURER: str = "manufacturer"

    CONF_COM_PORT: str = "com_port"
    CONF_BAUDRATE: str = "baudrate"
    CONF_BYTESIZE: str = "bytesize"
    CONF_PARITY: str = "parity"
    CONF_STOPBITS: str = "stopbits"

    CONF_CONNECT_TO: str = "connect_to"

    MODBUS_TCP: str = "ModBus TCP/IP"
    MODBUS_UDP: str = "ModBus UDP/IP"
    MODBUS_SERIAL: str = "SerialPort"

    MODBUS_ERROR: dict[int, str] = {  # TODO Do not used!
        1: "Принятый код функции не может быть обработан.",
        2: "Адрес данных, указанный в запросе, недоступен.",
        3: "Значение, содержащееся в поле данных запроса, является недопустимой величиной.",
        4: "Невосстанавливаемая ошибка имела место, пока ведомое устройство пыталось выполнить затребованное действие.",
        5: "Ведомое устройство приняло запрос и обрабатывает его, но это требует много времени. Этот ответ предохраняет ведущее устройство от генерации ошибки тайм-аута.",
        6: "Ведомое устройство занято обработкой команды. Ведущее устройство должно повторить сообщение позже, когда ведомое освободится.",
        7: "Ведомое устройство не может выполнить программную функцию, заданную в запросе. Этот код возвращается для неуспешного программного запроса, использующего функции с номерами 13 или 14. Ведущее устройство должно запросить диагностическую информацию или информацию об ошибках от ведомого.",
        8: "Ведомое устройство при чтении расширенной памяти обнаружило ошибку паритета. Ведущее устройство может повторить запрос, но обычно в таких случаях требуется ремонт.",
        9: "Шлюз неправильно настроен или перегружен запросами.",
        10: "Slave устройства нет в сети или от него нет ответа.",
        11: "Устройство шлюза не ответило",
    }
