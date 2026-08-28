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
        self._write_generation = 0
        self._pending_write_patches: dict[tuple, tuple[int, object]] = {}

        super().__init__(
            hass,
            _LOGGER,
            name="modbus_device",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Fetch data from device."""

        try:
            update_generation = self._write_generation
            snapshot_reader = getattr(self.device, "async_get_snapshot", None)
            if callable(snapshot_reader):
                data = await snapshot_reader()
                self._reconcile_pending_writes(data, update_generation)
                return data

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

            self._reconcile_pending_writes(data, update_generation)
            return data

        except ConnectionException as exc:
            raise UpdateFailed(
                f"Modbus update failed: {exc}"
            ) from exc

        except Exception as exc:
            raise UpdateFailed(
                f"Unexpected error: {exc}"
            ) from exc

    def async_apply_optimistic_write(self, path: tuple, value: object) -> None:
        """Publish a successful write while protecting it from an older poll."""
        self._write_generation += 1
        self._pending_write_patches[path] = (self._write_generation, value)

        data = self._copy_and_patch(self.data or {}, path, value)
        self.async_set_updated_data(data)

    def _reconcile_pending_writes(
        self,
        data: dict,
        update_generation: int,
    ) -> None:
        """Keep writes newer than this poll and retire writes it can verify."""
        for path, (generation, value) in list(
            self._pending_write_patches.items()
        ):
            if generation > update_generation:
                self._patch_in_place(data, path, value)
            else:
                self._pending_write_patches.pop(path, None)

    @staticmethod
    def _patch_in_place(data: dict, path: tuple, value: object) -> None:
        """Patch a newly fetched snapshot without repeatedly copying it."""
        current = data
        for key in path[:-1]:
            child = current.get(key)
            if not isinstance(child, dict):
                child = {}
                current[key] = child
            current = child
        current[path[-1]] = value

    @staticmethod
    def _copy_and_patch(data: dict, path: tuple, value: object) -> dict:
        """Copy a coordinator snapshot and set a nested value."""
        result = dict(data)
        current = result

        for key in path[:-1]:
            child = current.get(key, {})
            child = dict(child) if isinstance(child, dict) else {}
            current[key] = child
            current = child

        current[path[-1]] = value
        return result
