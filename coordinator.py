"""Modbus device coordinator."""

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


class ModbusDeviceCoordinator(DataUpdateCoordinator):
    """Shared coordinator for all Modbus entities."""

    def __init__(self, hass: HomeAssistant | None, device) -> None:
        """Initialize coordinator."""

        self.device = device

        super().__init__(
            hass,
            _LOGGER,
            name="modbus_device",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch all device data."""

        try:
            inputs = await self.device.get_inputs()
            outputs = await self.device.get_outputs()

            return {
                "inputs": {
                    inp["input_number"]: inp
                    for inp in inputs
                },
                "outputs": {
                    out["out_number"]: out
                    for out in outputs
                },
            }

        except ConnectionException as exc:
            raise UpdateFailed(
                f"Modbus update failed: {exc}"
            ) from exc
