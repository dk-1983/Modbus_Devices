"""The modbus_devices service integration."""

from logging import getLogger

from pymodbus.exceptions import ConnectionException, ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import Config
from .coordinator import ModbusDeviceCoordinator
from .equipment.equipment import get_class
from .gateway import ResolvedDeviceMapping
from .manufacturer import canonicalize_manufacturer_options
from .modbus_client import connect_modbus

_LOGGER = getLogger(__name__)


def _close_client(client) -> None:
    """Close a client without masking the lifecycle exception being handled."""
    if client is None:
        return
    try:
        client.close()
    except Exception:
        _LOGGER.exception("Error closing Modbus client")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up ModbusDevices from a config entry."""

    hass.data.setdefault(Config.DOMAIN, {})

    # Migrate old data -> options and canonicalize persisted manufacturer values.
    try:
        options = canonicalize_manufacturer_options(entry.options or entry.data)
    except ValueError as exc:
        raise ConfigEntryError(str(exc)) from exc

    if options != dict(entry.options) or (entry.data and not entry.options):
        hass.config_entries.async_update_entry(
            entry,
            data={},
            options=options,
        )

    manufacturer = options.get(Config.CONF_MANUFACTURER)
    client = None

    try:
        # -----------------------------------
        # Create Modbus client
        # -----------------------------------
        client = await connect_modbus(options)

        if not client or not getattr(client, "connected", False):
            raise ConfigEntryNotReady("Unable to establish Modbus connection")

        # -----------------------------------
        # Read safe config values
        # -----------------------------------
        manufacturer = options.get(Config.CONF_MANUFACTURER)
        device_name = options.get(Config.CONF_DEVICE_CLASS)
        device_id = options.get("device_id") or options.get(Config.CONF_DEVICE_ID)

        if not manufacturer or not device_name:
            raise ConfigEntryError(
                f"Missing config: manufacturer={manufacturer}, device={device_name}"
            )

        # -----------------------------------
        # Load device class
        # -----------------------------------
        try:
            device_class = await hass.async_add_executor_job(
                get_class,
                manufacturer,
                device_name,
            )
        except (AttributeError, ImportError, ValueError) as exc:
            raise ConfigEntryError(
                f"Invalid equipment configuration: {manufacturer}/{device_name}"
            ) from exc

        mapping_data = options.get(Config.CONF_GATEWAY_MAPPING)
        try:
            gateway_mapping = (
                None
                if mapping_data is None
                else ResolvedDeviceMapping.from_dict(mapping_data)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigEntryError("Invalid persisted gateway mapping") from exc
        required_gateway = getattr(device_class, "required_gateway", None)
        if required_gateway is not None and gateway_mapping is None:
            raise ConfigEntryError(
                f"{device_name} requires a validated gateway mapping"
            )
        if (
            required_gateway is not None
            and gateway_mapping.identity.gateway.gateway_type is not required_gateway
        ):
            raise ConfigEntryError(
                f"Gateway mapping type does not match {device_name}"
            )

        # -----------------------------------
        # Create device
        # -----------------------------------
        device = device_class(
            client,
            device_id,
        )

        io_mapping = options.get(Config.CONF_IO_MAPPING)
        if io_mapping is not None:
            apply_io_mapping = getattr(device, "apply_io_mapping", None)
            if not callable(apply_io_mapping):
                raise ConfigEntryError(
                    f"{device_name} does not support direct I/O mappings"
                )
            try:
                apply_io_mapping(io_mapping)
            except (KeyError, TypeError, ValueError) as exc:
                raise ConfigEntryError("Invalid persisted direct I/O mapping") from exc

        if getattr(device, "uses_stable_entry_identity", False):
            stable_identity = entry.unique_id or entry.entry_id
            device.attr_unique_id_prefix = stable_identity
            device.attr_device_identifier = stable_identity

        if gateway_mapping is not None:
            apply_mapping = getattr(device, "apply_gateway_mapping", None)
            if not callable(apply_mapping):
                raise ConfigEntryError(
                    f"{device_name} does not support gateway mappings"
                )
            try:
                apply_mapping(gateway_mapping)
            except (KeyError, TypeError, ValueError) as exc:
                raise ConfigEntryError("Invalid equipment gateway mapping") from exc

        await device.data_init()

        # -----------------------------------
        # Coordinator
        # -----------------------------------
        coordinator = ModbusDeviceCoordinator(
            hass=hass,
            device=device,
        )

        await coordinator.async_config_entry_first_refresh()

        # -----------------------------------
        # Store runtime objects
        # -----------------------------------
        hass.data[Config.DOMAIN][entry.entry_id] = {
            "client": client,
            "device": device,
            "coordinator": coordinator,
            "gateway_mapping": gateway_mapping,
        }

        _LOGGER.info(
            "Modbus device initialized: %s (%s)",
            entry.title,
            manufacturer,
        )

        # -----------------------------------
        # Platforms
        # -----------------------------------
        await hass.config_entries.async_forward_entry_setups(
            entry,
            device.attr_platforms,
        )

        _LOGGER.info(
            "Platforms loaded: %s",
            device.attr_platforms,
        )

        return True

    except (ConnectionException, ModbusException, OSError, TimeoutError) as exc:
        _close_client(client)
        raise ConfigEntryNotReady(f"Modbus connection failed: {exc}") from exc

    except (ConfigEntryError, ConfigEntryNotReady):
        _close_client(client)
        raise

    except Exception:
        # Programming and platform errors must remain visible to Home Assistant.
        hass.data[Config.DOMAIN].pop(entry.entry_id, None)
        _close_client(client)
        raise


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload ModbusDevices config entry."""

    entry_data = hass.data.get(Config.DOMAIN, {}).get(entry.entry_id)

    if not entry_data:
        _LOGGER.warning("Device already removed: %s", entry.entry_id)
        return True

    device = entry_data["device"]
    client = entry_data["client"]

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        device.attr_platforms,
    )

    if unload_ok:
        _close_client(client)

        hass.data[Config.DOMAIN].pop(entry.entry_id, None)

        _LOGGER.info("Modbus device unloaded: %s", entry.title)

    return unload_ok
