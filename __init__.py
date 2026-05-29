"""The modbus_devices service integration."""

from logging import getLogger

from pymodbus.exceptions import ConnectionException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import Config
from .coordinator import ModbusDeviceCoordinator
from .equipment.equipment import get_class
from .modbus_client import connect_modbus

_LOGGER = getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up ModbusDevices from a config entry."""

    hass.data.setdefault(Config.DOMAIN, {})

    # migrate old data -> options (safe)
    if entry.data and not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            data={},
            options=dict(entry.data),
        )

    options = entry.options or {}

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
            raise ConfigEntryNotReady(
                f"Missing config: manufacturer={manufacturer}, device={device_name}"
            )

        manufacturer_module = manufacturer.strip().lower()

        # -----------------------------------
        # Load device class
        # -----------------------------------
        device_class = await get_class(
            module=manufacturer_module,
            cls_name=device_name,
        )

        # -----------------------------------
        # Create device
        # -----------------------------------
        device = device_class(
            client,
            device_id,
        )

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

    except ConnectionException as exc:
        raise ConfigEntryNotReady(
            f"Modbus connection failed: {exc}"
        ) from exc

    except ConfigEntryNotReady:
        raise

    except Exception as exc:
        _LOGGER.exception("Setup failed: %s", exc)
        return False


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
        if client:
            try:
                client.close()
            except Exception:
                _LOGGER.exception("Error closing Modbus client")

        hass.data[Config.DOMAIN].pop(entry.entry_id, None)

        _LOGGER.info("Modbus device unloaded: %s", entry.title)

    return unload_ok
