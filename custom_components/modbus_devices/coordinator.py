"""Universal Modbus device coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging

from pymodbus.exceptions import ConnectionException

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)


class ModbusDeviceCoordinator(
    DataUpdateCoordinator,
):
    """Universal coordinator for Modbus devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        device,
    ) -> None:
        """Initialize coordinator."""

        self.device = device

        super().__init__(
            hass,
            _LOGGER,
            name="modbus_device",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch data from device."""

        try:
            data: dict = {}

            # ---------------------------------
            # Binary inputs
            # ---------------------------------
            if hasattr(
                self.device,
                "get_inputs",
            ):
                inputs = await self.device.get_inputs()

                data["inputs"] = {
                    inp["input_number"]: inp
                    for inp in inputs
                }

            # ---------------------------------
            # Relay outputs
            # ---------------------------------
            if hasattr(
                self.device,
                "get_outputs",
            ):
                outputs = await self.device.get_outputs()

                data["outputs"] = {
                    out["out_number"]: out
                    for out in outputs
                }

            # ---------------------------------
            # Analog channels / sensors
            # ---------------------------------
            if hasattr(
                self.device,
                "get_chanels",
            ):
                chanels = (
                    await self.device.get_chanels()
                )

                data["chanels"] = {
                    ch["chanel_number"]: ch
                    for ch in chanels
                }

            # ---------------------------------
            # Device time
            # ---------------------------------
            if hasattr(
                self.device,
                "get_time",
            ):
                data["time"] = (
                    await self.device.get_time()
                )

            return data

        except ConnectionException as exc:
            raise UpdateFailed(
                f"Modbus update failed: {exc}"
            ) from exc

        except Exception as exc:
            raise UpdateFailed(
                f"Unexpected error: {exc}"
            ) from exc
