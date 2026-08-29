"""Regression tests for Home Assistant downstream device topology."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.binary_sensor import (
    ModBusBinarySensorEntity,
    ModBusDescribedBinarySensorEntity,
)
from custom_components.modbus_devices.button import ModBusCommandButtonEntity
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.device_info import (
    EquipmentMetadata,
    via_device_for_entry,
)
from custom_components.modbus_devices.equipment.bolid import (
    C2000KPB,
    C2000SP4,
    C2000VT,
    MIP24Isp20,
    S2000PP,
)
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import (
    manual_relay_mapping,
    manual_zone_mapping,
)
from custom_components.modbus_devices.sensor import (
    ModBusNumericSensorEntity,
    ModBusSensorEntity,
    ModBusStateSensorEntity,
)
from custom_components.modbus_devices.switch import ModBusSwitchEntity


class Entry:
    """Minimal ConfigEntry surface used by entity constructors."""

    def __init__(self, entry_id: str, *, options=None, data=None) -> None:
        self.entry_id = entry_id
        self.options = {} if options is None else options
        self.data = {} if data is None else data


def coordinator(device, data=None):
    return SimpleNamespace(
        data={} if data is None else data,
        device=device,
        last_update_success=True,
    )


def gateway_context(gateway_entry_id: str) -> GatewayContext:
    return GatewayContext(
        GatewayType.S2000_PP,
        gateway_entry_id,
        f"config_entry:{gateway_entry_id}",
        1,
    )


def child_entry(entry_id: str, gateway_entry_id: str) -> Entry:
    return Entry(
        entry_id,
        options={Config.CONF_GATEWAY_ENTRY_ID: gateway_entry_id},
    )


def vt_mapping(gateway_entry_id: str = "gateway-1") -> ResolvedDeviceMapping:
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            gateway_context(gateway_entry_id),
            "C2000VT",
            7,
            DPLSSubIdentity(20, 2),
            DownstreamDeviceMetadata("vt"),
        ),
        MappingSource.MANUAL,
        (
            manual_zone_mapping(20, 1, 6, 0, None),
            manual_zone_mapping(21, 2, 6, 0, None),
        ),
    )


def mip_mapping(gateway_entry_id: str = "gateway-1") -> ResolvedDeviceMapping:
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            gateway_context(gateway_entry_id),
            "MIP24Isp20",
            2,
        ),
        MappingSource.MANUAL,
        (manual_zone_mapping(0, 20, 3, 0, None),) + tuple(
            manual_zone_mapping(local, local + 20, 8, 0, None)
            for local in range(1, 6)
        ),
    )


def kpb_mapping(gateway_entry_id: str, orion_address: int) -> ResolvedDeviceMapping:
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            gateway_context(gateway_entry_id),
            "C2000KPB",
            orion_address,
        ),
        MappingSource.MANUAL,
        (manual_relay_mapping(1, orion_address),),
    )


def sp4_mapping(gateway_entry_id: str = "gateway-1") -> ResolvedDeviceMapping:
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            gateway_context(gateway_entry_id),
            "C2000SP4",
            7,
            DPLSSubIdentity(30, 5),
            DownstreamDeviceMetadata("sp4_24"),
        ),
        MappingSource.MANUAL,
        (manual_relay_mapping(30, 1),),
    )


def test_direct_device_and_direct_s2000_pp_have_no_parent() -> None:
    direct = Entry("direct-device", options={Config.CONF_MODBUS_MODE: "serial"})
    gateway = Entry(
        "gateway-1",
        options={
            Config.CONF_MODBUS_MODE: "serial",
            Config.CONF_DEVICE_CLASS: "S2000PP",
        },
    )

    assert via_device_for_entry(direct) is None
    assert via_device_for_entry(gateway) is None

    device = S2000PP(None, 1)
    entity = ModBusBinarySensorEntity(
        coordinator(device), device, gateway, device.attr_in1
    )
    assert entity.device_info["identifiers"] == {(Config.DOMAIN, "gateway-1")}
    assert entity.device_info["via_device"] is None


def test_c2000_vt_entities_share_one_device_and_gateway_parent() -> None:
    device = C2000VT(None, 1)
    device.apply_gateway_mapping(vt_mapping())
    entry = child_entry("vt-entry", "gateway-1")
    state_entities = [
        ModBusStateSensorEntity(coordinator(device), device, entry, description)
        for description in device.get_state_sensor_descriptions()
    ]
    numeric_entities = [
        ModBusNumericSensorEntity(coordinator(device), device, entry, description)
        for description in device.get_numeric_sensor_descriptions()
    ]
    entities = state_entities + numeric_entities

    expected_identifier = {(Config.DOMAIN, device.attr_device_identifier)}
    expected_parent = (Config.DOMAIN, "gateway-1")
    assert len(entities) == 4
    assert len({entity.unique_id for entity in entities}) == 4
    assert all(entity.device_info["identifiers"] == expected_identifier for entity in entities)
    assert all(entity.device_info["via_device"] == expected_parent for entity in entities)
    assert all(entity.entity_category is EntityCategory.DIAGNOSTIC for entity in state_entities)
    assert {entity.unique_id for entity in entities} == {
        f"{device.attr_unique_id_prefix}_{key}"
        for key in ("temperature_state", "temperature", "humidity_state", "humidity")
    }


def test_mip_six_rows_share_one_device_parent_and_unique_entity_ids() -> None:
    device = MIP24Isp20(None, 1)
    device.apply_gateway_mapping(mip_mapping())
    entry = child_entry("mip-entry", "gateway-1")
    state_entities = [
        ModBusStateSensorEntity(coordinator(device), device, entry, description)
        for description in device.get_state_sensor_descriptions()
    ]
    numeric_entities = [
        ModBusNumericSensorEntity(coordinator(device), device, entry, description)
        for description in device.get_numeric_sensor_descriptions()
    ]
    binary_entities = [
        ModBusDescribedBinarySensorEntity(
            coordinator(device), device, entry, description
        )
        for description in device.get_binary_sensor_descriptions()
    ]
    entities = state_entities + numeric_entities + binary_entities

    assert len(entities) == 12
    assert len({entity.unique_id for entity in entities}) == 12
    expected_identifier = {(Config.DOMAIN, device.attr_device_identifier)}
    assert all(entity.device_info["identifiers"] == expected_identifier for entity in entities)
    assert {entity.device_info["via_device"] for entity in entities} == {
        (Config.DOMAIN, "gateway-1")
    }
    tamper = binary_entities[0]
    assert tamper.unique_id == f"{device.attr_unique_id_prefix}_tamper"
    assert tamper.device_class is BinarySensorDeviceClass.TAMPER
    assert tamper.is_on is None

    open_tamper = ModBusDescribedBinarySensorEntity(
        coordinator(device, {"binary_sensors": {"tamper": {"state": True}}}),
        device,
        entry,
        device.get_binary_sensor_descriptions()[0],
    )
    assert open_tamper.is_on is True

    failed_coordinator = coordinator(device)
    failed_coordinator.last_update_success = False
    unavailable_tamper = ModBusDescribedBinarySensorEntity(
        failed_coordinator,
        device,
        entry,
        device.get_binary_sensor_descriptions()[0],
    )
    assert unavailable_tamper.available is False


def test_two_kpb_children_keep_distinct_devices_and_one_parent() -> None:
    first = C2000KPB(None, 1)
    second = C2000KPB(None, 1)
    first.apply_gateway_mapping(kpb_mapping("gateway-1", 9))
    second.apply_gateway_mapping(kpb_mapping("gateway-1", 10))
    first_entity = ModBusSwitchEntity(
        coordinator(first), first, child_entry("kpb-9", "gateway-1"), first.attr_out1
    )
    second_entity = ModBusSwitchEntity(
        coordinator(second),
        second,
        child_entry("kpb-10", "gateway-1"),
        second.attr_out1,
    )

    assert first_entity.device_info["identifiers"] != second_entity.device_info["identifiers"]
    assert first_entity.device_info["via_device"] == (Config.DOMAIN, "gateway-1")
    assert second_entity.device_info["via_device"] == (Config.DOMAIN, "gateway-1")
    assert first_entity.unique_id == f"{first.attr_unique_id_prefix}_output_1"
    assert second_entity.unique_id == f"{second.attr_unique_id_prefix}_output_1"


def test_same_child_identity_behind_two_gateways_has_distinct_topology() -> None:
    first = C2000KPB(None, 1)
    second = C2000KPB(None, 1)
    first.apply_gateway_mapping(kpb_mapping("gateway-1", 9))
    second.apply_gateway_mapping(kpb_mapping("gateway-2", 9))
    first_entity = ModBusSwitchEntity(
        coordinator(first), first, child_entry("child-a", "gateway-1"), first.attr_out1
    )
    second_entity = ModBusSwitchEntity(
        coordinator(second), second, child_entry("child-b", "gateway-2"), second.attr_out1
    )

    assert first_entity.device_info["identifiers"] != second_entity.device_info["identifiers"]
    assert first_entity.device_info["via_device"] == (Config.DOMAIN, "gateway-1")
    assert second_entity.device_info["via_device"] == (Config.DOMAIN, "gateway-2")


def test_future_sp4_uses_the_common_downstream_topology_path() -> None:
    device = C2000SP4(None, 1)
    device.apply_gateway_mapping(sp4_mapping())
    entity = ModBusSwitchEntity(
        coordinator(device),
        device,
        child_entry("sp4-entry", "gateway-1"),
        device.attr_out1,
    )

    assert entity.device_info["identifiers"] == {
        (Config.DOMAIN, device.attr_device_identifier)
    }
    assert entity.device_info["via_device"] == (Config.DOMAIN, "gateway-1")


def test_existing_child_data_format_resolves_parent_without_runtime() -> None:
    entry = Entry(
        "legacy-child",
        data={Config.CONF_GATEWAY_ENTRY_ID: "gateway-legacy"},
    )
    assert via_device_for_entry(entry) == (Config.DOMAIN, "gateway-legacy")


def test_all_entity_platform_device_info_uses_the_same_parent() -> None:
    device = SimpleNamespace(
        attr_device_identifier="child-identity",
        attr_unique_id_prefix="child-identity",
        attr_manufactures_name="Test",
        attr_model_name="Test child",
        attr_description="Test child",
        attr_hardware_version=None,
        attr_software_version=None,
        attr_serial_number=None,
    )
    entry = child_entry("child-entry", "gateway-1")
    coord = coordinator(device)
    entities = (
        ModBusSensorEntity(
            coord,
            device,
            entry,
            {
                "chanel_number": 1,
                "chanel_number_view": 1,
                "chanel_type": "Value",
                "device_class": None,
                "state_class": None,
                "unit_of_temperature_c": None,
            },
        ),
        ModBusStateSensorEntity(
            coord, device, entry, {"sensor_id": "state", "name": "State"}
        ),
        ModBusNumericSensorEntity(
            coord,
            device,
            entry,
            {
                "sensor_id": "numeric",
                "name": "Numeric",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
            },
        ),
        ModBusBinarySensorEntity(
            coord,
            device,
            entry,
            {
                "input_number": 1,
                "input_number_view": 1,
                "input_type": "Input",
                "device_class": None,
                "icon_on": None,
                "icon_off": None,
            },
        ),
        ModBusSwitchEntity(
            coord,
            device,
            entry,
            {
                "out_number": 1,
                "out_number_view": 1,
                "out_type": "Output",
                "device_class": None,
            },
        ),
        ModBusCommandButtonEntity(
            coord,
            device,
            entry,
            {"button_id": "command", "name": "Command", "command": "run"},
        ),
    )

    assert {entity.device_info["via_device"] for entity in entities} == {
        (Config.DOMAIN, "gateway-1")
    }


def test_protocol_metadata_uses_native_device_info_fields_consistently() -> None:
    device = SimpleNamespace(
        attr_device_identifier="child-identity",
        attr_unique_id_prefix="child-identity",
        attr_manufactures_name="Test",
        attr_model_name="Test child",
        attr_description="Test child",
        attr_device_type=36,
        attr_hardware_version="2.0",
        attr_software_version="3.01",
        attr_serial_number="ABC123",
    )
    entry = child_entry("child-entry", "gateway-1")
    coord = coordinator(device)
    entities = (
        ModBusStateSensorEntity(
            coord, device, entry, {"sensor_id": "state", "name": "State"}
        ),
        ModBusNumericSensorEntity(
            coord,
            device,
            entry,
            {
                "sensor_id": "numeric",
                "name": "Numeric",
                "device_class": None,
                "state_class": None,
                "unit": None,
                "precision": 0,
            },
        ),
    )

    expected = {
        "model_id": "36",
        "hw_version": "2.0",
        "sw_version": "3.01",
        "serial_number": "ABC123",
    }
    assert all(
        {key: entity.device_info[key] for key in expected} == expected
        for entity in entities
    )


def test_missing_protocol_metadata_stays_none_without_placeholders() -> None:
    device = SimpleNamespace(attr_device_type=None)

    assert EquipmentMetadata.from_device(device) == EquipmentMetadata()


def test_missing_binary_and_switch_snapshot_values_are_unknown() -> None:
    """A successful partial snapshot must not turn missing values into false."""
    device = S2000PP(None, 1)
    entry = Entry("gateway-1")
    empty_snapshot = coordinator(device, {"inputs": {}, "outputs": {}})

    binary = ModBusBinarySensorEntity(
        empty_snapshot, device, entry, device.attr_in1
    )
    switch = ModBusSwitchEntity(
        empty_snapshot,
        device,
        entry,
        {
            "out_number": 1,
            "out_number_view": 1,
            "out_type": "Output",
            "device_class": None,
        },
    )

    assert binary.is_on is None
    assert switch.is_on is None

    empty_snapshot.data = {
        "inputs": {1: {"state": False}},
        "outputs": {1: {"state": False}},
    }
    assert binary.is_on is False
    assert switch.is_on is False

    empty_snapshot.data = {
        "inputs": {1: {"state": True}},
        "outputs": {1: {"state": True}},
    }
    assert binary.is_on is True
    assert switch.is_on is True

    empty_snapshot.last_update_success = False
    assert binary.available is False
    assert switch.available is False
