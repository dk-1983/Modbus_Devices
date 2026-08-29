# Equipment implementation contract

This contract applies when adding an equipment model, performing a substantial
audit of an existing model, or extending capabilities from hardware evidence.
It complements the integration architecture and does not authorize hardware
writes.

## Identity and physical boundaries

- Record the manufacturer, canonical model, full official designation,
  execution/revision when known, and protocol identity.
- Define the physical-device boundary explicitly. A multi-row or multi-input
  footprint must remain one Home Assistant device.
- Preserve stable device identifiers, entity unique IDs, and the parent
  `via_device` relationship. Do not change existing identity without evidence.
- For multi-row devices, declare canonical input order, validate the complete
  footprint, reject neighboring rows, and make automatic and saved mappings
  deterministic.

## Native Home Assistant metadata

Audit every protocol path for values that map to native DeviceInfo fields:
`manufacturer`, `model`, `model_id`, `sw_version`, `hw_version`,
`serial_number`, `via_device`, and a genuinely usable `configuration_url`.
Use native fields instead of custom entity attributes.

Only values read from the particular physical device through a documented path
may be exposed. A version printed in a manual is a compatibility or target
version, not runtime `sw_version`. Missing metadata remains `None`; never use
placeholders such as `Unknown`, `N/A`, or `Not supported`.

Nearly immutable metadata should normally be read once during setup, cached on
the physical equipment runtime, and shared by all its entities. It must not be
added to the normal five-second coordinator refresh unless the protocol makes
that necessary. Account for every additional metadata request.

## Complete capability and state audit

- Compare official documentation with the capabilities actually reachable via
  the configured Modbus/gateway path: state and diagnostic sensors, binary
  sensors, numeric values, counters, battery/mains/fault data, controls, and
  service values.
- A device capability that is absent from the active protocol path is a
  documented limitation, not an entity.
- For Bolid equipment, always audit enclosure/tamper events and their exact
  input, row, and state codes. If available, expose a semantic tamper binary
  sensor (`open = on`, `restored = off`) while retaining lossless multistate
  data when compatibility or diagnostics require it.
- Preserve `None` for missing data, real booleans for real states, and numeric
  zero as zero. Coordinator/transport failure means unavailable. A skipped
  expensive measurement keeps its cache; a confirmed terminal unavailable
  result clears stale data when the device contract requires it.

## Polling and protocol errors

Before adding a capability, calculate requests per refresh, requests per
minute, multi-device worst case, selector contention, pending behavior, and
retry behavior. Fast state polling and expensive measurement polling need not
share a cadence. Use device-appropriate cache, cadence, round-robin, cooldown,
and shared selector serialization without adding background schedulers unless
there is a demonstrated need.

A pending selector/result operation must complete according to the documented
session contract, normally by repeating the result read without a new
selector. Device-specific exception handling must be scoped to the exact
device, operation, and code; other protocol and transport errors remain fatal.

## Presentation

Review presentation whenever a physical device has multiple useful entities.
Keep generator-first behavior: one physical device produces one standard
native Home Assistant entities card with semantic ordering, related state and
measurement pairs, visible diagnostic/tamper states, clean names, and no
duplicates. Add a device-specific presentation profile only when it improves
that ordering.

## Evidence, documentation, and tests

Start with current official documentation. When hardware is available, use
controlled read-only validation: actual mapping and state, raw TX/RX and CRC,
numeric payload, latency, pending behavior, and documented metadata reads.
Actuator or configuration writes require separate authorization. Do not put
addresses, credentials, site identifiers, or host-specific port names in
runtime logic.

Record validation and limitations in `docs/hardware_validation.md`. README
changes belong to a separate documentation/release step unless explicitly in
scope. Hardware-derived values should become deterministic fixtures when they
protect a protocol contract.

Tests must cover every applicable concern: physical and automatic mapping,
stable identity and `via_device`, entity matrix and no duplicates, state and
numeric semantics, missing/unavailable behavior, tamper, pending/errors,
polling/load, presentation, no unintended writes, and backward compatibility.
No test may require real hardware.

## Review checklist

An equipment review is complete only when its evidence states:

1. what the physical device is and which protocol objects it owns;
2. which native metadata fields are documented, read, cached, and exposed;
3. which capabilities are implemented or deferred by transport limitations;
4. the request budget and pending/error state machine;
5. the entity/presentation matrix and compatibility impact;
6. the documentation and deterministic tests that preserve those conclusions.
