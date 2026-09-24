# Modbus Devices 1.5.1 — faster ERMAN runtime monitoring

Modbus Devices 1.5.1 increases the ERMAN ER-G-220-05 runtime polling rate from
the integration-wide five-second default to one update per second.

## Scope

- Only ER-G-220-05 receives the one-second interval.
- Drive state, output frequency, current pressure, motor current, and the rest
  of its existing grouped snapshot are refreshed together.
- Other equipment retains the five-second default.
- The interval is declared by the equipment profile and is not user
  configurable.
- A coordinator guard prevents any equipment profile from requesting a polling
  rate faster than one cycle per second.
- The existing single grouped FC04 runtime read, strict response validation,
  serialization, entities, and configuration remain unchanged.

## Important limitation

ER-G-220-05 is a Modbus slave/server and cannot initiate a state update. Home
Assistant, acting as the Modbus master/client, receives only the register values
present at the instant of each request. One-second polling substantially
improves runtime visibility but is not a real-time event recorder and cannot
guarantee capture of a state that appears and disappears between polls. Safety
and fault handling must continue to use the drive's latched fault code and its
own diagnostics.

## Upgrade

No configuration or entity migration is required. Update the integration and
restart Home Assistant.
