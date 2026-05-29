"""helpers function for dir work."""

import inspect
import logging
import os
from pathlib import Path
import random
import sys

from serial.tools import list_ports

from ..const import Config

_LOGGER = logging.getLogger(__name__)


async def get_class(module: str, cls_name: str):
    """Get objeckt from equipment."""

    return getattr(
        __import__(name=module, globals=globals(), locals=locals(), level=1),
        cls_name,
    )


async def get_classes_from_files() -> dict[str, list[str]]:
    """Return devices grouped by manufacturer."""

    result: dict[str, list[str]] = {}

    dir_path = Path(__file__).parent

    for file in [
        f.stem
        for f in dir_path.iterdir()
        if f.is_file()
        and f.suffix == ".py"
        and f.stem != "__init__"
        and f.stem != "equipment"
    ]:

        module = __import__(
            name=file,
            globals=globals(),
            locals=locals(),
            level=1,
        )

        for name, obj in inspect.getmembers(
            module,
            inspect.isclass,
        ):

            if obj.__module__.split(".")[-1] != file:
                continue

            try:
                instance = obj(None, 1)

                manufacturer = (
                    instance.attr_manufactures_name
                )

                result.setdefault(
                    manufacturer,
                    []
                ).append(name)

            except Exception:
                continue

    return result


async def get_serial_ports() -> list[str]:
    """Return available serial ports."""

    result = set()

    # -------------------------
    # 1. PySerial (best source)
    # -------------------------
    try:
        for p in list_ports.comports():
            result.add(p.device)
    except Exception:
        pass

    # -------------------------
    # 2. Linux / WSL fallback
    # -------------------------
    if sys.platform.startswith(("linux", "cygwin")):

        patterns = (
            "ttyUSB*",
            "ttyACM*",
            "ttyS*",
        )

        for pattern in patterns:
            for dev in Path("/dev").glob(pattern):
                result.add(str(dev))

    # -------------------------
    # 3. macOS
    # -------------------------
    elif sys.platform.startswith("darwin"):
        for dev in Path("/dev").glob("tty.*"):
            result.add(str(dev))

    # -------------------------
    # 4. Windows fallback
    # -------------------------
    elif sys.platform.startswith("win"):

        # pyserial usually already handles this,
        # but keep simple fallback
        for i in range(1, 33):  # 256 is overkill
            result.add(f"COM{i}")

    ports = sorted(result)

    return ports or ["Not Found"]

# async def get_serial_ports() -> list[str]:
#     """
#     Lists serial port names

#     :raises EnvironmentError:
#        On unsupported or unknown platforms

#     :returns:
#        A list of the serial ports available on the system.
#     """

#     if sys.platform.startswith("win"):
#         ports = ["COM%s" % (i + 1) for i in range(256)]
#     elif sys.platform.startswith("linux") or sys.platform.startswith("cygwin"):
#         # this excludes your current terminal "/dev/tty"
#         ports = list(Path("/dev").glob("tty[A-Za-z]*"))
#     elif sys.platform.startswith("darwin"):
#         ports = list(Path("/dev").glob("tty.*"))
#     else:
#         raise OSError("Unsupported platform")

#     result = []
#     for port in ports:
#         try:
#             s = Serial(str(port))
#             s.close()
#             result.append(str(port))
#         except (OSError, SerialException):
#             pass
#     return (
#         result[::-1],
#         [
#             "Not Found.",
#         ],
#     )[not result]


def get_random_hex_string(_range: int = 32):
    """Randomize hex number string."""
    return "".join([random.choice(Config.WORD) for x in range(_range)])
