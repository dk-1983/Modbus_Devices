# Modbus Devices 1.4.0 — ERMAN pump control and TRM-138 outputs

Modbus Devices 1.4.0 adds the ERMAN ER-G-220-05 pump-drive profile and manual
output-state control for Owen TRM-138.

## ERMAN ER-G-220-05

The new equipment profile follows the
[MODBUS protocol document v1.2](https://github.com/user-attachments/files/32493266/protocol_modbus_erg-220-05.pdf)
for device software 01.25.

- Reads Input registers 2000…2009 as one FC04 runtime block.
- Exposes output frequency, motor current, input voltage, drive temperature,
  current pressure, and analog inputs A1/A2.
- Preserves documented, reserved, and unknown drive/fault codes losslessly.
- Provides explicit FC05 buttons for start, stop, emergency stop, fault reset,
  and parameter save/load commands. Reserved coils are not exposed.
- Exposes Y1/Y2 as switches only after checking that P118/P120 respectively
  select function `4`.
- Serializes the function check, FC05 write, and exact FC01 readback as one
  physical operation. Home Assistant state changes only after confirmed
  readback.

Pressure is exposed in `atm`, matching the protocol document rather than
third-party YAML examples that may label the same value as `bar`.

The profile has comprehensive synthetic protocol and entity tests. Physical
hardware was not available during development; the requesting user will
validate it and provide logs for any required compatibility corrections.

## Owen TRM-138

- Adds switches named exactly as the manual parameters `Состояние ВУ 1…8`.
- Reads all eight output coils together through FC01.
- Before a manual write, reads C.dr 1…8 and refuses to take control of an
  output assigned to any comparator channel.
- Validates the mirrored FC05 response and an exact FC01 readback in one
  physical-client critical section.
- Never clears or changes a C.dr assignment automatically.

The TRM-138 output-state path is covered by automated protocol, rejection,
readback, entity, and regression tests.

## Upgrade

No configuration or entity migration is required. Update the integration and
restart Home Assistant. Existing configurations remain compatible.

Equipment details and source references are documented in the
[English README](../README.md) and [Russian README](../README_RU.md).
