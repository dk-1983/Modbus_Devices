"""Equipment-category registry and config-flow coverage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.equipment.category import EquipmentCategory
from custom_components.modbus_devices.equipment.equipment import (
    _get_equipment_classes,
    _validate_equipment_classes,
    get_equipment_catalog,
)
from custom_components.modbus_devices.manufacturer import MANUFACTURERS


class FakeHass:
    """Minimal Home Assistant surface for selector-flow tests."""

    def __init__(self):
        self.data = {}
        self.config_entries = SimpleNamespace(async_entries=lambda _domain: [])

    async def async_add_executor_job(self, target, *args):
        return target(*args)


def _selector_options(result):
    selector_field = next(iter(result["data_schema"].schema.values()))
    return selector_field.config["options"]


def test_every_registered_model_has_one_canonical_category():
    classes = [
        equipment_class
        for manufacturer in MANUFACTURERS
        for equipment_class in _get_equipment_classes(manufacturer.canonical_name)
    ]

    assert len(classes) == 40
    assert all(
        isinstance(equipment_class.equipment_category, EquipmentCategory)
        for equipment_class in classes
    )


def test_catalog_contains_every_model_exactly_once():
    catalog = get_equipment_catalog()
    flattened = [
        (category, manufacturer, class_name)
        for category, manufacturers in catalog.items()
        for manufacturer, class_names in manufacturers.items()
        for class_name in class_names
    ]

    assert len(flattened) == 40
    assert (
        len({(manufacturer, class_name) for _, manufacturer, class_name in flattened})
        == 40
    )
    assert catalog[EquipmentCategory.VARIABLE_FREQUENCY_DRIVES]["ERMAN"] == ["ERG22005"]
    assert catalog[EquipmentCategory.BUILDING_AUTOMATION]["Bolid"] == ["M3000BB1020"]
    assert catalog[EquipmentCategory.METERING]["Bolid"] == [
        "SVK15_3_2_B",
        "SVK15_3_8_1_B3",
    ]


def test_registry_rejects_a_new_model_without_category():
    class Unclassified:
        equipment_manufacturer = "ERMAN"
        equipment_model = "Unclassified"

    Unclassified.__module__ = "custom_components.modbus_devices.equipment.erman"

    with pytest.raises(ValueError, match="has no canonical equipment_category"):
        _validate_equipment_classes("ERMAN", "erman", (Unclassified,))


@pytest.mark.asyncio
async def test_config_flow_filters_manufacturers_and_models_by_category(monkeypatch):
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    monkeypatch.setattr(
        "custom_components.modbus_devices.config_flow.get_serial_ports", lambda: []
    )

    result = await flow.async_step_user({Config.CONF_MODBUS_MODE: Config.MODBUS_TCP})
    assert result["step_id"] == "category"
    assert set(_selector_options(result)) == {
        category.value for category in EquipmentCategory
    }

    result = await flow.async_step_category(
        {Config.CONF_EQUIPMENT_CATEGORY: EquipmentCategory.VARIABLE_FREQUENCY_DRIVES}
    )
    assert result["step_id"] == "manufacturer"
    assert _selector_options(result) == ["Dyna Drive", "ERMAN", "Zuked"]

    result = await flow.async_step_manufacturer({Config.CONF_MANUFACTURER: "ERMAN"})
    assert result["step_id"] == "device"
    assert _selector_options(result) == [{"value": "ERG22005", "label": "ER-G-220-05"}]
    assert Config.CONF_EQUIPMENT_CATEGORY not in flow._data
