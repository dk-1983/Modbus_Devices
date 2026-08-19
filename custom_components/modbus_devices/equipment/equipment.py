"""Helpers for equipment discovery."""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
import random
import sys
from typing import Any

from pymodbus.exceptions import ModbusException
from serial.tools import list_ports

from ..const import Config
from ..gateway import GatewayCapabilitySpec, ResolvedDeviceMapping
from ..manufacturer import canonical_manufacturer_name, manufacturer_module_name

_LOGGER = logging.getLogger(__name__)


def validate_write_response(response: Any, operation: str) -> None:
    """Validate that a Modbus write request was accepted."""
    if response is None:
        raise ModbusException(f"Empty Modbus response for {operation}")

    is_error = getattr(response, "isError", None)
    if not callable(is_error):
        raise ModbusException(f"Invalid Modbus response for {operation}")

    if is_error():
        raise ModbusException(f"Modbus error response for {operation}: {response}")


def get_class(module: str, cls_name: str) -> type[Any]:
    """Return an equipment class from a driver module."""
    module = manufacturer_module_name(module)
    imported_module = __import__(
        name=module,
        globals=globals(),
        locals=locals(),
        level=1,
    )
    return getattr(imported_module, cls_name)


def get_gateway_requirement(module: str, cls_name: str):
    """Return the gateway type declared by an equipment class, if any."""
    return getattr(get_class(module, cls_name), "required_gateway", None)


def get_manual_io_mapping_spec(module: str, cls_name: str) -> dict[str, Any] | None:
    """Return an equipment-owned direct Modbus I/O mapping specification."""
    specification = getattr(
        get_class(module, cls_name), "manual_io_mapping_spec", None
    )
    return None if specification is None else dict(specification)


def get_gateway_capabilities(
    module: str,
    cls_name: str,
) -> tuple[GatewayCapabilitySpec, ...]:
    """Return equipment-owned gateway capability definitions."""
    equipment_class = get_class(module, cls_name)
    reader = getattr(equipment_class, "get_gateway_capabilities", None)
    return tuple(reader()) if callable(reader) else ()


def get_gateway_device_metadata(module: str, cls_name: str) -> dict[str, Any]:
    """Return declarative gateway-flow metadata owned by equipment."""
    equipment_class = get_class(module, cls_name)
    variant_reader = getattr(equipment_class, "get_variant_options", None)
    return {
        "uses_dpls_identity": bool(
            getattr(equipment_class, "uses_dpls_identity", False)
        ),
        "dpls_address_count": getattr(equipment_class, "dpls_address_count", None),
        "variants": dict(variant_reader()) if callable(variant_reader) else {},
        "variant_optional": bool(
            getattr(equipment_class, "variant_optional", False)
        ),
        "unsupported_variants": dict(
            getattr(equipment_class, "unsupported_variants", {})
        ),
        "variant_dpls_address_counts": dict(
            getattr(equipment_class, "variant_dpls_address_counts", {})
        ),
        "gateway_transport_supported": bool(
            getattr(equipment_class, "gateway_transport_supported", True)
        ),
        "gateway_transport_limitation": getattr(
            equipment_class, "gateway_transport_limitation", None
        ),
    }


def validate_equipment_gateway_mapping(
    module: str,
    cls_name: str,
    mapping: ResolvedDeviceMapping,
) -> None:
    """Validate a resolved mapping against equipment-owned capabilities."""
    equipment_class = get_class(module, cls_name)
    equipment = equipment_class(None, mapping.identity.gateway.modbus_unit_id)
    apply_mapping = getattr(equipment, "apply_gateway_mapping", None)
    if not callable(apply_mapping):
        raise ValueError(f"{cls_name} does not support gateway mappings")
    apply_mapping(mapping)


def get_classes_from_files() -> dict[str, list[str]]:
    """Return available equipment classes grouped by manufacturer."""
    result: dict[str, list[str]] = {}
    directory = Path(__file__).parent

    driver_files = (
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix == ".py"
        and path.stem not in {"__init__", "equipment"}
    )

    for driver_file in driver_files:
        module_name = driver_file.stem
        module = __import__(
            name=module_name,
            globals=globals(),
            locals=locals(),
            level=1,
        )

        for class_name, equipment_class in inspect.getmembers(
            module,
            inspect.isclass,
        ):
            if equipment_class.__module__.split(".")[-1] != module_name:
                continue

            try:
                instance = equipment_class(None, 1)
                manufacturer = canonical_manufacturer_name(
                    instance.attr_manufactures_name
                )
            except Exception:
                _LOGGER.debug(
                    "Unable to inspect equipment class %s from module %s",
                    class_name,
                    module_name,
                    exc_info=True,
                )
                continue

            result.setdefault(manufacturer, []).append(class_name)

    for class_names in result.values():
        class_names.sort()

    return result


def get_serial_ports() -> list[str]:
    """Return available serial ports."""
    result: set[str] = set()

    try:
        for port in list_ports.comports():
            result.add(port.device)
    except Exception:
        _LOGGER.debug("Unable to enumerate serial ports with pyserial", exc_info=True)

    if sys.platform.startswith(("linux", "cygwin")):
        for pattern in ("ttyUSB*", "ttyACM*", "ttyS*"):
            for device in Path("/dev").glob(pattern):
                result.add(str(device))

    elif sys.platform.startswith("darwin"):
        for device in Path("/dev").glob("tty.*"):
            result.add(str(device))

    elif sys.platform.startswith("win"):
        for number in range(1, 33):
            result.add(f"COM{number}")

    ports = sorted(result)
    return ports or ["Not Found"]


def get_random_hex_string(_range: int = 32) -> str:
    """Return a random hexadecimal-like identifier string."""
    return "".join(random.choice(Config.WORD) for _ in range(_range))
