"""Tests for coordinator diagnostic labels and exceptions."""

from types import SimpleNamespace

from custom_components.modbus_devices.coordinator import (
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
