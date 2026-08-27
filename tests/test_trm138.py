"""Protocol and compatibility tests for Owen TRM-138."""

import struct

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.equipment.owen import TRM138


class Response:
    def __init__(
        self, registers: list[int] | None, *, function_code: int = 4, error=False
    ) -> None:
        self.registers = registers
        self.function_code = function_code
        self.error = error

    def isError(self) -> bool:
        return self.error


class Client:
    def __init__(self, registers: list[int]) -> None:
        self.registers = registers
        self.calls: list[dict] = []

    async def read_input_registers(self, **kwargs):
        self.calls.append(kwargs)
        address = kwargs["address"]
        count = kwargs["count"]
        return Response(self.registers[address : address + count])


def float_words(value: float) -> list[int]:
    return list(struct.unpack(">HH", struct.pack(">f", value)))


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
    assert snapshot["chanels"][1]["value"][:3] == [1, 10, 0]
    assert snapshot["chanels"][8]["value"][:3] == [0, 80, 0]
    assert device.attr_ch8 is snapshot["chanels"][8]


@pytest.mark.asyncio
async def test_signed_int16_measurement_and_float_high_low_words_are_decoded():
    client = Client(channel_payload(1, 0xFF85, precision=2, float_value=-1.25))
    device = TRM138(client, 1)

    channel = await device.get_chanel(1)

    assert channel["value"][:3] == [2, -123, 0]
    assert channel["measurement"] == -1.23
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

    assert channel["measurement"] == 1234 / (10**precision)


@pytest.mark.asyncio
async def test_known_and_unknown_statuses_are_device_level_channel_failures():
    known = await TRM138(
        Client(channel_payload(1, 100, status=11)), 1
    ).get_chanel(1)
    unknown = await TRM138(
        Client(channel_payload(1, 100, status=99)), 1
    ).get_chanel(1)

    assert (known["status"], known["valid"]) == ("sensor_line_break", False)
    assert (unknown["status"], unknown["valid"]) == ("unknown", False)


@pytest.mark.asyncio
async def test_invalid_decimal_point_is_rejected_semantically():
    with pytest.raises(ModbusException, match="decimal point"):
        await TRM138(
            Client(channel_payload(1, 100, precision=4)), 1
        ).get_chanel(1)


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
            return Response(
                registers, function_code=function_code, error=error
            )

    with pytest.raises(ModbusException):
        await TRM138(FailingClient(registers), 9).async_get_snapshot()


def test_channel_descriptions_preserve_entity_contract_and_order():
    device = TRM138(Client([0] * 40), 1)

    assert list(device._channels) == list(range(1, 9))
    assert [
        device._channels[n]["chanel_number_view"] for n in device._channels
    ] == list(range(1, 9))
    assert all(
        channel["chanel_type"] == "Temperature"
        for channel in device._channels.values()
    )
    assert all(channel["count"] == 5 for channel in device._channels.values())
