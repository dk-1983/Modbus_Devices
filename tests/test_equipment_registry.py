"""Characterization tests for the explicit equipment registry."""

from __future__ import annotations

import pytest

from custom_components.modbus_devices.equipment import bolid, dyna_drive, owen
from custom_components.modbus_devices.equipment.dyna_drive import DN310, DN310Command
from custom_components.modbus_devices.equipment.equipment import (
    _get_equipment_classes,
    _validate_equipment_classes,
    get_class,
    get_equipment_classes_by_manufacturer,
    get_equipment_display_name,
    get_gateway_requirement,
)


EXPECTED_CLASSES = {
    "Bolid": [
        "C20002",
        "C20004",
        "C2000BKI",
        "C2000DZ",
        "C2000IP03",
        "C2000KDL",
        "C2000KPB",
        "C2000RARR125",
        "C2000RDIP",
        "C2000RIP",
        "C2000RRM",
        "C2000RSMK",
        "C2000RST01",
        "C2000RSirena",
        "C2000SMK",
        "C2000SP2",
        "C2000SP4",
        "C2000ST04",
        "C2000VT",
        "C2000VTI",
        "DIP34A05",
        "M3000BB1020",
        "MIP24Isp20",
        "Signal20M",
        "S2000PP",
        "SVK15_3_2_B",
        "SVK15_3_8_1_B3",
    ],
    "Dyna Drive": ["DN310"],
    "Owen": ["PLC110_24_60_K_M", "TRM138"],
}

EXPECTED_MODELS = {
    "Bolid": [
        "С2000-2",
        "С2000-4",
        "С2000-БКИ",
        "С2000-ДЗ",
        "С2000-ИП-03",
        "С2000-КДЛ",
        "С2000-КПБ",
        "С2000Р-АРР125",
        "С2000Р-ДИП",
        "С2000Р-ИП",
        "С2000Р-РМ",
        "С2000Р-СМК",
        "С2000Р-СТ исп.01",
        "С2000Р-Сирена",
        "С2000-СМК",
        "С2000-СП2",
        "С2000-СП4/24(220)",
        "С2000-СТ исп.04",
        "С2000-ВТ",
        "С2000-ВТИ",
        "ДИП-34А-05",
        "M3000-BB-1020",
        "МИП-24 исп.20",
        "Сигнал-20М",
        "С2000-ПП",
        "СВК15-3-2-Б",
        "СВК15-3-8-1-Б3",
    ],
    "Dyna Drive": ["DN310"],
    "Owen": ["ПЛК110-24.60.К-М", "TRM-138"],
}


def test_explicit_registry_preserves_canonical_set_and_order():
    assert get_equipment_classes_by_manufacturer() == EXPECTED_CLASSES
    assert sum(map(len, EXPECTED_CLASSES.values())) == 30


def test_module_exports_are_the_single_registry_source():
    assert bolid.EQUIPMENT_CLASSES == _get_equipment_classes("Bolid")
    assert dyna_drive.EQUIPMENT_CLASSES == _get_equipment_classes("Dyna Drive")
    assert owen.EQUIPMENT_CLASSES == _get_equipment_classes("Owen")

    for manufacturer, class_names in EXPECTED_CLASSES.items():
        assert [
            get_class(manufacturer, class_name).equipment_model
            for class_name in class_names
        ] == EXPECTED_MODELS[manufacturer]


def test_class_metadata_matches_existing_instance_metadata():
    for manufacturer, class_names in EXPECTED_CLASSES.items():
        for class_name in class_names:
            equipment_class = get_class(manufacturer, class_name)
            instance = equipment_class(None, 1)
            assert equipment_class.equipment_manufacturer == (
                instance.attr_manufactures_name
            )
            assert equipment_class.equipment_model == instance.attr_model_name


def test_discovery_and_display_labels_do_not_instantiate_equipment(monkeypatch):
    def fail_init(*_args, **_kwargs):
        raise AssertionError("registry discovery instantiated DN310")

    monkeypatch.setattr(DN310, "__init__", fail_init)

    assert get_equipment_classes_by_manufacturer() == EXPECTED_CLASSES
    assert get_equipment_display_name("Dyna Drive", "DN310") == "DN310"
    assert get_class("Dyna Drive", "DN310") is DN310


def test_helpers_and_legacy_aliases_are_not_selectable_models():
    registered = {
        equipment_class
        for manufacturer in EXPECTED_CLASSES
        for equipment_class in _get_equipment_classes(manufacturer)
    }
    assert DN310Command not in registered
    assert bolid.BolidDPLSDetectorBase not in registered
    assert bolid.BolidDPLSOutputBase not in registered
    assert bolid.BolidDPLSWaterMeterBase not in registered
    assert "C2000DIP" not in EXPECTED_CLASSES["Bolid"]
    assert "C2000IP" not in EXPECTED_CLASSES["Bolid"]


def test_runtime_resolution_and_gateway_metadata_use_the_same_registry():
    for manufacturer, class_names in EXPECTED_CLASSES.items():
        for class_name in class_names:
            equipment_class = get_class(manufacturer, class_name)
            assert equipment_class in _get_equipment_classes(manufacturer)
            assert get_gateway_requirement(manufacturer, class_name) == getattr(
                equipment_class, "required_gateway", None
            )


def test_legacy_equipment_names_resolve_but_are_not_exported():
    assert get_class("Bolid", "C2000DIP") is bolid.DIP34A05
    assert get_class("Bolid", "C2000IP") is bolid.C2000IP03
    assert "C2000DIP" not in get_equipment_classes_by_manufacturer()["Bolid"]
    assert "C2000IP" not in get_equipment_classes_by_manufacturer()["Bolid"]


def test_unknown_equipment_fails_clearly():
    with pytest.raises(ValueError, match="Unsupported equipment class"):
        get_class("Owen", "NotADevice")


def test_invalid_registry_export_fails_loudly():
    with pytest.raises(TypeError, match="must be a tuple"):
        _validate_equipment_classes("Dyna Drive", "dyna_drive", [DN310])
    with pytest.raises(ValueError, match="Duplicate equipment class"):
        _validate_equipment_classes(
            "Dyna Drive", "dyna_drive", (DN310, DN310)
        )
    with pytest.raises(TypeError, match="non-class"):
        _validate_equipment_classes("Dyna Drive", "dyna_drive", (object(),))
