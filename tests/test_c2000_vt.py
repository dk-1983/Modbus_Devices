"""Tests for C2000-VT model and mapping."""

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from custom_components.modbus_devices.equipment.bolid import C2000VT
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
    S2000PPZoneRow,
    manual_zone_mapping,
    resolve_zone_row,
)


def make_mapping(*objects, base=20, kdl=10, variant="vt"):
    return ResolvedDeviceMapping(
        identity=DownstreamDeviceIdentity(
            gateway=GatewayContext(GatewayType.S2000_PP, "pp", "tcp:x", 1),
            model="C2000VT",
            orion_address=kdl,
            dpls=DPLSSubIdentity(base, 2),
            metadata=DownstreamDeviceMetadata(variant),
        ),
        source=MappingSource.MANUAL,
        objects=objects,
    )


@pytest.mark.parametrize("variant", ["vt", "vt_01"])
def test_variants_and_service_metadata(variant):
    device = C2000VT(None, 1)
    device.apply_gateway_mapping(
        make_mapping(manual_zone_mapping(20, 1, 6, 0, None), variant=variant)
    )
    assert device.attr_device_metadata["variant"].startswith("С2000-ВТ")
    assert device.attr_serial_number is None
    assert device.attr_software_version is None


def test_base_address_validation():
    with pytest.raises(ValueError):
        DPLSSubIdentity(127, 2)


def test_temperature_humidity_mapping_and_entity_metadata():
    device = C2000VT(None, 1)
    device.apply_gateway_mapping(
        make_mapping(
            manual_zone_mapping(20, 11, 6, 0, None),
            manual_zone_mapping(21, 12, 6, 0, None),
        )
    )
    descriptions = {item["sensor_id"]: item for item in device.get_numeric_sensor_descriptions()}
    assert descriptions["temperature"]["device_class"] is SensorDeviceClass.TEMPERATURE
    assert descriptions["temperature"]["unit"] == UnitOfTemperature.CELSIUS
    assert descriptions["humidity"]["device_class"] is SensorDeviceClass.HUMIDITY
    assert descriptions["humidity"]["unit"] == PERCENTAGE
    assert {item["sensor_id"] for item in device.get_state_sensor_descriptions()} == {
        "temperature_state", "humidity_state"
    }


def test_nested_identity_distinguishes_devices():
    first = make_mapping(manual_zone_mapping(20, 1, 6, 0, None), base=20, kdl=10)
    second = make_mapping(manual_zone_mapping(30, 2, 6, 0, None), base=30, kdl=10)
    third = make_mapping(manual_zone_mapping(20, 3, 6, 0, None), base=20, kdl=11)
    assert len({first.identity.stable_id, second.identity.stable_id, third.identity.stable_id}) == 3


def test_wrong_zone_type_or_local_number_rejected():
    with pytest.raises(ValueError):
        C2000VT(None, 1).apply_gateway_mapping(
            make_mapping(manual_zone_mapping(20, 1, 1, 0, None))
        )
    with pytest.raises(ValueError):
        C2000VT(None, 1).apply_gateway_mapping(
            make_mapping(manual_zone_mapping(22, 1, 6, 0, None))
        )


def test_manual_and_automatic_objects_are_equivalent():
    manual = manual_zone_mapping(20, 41, 6, 0, None)
    automatic = resolve_zone_row(S2000PPZoneRow(41, 10, 20, 0, 6), None)
    assert manual == automatic


@pytest.mark.asyncio
async def test_pending_preserves_previous_confirmed_value():
    class Response:
        def __init__(self, registers=None, error=False, code=None, address=None,
                     value=None, function_code=None):
            self.registers = registers
            self._error = error
            self.exception_code = code
            self.address = address
            self.value = value
            self.function_code = function_code

        def isError(self):
            return self._error

    class Client:
        async def write_register(self, **kwargs):
            return Response(
                address=kwargs["address"],
                value=kwargs["value"],
                function_code=6,
            )

        async def read_holding_registers(self, *, address, count, device_id):
            if address == 46328:
                return Response(error=True, code=15)
            return Response(registers=[0] * count, function_code=3)

        async def read_input_registers(self, *, address, count, device_id):
            return Response(registers=[0] * count, function_code=4)

    device = C2000VT(Client(), 1)
    device.apply_gateway_mapping(
        make_mapping(manual_zone_mapping(20, 1, 6, 0, None))
    )
    device._numeric_values["temperature"] = {
        "value": 23.5,
        "raw_register": 6016,
        "parameter_kind": "temperature",
    }
    snapshot = await device.async_get_snapshot()
    assert snapshot["numeric_sensors"]["temperature"]["value"] == 23.5
