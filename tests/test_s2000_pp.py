"""Unit tests for pure С2000-ПП configuration parsing and resolution."""

from __future__ import annotations

import asyncio

import pytest
from pymodbus.exceptions import ModbusException

from custom_components.modbus_devices.gateway import GatewayContext, GatewayType
from custom_components.modbus_devices.mapping import AutomaticDeviceMappingProvider
from custom_components.modbus_devices.s2000_pp import (
    S2000_PP_PARTITION_COUNT,
    S2000_PP_RELAY_COUNT,
    S2000_PP_ZONE_COUNT,
    S2000PPRelayRow,
    S2000PPConfiguration,
    S2000PPConfigurationCache,
    S2000PPConfigurationReader,
    S2000PPZoneRow,
    manual_relay_mapping,
    parse_partition_table,
    parse_relay_table,
    parse_zone_table,
    resolve_relay_row,
    resolve_zone_row,
)


def test_parse_zone_table_preserves_raw_rows() -> None:
    """Zone parser keeps every row, including all-zero rows."""
    registers = [0] * (S2000_PP_ZONE_COUNT * 4)
    registers[:4] = [10, 3, 2, 6]

    rows = parse_zone_table(registers)

    assert len(rows) == S2000_PP_ZONE_COUNT
    assert rows[0] == S2000PPZoneRow(1, 10, 3, 2, 6)
    assert rows[1] == S2000PPZoneRow(2, 0, 0, 0, 0)


def test_parse_relay_table_preserves_table_number() -> None:
    """Relay parser assigns the documented one-based table number."""
    registers = [0] * (S2000_PP_RELAY_COUNT * 2)
    registers[80:82] = [20, 4]

    rows = parse_relay_table(registers)

    assert len(rows) == S2000_PP_RELAY_COUNT
    assert rows[40] == S2000PPRelayRow(41, 20, 4)


def test_partition_parser_preserves_undocumented_registers() -> None:
    """Only 64 documented IDs are interpreted; all other values retain addresses."""
    registers = list(range(130))

    partitions, unparsed = parse_partition_table(registers)

    assert len(partitions) == S2000_PP_PARTITION_COUNT
    assert partitions[0].partition_id == 2
    assert {item.address for item in unparsed} == {
        2558,
        2559,
        *range(2624, 2688),
    }


def test_documented_relay_and_zone_address_formulas() -> None:
    """Resolvers apply only documented С2000-ПП address formulas."""
    relay = resolve_relay_row(S2000PPRelayRow(41, 10, 1))
    zone = resolve_zone_row(S2000PPZoneRow(41, 10, 3, 2, 6), 123)

    assert relay.modbus_address == 10040
    assert zone.modbus_address == 40040
    assert zone.zone_details is not None
    assert zone.zone_details.expanded_state_address == 4736
    assert zone.zone_details.partition_id == 123


def test_truncated_table_is_rejected() -> None:
    """A partial configuration table is never accepted as complete."""
    with pytest.raises(ModbusException):
        parse_zone_table([0] * (S2000_PP_ZONE_COUNT * 4 - 1))


def test_configuration_reader_uses_bounded_fc04_chunks() -> None:
    """The complete range is read in bounded blocks, never field by field."""

    class Response:
        def __init__(self, registers: list[int]) -> None:
            self.registers = registers
            self.function_code = 4

        @staticmethod
        def isError() -> bool:
            return False

    class Client:
        def __init__(self) -> None:
            self.requests: list[tuple[int, int, int]] = []

        async def read_input_registers(
            self,
            address: int,
            count: int,
            device_id: int,
        ) -> Response:
            self.requests.append((address, count, device_id))
            return Response([0] * count)

    client = Client()
    configuration = asyncio.run(S2000PPConfigurationReader(client, 7).async_read())

    assert len(configuration.zones) == 512
    assert len(configuration.relays) == 255
    assert len(configuration.partitions) == 64
    assert max(count for _, count, _ in client.requests) == 120
    assert all(device_id == 7 for _, _, device_id in client.requests)
    assert len(client.requests) == 25


def test_manual_and_automatic_relay_resolution_are_equivalent() -> None:
    """Manual input and a parsed table row produce the same runtime address."""
    automatic = resolve_relay_row(S2000PPRelayRow(41, 10, 3))
    manual = manual_relay_mapping(local_object_number=3, table_number=41)

    assert manual == automatic


def test_automatic_provider_separates_two_orion_devices() -> None:
    """Rows from one gateway are grouped by their Orion device address."""
    configuration = S2000PPConfiguration(
        zones=(),
        relays=tuple(
            S2000PPRelayRow(
                table_number=index + 1,
                device_address=10 if index < 6 else 20,
                local_relay_number=index % 6 + 1,
            )
            for index in range(12)
        ),
        partitions=(),
        unparsed_registers=(),
    )

    class Reader:
        async def async_read(self) -> S2000PPConfiguration:
            return configuration

    gateway = GatewayContext(
        gateway_type=GatewayType.S2000_PP,
        gateway_id="gateway-a",
        connection_key="serial:COM1",
        modbus_unit_id=1,
    )
    provider = AutomaticDeviceMappingProvider(
        reader=Reader(),
        cache=S2000PPConfigurationCache(),
    )

    async def resolve():
        first = await provider.async_resolve(gateway, "C2000KPB", 10)
        second = await provider.async_resolve(gateway, "C2000KPB", 20)
        return first, second

    first, second = asyncio.run(resolve())

    assert [item.modbus_address for item in first.objects] == list(
        range(10000, 10006)
    )
    assert [item.modbus_address for item in second.objects] == list(
        range(10006, 10012)
    )
