"""Tests for the hardware-confirmed C2000-VTI family."""

import pytest

from custom_components.modbus_devices.equipment.bolid import C2000VTI, C2000VT
from custom_components.modbus_devices.equipment.equipment import get_gateway_device_metadata
from custom_components.modbus_devices.gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    GatewayType,
    MappingSource,
    ResolvedDeviceMapping,
)
from custom_components.modbus_devices.s2000_pp import manual_zone_mapping


class Response:
    def __init__(self, *, registers=None, exception_code=None, address=None,
                 value=None, function_code=None):
        self.registers = registers
        self.exception_code = exception_code
        self.address = address
        self.value = value
        self.function_code = function_code

    def isError(self):
        return self.exception_code is not None


class RoundRobinClient:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    async def write_register(self, *, address, value, device_id):
        self.calls.append(("select", address, value))
        return Response(address=address, value=value, function_code=6)

    async def read_holding_registers(self, *, address, count, device_id):
        self.calls.append(("holding", address, count))
        if address == 46328:
            result = next(self.results)
            if result == "pending":
                return Response(exception_code=15)
            if result in {"error3", "error4"}:
                return Response(
                    exception_code=4 if result == "error4" else 3,
                    function_code=0x83,
                )
            return Response(registers=[result], function_code=3)
        return Response(registers=[0x4E2F, 0x482F], function_code=3)

    async def read_input_registers(self, *, address, count, device_id):
        self.calls.append(("input", address, count))
        blocks = ([78, 47, 188, 251, 111, *([0] * 11)],
                  [72, 47, 188, 251, 111, *([0] * 11)])
        return Response(
            registers=[value for block in blocks for value in block][:count],
            function_code=4,
        )


def test_vti_reuses_the_hardware_confirmed_two_channel_vt_lifecycle():
    assert issubclass(C2000VTI, C2000VT)


@pytest.mark.parametrize(("variant", "count"), [("vti", 2), ("vti_01", 3)])
def test_variant_topology(variant, count):
    assert C2000VTI.variant_dpls_address_counts[variant] == count
    assert DPLSSubIdentity(128 - count, count).address_count == count


def test_co_and_sounder_only_on_vti_01():
    plain = C2000VTI.variants[C2000VTI.Variant.VTI].device_metadata
    extended = C2000VTI.variants[C2000VTI.Variant.VTI_01].device_metadata
    assert plain["co_sensor"] is False
    assert plain["local_sounder"] is False
    assert extended["co_sensor"] is True
    assert extended["local_sounder"] is True
    assert extended["remote_sounder_control"] is False
    assert "co_concentration" in C2000VTI.numeric_kinds


def mapping(variant="vti", count=2):
    return ResolvedDeviceMapping(
        DownstreamDeviceIdentity(
            GatewayContext(GatewayType.S2000_PP, "pp", "serial:local", 2),
            "C2000VTI",
            3,
            DPLSSubIdentity(55, count),
            DownstreamDeviceMetadata(variant),
        ),
        MappingSource.AUTOMATIC,
        (
            manual_zone_mapping(55, 9, 6, 1, None),
            manual_zone_mapping(56, 10, 6, 1, None),
        ),
    )


def test_plain_vti_s2000_pp_transport_is_enabled_but_vti_01_is_explicitly_blocked():
    metadata = get_gateway_device_metadata("bolid", "C2000VTI")
    assert metadata["gateway_transport_supported"] is True
    assert metadata["unsupported_variants"] == {
        "vti_01": "С2000-ВТИ исп.01 CO channel is not hardware validated"
    }
    assert C2000VTI(None, 1).attr_serial_number is None
    assert C2000VTI(None, 1).attr_software_version is None

    with pytest.raises(ValueError, match="separate CO validation"):
        C2000VTI(None, 1).apply_gateway_mapping(mapping("vti_01", 3))


def test_plain_vti_hardware_mapping_is_one_device_with_four_entities():
    device = C2000VTI(None, 2)
    device.apply_gateway_mapping(mapping())

    assert device.attr_model_name == "С2000-ВТИ"
    assert device.attr_gateway_mapping.identity.dpls == DPLSSubIdentity(55, 2)
    assert {item["sensor_id"] for item in device.get_state_sensor_descriptions()} == {
        "temperature_state", "humidity_state"
    }
    assert {item["sensor_id"] for item in device.get_numeric_sensor_descriptions()} == {
        "temperature", "humidity"
    }


@pytest.mark.asyncio
async def test_plain_vti_hardware_numeric_fixture_uses_shared_signed_q8_8_round_robin():
    client = RoundRobinClient([0x1440, "pending", 0x3C40])
    device = C2000VTI(client, 2)
    device.apply_gateway_mapping(mapping())

    first = await device.async_get_snapshot()
    pending = await device.async_get_snapshot()
    ready = await device.async_get_snapshot()

    assert first["numeric_sensors"]["temperature"]["value"] == 20.25
    assert "humidity" not in pending["numeric_sensors"]
    assert ready["numeric_sensors"]["humidity"]["value"] == 60.25
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 9),
        ("select", 46179, 10),
    ]


@pytest.mark.asyncio
async def test_plain_vti_numeric_protocol_error_keeps_states_and_recovers():
    client = RoundRobinClient(["error4", 0x1440])
    device = C2000VTI(client, 2)
    device.apply_gateway_mapping(mapping())

    failed = await device.async_get_snapshot()
    recovered = await device.async_get_snapshot()

    assert failed["numeric_sensors"] == {}
    assert set(failed["state_sensors"]) == {
        "temperature_state",
        "humidity_state",
    }
    assert recovered["numeric_sensors"]["temperature"]["value"] == 20.25
    assert [call for call in client.calls if call[0] == "select"] == [
        ("select", 46179, 9),
        ("select", 46179, 9),
    ]
