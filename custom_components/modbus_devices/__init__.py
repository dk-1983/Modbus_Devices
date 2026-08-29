"""The modbus_devices service integration."""

from logging import getLogger

from pymodbus.exceptions import ConnectionException, ModbusException

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import Config
from .coordinator import ModbusDeviceCoordinator
from .dashboard import async_register_dashboard_frontend
from .equipment.equipment import get_class
from .gateway import ResolvedDeviceMapping, dpls_ranges_overlap
from .manufacturer import canonicalize_manufacturer_options
from .modbus_client import connect_modbus
from .runtime import ModbusDevicesConfigEntry, ModbusDevicesRuntimeData
from .s2000_pp import S2000PPConfigurationCache, S2000PPConfigurationReader

_LOGGER = getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(Config.DOMAIN)


async def _async_reconcile_gateway_mapping(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
    options: dict,
    device_class,
    client,
    mapping: ResolvedDeviceMapping,
) -> tuple[dict, ResolvedDeviceMapping]:
    """Repair an equipment mapping only from an unambiguous live table."""
    reconcile = getattr(device_class, "reconcile_gateway_mapping", None)
    if not callable(reconcile):
        return options, mapping

    domain_data = hass.data.setdefault(Config.DOMAIN, {})
    cache = domain_data.setdefault(
        "s2000_pp_mapping_reconciliation_cache",
        S2000PPConfigurationCache(),
    )
    gateway = mapping.identity.gateway
    configuration = await cache.async_get_or_load(
        gateway.stable_id,
        S2000PPConfigurationReader(
            client,
            gateway.modbus_unit_id,
        ).async_read,
    )
    try:
        reconciled = reconcile(mapping, configuration)
    except ValueError as exc:
        raise ConfigEntryError(
            "Persisted equipment mapping does not match the current S2000-PP "
            "configuration; reconfigure the device mapping"
        ) from exc

    async_entries = getattr(hass.config_entries, "async_entries", None)
    if callable(async_entries):
        for other in async_entries(Config.DOMAIN):
            if getattr(other, "entry_id", None) == getattr(entry, "entry_id", None):
                continue
            other_data = (other.options or other.data).get(Config.CONF_GATEWAY_MAPPING)
            if not other_data:
                continue
            try:
                other_identity = ResolvedDeviceMapping.from_dict(other_data).identity
            except (KeyError, TypeError, ValueError):
                continue
            if (
                other_identity.stable_id == reconciled.identity.stable_id
                or dpls_ranges_overlap(other_identity, reconciled.identity)
            ):
                raise ConfigEntryError(
                    "Persisted equipment mappings claim the same physical DPLS "
                    "device; reconfigure the duplicate entries"
                )

    if reconciled == mapping:
        return options, mapping

    repaired_options = dict(options)
    repaired_options[Config.CONF_GATEWAY_MAPPING] = reconciled.to_dict()
    hass.config_entries.async_update_entry(
        entry,
        data={},
        options=repaired_options,
    )
    return repaired_options, reconciled


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration-wide dashboard presentation support once."""
    await async_register_dashboard_frontend(hass)
    return True


def _close_client(client) -> None:
    """Close a client without masking the lifecycle exception being handled."""
    if client is None:
        return
    try:
        client.close()
    except Exception:
        _LOGGER.exception("Error closing Modbus client")


def _clear_runtime_data(entry: ModbusDevicesConfigEntry) -> None:
    """Discard runtime references after failed setup or successful unload."""
    if hasattr(entry, "runtime_data"):
        del entry.runtime_data


def _remove_legacy_clock_control(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
    device,
) -> None:
    """Remove the former writable M3000 clock entity from the registry."""
    if not getattr(device, "attr_has_device_time_sensor", False):
        return
    entity_registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_clock_1"
    if entity_id := entity_registry.async_get_entity_id(
        Platform.DATETIME,
        Config.DOMAIN,
        unique_id,
    ):
        entity_registry.async_remove(entity_id)
        _LOGGER.info("Removed legacy writable M3000 clock entity: %s", entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
) -> bool:
    """Set up ModbusDevices from a config entry."""

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
    owns_client = True
    gateway_entry_id = options.get(Config.CONF_GATEWAY_ENTRY_ID)
    setup_succeeded = False

    try:
        # -----------------------------------
        # Create Modbus client
        # -----------------------------------
        if gateway_entry_id:
            gateway_entry = hass.config_entries.async_get_entry(gateway_entry_id)
            if gateway_entry is None or not hasattr(gateway_entry, "runtime_data"):
                raise ConfigEntryNotReady("S2000-PP gateway is not loaded")
            client = gateway_entry.runtime_data.client
            owns_client = False
        else:
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

        if gateway_mapping is not None:
            options, gateway_mapping = await _async_reconcile_gateway_mapping(
                hass,
                entry,
                options,
                device_class,
                client,
                gateway_mapping,
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

        post_first_refresh = getattr(device, "async_post_first_refresh", None)
        if callable(post_first_refresh):
            try:
                await post_first_refresh(coordinator.data or {})
            except (ConnectionException, ModbusException, OSError, TimeoutError):
                _LOGGER.warning(
                    "Optional post-refresh maintenance failed for %s",
                    device_name,
                    exc_info=True,
                )

        # -----------------------------------
        # Store runtime objects
        # -----------------------------------
        entry.runtime_data = ModbusDevicesRuntimeData(
            client=client,
            coordinator=coordinator,
            owns_client=owns_client,
        )

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

        _remove_legacy_clock_control(hass, entry, device)

        _LOGGER.info(
            "Platforms loaded: %s",
            device.attr_platforms,
        )

        setup_succeeded = True
        return True

    except (ConnectionException, ModbusException, OSError, TimeoutError) as exc:
        raise ConfigEntryNotReady(f"Modbus connection failed: {exc}") from exc
    finally:
        if not setup_succeeded:
            _clear_runtime_data(entry)
            if owns_client:
                _close_client(client)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ModbusDevicesConfigEntry,
) -> bool:
    """Unload ModbusDevices config entry."""

    if not hasattr(entry, "runtime_data"):
        _LOGGER.warning("Device already removed: %s", entry.entry_id)
        return True

    runtime = entry.runtime_data
    device = runtime.coordinator.device
    client = runtime.client

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        device.attr_platforms,
    )

    if unload_ok:
        if getattr(runtime, "owns_client", True):
            _close_client(client)

        _LOGGER.info("Modbus device unloaded: %s", entry.title)

    return unload_ok
