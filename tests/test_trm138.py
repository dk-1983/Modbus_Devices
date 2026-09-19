"""Protocol and compatibility tests for Owen TRM-138."""

import struct
from types import SimpleNamespace

import pytest
from pymodbus.exceptions import ModbusException
from homeassistant.const import EntityCategory

from custom_components.modbus_devices.equipment.owen import TRM138
from custom_components.modbus_devices.number import ModBusNumberEntity
from custom_components.modbus_devices.sensor import ModBusSensorEntity


class Response:
    def __init__(
        self,
        registers: list[int] | None = None,
        *,
        function_code: int = 4,
        error=False,
        address: int | None = None,
        value: int | None = None,
        dev_id: int | None = None,
    ) -> None:
        self.registers = registers
        self.function_code = function_code
        self.error = error
        self.address = address
        self.value = value
        self.dev_id = dev_id

    def isError(self) -> bool:
        return self.error


class Client:
    def __init__(
        self, registers: list[int], comparator_outputs: list[int] | None = None
    ) -> None:
        self.registers = registers
        self.comparator_outputs = comparator_outputs or [0] * 8
        self.calls: list[dict] = []
        self.holding_calls: list[dict] = []
        self.write_calls: list[dict] = []

    async def read_input_registers(self, **kwargs):
        self.calls.append(kwargs)
        address = kwargs["address"]
        count = kwargs["count"]
        return Response(self.registers[address : address + count])

    async def read_holding_registers(self, **kwargs):
        self.holding_calls.append(kwargs)
        address = kwargs["address"] - TRM138.COMPARATOR_OUTPUT_BASE_ADDRESS
        count = kwargs["count"]
        return Response(
            self.comparator_outputs[address : address + count], function_code=3
        )

    async def write_register(self, **kwargs):
        self.write_calls.append(kwargs)
        return Response(
            function_code=6,
            address=kwargs["address"],
            value=kwargs["value"],
            dev_id=kwargs["device_id"],
        )


def float_words(value: float) -> list[int]:
    return list(struct.unpack(">HH", struct.pack(">f", value)))


HARDWARE_VECTORS = [
    ([3, 15, 0, 0x4171, 0xF36D], 15.12193, 0.015),
    ([3, 15, 0, 0x4171, 0xC80D], 15.11134, 0.015),
    ([3, 15, 0, 0x4171, 0xC196], 15.10976, 0.015),
    ([0, 1510, 0, 0x4171, 0xAB2C], 15.10429, 1510.0),
    ([3, 15, 0, 0x4171, 0xBFA5], 15.10929, 0.015),
]


def sensor(device, channel):
    coordinator = SimpleNamespace(
        data={"chanels": {channel["chanel_number"]: channel}},
        last_update_success=True,
    )
    return ModBusSensorEntity(
        coordinator, device, SimpleNamespace(entry_id="trm138"), channel
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("registers", "expected", "legacy"), HARDWARE_VECTORS)
async def test_hardware_vectors_use_float_for_all_eight_channels(
    registers, expected, legacy
):
    client = Client(registers * 8)
    device = TRM138(client, 8)

    snapshot = await device.async_get_snapshot()

    assert client.calls == [{"address": 0, "count": 40, "device_id": 8}]
    assert client.holding_calls == [{"address": 65, "count": 8, "device_id": 8}]
    assert set(snapshot["chanels"]) == set(range(1, 9))
    for number, channel in snapshot["chanels"].items():
        assert channel["chanel_number"] == number
        assert channel["raw_registers"] == registers
        assert channel["decimal_point"] == registers[0]
        assert channel["integer_value"] == registers[1]
        assert channel["legacy_measurement"] == legacy
        assert channel["measurement"] == pytest.approx(expected, abs=0.000005)
        assert channel["measurement"] == channel["float_value"]
        assert channel["valid"] is True
        entity = sensor(device, channel)
        assert entity.native_value == channel["measurement"]
        assert entity.suggested_display_precision == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("float_value", [float("nan"), float("inf"), -float("inf")])
async def test_non_finite_float_invalidates_only_affected_channel(float_value):
    registers = channel_payload(1, 123, float_value=float_value)
    device = TRM138(Client(registers + channel_payload(2) * 7), 8)
    snapshot = await device.async_get_snapshot()
    channel = snapshot["chanels"][1]

    assert channel["valid"] is False
    assert channel["measurement"] is None
    assert channel["float_value"] is None
    assert channel["raw_registers"] == registers
    assert channel["legacy_measurement"] == 12.3
    assert sensor(device, channel).native_value is None
    assert all(snapshot["chanels"][n]["valid"] for n in range(2, 9))


@pytest.mark.asyncio
async def test_entity_uses_current_measurement_and_stable_display_precision():
    device = TRM138(Client([]), 8)
    entity = sensor(device, device.attr_ch2)
    assert entity.native_value is None
    assert entity.suggested_display_precision == 2
    for registers, _, _ in HARDWARE_VECTORS:
        channel = device._update_channel(2, registers)
        entity.coordinator.data = {"chanels": {2: channel}}
        assert entity.native_value == channel["measurement"]
        assert entity.suggested_display_precision == 2

    # The entity consumes the decoder result even without the legacy block.
    entity.coordinator.data = {"chanels": {2: {"measurement": -12.345}}}
    assert entity.native_value == -12.345
    entity.coordinator.data = {"chanels": {}}
    assert entity.native_value is None
    assert entity.suggested_display_precision == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [1, 11, 99])
async def test_entity_suppresses_status_error_and_recovers(status):
    device = TRM138(Client([]), 8)
    entity = sensor(device, device.attr_ch1)
    for current_status in (0, status, 0):
        channel = device._update_channel(
            1, channel_payload(1, status=current_status, float_value=15.1)
        )
        entity.coordinator.data = {"chanels": {1: channel}}
        assert entity.available
        if current_status:
            assert entity.native_value is None
        else:
            assert entity.native_value == pytest.approx(15.1)
    entity.coordinator.data = {
        "chanels": {1: {"measurement": 15.1, "status_code": status}}
    }
    assert entity.native_value is None


def channel_payload(
    number: int,
    raw_value: int = 0,
    *,
    precision: int | None = None,
    status: int = 0,
    float_value: float | None = None,
) -> list[int]:
    return [
        number % 4 if precision is None else precision,
        raw_value,
        status,
        *float_words(float(number) if float_value is None else float_value),
    ]


@pytest.mark.asyncio
async def test_snapshot_slices_documented_contiguous_channel_map():
    registers = [
        register
        for number in range(1, 9)
        for register in channel_payload(number, number * 10)
    ]
    client = Client(registers)
    device = TRM138(client, 7)

    snapshot = await device.async_get_snapshot()

    assert client.calls == [{"address": 0, "count": 40, "device_id": 7}]
    assert snapshot["comparator_outputs"] == dict.fromkeys(range(1, 9), 0)
    assert snapshot["chanels"][1]["value"][:3] == [1, 10, 0]
    assert snapshot["chanels"][8]["value"][:3] == [0, 80, 0]
    assert device.attr_ch8 is snapshot["chanels"][8]


@pytest.mark.asyncio
async def test_signed_int16_measurement_and_float_high_low_words_are_decoded():
    client = Client(channel_payload(1, 0xFF85, precision=2, float_value=-1.25))
    device = TRM138(client, 1)

    channel = await device.get_chanel(1)

    assert channel["value"][:3] == [2, -123, 0]
    assert channel["measurement"] == -1.25
    assert channel["integer_value"] == -123
    assert channel["legacy_measurement"] == -1.23
    assert channel["float_value"] == -1.25
    assert channel["raw_registers"][1] == 0xFF85
    assert channel["valid"] is True


@pytest.mark.asyncio
async def test_selected_channels_keep_legacy_order_and_individual_reads():
    registers = [
        register
        for number in range(1, 9)
        for register in channel_payload(number, number)
    ]
    client = Client(registers)
    device = TRM138(client, 3)

    channels = await device.get_chanels([8, 2])

    assert [channel["chanel_number"] for channel in channels] == [8, 2]
    assert [(call["address"], call["count"]) for call in client.calls] == [
        (35, 5),
        (5, 5),
    ]


@pytest.mark.asyncio
async def test_unknown_channel_is_rejected_before_io():
    client = Client([0] * 40)
    device = TRM138(client, 1)

    with pytest.raises(ValueError, match="Unknown TRM-138 channels"):
        await device.get_chanels([0])

    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("precision", [0, 1, 2, 3])
async def test_documented_decimal_point_scaling(precision):
    channel = await TRM138(
        Client(channel_payload(1, 1234, precision=precision)), 1
    ).get_chanel(1)

    assert channel["legacy_measurement"] == 1234 / (10**precision)
    assert channel["decimal_point"] == precision
    assert channel["measurement"] == 1.0


@pytest.mark.asyncio
async def test_known_and_unknown_statuses_are_device_level_channel_failures():
    known = await TRM138(Client(channel_payload(1, 100, status=11)), 1).get_chanel(1)
    unknown = await TRM138(Client(channel_payload(1, 100, status=99)), 1).get_chanel(1)

    assert (known["status"], known["valid"]) == ("sensor_line_break", False)
    assert (unknown["status"], unknown["valid"]) == ("unknown", False)
    assert known["measurement"] is None
    assert unknown["measurement"] is None


@pytest.mark.asyncio
async def test_invalid_decimal_point_is_rejected_semantically():
    with pytest.raises(ModbusException, match="decimal point"):
        await TRM138(Client(channel_payload(1, 100, precision=4)), 1).get_chanel(1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("registers", "function_code", "error"),
    [([0] * 39, 4, False), ([0] * 40, 3, False), ([0] * 40, 4, True)],
)
async def test_snapshot_rejects_short_wrong_function_and_exception_response(
    registers, function_code, error
):
    class FailingClient(Client):
        async def read_input_registers(self, **kwargs):
            self.calls.append(kwargs)
            return Response(registers, function_code=function_code, error=error)

    with pytest.raises(ModbusException):
        await TRM138(FailingClient(registers), 9).async_get_snapshot()


def test_channel_descriptions_preserve_entity_contract_and_order():
    device = TRM138(Client([0] * 40), 1)

    assert list(device._channels) == list(range(1, 9))
    assert [
        device._channels[n]["chanel_number_view"] for n in device._channels
    ] == list(range(1, 9))
    assert all(
        channel["chanel_type"] == "Temperature" for channel in device._channels.values()
    )
    assert all(channel["count"] == 5 for channel in device._channels.values())


@pytest.mark.asyncio
async def test_comparator_outputs_use_documented_grouped_fc03_map():
    client = Client([], [0, 1, 2, 3, 4, 5, 6, 8])
    device = TRM138(client, 8)

    outputs = await device.get_comparator_outputs()

    assert outputs == {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 8}
    assert client.holding_calls == [{"address": 65, "count": 8, "device_id": 8}]


@pytest.mark.asyncio
async def test_comparator_outputs_reject_impossible_device_value():
    client = Client([], [0, 1, 2, 3, 4, 5, 6, 9])

    with pytest.raises(ModbusException, match="channel 8 comparator output"):
        await TRM138(client, 8).get_comparator_outputs()


@pytest.mark.asyncio
@pytest.mark.parametrize(("channel", "output", "address"), [(1, 0, 65), (8, 8, 72)])
async def test_comparator_output_write_uses_strict_fc06(channel, output, address):
    client = Client([])
    device = TRM138(client, 8)

    await device.set_comparator_output(channel, output)

    assert client.write_calls == [{"address": address, "value": output, "device_id": 8}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel", "output"), [(0, 1), (9, 1), (1, -1), (1, 9), (1, True)]
)
async def test_comparator_output_rejects_invalid_values_without_io(channel, output):
    client = Client([])
    with pytest.raises(ValueError):
        await TRM138(client, 8).set_comparator_output(channel, output)
    assert client.write_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        Response(function_code=6, address=66, value=4, dev_id=8),
        Response(function_code=6, address=65, value=5, dev_id=8),
        Response(function_code=3, address=65, value=4, dev_id=8),
        Response(function_code=6, address=65, value=4, dev_id=9),
        Response(function_code=6, address=65, value=4, dev_id=8, error=True),
    ],
)
async def test_comparator_output_rejects_invalid_fc06_echo(response):
    client = Client([])

    async def write_register(**kwargs):
        client.write_calls.append(kwargs)
        return response

    client.write_register = write_register
    with pytest.raises(ModbusException):
        await TRM138(client, 8).set_comparator_output(1, 4)


def number_entity(device, channel, values=None):
    patches = []
    coordinator = SimpleNamespace(
        data={"comparator_outputs": values or {}},
        last_update_success=True,
    )

    def apply(path, value):
        patches.append((path, value))
        coordinator.data[path[0]][path[1]] = value

    coordinator.async_apply_optimistic_write = apply
    description = device.get_number_descriptions()[channel - 1]
    entity = ModBusNumberEntity(
        coordinator, device, SimpleNamespace(entry_id="trm138"), description
    )
    return entity, patches


@pytest.mark.asyncio
async def test_number_entity_writes_selected_channel_and_updates_after_success():
    client = Client([])
    device = TRM138(client, 8)
    entity, patches = number_entity(device, 2, {2: 3})

    assert entity.native_value == 3
    assert entity.entity_category is EntityCategory.CONFIG
    assert entity.name == "C.dr 2"
    assert entity.native_min_value == 0
    assert entity.native_max_value == 8
    assert entity.native_step == 1

    await entity.async_set_native_value(6.0)

    assert client.write_calls == [{"address": 66, "value": 6, "device_id": 8}]
    assert patches == [(("comparator_outputs", 2), 6)]


@pytest.mark.asyncio
async def test_number_entity_does_not_update_after_failed_write():
    client = Client([])
    device = TRM138(client, 8)
    entity, patches = number_entity(device, 1, {1: 2})

    async def fail(*args, **kwargs):
        raise ModbusException("write failed")

    device.set_comparator_output = fail
    with pytest.raises(ModbusException, match="write failed"):
        await entity.async_set_native_value(4)
    assert patches == []
