"""Tests for the old-family Owen PLC110-24.60.K-M equipment model."""

import pytest

from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.coordinator import ModbusDeviceCoordinator
from custom_components.modbus_devices.equipment.owen import PLC110_24_60_K_M


class Response:
    def __init__(self, *, bits=None, error=False, function_code=None, address=None, value=None):
        self.bits = bits
        self._error = error
        self.function_code = function_code
        self.address = address
        self.value = value

    def isError(self):
        return self._error


class Client:
    def __init__(self):
        self.discrete = {}
        self.coils = {}
        self.writes = []
        self.write_response = Response()

    async def read_discrete_inputs(self, *, address, count, device_id):
        return Response(
            bits=[self.discrete.get(address + item, False) for item in range(count)],
            function_code=2,
        )

    async def read_coils(self, *, address, count, device_id):
        return Response(
            bits=[self.coils.get(address + item, False) for item in range(count)],
            function_code=1,
        )

    async def write_coil(self, **kwargs):
        self.writes.append(kwargs)
        if self.write_response._error:
            return self.write_response
        return Response(
            function_code=5,
            address=kwargs["address"],
            value=kwargs["value"],
        )


def compact_mapping(di_area="discrete_input", di_base=100, di_stride=1, do_base=200, do_stride=1):
    return {
        Config.CONF_DI_DATA_AREA: di_area,
        Config.CONF_DI_BASE_ADDRESS: di_base,
        Config.CONF_DI_ADDRESS_STRIDE: di_stride,
        Config.CONF_DO_BASE_ADDRESS: do_base,
        Config.CONF_DO_ADDRESS_STRIDE: do_stride,
    }


def configured_device(client=None, **mapping):
    device = PLC110_24_60_K_M(client or Client(), 1)
    device.apply_io_mapping(compact_mapping(**mapping))
    return device


def test_physical_model_capabilities_and_metadata():
    device = PLC110_24_60_K_M(None, 1)
    assert device.input_count == 36
    assert device.output_count == 24
    assert device.fast_input_numbers == {1, 2, 3, 4}
    assert device.fast_output_numbers == {1, 2, 3, 4}
    assert device.attr_device_metadata["supply"] == "24 V DC"
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert device.attr_hardware_version is None


def test_compact_address_mapping_and_fast_channel_metadata():
    device = configured_device(di_base=10, di_stride=8, do_base=400, do_stride=2)
    assert device._inputs[1]["address"] == 10
    assert device._inputs[36]["address"] == 290
    assert device._outputs[1]["address"] == 400
    assert device._outputs[24]["address"] == 446
    assert device._inputs[4]["high_speed"] is True
    assert device._inputs[5]["high_speed"] is False
    assert device._outputs[4]["high_speed"] is True
    assert device._outputs[5]["high_speed"] is False


@pytest.mark.parametrize(
    "mapping",
    [
        compact_mapping(di_area="holding_register"),
        compact_mapping(di_stride=0),
        compact_mapping(do_stride=0),
        compact_mapping(di_area="coil", di_base=0, do_base=20),
    ],
)
def test_invalid_manual_mapping_rejected(mapping):
    with pytest.raises(ValueError):
        PLC110_24_60_K_M(None, 1).apply_io_mapping(mapping)


@pytest.mark.asyncio
async def test_read_inputs_and_outputs():
    client = Client()
    client.discrete[100] = True
    client.discrete[135] = True
    client.coils[200] = True
    client.coils[223] = True
    device = configured_device(client)
    inputs = await device.get_inputs()
    outputs = await device.get_outputs()
    assert len(inputs) == 36 and inputs[0]["state"] is True and inputs[-1]["state"] is True
    assert len(outputs) == 24 and outputs[0]["state"] is True and outputs[-1]["state"] is True


@pytest.mark.asyncio
async def test_write_output_uses_resolved_coil_and_local_optimism():
    client = Client()
    device = configured_device(client, do_base=500)
    result = await device.set_output(4, True)
    assert client.writes == [{"address": 503, "value": True, "device_id": 1}]
    assert result["state"] is True


@pytest.mark.asyncio
async def test_write_error_is_not_optimistic_success():
    client = Client()
    client.write_response = Response(error=True)
    device = configured_device(client)
    with pytest.raises(ModbusException):
        await device.set_output(1, True)
    assert device._outputs[1]["state"] is None


@pytest.mark.asyncio
async def test_communication_error_is_not_off():
    class BrokenClient(Client):
        async def read_discrete_inputs(self, **kwargs):
            return None

    device = configured_device(BrokenClient())
    with pytest.raises(ModbusException):
        await device.get_inputs()


def test_optimistic_patch_and_stale_poll_protection():
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}
    coordinator.data = {"outputs": {1: {"state": False}}}
    published = []
    coordinator.async_set_updated_data = published.append
    coordinator.async_apply_optimistic_write(("outputs", 1, "state"), True)
    assert published[-1]["outputs"][1]["state"] is True
    stale = {"outputs": {1: {"state": False}}}
    coordinator._reconcile_pending_writes(stale, update_generation=0)
    assert stale["outputs"][1]["state"] is True
    verified = {"outputs": {1: {"state": False}}}
    coordinator._reconcile_pending_writes(verified, update_generation=1)
    assert verified["outputs"][1]["state"] is False
