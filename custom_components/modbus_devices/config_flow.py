"""Config flow for Modbus Devices."""

from __future__ import annotations

from logging import getLogger
from typing import Any

from pymodbus.exceptions import ModbusException
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME, CONF_PORT
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import Config
from .equipment.equipment import (
    get_classes_from_files,
    get_gateway_capabilities,
    get_gateway_device_metadata,
    get_gateway_requirement,
    get_serial_ports,
    validate_equipment_gateway_mapping,
)
from .gateway import (
    DPLSSubIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayCapabilitySpec,
    GatewayType,
    MappingSource,
    ObjectKind,
    ResolvedDeviceMapping,
    ResolvedObjectMapping,
    dpls_ranges_overlap,
)
from .mapping import (
    AutomaticDeviceMappingProvider,
    DeviceMappingNotFoundError,
    ManualDeviceMappingProvider,
)
from .modbus_client import connect_modbus
from .s2000_pp import (
    S2000PPConfigurationCache,
    S2000PPConfigurationReader,
    manual_relay_mapping,
    manual_zone_mapping,
)

_LOGGER = getLogger(__name__)


class ModbusDevicesConfigFlow(ConfigFlow, domain=Config.DOMAIN):
    """Handle config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

        self._device_classes: dict[str, list[str]] = {}

        self._serial_ports: list[str] = []
        self._selected_manufacturer: str = ""
        self._manufacturer_devices: list[str] = []
        self._required_gateway: GatewayType | None = None
        self._gateway_context: GatewayContext | None = None
        self._manual_objects: list[ResolvedObjectMapping] = []
        self._orion_address: int | None = None
        self._manual_mapping_error: str | None = None
        self._gateway_capabilities: tuple[GatewayCapabilitySpec, ...] = ()
        self._dpls_identity: DPLSSubIdentity | None = None
        self._device_metadata = DownstreamDeviceMetadata()
        self._gateway_device_metadata: dict[str, Any] = {}

    # ---------------------------------------------------------
    # STEP 1 - MODE
    # ---------------------------------------------------------
    async def async_step_user(self, user_input=None):
        """Select connection type."""

        if not self._device_classes:
            self._device_classes = await self.hass.async_add_executor_job(
                get_classes_from_files
            )

        if not self._serial_ports:
            self._serial_ports = await self.hass.async_add_executor_job(
                get_serial_ports
            )

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_manufacturer()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_MODBUS_MODE): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [
                                Config.MODBUS_TCP,
                                Config.MODBUS_UDP,
                                Config.MODBUS_SERIAL,
                            ],
                        }
                    }
                )
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    # ---------------------------------------------------------
    # STEP 2 - MANUFACTURER
    # ---------------------------------------------------------
    async def async_step_manufacturer(self, user_input=None):
        """Select manufacturer."""

        if not self._device_classes:
            return self.async_abort(reason="no_devices")

        if user_input is not None:
            self._selected_manufacturer = user_input[Config.CONF_MANUFACTURER]

            self._manufacturer_devices = self._device_classes.get(
                self._selected_manufacturer, []
            )

            return await self.async_step_device()

        manufacturers = sorted(self._device_classes.keys())

        if not manufacturers:
            return self.async_abort(reason="no_manufacturers")

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_MANUFACTURER): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": manufacturers,
                        }
                    }
                )
            }
        )

        return self.async_show_form(
            step_id="manufacturer",
            data_schema=schema,
        )

    # ---------------------------------------------------------
    # STEP 3 - DEVICE
    # ---------------------------------------------------------
    async def async_step_device(self, user_input=None):
        """Select device."""

        if user_input is not None:
            device_name = user_input[Config.CONF_DEVICE_CLASS]

            # FIX: сохраняем ВСЁ что нужно дальше
            self._data[Config.CONF_MANUFACTURER] = self._selected_manufacturer
            self._data[Config.CONF_DEVICE_CLASS] = device_name

            self._required_gateway = await self.hass.async_add_executor_job(
                get_gateway_requirement,
                self._selected_manufacturer.lower(),
                device_name,
            )

            return await self._next_step()

        devices = list(self._manufacturer_devices)

        if not devices:
            return self.async_abort(reason="no_devices_for_manufacturer")

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_DEVICE_CLASS): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": sorted(devices),
                        }
                    }
                )
            }
        )

        return self.async_show_form(step_id="device", data_schema=schema)

    # ---------------------------------------------------------
    # ROUTER
    # ---------------------------------------------------------
    async def _next_step(self):
        mode = self._data.get(Config.CONF_MODBUS_MODE)

        if mode in (Config.MODBUS_TCP, Config.MODBUS_UDP):
            return await self.async_step_network()

        return await self.async_step_serial()

    # ---------------------------------------------------------
    # STEP 4 - NETWORK (TCP/UDP)
    # ---------------------------------------------------------
    async def async_step_network(self, user_input=None):
        """TCP/UDP setup."""

        errors = {}

        if user_input is not None:
            self._data.update(user_input)

            self._data.setdefault(CONF_DEVICE_ID, 1)

            try:
                client = await connect_modbus(self._data)

                if not client or not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    client.close()

                    unique_id = (
                        f"{self._data.get(CONF_HOST)}_"
                        f"{self._data.get(CONF_PORT)}_"
                        f"{self._data.get(CONF_DEVICE_ID)}_"
                        f"{self._selected_manufacturer}_"
                        f"{self._data.get(Config.CONF_DEVICE_CLASS)}"
                    )
                    return await self._async_connection_ready(unique_id)

            except ModbusException:
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default="10.0.2.13"): cv.string,
                vol.Required(CONF_PORT, default=510): int,
                vol.Required(CONF_DEVICE_ID, default=1): int,
                vol.Optional(CONF_NAME, default="Modbus Device"): cv.string,
            }
        )

        return self.async_show_form(
            step_id="network",
            data_schema=schema,
            errors=errors,
        )

    # ---------------------------------------------------------
    # STEP 5 - SERIAL (FULL SETTINGS RESTORED)
    # ---------------------------------------------------------
    async def async_step_serial(self, user_input=None):
        """Serial setup."""

        errors = {}

        if user_input is not None:
            self._data.update(user_input)

            self._data.setdefault(CONF_DEVICE_ID, 1)

            try:
                client = await connect_modbus(self._data)

                if not client or not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    client.close()

                    unique_id = (
                        f"{self._data.get(Config.CONF_COM_PORT)}_"
                        f"{self._data.get(CONF_DEVICE_ID)}_"
                        f"{self._selected_manufacturer}_"
                        f"{self._data.get(Config.CONF_DEVICE_CLASS)}"
                    )
                    return await self._async_connection_ready(unique_id)

            except ModbusException:
                errors["base"] = "cannot_connect"

        # -------------------------
        # FULL SERIAL CONFIG
        # -------------------------
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID, default=1): int,
                vol.Required(Config.CONF_COM_PORT): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": self._serial_ports,
                        }
                    }
                ),
                vol.Required(Config.CONF_BAUDRATE, default="9600"): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [
                                "300",
                                "600",
                                "1200",
                                "2400",
                                "4800",
                                "9600",
                                "14400",
                                "19200",
                                "38400",
                                "56000",
                                "57600",
                                "115200",
                                "128000",
                                "153600",
                                "230400",
                                "256000",
                                "460800",
                                "921600",
                            ],
                        }
                    }
                ),
                vol.Required(Config.CONF_BYTESIZE, default="8"): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": ["7", "8"],
                        }
                    }
                ),
                vol.Required(Config.CONF_PARITY, default="N"): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": ["N", "E", "O"],
                        }
                    }
                ),
                vol.Required(Config.CONF_STOPBITS, default="1"): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": ["1", "2"],
                        }
                    }
                ),
                vol.Optional(CONF_NAME, default="Modbus Device"): cv.string,
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=schema,
            errors=errors,
        )

    async def _async_connection_ready(self, legacy_unique_id: str):
        """Continue with a gateway flow or create a static-device entry."""
        if self._required_gateway is not None:
            return await self.async_step_gateway_context()

        await self.async_set_unique_id(legacy_unique_id)
        self._abort_if_unique_id_configured()
        return self._create_device_entry()

    def _create_device_entry(self, suffix: str = ""):
        """Create a Config Entry using the accumulated validated data."""
        title = (
            f"{self._selected_manufacturer} "
            f"{self._data[Config.CONF_DEVICE_CLASS]}{suffix}"
        )
        return self.async_create_entry(title=title, data=self._data)

    def _connection_key(self) -> str:
        """Return a stable transport key for gateway identity and reuse."""
        mode = self._data[Config.CONF_MODBUS_MODE]
        if mode in (Config.MODBUS_TCP, Config.MODBUS_UDP):
            return f"{mode}:{self._data[CONF_HOST]}:{self._data[CONF_PORT]}"

        return (
            f"{mode}:{self._data[Config.CONF_COM_PORT]}:"
            f"{self._data[Config.CONF_BAUDRATE]}:"
            f"{self._data[Config.CONF_BYTESIZE]}:"
            f"{self._data[Config.CONF_PARITY]}:"
            f"{self._data[Config.CONF_STOPBITS]}"
        )

    def _existing_gateway_contexts(self) -> dict[str, GatewayContext]:
        """Return compatible gateway contexts from existing entries."""
        contexts: dict[str, GatewayContext] = {}
        connection_key = self._connection_key()

        for entry in self.hass.config_entries.async_entries(Config.DOMAIN):
            config = entry.options or entry.data
            mapping_data = config.get(Config.CONF_GATEWAY_MAPPING)
            if not mapping_data:
                continue

            try:
                mapping = ResolvedDeviceMapping.from_dict(mapping_data)
            except (KeyError, TypeError, ValueError):
                continue

            gateway = mapping.identity.gateway
            if (
                gateway.gateway_type is self._required_gateway
                and gateway.connection_key == connection_key
                and gateway.modbus_unit_id == self._data[CONF_DEVICE_ID]
            ):
                contexts[gateway.stable_id] = gateway

        return contexts

    async def async_step_gateway_context(self, user_input=None):
        """Select an existing gateway context or define a new one."""
        contexts = self._existing_gateway_contexts()

        if user_input is not None:
            selection = user_input[Config.CONF_GATEWAY_SELECTION]
            if selection == "new":
                return await self.async_step_gateway_new()

            self._gateway_context = contexts[selection]
            return await self.async_step_gateway_device()

        options = [
            {"value": stable_id, "label": gateway.gateway_id}
            for stable_id, gateway in sorted(contexts.items())
        ]
        options.append({"value": "new", "label": "Add new С2000-ПП"})

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_GATEWAY_SELECTION): selector(
                    {"select": {"mode": "dropdown", "options": options}}
                )
            }
        )
        return self.async_show_form(
            step_id="gateway_context",
            data_schema=schema,
        )

    async def async_step_gateway_new(self, user_input=None):
        """Create a stable context for a new gateway."""
        errors = {}
        if user_input is not None:
            try:
                self._gateway_context = GatewayContext(
                    gateway_type=self._required_gateway,
                    gateway_id=user_input[Config.CONF_GATEWAY_ID],
                    connection_key=self._connection_key(),
                    modbus_unit_id=self._data[CONF_DEVICE_ID],
                )
            except ValueError:
                errors["base"] = "invalid_gateway"
            else:
                return await self.async_step_gateway_device()

        schema = vol.Schema(
            {
                vol.Required(
                    Config.CONF_GATEWAY_ID,
                    default="С2000-ПП",
                ): cv.string,
            }
        )
        return self.async_show_form(
            step_id="gateway_new",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_gateway_device(self, user_input=None):
        """Collect declarative nested identity and variant metadata."""
        if not self._gateway_device_metadata:
            self._gateway_device_metadata = await self.hass.async_add_executor_job(
                get_gateway_device_metadata,
                self._selected_manufacturer.lower(),
                self._data[Config.CONF_DEVICE_CLASS],
            )
        if not self._gateway_device_metadata["uses_dpls_identity"]:
            return await self.async_step_mapping_source()

        errors = {}
        if user_input is not None:
            variant = user_input[Config.CONF_DEVICE_VARIANT]
            if variant in self._gateway_device_metadata["unsupported_variants"]:
                errors[Config.CONF_DEVICE_VARIANT] = "unsupported_variant"
            else:
                try:
                    self._orion_address = user_input[Config.CONF_ORION_ADDRESS]
                    self._dpls_identity = DPLSSubIdentity(
                        base_address=user_input[Config.CONF_DPLS_BASE_ADDRESS],
                        address_count=self._gateway_device_metadata["dpls_address_count"],
                    )
                    self._device_metadata = DownstreamDeviceMetadata(variant=variant)
                except (KeyError, TypeError, ValueError):
                    errors["base"] = "invalid_mapping"
                else:
                    return await self.async_step_mapping_source()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_DEVICE_VARIANT): selector(
                    {"select": {"mode": "dropdown", "options": [
                        {"value": value, "label": label}
                        for value, label in self._gateway_device_metadata["variants"].items()
                    ]}}
                ),
                vol.Required(Config.CONF_ORION_ADDRESS): vol.All(
                    int, vol.Range(min=1, max=127)
                ),
                vol.Required(Config.CONF_DPLS_BASE_ADDRESS): vol.All(
                    int, vol.Range(min=1, max=127)
                ),
            }
        )
        return self.async_show_form(
            step_id="gateway_device", data_schema=schema, errors=errors,
            description_placeholders={
                "unsupported_variant": "С2000-СП4/220 исп.02 is not supported"
            },
        )

    async def async_step_mapping_source(self, user_input=None):
        """Select manual mapping or the future automatic provider."""
        if user_input is not None:
            source = MappingSource(user_input[Config.CONF_MAPPING_SOURCE])
            if source is MappingSource.AUTOMATIC:
                return await self.async_step_automatic_device()
            return await self.async_step_manual_device()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_MAPPING_SOURCE): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": [source.value for source in MappingSource],
                        }
                    }
                )
            }
        )
        return self.async_show_form(
            step_id="mapping_source",
            data_schema=schema,
        )

    async def async_step_manual_device(self, user_input=None):
        """Identify the downstream physical device."""
        if self._dpls_identity is not None and self._orion_address is not None:
            self._gateway_capabilities = await self.hass.async_add_executor_job(
                get_gateway_capabilities,
                self._selected_manufacturer.lower(),
                self._data[Config.CONF_DEVICE_CLASS],
            )
            return await self.async_step_manual_object()
        if user_input is not None:
            self._orion_address = user_input[Config.CONF_ORION_ADDRESS]
            self._gateway_capabilities = await self.hass.async_add_executor_job(
                get_gateway_capabilities,
                self._selected_manufacturer.lower(),
                self._data[Config.CONF_DEVICE_CLASS],
            )
            return await self.async_step_manual_object()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_ORION_ADDRESS): vol.All(
                    int,
                    vol.Range(min=1, max=127),
                )
            }
        )
        return self.async_show_form(
            step_id="manual_device",
            data_schema=schema,
        )

    async def async_step_manual_object(self, user_input=None):
        """Add one typed downstream object mapping row."""
        if self._gateway_capabilities:
            return await self.async_step_manual_capability(user_input)

        errors = {}
        if self._manual_mapping_error is not None:
            errors["base"] = self._manual_mapping_error
            self._manual_mapping_error = None
        if user_input is not None:
            try:
                object_kind = ObjectKind(
                    user_input[Config.CONF_OBJECT_KIND]
                )
                if object_kind is ObjectKind.RELAY:
                    resolved_object = manual_relay_mapping(
                        local_object_number=user_input[
                            Config.CONF_LOCAL_OBJECT_NUMBER
                        ],
                        table_number=user_input[
                            Config.CONF_GATEWAY_OBJECT_NUMBER
                        ],
                    )
                elif object_kind is ObjectKind.ZONE:
                    resolved_object = manual_zone_mapping(
                        local_object_number=user_input[
                            Config.CONF_LOCAL_OBJECT_NUMBER
                        ],
                        table_number=user_input[
                            Config.CONF_GATEWAY_OBJECT_NUMBER
                        ],
                        zone_type=user_input[Config.CONF_ZONE_TYPE],
                        partition_number=user_input.get(
                            Config.CONF_PARTITION_NUMBER,
                            0,
                        ),
                        partition_id=user_input.get(Config.CONF_PARTITION_ID),
                    )
                else:
                    raise ValueError("Unsupported manual S2000-PP object kind")
                self._manual_objects.append(
                    resolved_object
                )
            except (KeyError, ValueError):
                errors["base"] = "invalid_mapping"
            else:
                if user_input[Config.CONF_ADD_ANOTHER_OBJECT]:
                    return await self.async_step_manual_object()
                return await self._async_finish_manual_mapping()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_OBJECT_KIND): selector(
                    {
                        "select": {
                            "options": [
                                ObjectKind.RELAY.value,
                                ObjectKind.ZONE.value,
                            ]
                        }
                    }
                ),
                vol.Required(Config.CONF_LOCAL_OBJECT_NUMBER): vol.All(
                    int, vol.Range(min=0)
                ),
                vol.Required(Config.CONF_GATEWAY_OBJECT_NUMBER): vol.All(
                    int, vol.Range(min=1)
                ),
                vol.Optional(Config.CONF_ZONE_TYPE): vol.All(
                    int,
                    vol.Range(min=0, max=65535),
                ),
                vol.Optional(Config.CONF_PARTITION_NUMBER): vol.All(
                    int,
                    vol.Range(min=0, max=64),
                ),
                vol.Optional(Config.CONF_PARTITION_ID): vol.All(
                    int,
                    vol.Range(min=1, max=65534),
                ),
                vol.Required(Config.CONF_ADD_ANOTHER_OBJECT, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="manual_object",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_manual_capability(self, user_input=None):
        """Map an equipment-owned optional capability to one gateway table row."""
        errors = {}
        mapped_keys = {
            self._capability_key_for_mapping(item) for item in self._manual_objects
        }
        available = {
            spec.key: spec
            for spec in self._gateway_capabilities
            if spec.key not in mapped_keys
        }
        if user_input is not None:
            try:
                spec = available[user_input[Config.CONF_CAPABILITY_KEY]]
                table_number = user_input[Config.CONF_GATEWAY_OBJECT_NUMBER]
                if spec.object_kind is ObjectKind.RELAY:
                    resolved_object = manual_relay_mapping(
                        local_object_number=spec.resolved_local_object_number(
                            None if self._dpls_identity is None else self._dpls_identity.base_address
                        ),
                        table_number=table_number,
                    )
                elif spec.object_kind is ObjectKind.ZONE:
                    resolved_object = manual_zone_mapping(
                        local_object_number=spec.resolved_local_object_number(
                            None if self._dpls_identity is None else self._dpls_identity.base_address
                        ),
                        table_number=table_number,
                        zone_type=spec.zone_type,
                        partition_number=0,
                        partition_id=None,
                    )
                else:
                    raise ValueError("Unsupported gateway capability object kind")
                self._manual_objects.append(resolved_object)
            except (KeyError, ValueError):
                errors["base"] = "invalid_mapping"
            else:
                if user_input[Config.CONF_ADD_ANOTHER_OBJECT]:
                    return await self.async_step_manual_capability()
                return await self._async_finish_manual_mapping()

        options = [
            {"value": spec.key, "label": spec.name}
            for spec in available.values()
        ]
        if not options:
            return await self._async_finish_manual_mapping()
        schema = vol.Schema(
            {
                vol.Required(Config.CONF_CAPABILITY_KEY): selector(
                    {"select": {"mode": "dropdown", "options": options}}
                ),
                vol.Required(Config.CONF_GATEWAY_OBJECT_NUMBER): vol.All(
                    int,
                    vol.Range(min=1),
                ),
                vol.Required(Config.CONF_ADD_ANOTHER_OBJECT, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="manual_capability",
            data_schema=schema,
            errors=errors,
        )

    def _capability_key_for_mapping(self, mapping: ResolvedObjectMapping) -> str:
        """Return the equipment capability key represented by a manual mapping."""
        zone_type = (
            None if mapping.zone_details is None else mapping.zone_details.zone_type
        )
        for spec in self._gateway_capabilities:
            if (
                spec.object_kind is mapping.object_kind
                and spec.resolved_local_object_number(
                    None if self._dpls_identity is None else self._dpls_identity.base_address
                ) == mapping.local_object_number
                and spec.zone_type == zone_type
            ):
                return spec.key
        raise ValueError("Manual mapping does not match an equipment capability")

    async def _async_finish_manual_mapping(self):
        """Resolve, validate and store the common mapping representation."""
        provider = ManualDeviceMappingProvider()
        try:
            mapping = await provider.async_resolve(
                gateway=self._gateway_context,
                model=self._data[Config.CONF_DEVICE_CLASS],
                orion_address=self._orion_address,
                objects=tuple(self._manual_objects),
                dpls=self._dpls_identity,
                metadata=self._device_metadata,
            )
        except ValueError:
            self._manual_mapping_error = "invalid_mapping"
            return await self.async_step_manual_object(
                user_input=None,
            )

        if not await self._async_validate_and_store_mapping(mapping):
            self._manual_mapping_error = "invalid_equipment_mapping"
            return await self.async_step_manual_object(user_input=None)
        return self._create_device_entry(
            suffix=f" Orion {mapping.identity.orion_address}"
        )

    async def async_step_automatic_device(self, user_input=None):
        """Resolve one downstream device from С2000-ПП configuration tables."""
        errors = {}
        if self._dpls_identity is not None and self._orion_address is not None and user_input is None:
            user_input = {Config.CONF_ORION_ADDRESS: self._orion_address}
        if user_input is not None:
            self._orion_address = user_input[Config.CONF_ORION_ADDRESS]
            client = None
            try:
                client = await connect_modbus(self._data)
                if not client or not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    domain_data = self.hass.data.setdefault(Config.DOMAIN, {})
                    cache = domain_data.setdefault(
                        "s2000_pp_configuration_cache",
                        S2000PPConfigurationCache(),
                    )
                    provider = AutomaticDeviceMappingProvider(
                        reader=S2000PPConfigurationReader(
                            client,
                            self._gateway_context.modbus_unit_id,
                        ),
                        cache=cache,
                    )
                    mapping = await provider.async_resolve(
                        gateway=self._gateway_context,
                        model=self._data[Config.CONF_DEVICE_CLASS],
                        orion_address=self._orion_address,
                        dpls=self._dpls_identity,
                        metadata=self._device_metadata,
                    )
                    if await self._async_validate_and_store_mapping(mapping):
                        return self._create_device_entry(
                            suffix=f" Orion {mapping.identity.orion_address}"
                        )
                    errors["base"] = "invalid_equipment_mapping"
            except DeviceMappingNotFoundError:
                errors["base"] = "downstream_device_not_found"
            except ModbusException:
                errors["base"] = "cannot_read_gateway_configuration"
            except ValueError:
                errors["base"] = "invalid_mapping"
            except Exception as exc:  # pymodbus transports expose backend exceptions
                _LOGGER.exception("Failed to read S2000-PP configuration: %s", exc)
                errors["base"] = "cannot_read_gateway_configuration"
            finally:
                if client is not None:
                    client.close()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_ORION_ADDRESS): vol.All(
                    int,
                    vol.Range(min=1, max=127),
                )
            }
        )
        return self.async_show_form(
            step_id="automatic_device",
            data_schema=schema,
            errors=errors,
        )

    async def _async_validate_and_store_mapping(
        self,
        mapping: ResolvedDeviceMapping,
    ) -> bool:
        """Validate equipment capabilities and store a resolved mapping."""
        try:
            await self.hass.async_add_executor_job(
                validate_equipment_gateway_mapping,
                self._selected_manufacturer.lower(),
                self._data[Config.CONF_DEVICE_CLASS],
                mapping,
            )
        except ValueError:
            return False

        identity = mapping.identity
        if identity.dpls is not None:
            for entry in self.hass.config_entries.async_entries(Config.DOMAIN):
                config = entry.options or entry.data
                existing_data = config.get(Config.CONF_GATEWAY_MAPPING)
                if not existing_data:
                    continue
                try:
                    existing = ResolvedDeviceMapping.from_dict(existing_data).identity
                except (KeyError, TypeError, ValueError):
                    continue
                if dpls_ranges_overlap(identity, existing):
                    return False

        self._data[Config.CONF_GATEWAY_MAPPING] = mapping.to_dict()
        await self.async_set_unique_id(mapping.identity.stable_id)
        self._abort_if_unique_id_configured()
        return True
