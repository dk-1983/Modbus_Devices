"""Helpers for equipment discovery."""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
import random
import sys
from typing import Any

from serial.tools import list_ports

from ..const import Config

_LOGGER = logging.getLogger(__name__)


def get_class(module: str, cls_name: str) -> type[Any]:
    """Return an equipment class from a driver module."""
    imported_module = __import__(
        name=module,
        globals=globals(),
        locals=locals(),
        level=1,
    )
    return getattr(imported_module, cls_name)


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
                manufacturer = instance.attr_manufactures_name
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
