"""Canonical functional categories for supported equipment."""

from __future__ import annotations

from enum import StrEnum


class EquipmentCategory(StrEnum):
    """Stable category identifiers used to build the equipment catalog."""

    BUILDING_AUTOMATION = "building_automation"
    CLIMATE_CONTROL = "climate_control"
    ENGINEERING_MONITORING = "engineering_monitoring"
    FIRE_AND_SECURITY = "fire_and_security"
    INDUSTRIAL_AUTOMATION = "industrial_automation"
    MEASUREMENT_AND_CONTROL = "measurement_and_control"
    METERING = "metering"
    POWER_AND_BACKUP = "power_and_backup"
    VARIABLE_FREQUENCY_DRIVES = "variable_frequency_drives"
