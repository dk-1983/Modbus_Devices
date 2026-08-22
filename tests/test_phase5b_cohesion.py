"""Focused coverage for the Phase 5B cohesion cleanup."""

from types import SimpleNamespace

from custom_components.modbus_devices import config_flow, modbus_client
from custom_components.modbus_devices.equipment.equipment import (
    get_equipment_classes_by_manufacturer,
)


def test_serial_port_discovery_preserves_windows_behavior(monkeypatch):
    monkeypatch.setattr(modbus_client.sys, "platform", "win32")
    monkeypatch.setattr(
        modbus_client.list_ports,
        "comports",
        lambda: [SimpleNamespace(device="COM40"), SimpleNamespace(device="COM2")],
    )

    ports = modbus_client.get_serial_ports()

    assert ports == sorted({f"COM{number}" for number in range(1, 33)} | {"COM40"})


def test_serial_port_discovery_preserves_error_fallback(monkeypatch):
    monkeypatch.setattr(modbus_client.sys, "platform", "unknown")

    def fail_enumeration():
        raise OSError("serial enumeration failed")

    monkeypatch.setattr(modbus_client.list_ports, "comports", fail_enumeration)

    assert modbus_client.get_serial_ports() == ["Not Found"]


def test_config_flow_keeps_module_level_serial_discovery_surface():
    assert config_flow.get_serial_ports is modbus_client.get_serial_ports


def test_registry_counts_and_order_remain_unchanged():
    equipment = get_equipment_classes_by_manufacturer()

    assert list(equipment) == ["Bolid", "Dyna Drive", "Owen"]
    assert [len(equipment[name]) for name in equipment] == [22, 1, 2]
    assert sum(map(len, equipment.values())) == 25
