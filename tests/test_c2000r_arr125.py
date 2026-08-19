"""Tests for the Bolid C2000R-ARR125 DPLS radio expander."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import C2000RARR125
from custom_components.modbus_devices.equipment.equipment import (
    get_classes_from_files,
    get_gateway_device_metadata,
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
from custom_components.modbus_devices.mapping import (
    AutomaticDeviceMappingProvider,
    DeviceMappingNotFoundError,
)
from custom_components.modbus_devices.s2000_pp import (
    S2000PPConfiguration,
    S2000PPConfigurationCache,
    S2000PPRelayRow,
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
)


class Response:
    def __init__(self, *, registers=None, error=False):
        self.registers = registers
        self._error = error

    def isError(self):
        return self._error


class Client:
    def __init__(self, primary=198, expanded=None, failure=None):
        self.primary = primary
        self.expanded = expanded or [198, 149, 187, 203, 999]
        self.failure = failure

    async def read_holding_registers(self, *, address, count, device_id):
        if self.failure == "empty":
            return None
        if self.failure == "error":
            return Response(error=True)
        if self.failure == "invalid":
            return object()
        if self.failure == "truncated":
            return Response(registers=[])
        return Response(registers=[self.primary] * count)

    async def read_input_registers(self, *, address, count, device_id):
        if self.failure == "expanded_empty":
            return None
        values = (self.expanded + [0] * count)[:count]
        return Response(registers=values)


def gateway(name="pp-a", connection="serial:COM1"):
    return GatewayContext(GatewayType.S2000_PP, name, connection, 1)


def mapping(
    *objects,
    base=20,
    kdl=10,
    variant="hardware_1_0",
    gateway_context=None,
):
    return ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=gateway_context or gateway(),
            model="C2000RARR125",
            orion_address=kdl,
            dpls=DPLSSubIdentity(base, 1),
            metadata=DownstreamDeviceMetadata(variant=variant),
        ),
        source=MappingSource.MANUAL,
        objects=objects,
    )


def configured_device(client=None, **options):
    base = options.get("base", 20)
    device = C2000RARR125(client or Client(), 1)
    device.apply_gateway_mapping(
        mapping(manual_zone_mapping(base, 5, 1, 0, None), **options)
    )
    return device


def test_registered_under_bolid_and_declares_one_dpls_address():
    assert "C2000RARR125" in get_classes_from_files()["Bolid"]
    assert C2000RARR125.dpls_address_count == 1


@pytest.mark.parametrize(
    ("variant", "display_name"),
    [("hardware_1_0", "1.0"), ("hardware_14_0", "14.0")],
)
def test_hardware_variants_are_typed_static_metadata(variant, display_name):
    device = configured_device(variant=variant)

    assert device.attr_device_metadata["hardware_variant"] == display_name
    assert device.attr_hardware_version is None
    assert device.attr_software_version is None
    assert C2000RARR125.documented_target_firmware == "1.31"


def test_hardware_variant_is_optional_when_transport_cannot_detect_it():
    device = configured_device(variant=None)
    flow_metadata = get_gateway_device_metadata("Bolid", "C2000RARR125")

    assert flow_metadata["variant_optional"] is True
    assert "hardware_variant" not in device.attr_device_metadata
    assert device.attr_hardware_version is None


def test_identity_is_gateway_plus_kdl_plus_one_dpls_address():
    device = configured_device(base=20, kdl=10)
    identity = device.attr_gateway_mapping.identity

    assert identity.dpls == DPLSSubIdentity(20, 1)
    assert identity.stable_id == f"{gateway().stable_id}:orion:10:dpls:20"
    assert device.attr_device_identifier == identity.stable_id
    assert device.attr_unique_id_prefix == identity.stable_id


def test_multiple_arr_and_same_addresses_in_other_contexts_are_distinct():
    devices = (
        configured_device(base=20, kdl=10),
        configured_device(base=40, kdl=10),
        configured_device(base=20, kdl=20),
        configured_device(
            base=20,
            kdl=10,
            gateway_context=gateway("pp-b", "tcp:192.0.2.2:502"),
        ),
    )
    assert len({device.attr_device_identifier for device in devices}) == 4


def test_exact_own_zone_uses_configured_dpls_base_not_kdl_input_type():
    device = configured_device(base=37)
    capability = device.get_gateway_capabilities()[0]

    assert capability.resolved_local_object_number(37) == 37
    assert capability.zone_type == 1
    assert C2000RARR125.supported_kdl_input_types == (5, 6)
    assert capability.zone_type not in C2000RARR125.supported_kdl_input_types
    assert device.attr_platforms == [Platform.SENSOR]
    assert device.get_state_sensor_descriptions()[0]["entity_category"] is EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    "object_mapping",
    [
        manual_zone_mapping(19, 1, 1, 0, None),
        manual_zone_mapping(21, 1, 1, 0, None),
        manual_zone_mapping(0, 1, 3, 0, None),
        manual_zone_mapping(20, 1, 2, 0, None),
        manual_zone_mapping(20, 1, 6, 0, None),
        manual_zone_mapping(20, 1, 7, 0, None),
        manual_relay_mapping(20, 1),
    ],
)
def test_non_owned_kdl_radio_relay_numeric_and_counter_rows_are_rejected(
    object_mapping,
):
    with pytest.raises(ValueError, match="own type-1 zone"):
        C2000RARR125(Client(), 1).apply_gateway_mapping(mapping(object_mapping))


def test_mapping_cannot_claim_adjacent_radio_device_range():
    with pytest.raises(ValueError, match="exactly one"):
        C2000RARR125(Client(), 1).apply_gateway_mapping(
            mapping(
                manual_zone_mapping(20, 1, 1, 0, None),
                manual_zone_mapping(21, 2, 1, 0, None),
            )
        )


def test_primary_expanded_raw_and_unknown_states_are_lossless():
    state = asyncio.run(configured_device().async_get_snapshot())["state_sensors"][
        "device_state"
    ]

    assert state["state"] == "power_fault"
    assert state["primary_code"] == 198
    assert state["expanded_codes"][:5] == (198, 149, 187, 203, 999)
    assert state["expanded_states"] == (
        "power_fault",
        "enclosure_tamper",
        "input_communication_lost",
        "device_restarted",
        "unknown_999",
    )


def test_unknown_primary_state_is_preserved():
    state = asyncio.run(
        configured_device(Client(primary=777, expanded=[777])).async_get_snapshot()
    )["state_sensors"]["device_state"]
    assert state["state"] == "unknown_777"


@pytest.mark.parametrize(
    "failure", ["empty", "error", "invalid", "truncated", "expanded_empty"]
)
def test_communication_and_invalid_responses_do_not_become_normal(failure):
    with pytest.raises(ModbusException):
        asyncio.run(configured_device(Client(failure=failure)).async_get_snapshot())


def test_missing_mapping_and_invalid_identity_are_rejected():
    with pytest.raises(ValueError, match="not configured"):
        asyncio.run(C2000RARR125(Client(), 1).data_init())

    identity = mapping(manual_zone_mapping(20, 1, 1, 0, None)).identity
    invalid = ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=identity.gateway,
            model=identity.model,
            orion_address=identity.orion_address,
            dpls=DPLSSubIdentity(20, 2),
            metadata=identity.metadata,
        ),
        source=MappingSource.MANUAL,
        objects=(manual_zone_mapping(20, 1, 1, 0, None),),
    )
    with pytest.raises(ValueError, match="one DPLS address"):
        C2000RARR125(Client(), 1).apply_gateway_mapping(invalid)


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    configuration = S2000PPConfiguration(
        zones=(
            S2000PPZoneRow(5, 10, 20, 0, 1),
            S2000PPZoneRow(6, 10, 21, 0, 1),
            S2000PPZoneRow(7, 10, 0, 0, 3),
            S2000PPZoneRow(8, 10, 20, 0, 6),
            S2000PPZoneRow(9, 10, 20, 0, 7),
        ),
        relays=(S2000PPRelayRow(4, 10, 20),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    automatic = asyncio.run(
        AutomaticDeviceMappingProvider(
            Reader(), S2000PPConfigurationCache()
        ).async_resolve(
            gateway(),
            "C2000RARR125",
            10,
            dpls=DPLSSubIdentity(20, 1),
            metadata=DownstreamDeviceMetadata(variant="hardware_1_0"),
            capabilities=C2000RARR125.get_gateway_capabilities(),
        )
    )
    manual = mapping(manual_zone_mapping(20, 5, 1, 0, None))

    assert automatic.objects == manual.objects
    assert automatic.identity == manual.identity
    C2000RARR125(Client(), 1).apply_gateway_mapping(automatic)


def test_configuration_assisted_mapping_rejects_only_non_owned_rows():
    configuration = S2000PPConfiguration(
        zones=(S2000PPZoneRow(7, 10, 0, 0, 3),),
        relays=(S2000PPRelayRow(4, 10, 20),),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self):
            return configuration

    with pytest.raises(DeviceMappingNotFoundError):
        asyncio.run(
            AutomaticDeviceMappingProvider(
                Reader(), S2000PPConfigurationCache()
            ).async_resolve(
                gateway(),
                "C2000RARR125",
                10,
                dpls=DPLSSubIdentity(20, 1),
                metadata=DownstreamDeviceMetadata(variant="hardware_1_0"),
                capabilities=C2000RARR125.get_gateway_capabilities(),
            )
        )


def test_no_service_numeric_or_control_capabilities_are_invented():
    device = configured_device()
    info = asyncio.run(device.get_device_info())

    assert info == {
        "device_type": None,
        "serial_number": None,
        "hardware_version": None,
        "software_version": None,
    }
    assert Platform.SWITCH not in device.attr_platforms
    assert Platform.BUTTON not in device.attr_platforms
    assert not hasattr(device, "numeric_kinds")
    assert not hasattr(device, "set_output")


@pytest.mark.parametrize(
    ("model", "base", "count"),
    [
        ("C2000SP4", 20, 5),
        ("C2000VT", 30, 2),
        ("C2000VTI", 40, 3),
        ("C2000KPB", 50, 1),
    ],
)
def test_existing_dpls_identity_serialization_is_unchanged(model, base, count):
    identity = DownstreamDeviceIdentity(
        gateway=gateway(),
        model=model,
        orion_address=10,
        dpls=DPLSSubIdentity(base, count),
    )
    assert DownstreamDeviceIdentity.from_dict(identity.to_dict()) == identity
    assert identity.stable_id == f"{gateway().stable_id}:orion:10:dpls:{base}"
