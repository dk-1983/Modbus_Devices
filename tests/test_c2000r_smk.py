"""Tests for the radio magnetic-contact detector С2000Р-СМК."""

import asyncio

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from custom_components.modbus_devices.equipment.bolid import C2000RSMK
from custom_components.modbus_devices.equipment.equipment import (
    get_gateway_capabilities,
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
    S2000PPConfiguration,
    S2000PPZoneRow,
    manual_relay_mapping,
    manual_zone_mapping,
    resolve_zone_row,
)


class Response:
    def __init__(self, registers, function_code):
        self.registers = registers
        self.function_code = function_code

    def isError(self):
        return False


class Client:
    async def read_holding_registers(self, *, address, count, device_id):
        return Response([3, 35][:count], 3)

    async def read_input_registers(self, *, address, count, device_id):
        code = 3 if address < 30000 else 35
        return Response([code, 149, 211, 187, 999] + [0] * (count - 5), 4)


class HardwareClient:
    def __init__(self, row):
        self.row = row

    async def read_holding_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (39999 + self.row, 1, 2)
        return Response([0x6DC8], 3)

    async def read_input_registers(self, *, address, count, device_id):
        assert (address, count, device_id) == (
            4096 + (self.row - 1) * 16,
            16,
            2,
        )
        return Response([109, 200, 47, 188, 251, 111] + [0] * 10, 4)


def mapping(
    *objects, topology="contact_only", variant=None, base=20, connection="tcp:pp"
):
    count = 2 if topology == "contact_and_external_input" else 1
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", connection, 1),
            "C2000RSMK",
            10,
            DPLSSubIdentity(base, count),
            DownstreamDeviceMetadata(variant=variant, topology=topology),
        ),
        MappingSource.MANUAL,
        objects,
    )


@pytest.mark.parametrize("variant", [None, "hardware_1_0", "hardware_2_0"])
def test_variants_are_optional_static_metadata(variant):
    device = C2000RSMK(Client(), 1)
    device.apply_gateway_mapping(
        mapping(manual_zone_mapping(20, 1, 1, 0, None), variant=variant)
    )
    assert device.attr_model_name == "С2000Р-СМК"
    assert device.attr_hardware_version is None
    assert device.attr_software_version is None
    assert device.attr_device_metadata["documented_target_firmware"] == "1.13"
    assert device.attr_device_metadata["documented_firmware_family"] == (
        "1.04",
        "1.05",
        "1.06",
        "1.07",
        "1.12",
        "1.13",
    )
    assert device.attr_device_metadata["battery_topology"] == "single_er14505m"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(20, 1)


def test_topology_capabilities_and_two_independent_zones():
    metadata = DownstreamDeviceMetadata(topology="contact_and_external_input")
    assert [
        item.key for item in get_gateway_capabilities("Bolid", "C2000RSMK", metadata)
    ] == ["opening_state", "external_input_state"]
    device = C2000RSMK(Client(), 1)
    device.apply_gateway_mapping(
        mapping(
            manual_zone_mapping(20, 1, 1, 0, None),
            manual_zone_mapping(21, 2, 1, 0, None),
            topology="contact_and_external_input",
        )
    )
    snapshot = asyncio.run(device.async_get_snapshot())["state_sensors"]
    assert set(snapshot) == {
        "opening_state",
        "external_input_state",
        "battery_state",
    }
    assert len(device.get_state_sensor_descriptions()) == 3
    assert device.attr_device_metadata["dpls_address_count"] == 2


def test_manual_and_configuration_assisted_mapping_are_equivalent():
    for table, local in ((1, 20), (2, 21)):
        row = S2000PPZoneRow(table, 10, local, 0, 1)
        assert resolve_zone_row(row, None) == manual_zone_mapping(
            local, table, 1, 0, None
        )


def test_contact_only_reconciliation_uses_orion_dpls_and_type_not_partition():
    stale = mapping(manual_zone_mapping(20, 2, 1, 99, None))
    configuration = S2000PPConfiguration(
        (S2000PPZoneRow(17, 10, 20, 11, 1),), (), (), ()
    )

    repaired = C2000RSMK.reconcile_gateway_mapping(stale, configuration)

    assert repaired.identity == stale.identity
    assert repaired.source is stale.source
    assert repaired.objects[0].gateway_object_number == 17
    assert repaired.objects[0].zone_details.partition_number == 11


def test_two_row_topology_reconciliation_requires_both_exact_rows():
    persisted = mapping(
        manual_zone_mapping(20, 2, 1, 99, None),
        manual_zone_mapping(21, 3, 1, 99, None),
        topology="contact_and_external_input",
    )
    current = S2000PPConfiguration(
        (
            S2000PPZoneRow(17, 10, 20, 11, 1),
            S2000PPZoneRow(41, 10, 21, 12, 1),
        ),
        (),
        (),
        (),
    )

    repaired = C2000RSMK.reconcile_gateway_mapping(persisted, current)

    assert [item.gateway_object_number for item in repaired.objects] == [17, 41]

    with pytest.raises(ValueError, match="DPLS address 21"):
        C2000RSMK.reconcile_gateway_mapping(
            persisted,
            S2000PPConfiguration(current.zones[:1], (), (), ()),
        )


def test_contact_only_rejects_neighbor_and_two_zone_requires_both():
    with pytest.raises(ValueError):
        C2000RSMK(Client(), 1).apply_gateway_mapping(
            mapping(
                manual_zone_mapping(20, 1, 1, 0, None),
                manual_zone_mapping(21, 2, 1, 0, None),
            )
        )
    with pytest.raises(ValueError):
        C2000RSMK(Client(), 1).apply_gateway_mapping(
            mapping(
                manual_zone_mapping(20, 1, 1, 0, None),
                topology="contact_and_external_input",
            )
        )


@pytest.mark.parametrize(
    "wrong",
    [
        manual_zone_mapping(0, 1, 3, 0, None),
        manual_zone_mapping(20, 1, 6, 0, None),
        manual_relay_mapping(20, 1),
    ],
)
def test_unrelated_object_kinds_and_types_rejected(wrong):
    with pytest.raises(ValueError):
        C2000RSMK(Client(), 1).apply_gateway_mapping(mapping(wrong))


def test_radio_identity_and_unsupported_entities():
    device = C2000RSMK(Client(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))
    assert "arr" not in device.attr_device_identifier.lower()
    assert not hasattr(device, "get_numeric_sensor_descriptions")
    assert not hasattr(device, "get_output_descriptions")
    assert C2000RSMK._state_name(211) == "battery_low"
    assert C2000RSMK._state_name(999) == "unknown_999"
    assert [item["sensor_id"] for item in device.get_state_sensor_descriptions()] == [
        "opening_state",
        "battery_state",
    ]
    assert "entity_category" not in device.get_state_sensor_descriptions()[0]
    assert "reserve_battery_state" not in {
        item["sensor_id"] for item in device.get_state_sensor_descriptions()
    }
    binary = device.get_binary_sensor_descriptions()
    assert [item["sensor_id"] for item in binary] == [
        "opening",
        "enclosure_tamper",
    ]
    assert binary[0]["device_class"] is BinarySensorDeviceClass.OPENING
    assert binary[1]["device_class"] is BinarySensorDeviceClass.TAMPER
    assert not hasattr(device, "get_numeric_sensor_descriptions")


def test_two_radio_quiescent_hardware_rows_expose_one_battery_state():
    for dpls, row, partition in ((35, 17, 11), (36, 18, 12)):
        device = C2000RSMK(HardwareClient(row), 2)
        device.apply_gateway_mapping(
            mapping(
                manual_zone_mapping(dpls, row, 1, partition, None),
                base=dpls,
            )
        )

        full_snapshot = asyncio.run(device.async_get_snapshot())
        snapshot = full_snapshot["state_sensors"]

        assert snapshot["opening_state"] == {
            "sensor_id": "opening_state",
            "state": "disarmed",
            "primary_code": 109,
            "expanded_codes": (109, 200, 47, 188, 251, 111, *([0] * 10)),
            "expanded_states": (
                "disarmed",
                "battery_restored",
                "dpls_restored",
                "input_communication_restored",
                "device_communication_restored",
                "input_control_enabled",
            ),
        }
        assert snapshot["battery_state"]["state"] == "battery_restored"
        assert set(snapshot) == {"opening_state", "battery_state"}
        # HARDWARE VERIFIED baseline 109 does not disclose physical contact
        # position and cannot fabricate a binary OFF state.
        assert full_snapshot["binary_sensors"]["opening"]["state"] is None
        assert full_snapshot["binary_sensors"]["enclosure_tamper"]["state"] is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [(200, "battery_restored"), (202, "battery_fault"), (211, "battery_low")],
)
def test_documented_single_battery_codes_remain_multistate(code, expected):
    class CandidateClient:
        async def read_holding_registers(self, **kwargs):
            return Response([109], 3)

        async def read_input_registers(self, **kwargs):
            return Response([109, code] + [0] * 14, 4)

    device = C2000RSMK(CandidateClient(), 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))

    # Candidate fault codes are documentation-derived, not active hardware fixtures.
    snapshot = asyncio.run(device.async_get_snapshot())["state_sensors"]
    assert snapshot["battery_state"]["state"] == expected


class StatefulClient:
    def __init__(self, primary, expanded):
        self.primary = primary
        self.expanded = expanded

    async def read_holding_registers(self, **kwargs):
        return Response([self.primary], 3)

    async def read_input_registers(self, **kwargs):
        return Response([*self.expanded, *([0] * (16 - len(self.expanded)))], 4)


def configured_stateful_device(primary=109, expanded=(109, 200)):
    client = StatefulClient(primary, expanded)
    device = C2000RSMK(client, 1)
    device.apply_gateway_mapping(mapping(manual_zone_mapping(20, 1, 1, 0, None)))
    return device, client


def snapshot(device):
    return asyncio.run(device.async_get_snapshot())


def test_contact_alarm_lifecycle_requires_explicit_alarm_and_restore():
    """DOCUMENTED/CANONICAL: alarm and restore are explicit, not absence-based."""
    device, client = configured_stateful_device()
    assert snapshot(device)["binary_sensors"]["opening"]["state"] is None

    client.primary, client.expanded = 3, (3, 200, 149)
    active = snapshot(device)
    assert active["binary_sensors"]["opening"]["state"] is True
    assert active["binary_sensors"]["enclosure_tamper"]["state"] is True

    client.primary, client.expanded = 109, (109, 200)
    unchanged = snapshot(device)
    assert unchanged["binary_sensors"]["opening"]["state"] is True
    assert unchanged["binary_sensors"]["enclosure_tamper"]["state"] is True

    client.primary, client.expanded = 110, (110, 200, 152)
    restored = snapshot(device)
    assert restored["binary_sensors"]["opening"]["state"] is False
    assert restored["binary_sensors"]["enclosure_tamper"]["state"] is False


@pytest.mark.parametrize("alarm", [3, 36, 58, 118, 119])
@pytest.mark.parametrize("restored", [22, 24, 35, 110, 117])
def test_canonical_contact_alarm_and_restore_codes(alarm, restored):
    device, client = configured_stateful_device(alarm, (alarm, 200))
    assert snapshot(device)["binary_sensors"]["opening"]["state"] is True
    client.primary, client.expanded = restored, (restored, 200)
    assert snapshot(device)["binary_sensors"]["opening"]["state"] is False


def test_conflicting_contact_and_battery_evidence_is_conservative():
    device, _ = configured_stateful_device(3, (3, 24, 200, 211, 999))
    result = snapshot(device)
    assert result["binary_sensors"]["opening"]["state"] is None
    assert result["state_sensors"]["battery_state"]["state"] is None
    assert result["state_sensors"]["opening_state"]["expanded_states"][-1] == (
        "unknown_999"
    )


def test_dynamic_icons_and_single_radio_battery_contract():
    device, _ = configured_stateful_device()
    descriptions = {
        item["sensor_id"]: item for item in device.get_state_sensor_descriptions()
    }
    assert descriptions["opening_state"]["state_icons"] == {
        "armed": "mdi:door-closed",
        "alarm_reset": "mdi:door-closed",
        "control_restored": "mdi:door-closed",
        "technological_input_restored": "mdi:door-closed",
        "disarmed_input_restored": "mdi:door-closed",
        "intrusion_alarm": "mdi:door-open",
        "technological_input_violated": "mdi:door-open",
        "silent_alarm": "mdi:door-open",
        "input_alarm": "mdi:door-open",
        "disarmed_input_violated": "mdi:door-open",
        "equipment_fault": "mdi:alert-circle",
        "input_communication_lost": "mdi:alert-circle",
        "device_communication_lost": "mdi:alert-circle",
    }
    assert descriptions["opening_state"]["unknown_state_icon"] == (
        "mdi:help-circle-outline"
    )
    assert descriptions["battery_state"]["state_icons"]["battery_low"] == (
        "mdi:battery-alert"
    )
    assert "reserve_battery_state" not in descriptions


def test_external_circuit_remains_lossless_and_no_adc_entity_is_fabricated():
    """DOCUMENTED topology; numeric ADC has no S2000-PP type-1 read contract."""
    device = C2000RSMK(Client(), 1)
    device.apply_gateway_mapping(
        mapping(
            manual_zone_mapping(20, 1, 1, 0, None),
            manual_zone_mapping(21, 2, 1, 0, None),
            topology="contact_and_external_input",
        )
    )
    result = snapshot(device)
    assert result["state_sensors"]["external_input_state"]["state"] == (
        "technological_input_restored"
    )
    descriptions = {
        item["sensor_id"]: item for item in device.get_state_sensor_descriptions()
    }
    assert descriptions["external_input_state"]["entity_category"] is (
        EntityCategory.DIAGNOSTIC
    )
    assert "numeric_sensors" not in result
    assert "anti_sabotage" not in result["binary_sensors"]
    assert all(
        item["sensor_id"] != "external_input_resistance"
        for item in descriptions.values()
    )
