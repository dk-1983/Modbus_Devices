"""Documented С2000-ПП 3.xx configuration protocol support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable

from pymodbus.exceptions import ModbusException

from .gateway import (
    ModbusDataArea,
    ObjectKind,
    ResolvedObjectMapping,
    ResolvedZoneDetails,
)

S2000_PP_CONFIGURATION_START = 0
S2000_PP_CONFIGURATION_END = 2687
S2000_PP_ZONE_COUNT = 512
S2000_PP_ZONE_ROW_SIZE = 4
S2000_PP_RELAY_START = 2048
S2000_PP_RELAY_COUNT = 255
S2000_PP_RELAY_ROW_SIZE = 2
S2000_PP_UNDOCUMENTED_GAP_START = 2558
S2000_PP_PARTITION_START = 2560
S2000_PP_PARTITION_COUNT = 64
S2000_PP_CONFIGURATION_CHUNK_SIZE = 120

S2000_PP_RELAY_COIL_START = 10000
S2000_PP_ZONE_STATE_START = 40000
S2000_PP_EXPANDED_ZONE_START = 4096
S2000_PP_EXPANDED_ZONE_SIZE = 16
S2000_PP_RUNTIME_READ_CHUNK_SIZE = 120


@dataclass(frozen=True, slots=True)
class S2000PPZoneRow:
    """One raw row of the С2000-ПП zone configuration table."""

    table_number: int
    device_address: int
    local_zone_number: int
    partition_number: int
    zone_type: int


@dataclass(frozen=True, slots=True)
class S2000PPRelayRow:
    """One raw row of the С2000-ПП relay configuration table."""

    table_number: int
    device_address: int
    local_relay_number: int


@dataclass(frozen=True, slots=True)
class S2000PPPartitionRow:
    """One raw partition identifier row."""

    partition_number: int
    partition_id: int


@dataclass(frozen=True, slots=True)
class S2000PPRawRegister:
    """Configuration register whose meaning is not documented for this reader."""

    address: int
    value: int


@dataclass(frozen=True, slots=True)
class S2000PPConfiguration:
    """Immutable configuration snapshot read from one С2000-ПП."""

    zones: tuple[S2000PPZoneRow, ...]
    relays: tuple[S2000PPRelayRow, ...]
    partitions: tuple[S2000PPPartitionRow, ...]
    unparsed_registers: tuple[S2000PPRawRegister, ...]

    def zones_for_device(self, orion_address: int) -> tuple[S2000PPZoneRow, ...]:
        """Return rows explicitly assigned to the requested Orion address."""
        _validate_orion_address(orion_address)
        return tuple(
            row for row in self.zones if row.device_address == orion_address
        )

    def relays_for_device(
        self,
        orion_address: int,
    ) -> tuple[S2000PPRelayRow, ...]:
        """Return rows explicitly assigned to the requested Orion address."""
        _validate_orion_address(orion_address)
        return tuple(
            row for row in self.relays if row.device_address == orion_address
        )

    def partition_id(self, partition_number: int) -> int | None:
        """Return the raw optional identifier for a configured partition number."""
        if not 1 <= partition_number <= S2000_PP_PARTITION_COUNT:
            return None
        if len(self.partitions) < partition_number:
            return None
        partition_id = self.partitions[partition_number - 1].partition_id
        return partition_id if 1 <= partition_id <= 65534 else None


@dataclass(frozen=True, slots=True)
class S2000PPZoneState:
    """One complete runtime zone state without model-specific interpretation."""

    table_number: int
    primary_state: int
    expanded_states: tuple[int, ...]

    @property
    def raw_states(self) -> tuple[int, ...]:
        """Return every reported code, preserving zero and unknown values."""
        return self.expanded_states or (self.primary_state,)


def parse_zone_table(registers: list[int]) -> tuple[S2000PPZoneRow, ...]:
    """Parse a complete zone table without filtering raw rows."""
    expected = S2000_PP_ZONE_COUNT * S2000_PP_ZONE_ROW_SIZE
    _validate_register_count(registers, expected, "zone configuration table")
    return tuple(
        S2000PPZoneRow(
            table_number=index + 1,
            device_address=registers[index * 4],
            local_zone_number=registers[index * 4 + 1],
            partition_number=registers[index * 4 + 2],
            zone_type=registers[index * 4 + 3],
        )
        for index in range(S2000_PP_ZONE_COUNT)
    )


def parse_relay_table(registers: list[int]) -> tuple[S2000PPRelayRow, ...]:
    """Parse a complete relay table without filtering raw rows."""
    expected = S2000_PP_RELAY_COUNT * S2000_PP_RELAY_ROW_SIZE
    _validate_register_count(registers, expected, "relay configuration table")
    return tuple(
        S2000PPRelayRow(
            table_number=index + 1,
            device_address=registers[index * 2],
            local_relay_number=registers[index * 2 + 1],
        )
        for index in range(S2000_PP_RELAY_COUNT)
    )


def parse_partition_table(
    registers: list[int],
) -> tuple[tuple[S2000PPPartitionRow, ...], tuple[S2000PPRawRegister, ...]]:
    """Parse documented partition IDs and preserve every unexplained register."""
    expected = S2000_PP_CONFIGURATION_END - S2000_PP_UNDOCUMENTED_GAP_START + 1
    _validate_register_count(registers, expected, "partition configuration table")
    partition_offset = S2000_PP_PARTITION_START - S2000_PP_UNDOCUMENTED_GAP_START
    partitions = tuple(
        S2000PPPartitionRow(
            partition_number=index + 1,
            partition_id=registers[partition_offset + index],
        )
        for index in range(S2000_PP_PARTITION_COUNT)
    )
    documented_addresses = set(
        range(
            S2000_PP_PARTITION_START,
            S2000_PP_PARTITION_START + S2000_PP_PARTITION_COUNT,
        )
    )
    unparsed = tuple(
        S2000PPRawRegister(address=address, value=value)
        for address, value in enumerate(
            registers,
            start=S2000_PP_UNDOCUMENTED_GAP_START,
        )
        if address not in documented_addresses
    )
    return partitions, unparsed


def resolve_relay_row(row: S2000PPRelayRow) -> ResolvedObjectMapping:
    """Resolve one documented relay table row into its Modbus coil."""
    if row.local_relay_number < 1:
        raise ValueError("S2000-PP relay local number must be positive")
    return ResolvedObjectMapping(
        object_kind=ObjectKind.RELAY,
        data_area=ModbusDataArea.COIL,
        local_object_number=row.local_relay_number,
        gateway_object_number=row.table_number,
        modbus_address=S2000_PP_RELAY_COIL_START + row.table_number - 1,
    )


def resolve_zone_row(
    row: S2000PPZoneRow,
    partition_id: int | None,
) -> ResolvedObjectMapping:
    """Resolve one documented zone row without interpreting its state semantics."""
    return ResolvedObjectMapping(
        object_kind=ObjectKind.ZONE,
        data_area=ModbusDataArea.HOLDING_REGISTER,
        local_object_number=row.local_zone_number,
        gateway_object_number=row.table_number,
        modbus_address=S2000_PP_ZONE_STATE_START + row.table_number - 1,
        zone_details=ResolvedZoneDetails(
            zone_type=row.zone_type,
            partition_number=row.partition_number,
            partition_id=partition_id,
            expanded_state_address=(
                S2000_PP_EXPANDED_ZONE_START
                + (row.table_number - 1) * S2000_PP_EXPANDED_ZONE_SIZE
            ),
        ),
    )


def manual_relay_mapping(
    local_object_number: int,
    table_number: int,
) -> ResolvedObjectMapping:
    """Resolve user-supplied relay configuration fields."""
    _validate_table_number(table_number, S2000_PP_RELAY_COUNT, "relay")
    if local_object_number < 1:
        raise ValueError("S2000-PP relay local number must be positive")
    return resolve_relay_row(
        S2000PPRelayRow(
            table_number=table_number,
            device_address=0,
            local_relay_number=local_object_number,
        )
    )


def manual_zone_mapping(
    local_object_number: int,
    table_number: int,
    zone_type: int,
    partition_number: int,
    partition_id: int | None,
) -> ResolvedObjectMapping:
    """Resolve user-supplied zone configuration fields."""
    _validate_table_number(table_number, S2000_PP_ZONE_COUNT, "zone")
    return resolve_zone_row(
        S2000PPZoneRow(
            table_number=table_number,
            device_address=0,
            local_zone_number=local_object_number,
            partition_number=partition_number,
            zone_type=zone_type,
        ),
        partition_id,
    )


class S2000PPConfigurationReader:
    """Read the complete gateway configuration once, outside state polling."""

    def __init__(self, client, modbus_unit_id: int) -> None:
        self._client = client
        self._modbus_unit_id = modbus_unit_id

    async def async_read(self) -> S2000PPConfiguration:
        """Read and parse all documented configuration table ranges."""
        zone_registers = await self._read_range(
            S2000_PP_CONFIGURATION_START,
            S2000_PP_ZONE_COUNT * S2000_PP_ZONE_ROW_SIZE,
            "zone configuration table",
        )
        relay_registers = await self._read_range(
            S2000_PP_RELAY_START,
            S2000_PP_RELAY_COUNT * S2000_PP_RELAY_ROW_SIZE,
            "relay configuration table",
        )
        partition_registers = await self._read_range(
            S2000_PP_UNDOCUMENTED_GAP_START,
            S2000_PP_CONFIGURATION_END - S2000_PP_UNDOCUMENTED_GAP_START + 1,
            "partition configuration table",
        )
        partitions, unparsed_registers = parse_partition_table(partition_registers)
        return S2000PPConfiguration(
            zones=parse_zone_table(zone_registers),
            relays=parse_relay_table(relay_registers),
            partitions=partitions,
            unparsed_registers=unparsed_registers,
        )

    async def _read_range(
        self,
        start: int,
        count: int,
        operation: str,
    ) -> list[int]:
        registers: list[int] = []
        while len(registers) < count:
            chunk_start = start + len(registers)
            chunk_count = min(
                S2000_PP_CONFIGURATION_CHUNK_SIZE,
                count - len(registers),
            )
            response = await self._client.read_input_registers(
                address=chunk_start,
                count=chunk_count,
                device_id=self._modbus_unit_id,
            )
            registers.extend(
                validated_registers(
                    response,
                    chunk_count,
                    f"{operation} at {chunk_start}",
                )
            )
        return registers


class S2000PPConfigurationCache:
    """Small runtime cache keyed by stable gateway identity."""

    def __init__(self) -> None:
        self._configurations: dict[str, S2000PPConfiguration] = {}

    async def async_get_or_load(
        self,
        gateway_id: str,
        loader: Callable[[], Awaitable[S2000PPConfiguration]],
    ) -> S2000PPConfiguration:
        """Return cached configuration or load it once."""
        configuration = self._configurations.get(gateway_id)
        if configuration is None:
            configuration = await loader()
            self._configurations[gateway_id] = configuration
        return configuration

    def invalidate(self, gateway_id: str) -> None:
        """Drop one gateway configuration for an explicit future refresh."""
        self._configurations.pop(gateway_id, None)


class S2000PPRuntimeReader:
    """Read resolved coils and zone states without rescanning configuration."""

    def __init__(self, client, modbus_unit_id: int) -> None:
        self._client = client
        self._modbus_unit_id = modbus_unit_id

    async def async_read_coils(self, addresses: Iterable[int]) -> dict[int, bool]:
        """Read consecutive coil groups and return states keyed by address."""
        result: dict[int, bool] = {}
        for start, count in _consecutive_ranges(addresses):
            response = await self._client.read_coils(
                address=start,
                count=count,
                device_id=self._modbus_unit_id,
            )
            bits = validated_bits(response, count, f"read coils at {start}")
            result.update({start + offset: value for offset, value in enumerate(bits)})
        return result

    async def async_read_zone_states(
        self,
        mappings: Iterable[ResolvedObjectMapping],
    ) -> dict[int, S2000PPZoneState]:
        """Read primary and expanded states for the resolved zone mappings."""
        zone_mappings = tuple(sorted(mappings, key=lambda item: item.modbus_address))
        if any(item.zone_details is None for item in zone_mappings):
            raise ValueError("Zone runtime mapping is missing resolved zone details")
        primary = await self._read_holding_addresses(
            item.modbus_address for item in zone_mappings
        )
        expanded = await self._read_expanded_blocks(zone_mappings)
        return {
            item.gateway_object_number: S2000PPZoneState(
                table_number=item.gateway_object_number,
                primary_state=primary[item.modbus_address],
                expanded_states=expanded[item.gateway_object_number],
            )
            for item in zone_mappings
        }

    async def _read_holding_addresses(
        self,
        addresses: Iterable[int],
    ) -> dict[int, int]:
        result: dict[int, int] = {}
        for start, count in _consecutive_ranges(addresses):
            response = await self._client.read_holding_registers(
                address=start,
                count=count,
                device_id=self._modbus_unit_id,
            )
            registers = validated_registers(
                response,
                count,
                f"read zone states at {start}",
            )
            result.update(
                {start + offset: value for offset, value in enumerate(registers)}
            )
        return result

    async def _read_expanded_blocks(
        self,
        mappings: tuple[ResolvedObjectMapping, ...],
    ) -> dict[int, tuple[int, ...]]:
        result: dict[int, tuple[int, ...]] = {}
        ordered = sorted(
            mappings,
            key=lambda item: item.zone_details.expanded_state_address,
        )
        index = 0
        while index < len(ordered):
            group = [ordered[index]]
            index += 1
            while index < len(ordered):
                previous = group[-1].zone_details.expanded_state_address
                current = ordered[index].zone_details.expanded_state_address
                if (
                    current != previous + S2000_PP_EXPANDED_ZONE_SIZE
                    or (len(group) + 1) * S2000_PP_EXPANDED_ZONE_SIZE
                    > S2000_PP_RUNTIME_READ_CHUNK_SIZE
                ):
                    break
                group.append(ordered[index])
                index += 1

            start = group[0].zone_details.expanded_state_address
            count = len(group) * S2000_PP_EXPANDED_ZONE_SIZE
            response = await self._client.read_input_registers(
                address=start,
                count=count,
                device_id=self._modbus_unit_id,
            )
            registers = validated_registers(
                response,
                count,
                f"read expanded zone states at {start}",
            )
            for offset, mapping in enumerate(group):
                block_start = offset * S2000_PP_EXPANDED_ZONE_SIZE
                result[mapping.gateway_object_number] = tuple(
                    registers[
                        block_start : block_start + S2000_PP_EXPANDED_ZONE_SIZE
                    ]
                )
        return result


def validated_registers(response, expected: int, operation: str) -> list[int]:
    """Validate a Modbus read response and its exact register count."""
    if response is None:
        raise ModbusException(f"Empty Modbus response for {operation}")
    is_error = getattr(response, "isError", None)
    if not callable(is_error):
        raise ModbusException(f"Invalid Modbus response for {operation}")
    if is_error():
        raise ModbusException(f"Modbus error response for {operation}: {response}")
    registers = getattr(response, "registers", None)
    if not isinstance(registers, list):
        raise ModbusException(f"Missing registers in response for {operation}")
    _validate_register_count(registers, expected, operation)
    return registers


def validated_bits(response, expected: int, operation: str) -> list[bool]:
    """Validate a Modbus bit response, allowing protocol byte padding."""
    if response is None:
        raise ModbusException(f"Empty Modbus response for {operation}")
    is_error = getattr(response, "isError", None)
    if not callable(is_error):
        raise ModbusException(f"Invalid Modbus response for {operation}")
    if is_error():
        raise ModbusException(f"Modbus error response for {operation}: {response}")
    bits = getattr(response, "bits", None)
    if not isinstance(bits, list) or len(bits) < expected:
        actual = 0 if not isinstance(bits, list) else len(bits)
        raise ModbusException(
            f"Short Modbus response for {operation}: "
            f"expected at least {expected}, got {actual}"
        )
    return [bool(bit) for bit in bits[:expected]]


def _validate_register_count(
    registers: list[int],
    expected: int,
    operation: str,
) -> None:
    if len(registers) != expected:
        raise ModbusException(
            f"Short Modbus response for {operation}: "
            f"expected {expected}, got {len(registers)}"
        )


def _validate_orion_address(orion_address: int) -> None:
    if not 1 <= orion_address <= 127:
        raise ValueError("Orion device address must be between 1 and 127")


def _validate_table_number(table_number: int, maximum: int, name: str) -> None:
    if not 1 <= table_number <= maximum:
        raise ValueError(f"S2000-PP {name} table number is out of range")


def _consecutive_ranges(addresses: Iterable[int]) -> tuple[tuple[int, int], ...]:
    """Return bounded ranges containing only consecutive requested addresses."""
    ordered = sorted(set(addresses))
    if not ordered:
        return ()
    ranges: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for address in ordered[1:]:
        if (
            address != previous + 1
            or address - start + 1 > S2000_PP_RUNTIME_READ_CHUNK_SIZE
        ):
            ranges.append((start, previous - start + 1))
            start = address
        previous = address
    ranges.append((start, previous - start + 1))
    return tuple(ranges)
