"""Documented С2000-ПП 3.xx configuration protocol support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Iterable
from weakref import WeakKeyDictionary

from pymodbus.exceptions import ModbusException

from .gateway import (
    ModbusDataArea,
    ObjectKind,
    ResolvedObjectMapping,
    ResolvedZoneDetails,
)
from .modbus_validation import (
    validate_fc06_response,
    validated_bits,
    validated_registers,
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
S2000_PP_NUMERIC_SELECTOR = 46179
S2000_PP_POWER_NUMERIC_SELECTOR = 46181
S2000_PP_NUMERIC_RESULT = 46328
S2000_PP_NUMERIC_ZONE_TYPE = 6
S2000_PP_COUNTER_SELECTOR = 46180
S2000_PP_COUNTER_RESULT = 46332
S2000_PP_COUNTER_REGISTER_COUNT = 3
S2000_PP_COUNTER_ZONE_TYPE = 7


class NumericParameterKind(str, Enum):
    """Physical numeric parameters transported by the generic gateway API."""

    TEMPERATURE = "temperature"
    RELATIVE_HUMIDITY = "relative_humidity"
    CO_CONCENTRATION = "co_concentration"
    OUTPUT_VOLTAGE = "output_voltage"
    OUTPUT_CURRENT = "output_current"
    BATTERY_VOLTAGE = "battery_voltage"
    BATTERY_CHARGE = "battery_charge"
    MAINS_VOLTAGE = "mains_voltage"


_POWER_NUMERIC_KINDS = {
    NumericParameterKind.OUTPUT_VOLTAGE,
    NumericParameterKind.OUTPUT_CURRENT,
    NumericParameterKind.BATTERY_VOLTAGE,
    NumericParameterKind.BATTERY_CHARGE,
    NumericParameterKind.MAINS_VOLTAGE,
}


class NumericResultStatus(str, Enum):
    """Outcome of one non-blocking numeric-value transaction."""

    READY = "ready"
    PENDING = "pending"
    RETRYABLE = "retryable"
    PROTOCOL_ERROR = "protocol_error"


@dataclass(frozen=True, slots=True)
class S2000PPNumericResult:
    """Typed result preserving pending and protocol-error semantics."""

    status: NumericResultStatus
    parameter_kind: NumericParameterKind
    zone_table_number: int
    value: float | None = None
    raw_register: int | None = None
    exception_code: int | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class S2000PPCounterResult:
    """Typed result of one documented unsigned 48-bit counter request."""

    status: NumericResultStatus
    zone_table_number: int
    raw_count: int | None = None
    exception_code: int | None = None
    message: str | None = None
    result_register_read: bool = False


@dataclass(slots=True)
class _SelectorGatewaySession:
    lock: asyncio.Lock
    pending_request: tuple[str, int] | None = None


_SELECTOR_CLIENT_SESSIONS: WeakKeyDictionary[
    object, dict[str, _SelectorGatewaySession]
] = WeakKeyDictionary()


def _gateway_selector_session(client, gateway_key: str) -> _SelectorGatewaySession:
    """Return a selector session scoped to one client and gateway lifecycle."""
    sessions = _SELECTOR_CLIENT_SESSIONS.setdefault(client, {})
    return sessions.setdefault(gateway_key, _SelectorGatewaySession(asyncio.Lock()))


def decode_s2000_pp_q8_8(raw: int) -> float:
    """Decode the documented signed 16-bit Q8.8 physical value."""
    if not 0 <= raw <= 0xFFFF:
        raise ValueError("S2000-PP numeric register must be an unsigned 16-bit value")
    signed = raw - 0x10000 if raw & 0x8000 else raw
    return signed / 256


def decode_s2000_pp_unsigned_q8_8(raw: int) -> float:
    """Decode the documented unsigned direct-code Q8.8 physical value."""
    if not 0 <= raw <= 0xFFFF:
        raise ValueError("S2000-PP numeric register must be an unsigned 16-bit value")
    return raw / 256


def decode_s2000_pp_counter(registers: list[int]) -> int:
    """Decode the documented three-register unsigned big-endian counter."""
    if not isinstance(registers, list) or len(registers) != 3:
        raise ValueError("S2000-PP counter result must contain exactly three registers")
    if any(
        isinstance(register, bool)
        or not isinstance(register, int)
        or not 0 <= register <= 0xFFFF
        for register in registers
    ):
        raise ValueError("S2000-PP counter registers must be unsigned 16-bit values")
    return (registers[0] << 32) | (registers[1] << 16) | registers[2]


class S2000PPNumericValueReader:
    """Serialize and execute documented selector/result numeric transactions."""

    def __init__(self, client, modbus_unit_id: int, gateway_key: str) -> None:
        self._client = client
        self._modbus_unit_id = modbus_unit_id
        self._session = _gateway_selector_session(client, gateway_key)

    async def async_read(
        self,
        zone_table_number: int,
        parameter_kind: NumericParameterKind,
    ) -> S2000PPNumericResult:
        """Advance one transaction once; never sleep or busy-loop."""
        _validate_table_number(zone_table_number, S2000_PP_ZONE_COUNT, "zone")
        async with self._session.lock:
            request = ("numeric", zone_table_number)
            pending = self._session.pending_request
            if pending is not None and pending != request:
                return S2000PPNumericResult(
                    NumericResultStatus.RETRYABLE,
                    parameter_kind,
                    zone_table_number,
                    exception_code=6,
                    message=f"S2000-PP selector is parked for {pending[0]} zone {pending[1]}",
                )
            if pending is None:
                selected = await self._select(zone_table_number, parameter_kind)
                if selected is not None:
                    return selected
                self._session.pending_request = request

            result = await self._read_result(zone_table_number, parameter_kind)
            if result.status not in {
                NumericResultStatus.PENDING,
                NumericResultStatus.RETRYABLE,
            }:
                self._session.pending_request = None
            return result

    async def _select(self, zone: int, kind: NumericParameterKind):
        selector = (
            S2000_PP_POWER_NUMERIC_SELECTOR
            if kind in _POWER_NUMERIC_KINDS
            else S2000_PP_NUMERIC_SELECTOR
        )
        response = await self._client.write_register(
            address=selector,
            value=zone,
            device_id=self._modbus_unit_id,
        )
        error = _numeric_error_result(response, kind, zone, "select numeric zone")
        if error is not None:
            return error
        try:
            validate_fc06_response(
                response,
                address=selector,
                value=zone,
                device_id=self._modbus_unit_id,
                operation="select numeric zone",
            )
        except ModbusException:
            return S2000PPNumericResult(
                NumericResultStatus.PROTOCOL_ERROR,
                kind,
                zone,
                message="invalid FC06 selector echo",
            )
        return None

    async def _read_result(
        self, zone: int, kind: NumericParameterKind
    ) -> S2000PPNumericResult:
        response = await self._client.read_holding_registers(
            address=S2000_PP_NUMERIC_RESULT,
            count=1,
            device_id=self._modbus_unit_id,
        )
        error = _numeric_error_result(response, kind, zone, "read numeric result")
        if error is not None:
            return error
        try:
            registers = validated_registers(
                response,
                1,
                "read numeric result",
                expected_function=3,
            )
        except ModbusException as exc:
            return S2000PPNumericResult(
                NumericResultStatus.PROTOCOL_ERROR,
                kind,
                zone,
                message=str(exc),
            )
        raw = registers[0]
        try:
            value = (
                decode_s2000_pp_unsigned_q8_8(raw)
                if kind in _POWER_NUMERIC_KINDS
                else decode_s2000_pp_q8_8(raw)
            )
        except (ModbusException, TypeError, ValueError) as exc:
            return S2000PPNumericResult(
                NumericResultStatus.PROTOCOL_ERROR,
                kind,
                zone,
                message=str(exc),
            )
        return S2000PPNumericResult(
            NumericResultStatus.READY,
            kind,
            zone,
            value=value,
            raw_register=raw,
        )


class S2000PPCounterValueReader:
    """Execute documented selector/result counter transactions without scaling."""

    def __init__(self, client, modbus_unit_id: int, gateway_key: str) -> None:
        self._client = client
        self._modbus_unit_id = modbus_unit_id
        self._session = _gateway_selector_session(client, gateway_key)

    async def async_read(self, zone_table_number: int) -> S2000PPCounterResult:
        """Advance one serialized transaction once; never retry or sleep."""
        _validate_table_number(zone_table_number, S2000_PP_ZONE_COUNT, "zone")
        async with self._session.lock:
            request = ("counter", zone_table_number)
            pending = self._session.pending_request
            if pending is not None and pending != request:
                return S2000PPCounterResult(
                    NumericResultStatus.RETRYABLE,
                    zone_table_number,
                    exception_code=6,
                    message=(
                        f"S2000-PP selector is parked for {pending[0]} "
                        f"zone {pending[1]}"
                    ),
                )
            if pending is None:
                selected = await self._select(zone_table_number)
                if selected is not None:
                    return selected
                self._session.pending_request = request

            result = await self._read_result(zone_table_number)
            if result.status not in {
                NumericResultStatus.PENDING,
                NumericResultStatus.RETRYABLE,
            }:
                self._session.pending_request = None
            return result

    async def _select(self, zone: int) -> S2000PPCounterResult | None:
        response = await self._client.write_register(
            address=S2000_PP_COUNTER_SELECTOR,
            value=zone,
            device_id=self._modbus_unit_id,
        )
        error = _counter_error_result(response, zone, "select counter zone")
        if error is not None:
            return error
        try:
            validate_fc06_response(
                response,
                address=S2000_PP_COUNTER_SELECTOR,
                value=zone,
                device_id=self._modbus_unit_id,
                operation="select counter zone",
            )
        except ModbusException:
            return S2000PPCounterResult(
                NumericResultStatus.PROTOCOL_ERROR,
                zone,
                message="invalid FC06 counter selector echo",
            )
        return None

    async def _read_result(self, zone: int) -> S2000PPCounterResult:
        response = await self._client.read_holding_registers(
            address=S2000_PP_COUNTER_RESULT,
            count=S2000_PP_COUNTER_REGISTER_COUNT,
            device_id=self._modbus_unit_id,
        )
        error = _counter_error_result(
            response,
            zone,
            "read counter result",
            result_register_read=True,
        )
        if error is not None:
            return error
        try:
            registers = validated_registers(
                response,
                S2000_PP_COUNTER_REGISTER_COUNT,
                "read counter result",
                expected_function=3,
            )
            raw_count = decode_s2000_pp_counter(registers)
        except (ModbusException, TypeError, ValueError) as exc:
            return S2000PPCounterResult(
                NumericResultStatus.PROTOCOL_ERROR,
                zone,
                message=str(exc),
            )
        return S2000PPCounterResult(
            NumericResultStatus.READY,
            zone,
            raw_count=raw_count,
        )


def _counter_error_result(
    response, zone, operation, *, result_register_read: bool = False
):
    if response is None:
        return S2000PPCounterResult(
            NumericResultStatus.PROTOCOL_ERROR,
            zone,
            message=f"empty response for {operation}",
        )
    is_error = getattr(response, "isError", None)
    if not callable(is_error):
        return S2000PPCounterResult(
            NumericResultStatus.PROTOCOL_ERROR,
            zone,
            message=f"invalid response for {operation}",
        )
    if not is_error():
        return None
    code = getattr(response, "exception_code", None)
    status = (
        NumericResultStatus.PENDING
        if code == 15
        else NumericResultStatus.RETRYABLE
        if code == 6
        else NumericResultStatus.PROTOCOL_ERROR
    )
    return S2000PPCounterResult(
        status,
        zone,
        exception_code=code,
        message=f"Modbus exception during {operation}: {response}",
        result_register_read=result_register_read,
    )


def _numeric_error_result(response, kind, zone, operation):
    if response is None:
        return S2000PPNumericResult(
            NumericResultStatus.PROTOCOL_ERROR, kind, zone,
            message=f"empty response for {operation}",
        )
    is_error = getattr(response, "isError", None)
    if not callable(is_error):
        return S2000PPNumericResult(
            NumericResultStatus.PROTOCOL_ERROR, kind, zone,
            message=f"invalid response for {operation}",
        )
    if not is_error():
        return None
    code = getattr(response, "exception_code", None)
    status = (
        NumericResultStatus.PENDING
        if code == 15
        else NumericResultStatus.RETRYABLE
        if code == 6
        else NumericResultStatus.PROTOCOL_ERROR
    )
    return S2000PPNumericResult(
        status, kind, zone, exception_code=code,
        message=f"Modbus exception during {operation}: {response}",
    )


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
    primary_register: int | None = None
    priority_states: tuple[int, ...] = ()

    @property
    def raw_states(self) -> tuple[int, ...]:
        """Return every reported code, preserving zero and unknown values."""
        return self.expanded_states or (self.primary_state,)


def decode_s2000_pp_zone_state_register(raw: int) -> tuple[int, ...]:
    """Decode the two priority-ordered Orion state bytes from one register."""
    if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 0xFFFF:
        raise ValueError("S2000-PP zone state register must be an unsigned 16-bit value")
    high = (raw >> 8) & 0xFF
    low = raw & 0xFF
    return tuple(code for code in (high, low) if code != 0)


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
                    expected_function=4,
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
            bits = validated_bits(
                response,
                count,
                f"read coils at {start}",
                expected_function=1,
            )
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
        result = {}
        for item in zone_mappings:
            primary_register = primary[item.modbus_address]
            priority_states = decode_s2000_pp_zone_state_register(primary_register)
            result[item.gateway_object_number] = S2000PPZoneState(
                table_number=item.gateway_object_number,
                primary_state=priority_states[0] if priority_states else 0,
                expanded_states=expanded[item.gateway_object_number],
                primary_register=primary_register,
                priority_states=priority_states,
            )
        return result

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
                expected_function=3,
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
                expected_function=4,
            )
            for offset, mapping in enumerate(group):
                block_start = offset * S2000_PP_EXPANDED_ZONE_SIZE
                result[mapping.gateway_object_number] = tuple(
                    registers[
                        block_start : block_start + S2000_PP_EXPANDED_ZONE_SIZE
                    ]
                )
        return result


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
