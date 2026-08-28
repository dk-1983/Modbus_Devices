"""Typed runtime state for a Modbus Devices config entry."""

from __future__ import annotations

from dataclasses import dataclass
from homeassistant.config_entries import ConfigEntry

from .coordinator import ModbusDeviceCoordinator
from .modbus_client import SerializedModbusClient


@dataclass(slots=True)
class ModbusDevicesRuntimeData:
    """Objects owned by one loaded Modbus Devices config entry."""

    client: SerializedModbusClient
    coordinator: ModbusDeviceCoordinator
    owns_client: bool = True


type ModbusDevicesConfigEntry = ConfigEntry[ModbusDevicesRuntimeData]
