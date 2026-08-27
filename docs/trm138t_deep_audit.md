# TRM138T deep audit

## Scope and sources

This audit covers the integration's existing `TRM138` class (the user-facing
TRM-138/TRM138T target) and the documented measurement snapshot only. It does
not add regulator, output, configuration, or service operations.

Authoritative sources:

- [OWEN TRM138 operating manual](https://docs.owen.ru/product/trm138/doc/rukovodstvo-po-ekspluatacii-trm138), especially “Параметры протоколов Овен/Modbus”, “Коды ошибок”, and the decimal-point configuration table.
- [OWEN TRM138 product documentation index](https://docs.owen.ru/product/trm138).

The manual identifies eight universal measurement inputs and documents FC04
registers 0 through 39 as eight consecutive five-register channel blocks. It
calls the returned quantity “temperature” in the Modbus table, while other
sections explicitly describe configurations using unified current signals.
Consequently, the protocol decoder does not infer a physical quantity from the
register block. Existing Home Assistant temperature entity metadata is retained
only for compatibility; correcting that legacy presentation requires an
explicit migration design and is deferred.

## Capability and register matrix

| Capability | Function | Address/count | Classification | Current scope |
|---|---:|---:|---|---|
| Measurement channels 1–8 | FC04 | 0, 40 | documented read-only contiguous snapshot | implemented |
| One measurement channel N | FC04 | `(N-1)*5`, 5 | documented read-only compatibility method | implemented |
| Calculated channels | FC04 | 64 onward | documented read-only | deferred |
| Setpoints/hysteresis/configuration | FC03/06 | multiple ranges | documented read/write | deferred; no writes added |
| Output state/manual output | FC01/05 | 0 onward | documented read/write with safety conditions | deferred; no entities/writes added |

Each measurement channel block is:

| Offset | Meaning | Decoding |
|---:|---|---|
| 0 | decimal-point position | integer, semantically restricted to 0…3 |
| 1 | integer measurement | signed INT16, scaled by `10 ** decimal_point` |
| 2 | device channel status/error | unsigned code; zero valid, documented nonzero and unknown codes invalid |
| 3 | IEEE-754 value, high word | first word of big-endian binary32 |
| 4 | IEEE-754 value, low word | second word of big-endian binary32 |

The decoded channel retains the established five-item `value` list so existing
entities continue to use the same key and scaling contract. Additional explicit
fields expose `measurement`, `float_value`, `status_code`, `status`, `valid`, and
`raw_registers`. The float is decoded for protocol completeness; selecting it
as the entity state instead of the established scaled INT16 is deferred pending
hardware comparison across firmware/configuration variants.

## Method and transaction audit

Before this refactor, `get_chanels()` iterated over all eight channels and made
eight sequential FC04 reads of five registers. Coordinator polling called that
method once. There were no duplicate reads of the same channel within a poll,
but the per-channel loop was an N+1-style transaction pattern.

The manual documents a single contiguous FC04 area from address 0 through 39.
The polling snapshot now performs exactly one `read_input_registers(address=0,
count=40, device_id=...)`, validates the complete response, and slices it at
`(channel - 1) * 5`. Transaction count is therefore **8 -> 1 per polling
snapshot**. The public single-channel method and explicitly selected channel
list preserve their legacy per-channel reads; they are not used by ordinary
full snapshot polling.

There are no TRM138 writes in the class. Generic client serialization remains
the concurrency boundary, and no coordinator/shared-layer changes are needed.

## Error and availability semantics

Transport errors, Modbus exception responses, wrong function codes, malformed
payloads, short payloads, invalid register values, and impossible decimal-point
values raise `ModbusException`; the coordinator treats these as poll failures.
A successfully transported channel block with nonzero status is different: the
snapshot succeeds, the status is retained, the channel is marked invalid, and
the sensor does not publish the accompanying measurement. Unknown nonzero codes
are preserved numerically and labelled `unknown`; they are not guessed or
treated as valid. Entity availability remains tied to coordinator transport
success, preserving the existing integration-level availability contract.

## Functional parity

The refactor preserves eight sensor entities, channel numbers and dictionary
keys, ordering 1…8, names, unique-ID construction, device/state classes, units,
grouping under `chanels`, localization inputs, and presentation ordering. The
legacy misspelled `chanel`/`chanels` and unit keys remain intentionally intact.

## Implemented, deferred, and hardware-validation candidates

Implemented: exact FC04 snapshot, complete response validation, deterministic
channel slicing, signed INT16, decimal scaling, high-word/low-word IEEE-754
binary32, documented status mapping, unknown-status handling, and separation of
transport from device-level status.

Deferred: calculated channels, output/regulator/configuration support, all
writes, physical-quantity discovery and entity metadata migration, and choosing
the float rather than scaled INT16 as the canonical entity value.

Hardware-validation candidates (no hardware operations were performed): compare
INT16/scaling and float values on negative and fractional inputs; collect status
zero and each reachable fault code; verify NaN/infinity behavior if emitted;
confirm contiguous FC04/40 support on every supported TRM138T firmware variant;
and determine whether a readable input-type parameter can safely drive a future
physical-quantity/entity migration.
