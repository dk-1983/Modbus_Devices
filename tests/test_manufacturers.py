"""Tests for canonical manufacturer discovery and legacy compatibility."""

import pytest

from custom_components.modbus_devices.equipment.bolid import (
    C2000IP03,
    C2000KPB,
    C2000RDIP,
    C2000RIP,
    DIP34A05,
)
from custom_components.modbus_devices.equipment.equipment import (
    canonical_equipment_class_name,
    get_class,
    get_classes_from_files,
    get_equipment_display_name,
)
from custom_components.modbus_devices.equipment.owen import (
    PLC110_24_60_K_M,
    TRM138,
)
from custom_components.modbus_devices.manufacturer import (
    canonical_manufacturer_name,
    canonicalize_manufacturer_options,
    canonicalize_manufacturer_unique_id,
)
from custom_components.modbus_devices.const import Config


def test_manufacturer_discovery_has_one_canonical_group_per_manufacturer():
    manufacturers = get_classes_from_files()

    assert list(manufacturers).count("Bolid") == 1
    assert list(manufacturers).count("Owen") == 1
    assert "Oven" not in manufacturers
    assert "OWEN" not in manufacturers
    assert "OVEN" not in manufacturers


@pytest.mark.parametrize("legacy_name", ["Oven", "OWEN", "OVEN"])
def test_legacy_owen_names_normalize(legacy_name):
    assert canonical_manufacturer_name(legacy_name) == "Owen"


@pytest.mark.parametrize("stored_name", ["Owen", "Oven", "OWEN", "OVEN"])
def test_stored_owen_entries_still_resolve_equipment(stored_name):
    assert get_class(stored_name, "TRM138") is TRM138
    assert get_class(stored_name, "PLC110_24_60_K_M") is PLC110_24_60_K_M


@pytest.mark.parametrize("stored_name", ["Oven", "OWEN", "OVEN"])
def test_stored_entry_options_are_canonicalized_without_identity_fields(stored_name):
    options = {
        Config.CONF_MANUFACTURER: stored_name,
        Config.CONF_DEVICE_CLASS: "TRM138",
        "unrelated_identity": "keep-me",
    }

    normalized = canonicalize_manufacturer_options(options)

    assert normalized[Config.CONF_MANUFACTURER] == "Owen"
    assert normalized["unrelated_identity"] == "keep-me"
    assert options[Config.CONF_MANUFACTURER] == stored_name


def test_owen_group_contains_existing_equipment_and_plc110():
    owen_equipment = get_classes_from_files()["Owen"]

    assert "TRM138" in owen_equipment
    assert "PLC110_24_60_K_M" in owen_equipment


def test_bolid_resolution_is_unchanged():
    assert canonical_manufacturer_name("Bolid") == "Bolid"
    assert get_class("Bolid", "C2000KPB") is C2000KPB
    assert "C2000KPB" in get_classes_from_files()["Bolid"]


@pytest.mark.parametrize("legacy_name", ["Oven", "OWEN", "OVEN"])
def test_legacy_unique_ids_compare_as_existing_owen_identity(legacy_name):
    legacy_unique_id = f"192.0.2.1_502_1_{legacy_name}_TRM138"
    canonical_unique_id = "192.0.2.1_502_1_Owen_TRM138"

    assert canonicalize_manufacturer_unique_id(legacy_unique_id) == canonical_unique_id


@pytest.mark.parametrize(
    ("legacy", "canonical", "equipment_class"),
    [
        ("C2000DIP", "DIP34A05", DIP34A05),
        ("C2000IP", "C2000IP03", C2000IP03),
    ],
)
def test_legacy_detector_class_names_resolve_at_central_boundary(
    legacy, canonical, equipment_class
):
    assert canonical_equipment_class_name(legacy) == canonical
    assert get_class("Bolid", legacy) is equipment_class
    assert get_class("Bolid", canonical) is equipment_class


def test_only_canonical_wired_detector_class_names_are_discovered():
    devices = get_classes_from_files()["Bolid"]
    assert "DIP34A05" in devices
    assert "C2000IP03" in devices
    assert "C2000DIP" not in devices
    assert "C2000IP" not in devices


@pytest.mark.parametrize(
    ("class_name", "label"),
    [
        ("DIP34A05", "ДИП-34А-05"),
        ("C2000IP03", "С2000-ИП-03"),
        ("C2000RDIP", "С2000Р-ДИП"),
        ("C2000RIP", "С2000Р-ИП"),
    ],
)
def test_equipment_selector_uses_real_model_labels(class_name, label):
    assert get_equipment_display_name("Bolid", class_name) == label


def test_radio_detector_names_remain_canonical():
    assert get_class("Bolid", "C2000RDIP") is C2000RDIP
    assert get_class("Bolid", "C2000RIP") is C2000RIP
