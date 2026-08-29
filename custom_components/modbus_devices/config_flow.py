"""Config flow for Modbus Devices."""

from __future__ import annotations

import ipaddress
import math
from typing import Any

from pymodbus.exceptions import ModbusException
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME, CONF_PORT
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import Config
from .equipment.equipment import (
    get_equipment_classes_by_manufacturer,
    get_equipment_display_name,
    get_gateway_capabilities,
    get_gateway_device_metadata,
    get_gateway_requirement,
    get_manual_io_mapping_spec,
    validate_equipment_gateway_mapping,
)
from .gateway import (
    CapabilityRequirement,
    DPLSSubIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayCapabilitySpec,
    GatewayType,
    MappingSource,
    ObjectKind,
    ResolvedDeviceMapping,
    ResolvedObjectMapping,
    compatible_gateway_contexts,
)
from .mapping import (
    AmbiguousDeviceMappingError,
    AutomaticDeviceMappingProvider,
    DeviceMappingNotFoundError,
    ManualDeviceMappingProvider,
    available_gateway_capabilities,
    has_overlapping_dpls_mapping,
    manual_mapping_for_capability,
)
from .manufacturer import canonical_manufacturer_name
from .modbus_client import connect_modbus, get_serial_ports
from .s2000_pp import (
    S2000PPConfigurationCache,
    S2000PPConfigurationReader,
    manual_relay_mapping,
    manual_zone_mapping,
)

_TRANSPORT_CHOICES = {
    "modbus_tcp": Config.MODBUS_TCP,
    "modbus_udp": Config.MODBUS_UDP,
    Config.MODBUS_RTU_OVER_UDP: Config.MODBUS_RTU_OVER_UDP,
    "serial": Config.MODBUS_SERIAL,
}
_VIA_EXISTING_GATEWAY = "existing_gateway"


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
        self._manual_io_mapping_spec: dict[str, Any] | None = None
        self._gateway_entry_id: str | None = None
        self._discovered_addresses: tuple[int, ...] = ()

    # ---------------------------------------------------------
    # STEP 1 - MODE
    # ---------------------------------------------------------
    async def async_step_user(self, user_input=None):
        """Select connection type."""

        if not self._device_classes:
            self._device_classes = await self.hass.async_add_executor_job(
                get_equipment_classes_by_manufacturer
            )

        if not self._serial_ports:
            self._serial_ports = await self.hass.async_add_executor_job(
                get_serial_ports
            )

        if user_input is not None:
            selected = user_input[Config.CONF_MODBUS_MODE]
            if selected == _VIA_EXISTING_GATEWAY:
                return await self.async_step_existing_gateway()
            self._data[Config.CONF_MODBUS_MODE] = _TRANSPORT_CHOICES.get(
                selected, selected
            )
            return await self.async_step_manufacturer()

        schema = vol.Schema(
            {
                vol.Required(Config.CONF_MODBUS_MODE): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": list(_TRANSPORT_CHOICES)
                            + (
                                [_VIA_EXISTING_GATEWAY]
                                if self._existing_s2000_pp_entries()
                                else []
                            ),
                            "translation_key": "modbus_transport",
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
            self._selected_manufacturer = canonical_manufacturer_name(
                user_input[Config.CONF_MANUFACTURER]
            )

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
            await self._async_prepare_selected_device(device_name)

            if self._manual_io_mapping_spec is not None:
                return await self.async_step_io_mapping()

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
                            "options": [
                                {"value": name, "label": await self.hass.async_add_executor_job(
                                    get_equipment_display_name,
                                    self._selected_manufacturer,
                                    name,
                                )}
                                for name in sorted(devices)
                            ],
                        }
                    }
                )
            }
        )

        return self.async_show_form(step_id="device", data_schema=schema)

    async def _async_prepare_selected_device(self, device_name: str) -> None:
        """Load model-owned routing metadata without changing direct entry shape."""
        self._data[Config.CONF_MANUFACTURER] = self._selected_manufacturer
        self._data[Config.CONF_DEVICE_CLASS] = device_name
        self._required_gateway = await self.hass.async_add_executor_job(
            get_gateway_requirement,
            self._selected_manufacturer,
            device_name,
        )
        self._manual_io_mapping_spec = await self.hass.async_add_executor_job(
            get_manual_io_mapping_spec,
            self._selected_manufacturer,
            device_name,
        )

    def _existing_s2000_pp_entries(self) -> dict[str, Any]:
        """Return loaded direct С2000-ПП entries eligible for client sharing."""
        gateways = {}
        for entry in self.hass.config_entries.async_entries(Config.DOMAIN):
            options = entry.options or entry.data
            if (
                options.get(Config.CONF_MANUFACTURER) == "Bolid"
                and options.get(Config.CONF_DEVICE_CLASS) == "S2000PP"
                and not options.get(Config.CONF_GATEWAY_ENTRY_ID)
                and hasattr(entry, "runtime_data")
                and getattr(entry.runtime_data.client, "connected", False)
            ):
                gateways[entry.entry_id] = entry
        return gateways

    async def async_step_existing_gateway(self, user_input=None):
        """Select one already loaded direct С2000-ПП Config Entry."""
        gateways = self._existing_s2000_pp_entries()
        errors = {}
        if user_input is not None:
            entry_id = user_input[Config.CONF_GATEWAY_ENTRY_ID]
            gateway_entry = gateways.get(entry_id)
            if gateway_entry is None:
                errors["base"] = "gateway_unavailable"
            else:
                options = gateway_entry.options or gateway_entry.data
                unit_id = int(options.get(CONF_DEVICE_ID, 1))
                self._gateway_entry_id = entry_id
                self._required_gateway = GatewayType.S2000_PP
                self._gateway_context = GatewayContext(
                    gateway_type=GatewayType.S2000_PP,
                    gateway_id=gateway_entry.unique_id or gateway_entry.entry_id,
                    connection_key=f"config_entry:{gateway_entry.entry_id}",
                    modbus_unit_id=unit_id,
                )
                self._data = {
                    Config.CONF_GATEWAY_ENTRY_ID: entry_id,
                    Config.CONF_MANUFACTURER: "Bolid",
                    CONF_DEVICE_ID: unit_id,
                }
                self._selected_manufacturer = "Bolid"
                return await self.async_step_gateway_child_model()

        options = [
            {"value": entry_id, "label": entry.title}
            for entry_id, entry in sorted(gateways.items())
        ]
        if not options:
            return self.async_abort(reason="no_loaded_gateways")
        return self.async_show_form(
            step_id="existing_gateway",
            data_schema=vol.Schema(
                {
                    vol.Required(Config.CONF_GATEWAY_ENTRY_ID): selector(
                        {"select": {"mode": "dropdown", "options": options}}
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_gateway_child_model(self, user_input=None):
        """Select a model explicitly supported behind С2000-ПП."""
        devices = []
        for name in self._device_classes.get("Bolid", []):
            requirement = await self.hass.async_add_executor_job(
                get_gateway_requirement, "Bolid", name
            )
            metadata = await self.hass.async_add_executor_job(
                get_gateway_device_metadata, "Bolid", name
            )
            if (
                requirement is GatewayType.S2000_PP
                and metadata["gateway_transport_supported"]
            ):
                devices.append(name)
        if user_input is not None:
            device_name = user_input[Config.CONF_DEVICE_CLASS]
            if device_name not in devices:
                return self.async_show_form(
                    step_id="gateway_child_model",
                    data_schema=vol.Schema({}),
                    errors={"base": "unsupported_gateway_device"},
                )
            await self._async_prepare_selected_device(device_name)
            return await self.async_step_gateway_device()
        return self.async_show_form(
            step_id="gateway_child_model",
            data_schema=vol.Schema(
                {
                    vol.Required(Config.CONF_DEVICE_CLASS): selector(
                        {"select": {"mode": "dropdown", "options": [
                            {
                                "value": name,
                                "label": await self.hass.async_add_executor_job(
                                    get_equipment_display_name, "Bolid", name
                                ),
                            }
                            for name in sorted(devices)
                        ]}}
                    )
                }
            ),
        )

    # ---------------------------------------------------------
    # ROUTER
    # ---------------------------------------------------------
    async def _next_step(self):
        mode = self._data.get(Config.CONF_MODBUS_MODE)

        if mode in (Config.MODBUS_TCP, Config.MODBUS_UDP):
            return await self.async_step_network()

        if mode == Config.MODBUS_RTU_OVER_UDP:
            return await self.async_step_rtu_over_udp()

        return await self.async_step_serial()

    async def async_step_io_mapping(self, user_input=None):
        """Collect the compact user-program-defined Modbus I/O layout."""
        errors = {}
        if user_input is not None:
            try:
                di_area = user_input[Config.CONF_DI_DATA_AREA]
                if di_area not in self._manual_io_mapping_spec["di_data_areas"]:
                    raise ValueError("Unsupported DI data area")
                mapping = {
                    Config.CONF_DI_DATA_AREA: di_area,
                    Config.CONF_DI_BASE_ADDRESS: int(
                        user_input[Config.CONF_DI_BASE_ADDRESS]
                    ),
                    Config.CONF_DI_ADDRESS_STRIDE: int(
                        user_input[Config.CONF_DI_ADDRESS_STRIDE]
                    ),
                    Config.CONF_DO_BASE_ADDRESS: int(
                        user_input[Config.CONF_DO_BASE_ADDRESS]
                    ),
                    Config.CONF_DO_ADDRESS_STRIDE: int(
                        user_input[Config.CONF_DO_ADDRESS_STRIDE]
                    ),
                }
                if (
                    mapping[Config.CONF_DI_BASE_ADDRESS] < 0
                    or mapping[Config.CONF_DO_BASE_ADDRESS] < 0
                ):
                    raise ValueError("Base addresses must not be negative")
                if (
                    mapping[Config.CONF_DI_ADDRESS_STRIDE] < 1
                    or mapping[Config.CONF_DO_ADDRESS_STRIDE] < 1
                ):
                    raise ValueError("Address strides must be positive")
                self._data[Config.CONF_IO_MAPPING] = mapping
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_io_mapping"
            else:
                return await self._next_step()

        schema = vol.Schema(
            {
                vol.Required(
                    Config.CONF_DI_DATA_AREA,
                    default="discrete_input",
                ): selector(
                    {
                        "select": {
                            "mode": "dropdown",
                            "options": list(
                                self._manual_io_mapping_spec["di_data_areas"]
                            ),
                        }
                    }
                ),
                vol.Required(
                    Config.CONF_DI_BASE_ADDRESS,
                    default=0,
                ): vol.All(int, vol.Range(min=0)),
                vol.Required(
                    Config.CONF_DI_ADDRESS_STRIDE,
                    default=1,
                ): vol.All(int, vol.Range(min=1)),
                vol.Required(
                    Config.CONF_DO_BASE_ADDRESS,
                    default=0,
                ): vol.All(int, vol.Range(min=0)),
                vol.Required(
                    Config.CONF_DO_ADDRESS_STRIDE,
                    default=1,
                ): vol.All(int, vol.Range(min=1)),
            }
        )
        return self.async_show_form(
            step_id="io_mapping",
            data_schema=schema,
            errors=errors,
        )

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

            except (ModbusException, OSError, TimeoutError):
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

    async def async_step_rtu_over_udp(self, user_input=None):
        """Configure a raw Modbus RTU ADU transported over UDP."""
        errors = {}
        if user_input is not None:
            try:
                host = cv.string(user_input[CONF_HOST]).strip().lower()
                if not host:
                    raise ValueError("Remote host must not be empty")
                remote_port = int(user_input[Config.CONF_REMOTE_PORT])
                local_udp_port = int(
                    user_input.get(Config.CONF_LOCAL_UDP_PORT, remote_port)
                )
                timeout = float(user_input[Config.CONF_TIMEOUT])
                local_bind_address = cv.string(
                    user_input.get(Config.CONF_LOCAL_BIND_ADDRESS, "")
                ).strip()
                if not 1 <= remote_port <= 65535:
                    raise ValueError("Remote UDP port is out of range")
                if not 1 <= local_udp_port <= 65535:
                    raise ValueError("Local UDP port is out of range")
                if not math.isfinite(timeout) or timeout <= 0:
                    raise ValueError("Timeout must be positive and finite")
                if local_bind_address:
                    ipaddress.IPv4Address(local_bind_address)
                device_id = int(user_input.get(CONF_DEVICE_ID, 1))
                if not 1 <= device_id <= 247:
                    raise ValueError("Device ID is out of range")
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_rtu_over_udp_config"
            else:
                self._data.update(
                    {
                        CONF_HOST: host,
                        Config.CONF_REMOTE_PORT: remote_port,
                        Config.CONF_LOCAL_UDP_PORT: local_udp_port,
                        Config.CONF_TIMEOUT: timeout,
                        Config.CONF_LOCAL_BIND_ADDRESS: local_bind_address,
                        CONF_DEVICE_ID: device_id,
                        CONF_NAME: cv.string(
                            user_input.get(CONF_NAME, "Modbus Device")
                        ),
                    }
                )
                try:
                    client = await connect_modbus(self._data)
                    if not client or not client.connected:
                        errors["base"] = "cannot_connect"
                    else:
                        client.close()
                        unique_id = (
                            f"{Config.MODBUS_RTU_OVER_UDP}:{host}:"
                            f"{remote_port}:{device_id}"
                        )
                        return await self._async_connection_ready(unique_id)
                except (ModbusException, OSError, TimeoutError):
                    errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default="10.0.2.10"): cv.string,
                vol.Required(Config.CONF_REMOTE_PORT, default=40000): vol.All(
                    int, vol.Range(min=1, max=65535)
                ),
                vol.Optional(Config.CONF_LOCAL_UDP_PORT, default=40000): vol.All(
                    int, vol.Range(min=1, max=65535)
                ),
                vol.Required(Config.CONF_TIMEOUT, default=2.5): vol.Coerce(float),
                vol.Optional(Config.CONF_LOCAL_BIND_ADDRESS, default=""): cv.string,
                vol.Required(CONF_DEVICE_ID, default=1): vol.All(
                    int, vol.Range(min=1, max=247)
                ),
                vol.Optional(CONF_NAME, default="Modbus Device"): cv.string,
            }
        )
        return self.async_show_form(
            step_id="rtu_over_udp",
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

            except (ModbusException, OSError, TimeoutError):
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
        if mode == Config.MODBUS_RTU_OVER_UDP:
            return (
                f"{mode}:{self._data[CONF_HOST]}:"
                f"{self._data[Config.CONF_REMOTE_PORT]}"
            )

        return (
            f"{mode}:{self._data[Config.CONF_COM_PORT]}:"
            f"{self._data[Config.CONF_BAUDRATE]}:"
            f"{self._data[Config.CONF_BYTESIZE]}:"
            f"{self._data[Config.CONF_PARITY]}:"
            f"{self._data[Config.CONF_STOPBITS]}"
        )

    def _existing_gateway_contexts(self) -> dict[str, GatewayContext]:
        """Return compatible gateway contexts from existing entries."""
        serialized_mappings = (
            (entry.options or entry.data).get(Config.CONF_GATEWAY_MAPPING)
            for entry in self.hass.config_entries.async_entries(Config.DOMAIN)
        )
        return compatible_gateway_contexts(
            serialized_mappings,
            gateway_type=self._required_gateway,
            connection_key=self._connection_key(),
            modbus_unit_id=self._data[CONF_DEVICE_ID],
        )

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
                self._selected_manufacturer,
                self._data[Config.CONF_DEVICE_CLASS],
            )
        if not self._gateway_device_metadata["gateway_transport_supported"]:
            return self.async_show_form(
                step_id="gateway_device",
                data_schema=vol.Schema({}),
                errors={"base": "unsupported_gateway_transport"},
                description_placeholders={
                    "transport_limitation": self._gateway_device_metadata[
                        "gateway_transport_limitation"
                    ]
                    or "This gateway transport is not supported",
                },
            )
        if not self._gateway_device_metadata["uses_dpls_identity"]:
            return await self.async_step_mapping_source()

        errors = {}
        if user_input is not None:
            variant = user_input.get(Config.CONF_DEVICE_VARIANT)
            topology = user_input.get(Config.CONF_DEVICE_TOPOLOGY)
            if variant in self._gateway_device_metadata["unsupported_variants"]:
                errors[Config.CONF_DEVICE_VARIANT] = "unsupported_variant"
            else:
                try:
                    self._orion_address = user_input[Config.CONF_ORION_ADDRESS]
                    address_count = self._gateway_device_metadata[
                        "topology_dpls_address_counts"
                    ].get(topology)
                    if address_count is None:
                        address_count = self._gateway_device_metadata[
                            "variant_dpls_address_counts"
                        ].get(variant, self._gateway_device_metadata["dpls_address_count"])
                    self._dpls_identity = DPLSSubIdentity(
                        base_address=user_input[Config.CONF_DPLS_BASE_ADDRESS],
                        address_count=address_count,
                    )
                    self._device_metadata = DownstreamDeviceMetadata(
                        variant=variant, topology=topology
                    )
                except (KeyError, TypeError, ValueError):
                    errors["base"] = "invalid_mapping"
                else:
                    return await self.async_step_mapping_source()

        schema_fields = {}
        if self._gateway_device_metadata["variants"]:
            variant_key = (
                vol.Optional(Config.CONF_DEVICE_VARIANT)
                if self._gateway_device_metadata["variant_optional"]
                else vol.Required(Config.CONF_DEVICE_VARIANT)
            )
            schema_fields[variant_key] = selector(
                    {"select": {"mode": "dropdown", "options": [
                        {"value": value, "label": label}
                        for value, label in self._gateway_device_metadata["variants"].items()
                    ]}}
                )
        if self._gateway_device_metadata["topologies"]:
            schema_fields[vol.Required(Config.CONF_DEVICE_TOPOLOGY)] = selector(
                {"select": {"mode": "dropdown", "options": [
                    {"value": value, "label": label}
                    for value, label in self._gateway_device_metadata["topologies"].items()
                ]}}
            )
        schema_fields.update({
                vol.Required(Config.CONF_ORION_ADDRESS): vol.All(
                    int, vol.Range(min=1, max=127)
                ),
                vol.Required(Config.CONF_DPLS_BASE_ADDRESS): vol.All(
                    int, vol.Range(min=1, max=127)
                ),
            })
        schema = vol.Schema(schema_fields)
        return self.async_show_form(
            step_id="gateway_device", data_schema=schema, errors=errors,
            description_placeholders={
                "unsupported_variant": "С2000-СП4/220 исп.02 is not supported"
            },
        )

    async def async_step_mapping_source(self, user_input=None):
        """Select manual or configuration-assisted exact capability mapping."""
        if not self._gateway_capabilities:
            self._gateway_capabilities = await self.hass.async_add_executor_job(
                get_gateway_capabilities,
                self._selected_manufacturer,
                self._data[Config.CONF_DEVICE_CLASS],
                self._device_metadata,
            )
        if user_input is not None:
            source = MappingSource(user_input[Config.CONF_MAPPING_SOURCE])
            if source is MappingSource.AUTOMATIC:
                if self._gateway_entry_id is not None:
                    return await self.async_step_discovered_device()
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

    def _selected_gateway_runtime(self):
        """Return the still-loaded selected gateway runtime or None."""
        if self._gateway_entry_id is None:
            return None
        gateway = self._existing_s2000_pp_entries().get(self._gateway_entry_id)
        return None if gateway is None else gateway.runtime_data

    def _already_added_orion_addresses(self) -> set[int]:
        """Return physical Orion identities already added through this gateway."""
        addresses = set()
        for entry in self.hass.config_entries.async_entries(Config.DOMAIN):
            mapping_data = (entry.options or entry.data).get(
                Config.CONF_GATEWAY_MAPPING
            )
            if not mapping_data:
                continue
            try:
                identity = ResolvedDeviceMapping.from_dict(mapping_data).identity
            except (KeyError, TypeError, ValueError):
                continue
            if identity.gateway.stable_id == self._gateway_context.stable_id:
                addresses.add(identity.orion_address)
        return addresses

    async def async_step_discovered_device(self, user_input=None):
        """List configured Orion addresses without auto-importing any device."""
        errors = {}
        runtime = self._selected_gateway_runtime()
        if runtime is None:
            errors["base"] = "gateway_unavailable"
        else:
            try:
                domain_data = self.hass.data.setdefault(Config.DOMAIN, {})
                cache = domain_data.setdefault(
                    "s2000_pp_configuration_cache", S2000PPConfigurationCache()
                )
                configuration = await cache.async_get_or_load(
                    self._gateway_context.stable_id,
                    S2000PPConfigurationReader(
                        runtime.client, self._gateway_context.modbus_unit_id
                    ).async_read,
                )
                configured = {
                    row.device_address
                    for row in configuration.zones + configuration.relays
                    if 1 <= row.device_address <= 127
                }
                self._discovered_addresses = tuple(
                    sorted(configured - self._already_added_orion_addresses())
                )
            except (ModbusException, OSError, TimeoutError):
                errors["base"] = "cannot_read_gateway_configuration"

        if user_input is not None and not errors:
            try:
                address = int(user_input[Config.CONF_DISCOVERED_ADDRESS])
                if address not in self._discovered_addresses:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_dynamic_address"
            else:
                self._orion_address = address
                return await self.async_step_automatic_device(
                    {Config.CONF_ORION_ADDRESS: address}
                )

        options = [
            {"value": str(address), "label": f"Orion {address}"}
            for address in self._discovered_addresses
        ]
        if not options and not errors:
            errors["base"] = "no_discovered_devices"
        return self.async_show_form(
            step_id="discovered_device",
            data_schema=vol.Schema(
                {
                    vol.Required(Config.CONF_DISCOVERED_ADDRESS): selector(
                        {"select": {"mode": "dropdown", "options": options}}
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_manual_device(self, user_input=None):
        """Identify the downstream physical device."""
        if self._dpls_identity is not None and self._orion_address is not None:
            self._gateway_capabilities = await self.hass.async_add_executor_job(
                get_gateway_capabilities,
                self._selected_manufacturer,
                self._data[Config.CONF_DEVICE_CLASS],
                self._device_metadata,
            )
            return await self.async_step_manual_object()
        if user_input is not None:
            self._orion_address = user_input[Config.CONF_ORION_ADDRESS]
            self._gateway_capabilities = await self.hass.async_add_executor_job(
                get_gateway_capabilities,
                self._selected_manufacturer,
                self._data[Config.CONF_DEVICE_CLASS],
                self._device_metadata,
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
        available = available_gateway_capabilities(
            self._gateway_capabilities,
            self._manual_objects,
            self._dpls_identity,
        )
        if user_input is not None:
            try:
                spec = available[user_input[Config.CONF_CAPABILITY_KEY]]
                table_number = user_input[Config.CONF_GATEWAY_OBJECT_NUMBER]
                resolved_object = manual_mapping_for_capability(
                    spec,
                    table_number,
                    self._dpls_identity,
                )
                self._manual_objects.append(resolved_object)
            except (KeyError, ValueError):
                errors["base"] = "invalid_mapping"
            else:
                remaining = available_gateway_capabilities(
                    self._gateway_capabilities,
                    self._manual_objects,
                    self._dpls_identity,
                )
                required_remain = any(
                    item.requirement
                    is CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION
                    for item in remaining.values()
                )
                if required_remain or user_input[Config.CONF_ADD_ANOTHER_OBJECT]:
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
            owns_client = self._gateway_entry_id is None
            try:
                if owns_client:
                    client = await connect_modbus(self._data)
                else:
                    runtime = self._selected_gateway_runtime()
                    if runtime is None:
                        errors["base"] = "gateway_unavailable"
                        return self.async_show_form(
                            step_id="automatic_device",
                            data_schema=vol.Schema({}),
                            errors=errors,
                        )
                    client = runtime.client
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
                        capabilities=self._gateway_capabilities,
                    )
                    if await self._async_validate_and_store_mapping(mapping):
                        return self._create_device_entry(
                            suffix=f" Orion {mapping.identity.orion_address}"
                        )
                    errors["base"] = "invalid_equipment_mapping"
            except AmbiguousDeviceMappingError:
                errors["base"] = "ambiguous_device_mapping"
            except DeviceMappingNotFoundError:
                errors["base"] = "downstream_device_not_found"
            except ModbusException:
                errors["base"] = "cannot_read_gateway_configuration"
            except ValueError:
                errors["base"] = "invalid_mapping"
            except (OSError, TimeoutError):
                errors["base"] = "cannot_read_gateway_configuration"
            finally:
                if owns_client and client is not None:
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
                self._selected_manufacturer,
                self._data[Config.CONF_DEVICE_CLASS],
                mapping,
            )
        except ValueError:
            return False

        identity = mapping.identity
        if identity.dpls is not None:
            existing_mappings = (
                (entry.options or entry.data).get(Config.CONF_GATEWAY_MAPPING)
                for entry in self.hass.config_entries.async_entries(Config.DOMAIN)
            )
            if has_overlapping_dpls_mapping(
                identity,
                (item for item in existing_mappings if item),
            ):
                return False

        self._data[Config.CONF_GATEWAY_MAPPING] = mapping.to_dict()
        await self.async_set_unique_id(mapping.identity.stable_id)
        self._abort_if_unique_id_configured()
        return True
