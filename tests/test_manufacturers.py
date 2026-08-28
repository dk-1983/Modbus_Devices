"""Tests for canonical manufacturer discovery and module resolution."""

import pytest

from homeassistant.const import Platform

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
    get_equipment_classes_by_manufacturer,
    get_equipment_display_name,
)
from custom_components.modbus_devices.equipment.dyna_drive import DN310
from custom_components.modbus_devices.manufacturer import (
    MANUFACTURERS,
    canonical_manufacturer_name,
    canonicalize_manufacturer_options,
    manufacturer_module_name,
)
from custom_components.modbus_devices.const import Config


def test_manufacturer_discovery_has_one_canonical_group_per_manufacturer():
    manufacturers = get_equipment_classes_by_manufacturer()

    assert list(manufacturers) == ["Bolid", "Dyna Drive", "Owen"]


def test_registry_contains_only_canonical_manufacturers_and_modules():
    assert [
        (item.canonical_name, item.module_name) for item in MANUFACTURERS
    ] == [
        ("Bolid", "bolid"),
        ("Dyna Drive", "dyna_drive"),
        ("Owen", "owen"),
    ]
    assert manufacturer_module_name("Bolid") == "bolid"
    assert manufacturer_module_name("Owen") == "owen"
    assert manufacturer_module_name("Dyna Drive") == "dyna_drive"
    assert manufacturer_module_name("bolid") == "bolid"
    assert manufacturer_module_name("owen") == "owen"
    assert manufacturer_module_name("dyna_drive") == "dyna_drive"


@pytest.mark.parametrize("stored_name", ["Bolid", "Owen", "Dyna Drive"])
def test_canonical_entry_options_remain_stable(stored_name):
    options = {
        Config.CONF_MANUFACTURER: stored_name,
        Config.CONF_DEVICE_CLASS: "model",
        "unrelated_identity": "keep-me",
    }

    normalized = canonicalize_manufacturer_options(options)

    assert normalized[Config.CONF_MANUFACTURER] == stored_name
    assert normalized["unrelated_identity"] == "keep-me"
    assert options[Config.CONF_MANUFACTURER] == stored_name


def test_owen_group_contains_existing_equipment_and_plc110():
    owen_equipment = get_equipment_classes_by_manufacturer()["Owen"]

    assert "TRM138" in owen_equipment
    assert "PLC110_24_60_K_M" in owen_equipment


def test_bolid_resolution_is_unchanged():
    assert canonical_manufacturer_name("Bolid") == "Bolid"
    assert get_class("Bolid", "C2000KPB") is C2000KPB
    assert "C2000KPB" in get_equipment_classes_by_manufacturer()["Bolid"]


@pytest.mark.parametrize(
    "unsupported",
    [
        "bolid",
        "owen",
        "dyna_drive",
        "Ov" + "en",
        "OW" + "EN",
        "OV" + "EN",
        "ov" + "en",
        "DYNA DRIVE",
    ],
)
def test_unsupported_arbitrary_casing_is_rejected(unsupported):
    with pytest.raises(ValueError, match="Unsupported manufacturer"):
        canonical_manufacturer_name(unsupported)


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
    devices = get_equipment_classes_by_manufacturer()["Bolid"]
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


def test_dyna_drive_dn310_is_canonical_and_discoverable():
    assert canonical_manufacturer_name("Dyna Drive") == "Dyna Drive"
    assert get_class("Dyna Drive", "DN310") is DN310
    assert get_equipment_classes_by_manufacturer()["Dyna Drive"] == ["DN310"]


def test_dn310_is_the_only_canonical_equipment_loading_button_platform():
    for manufacturer, class_names in get_equipment_classes_by_manufacturer().items():
        for class_name in class_names:
            instance = get_class(manufacturer, class_name)(None, 1)
            if (manufacturer, class_name) == ("Dyna Drive", "DN310"):
                assert Platform.BUTTON in instance.attr_platforms
            else:
                assert Platform.BUTTON not in instance.attr_platforms
