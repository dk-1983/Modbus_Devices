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

    # migrate old data -> options
    if entry.data:
        hass.config_entries.async_update_entry(
            entry,
            data={},
            options=entry.data,
        )

    try:
        # -----------------------------------
        # Create Modbus client
        # -----------------------------------
        client = await connect_modbus(entry.options)

        if not client or not client.connected:
            raise ConfigEntryNotReady(
                "Unable to establish Modbus connection"
            )

        # -----------------------------------
        # Load device class
        # -----------------------------------
        _LOGGER = getLogger(entry.options[Config.CONF_DEVICE_CLASS])
        cls = entry.options[Config.CONF_DEVICE_CLASS].split(" ")

        device_class = await get_class(
            module=cls[0],
            cls_name=cls[1],
        )

        # -----------------------------------
        # Create device
        # -----------------------------------
        device = device_class(
            client,
            entry.options["device_id"],
        )

        await device.data_init()

        # -----------------------------------
        # Create coordinator
        # -----------------------------------
        coordinator = ModbusDeviceCoordinator(
            hass=hass,
            device=device,
        )

        await coordinator.async_config_entry_first_refresh()

        # -----------------------------------
        # Save integration data
        # -----------------------------------
        hass.data[Config.DOMAIN][entry.entry_id] = {
            "client": client,
            "device": device,
            "coordinator": coordinator,
        }

        _LOGGER.info(
            "Modbus device initialized: %s",
            entry.title,
        )

        # -----------------------------------
        # Forward platforms
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

    except Exception as exc:
        _LOGGER.exception(
            "Setup failed: %s",
            exc,
        )
        return False


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload ModbusDevices config entry."""

    entry_data = hass.data.get(
        Config.DOMAIN,
        {},
    ).get(entry.entry_id)

    if entry_data is None:
        _LOGGER.warning(
            "Device already removed: %s",
            entry.entry_id,
        )
        return True

    device = entry_data["device"]
    client = entry_data["client"]

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        device.attr_platforms,
    )

    if unload_ok:
        # close modbus connection
        if client:
            client.close()

        hass.data[Config.DOMAIN].pop(
            entry.entry_id,
            None,
        )

        _LOGGER.info(
            "Modbus device unloaded: %s",
            entry.title,
        )

    return unload_ok
