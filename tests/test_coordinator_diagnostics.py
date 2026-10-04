"""Tests for coordinator diagnostic labels and exceptions."""

from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.modbus_devices.coordinator import (
    ModbusDeviceCoordinator,
    format_exception,
    get_coordinator_name,
)


def test_coordinator_name_prefers_config_entry_title():
    """The user-visible entry title identifies a particular device instance."""
    device = SimpleNamespace(
        _config_entry_title="Server-room UPS",
        attr_manufactures_name="APC",
        attr_model_name="SmartUPS3000RMXL",
    )

    assert get_coordinator_name(device) == "Server-room UPS"


def test_coordinator_name_falls_back_to_manufacturer_and_model():
    """Equipment metadata remains useful outside config-entry setup."""
    device = SimpleNamespace(
        attr_manufactures_name="APC",
        attr_model_name="SmartUPS3000RMXL",
    )

    assert get_coordinator_name(device) == "APC SmartUPS3000RMXL"


def test_empty_exception_message_includes_exception_type():
    """TimeoutError must not produce an empty coordinator error."""
    assert format_exception(TimeoutError()) == "TimeoutError"


def test_exception_message_includes_type_and_detail():
    """Both exception class and transport detail aid troubleshooting."""
    assert (
        format_exception(RuntimeError("connection closed"))
        == "RuntimeError: connection closed"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (TimeoutError(), "Modbus update failed: TimeoutError"),
        (OSError("network down"), "Modbus update failed: OSError: network down"),
        (
            ModbusException("invalid response"),
            "Modbus update failed: ModbusException: Modbus Error: invalid response",
        ),
    ],
)
async def test_expected_transport_failures_are_not_reported_as_unexpected(
    failure, expected
):
    """Communication failures use one actionable coordinator classification."""

    class Device:
        async def async_get_snapshot(self):
            raise failure

    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.device = Device()
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}

    with pytest.raises(UpdateFailed) as raised:
        await coordinator._async_update_data()

    assert str(raised.value) == expected
