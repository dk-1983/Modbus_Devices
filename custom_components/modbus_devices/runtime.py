"""Typed runtime state for a Modbus Devices config entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .coordinator import ModbusDeviceCoordinator
from .gateway import ResolvedDeviceMapping
from .modbus_client import SerializedModbusClient


@dataclass(slots=True)
class ModbusDevicesRuntimeData:
    """Objects owned by one loaded Modbus Devices config entry."""

    client: SerializedModbusClient
    device: Any
    coordinator: ModbusDeviceCoordinator
    gateway_mapping: ResolvedDeviceMapping | None
    owns_client: bool = True
    gateway_entry_id: str | None = None


type ModbusDevicesConfigEntry = ConfigEntry[ModbusDevicesRuntimeData]
