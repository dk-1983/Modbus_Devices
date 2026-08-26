"""Protocol-map regression tests for the direct M3000-BB-1020."""

# ruff: noqa: INP001, SLF001

from unittest.mock import AsyncMock

from custom_components.modbus_devices.equipment.bolid import M3000BB1020
from pymodbus.exceptions import ModbusException
import pytest


class Response:
    """Minimal successful pymodbus response."""

    def __init__(self, *, function_code: int, registers=None, bits=None) -> None:
        """Initialize a response payload for one protocol call."""
        self.function_code = function_code
        self.registers = registers
        self.bits = bits

    def isError(self) -> bool:
        """Return a successful protocol status."""
        return False


def test_documented_input_and_relay_maps_are_unchanged() -> None:
    """Keep official sparse addresses and physical channel numbering stable."""
    device = M3000BB1020(None, 1)

    assert [getattr(device, f"attr_in{number}")["address"] for number in range(1, 13)] == [
        0x0000,
        0x0080,
        0x0100,
        0x0180,
        0x0200,
        0x0280,
        0x0300,
        0x0380,
        0x0400,
        0x0480,
        0x0500,
        0x0580,
    ]
    assert [getattr(device, f"attr_in{number}")["input_type"] for number in range(1, 13)] == [
        *("24 volts" for _ in range(6)),
        *("220 volts" for _ in range(6)),
    ]
    assert [
        getattr(device, f"attr_in{number}")["input_number_view"]
        for number in range(1, 13)
    ] == [1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6]
    assert [getattr(device, f"attr_out{number}")["address"] for number in range(1, 7)] == [
        0x1000,
        0x1080,
        0x1100,
        0x1180,
        0x1200,
        0x1280,
    ]


@pytest.mark.asyncio
async def test_sparse_inputs_and_relays_remain_individual_protocol_reads() -> None:
    """Do not read undocumented gaps between sparse FC01/FC02 addresses."""
    client = AsyncMock()
    client.read_discrete_inputs.side_effect = [
        Response(function_code=2, bits=[bool(number % 2)]) for number in range(12)
    ]
    client.read_coils.side_effect = [
        Response(function_code=1, bits=[bool(number % 2)]) for number in range(6)
    ]
    device = M3000BB1020(client, 7)

    inputs = await device.get_inputs()
    outputs = await device.get_outputs()

    assert len(inputs) == 12
    assert len(outputs) == 6
    assert [call.kwargs for call in client.read_discrete_inputs.await_args_list] == [
        {"address": address, "count": 1, "device_id": 7}
        for address in range(0, 0x0581, 0x80)
    ]
    assert [call.kwargs for call in client.read_coils.await_args_list] == [
        {"address": address, "count": 1, "device_id": 7}
        for address in range(0x1000, 0x1281, 0x80)
    ]


@pytest.mark.asyncio
async def test_runtime_header_rejects_short_combined_response() -> None:
    """Require all documented metadata and RTC words before decoding."""
    client = AsyncMock()
    client.read_holding_registers.return_value = Response(
        function_code=3,
        registers=[74, 100, 100, 1, 2, 3, 2026, 8, 26, 20, 45],
    )

    with pytest.raises(ModbusException, match="expected 12, got 11"):
        await M3000BB1020(client, 1)._get_runtime_header()
