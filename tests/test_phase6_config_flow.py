"""Config Flow characterization coverage for the Phase 6 boundary refactor."""

from types import SimpleNamespace
import inspect

import pytest

from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_PORT

from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.gateway import (
    CapabilityRequirement,
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayType,
    MappingSource,
    ObjectKind,
    ResolvedDeviceMapping,
    compatible_gateway_contexts,
)
from custom_components.modbus_devices import gateway, mapping
from custom_components.modbus_devices.mapping import (
    available_gateway_capabilities,
    has_overlapping_dpls_mapping,
    manual_mapping_for_capability,
)
from custom_components.modbus_devices.gateway import GatewayCapabilitySpec
from custom_components.modbus_devices.s2000_pp import manual_zone_mapping
from custom_components.modbus_devices.equipment.bolid import C2000VT


class FakeHass:
    def __init__(self, entries=()):
        self.data = {}
        self.config_entries = SimpleNamespace(
            async_entries=lambda _domain: list(entries)
        )

    async def async_add_executor_job(self, target, *args):
        return target(*args)


def form_fields(result):
    return {marker.schema for marker in result["data_schema"].schema}


@pytest.mark.asyncio
async def test_c2000_vt_manual_flow_cannot_finish_after_one_channel():
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._selected_manufacturer = "Bolid"
    flow._gateway_context = GatewayContext(
        GatewayType.S2000_PP, "PP", "tcp:test:502", 1
    )
    flow._orion_address = 10
    flow._dpls_identity = DPLSSubIdentity(20, 2)
    flow._device_metadata = DownstreamDeviceMetadata("vt")
    flow._gateway_capabilities = C2000VT.capability_requirements

    result = await flow.async_step_manual_capability(
        {
            Config.CONF_CAPABILITY_KEY: "temperature",
            Config.CONF_GATEWAY_OBJECT_NUMBER: 41,
            Config.CONF_ADD_ANOTHER_OBJECT: False,
        }
    )

    assert result["step_id"] == "manual_capability"
    options = next(iter(result["data_schema"].schema.values())).config["options"]
    assert options == [{"value": "humidity", "label": "Humidity"}]
    assert [item.local_object_number for item in flow._manual_objects] == [20]


@pytest.mark.asyncio
async def test_second_c2000_vt_flow_is_rejected_as_overlap_without_exception():
    gateway = GatewayContext(GatewayType.S2000_PP, "PP", "tcp:test:502", 1)
    existing = ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            gateway,
            "C2000VT",
            3,
            DPLSSubIdentity(51, 2),
            DownstreamDeviceMetadata("vt"),
        ),
        MappingSource.AUTOMATIC,
        (
            manual_zone_mapping(51, 5, 6, 1, None),
            manual_zone_mapping(52, 6, 6, 1, None),
        ),
    )
    entry = SimpleNamespace(
        data={}, options={Config.CONF_GATEWAY_MAPPING: existing.to_dict()}
    )
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass((entry,))
    flow._selected_manufacturer = "Bolid"
    flow._data = {Config.CONF_DEVICE_CLASS: "C2000VT"}

    duplicate = ResolvedDeviceMapping(
        existing.identity,
        MappingSource.MANUAL,
        existing.objects,
    )

    assert await flow._async_validate_and_store_mapping(duplicate) is False


@pytest.mark.asyncio
async def test_existing_gateway_context_flow_contract_is_frozen():
    gateway = GatewayContext(
        GatewayType.S2000_PP,
        "Main PP",
        "ModBus TCP/IP:10.0.2.10:502",
        1,
    )
    mapping = ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=gateway,
            model="C2000DZ",
            orion_address=4,
            dpls=DPLSSubIdentity(30, 1),
        ),
        source=MappingSource.MANUAL,
        objects=(manual_zone_mapping(30, 7, 1, 0, None),),
    )
    entries = (
        SimpleNamespace(
            data={Config.CONF_GATEWAY_MAPPING: mapping.to_dict()}, options={}
        ),
        SimpleNamespace(data={Config.CONF_GATEWAY_MAPPING: {"bad": "data"}}, options={}),
    )
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass(entries)
    flow._required_gateway = GatewayType.S2000_PP
    flow._data = {
        Config.CONF_MODBUS_MODE: Config.MODBUS_TCP,
        CONF_HOST: "10.0.2.10",
        CONF_PORT: 502,
        CONF_DEVICE_ID: 1,
    }

    result = await flow.async_step_gateway_context()

    assert result["step_id"] == "gateway_context"
    field = next(iter(result["data_schema"].schema.values()))
    assert field.config["options"] == [
        {"value": gateway.stable_id, "label": "Main PP"},
        {"value": "new", "label": "Add new С2000-ПП"},
    ]


@pytest.mark.asyncio
async def test_variant_and_topology_flow_contract_is_frozen():
    flow = ModbusDevicesConfigFlow()
    flow.hass = FakeHass()
    flow._selected_manufacturer = "Bolid"
    flow._required_gateway = GatewayType.S2000_PP
    flow._gateway_context = GatewayContext(
        GatewayType.S2000_PP,
        "Main PP",
        "ModBus TCP/IP:10.0.2.10:502",
        1,
    )
    flow._data = {
        Config.CONF_MANUFACTURER: "Bolid",
        Config.CONF_DEVICE_CLASS: "C2000RSMK",
    }

    result = await flow.async_step_gateway_device()
    assert result["step_id"] == "gateway_device"
    assert form_fields(result) == {
        Config.CONF_DEVICE_VARIANT,
        Config.CONF_DEVICE_TOPOLOGY,
        Config.CONF_ORION_ADDRESS,
        Config.CONF_DPLS_BASE_ADDRESS,
    }

    result = await flow.async_step_gateway_device(
        {
            Config.CONF_DEVICE_VARIANT: "hardware_2_0",
            Config.CONF_DEVICE_TOPOLOGY: "contact_and_external_input",
            Config.CONF_ORION_ADDRESS: 12,
            Config.CONF_DPLS_BASE_ADDRESS: 40,
        }
    )
    assert result["step_id"] == "mapping_source"
    assert flow._dpls_identity == DPLSSubIdentity(40, 2)


def test_gateway_context_lookup_is_a_typed_domain_service():
    gateway_context = GatewayContext(
        GatewayType.S2000_PP, "Main PP", "tcp:host:502", 1
    )
    mapping_data = ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway_context, "C2000DZ", 4, DPLSSubIdentity(30, 1)
        ),
        source=MappingSource.MANUAL,
        objects=(manual_zone_mapping(30, 7, 1, 0, None),),
    ).to_dict()

    result = compatible_gateway_contexts(
        (mapping_data, {"bad": "mapping"}, None),
        gateway_type=GatewayType.S2000_PP,
        connection_key="tcp:host:502",
        modbus_unit_id=1,
    )

    assert result == {gateway_context.stable_id: gateway_context}


def test_manual_capability_services_preserve_alternative_group_semantics():
    primary = GatewayCapabilitySpec(
        "primary",
        "Primary",
        ObjectKind.ZONE,
        0,
        CapabilityRequirement.REQUIRED_FOR_BASE_OPERATION,
        zone_type=1,
        local_object_offset=0,
        alternative_group="state",
    )
    alternative = GatewayCapabilitySpec(
        "alternative",
        "Alternative",
        ObjectKind.ZONE,
        0,
        CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        zone_type=6,
        local_object_offset=0,
        alternative_group="state",
    )
    extra = GatewayCapabilitySpec(
        "extra",
        "Extra",
        ObjectKind.ZONE,
        0,
        CapabilityRequirement.OPTIONAL_IF_CONFIGURED,
        zone_type=1,
        local_object_offset=1,
    )
    dpls = DPLSSubIdentity(30, 2)
    mapped = manual_mapping_for_capability(primary, 7, dpls)

    available = available_gateway_capabilities(
        (primary, alternative, extra), (mapped,), dpls
    )

    assert list(available) == ["extra"]
    assert manual_mapping_for_capability(extra, 8, dpls).to_dict() == (
        manual_zone_mapping(31, 8, 1, 0, None).to_dict()
    )


def test_overlap_service_ignores_invalid_persisted_rows():
    gateway_context = GatewayContext(
        GatewayType.S2000_PP, "Main PP", "tcp:host:502", 1
    )
    existing = ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway_context, "C2000RSMK", 12, DPLSSubIdentity(40, 2)
        ),
        source=MappingSource.MANUAL,
        objects=(manual_zone_mapping(40, 7, 1, 0, None),),
    )
    requested = DownstreamDeviceIdentity(
        gateway_context, "C2000DZ", 12, DPLSSubIdentity(41, 1)
    )

    assert has_overlapping_dpls_mapping(
        requested, ({"bad": "mapping"}, existing.to_dict())
    )


def test_wired_and_radio_water_models_cannot_claim_the_same_dpls_row():
    gateway_context = GatewayContext(
        GatewayType.S2000_PP, "Main PP", "tcp:host:502", 1
    )
    wired = ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway_context, "C2000DZ", 20, DPLSSubIdentity(53, 1)
        ),
        source=MappingSource.MANUAL,
        objects=(manual_zone_mapping(53, 11, 1, 20, None),),
    )
    radio = DownstreamDeviceIdentity(
        gateway_context, "C2000RDZ", 20, DPLSSubIdentity(53, 1)
    )

    assert has_overlapping_dpls_mapping(radio, (wired.to_dict(),))


def test_extracted_services_do_not_depend_on_home_assistant_flow_apis():
    assert "homeassistant" not in inspect.getsource(gateway)
    assert "homeassistant" not in inspect.getsource(mapping)
    assert "async_show_form" not in inspect.getsource(gateway)
    assert "async_show_form" not in inspect.getsource(mapping)
