# Modbus Devices 1.6.0 — ERMAN configuration controls

Modbus Devices 1.6.0 adds guarded configuration controls for the ERMAN
ER-G-220-05 pump drive.

## Scope

- 25 numeric parameters and 12 enumerated parameters from protocol pages 8–9.
- Documented `Pxxx` names, scales, steps, ranges, units, and English/Russian
  localization.
- Live dependent limits for parameters constrained by P006 or P102.
- Two grouped FC03 configuration reads every 30 seconds, independent of the
  existing one-second grouped runtime poll.
- Serialized single-register FC06 writes with mirrored-response validation and
  exact FC03 readback before publishing the new Home Assistant state.
- Reserved register addresses are never written.

## Connection safety

P122 (Modbus slave ID) and P123 (baud rate) are intentionally not writable from
Home Assistant. Change them locally on the drive, then recreate the Modbus
Devices connection with the new values. This prevents a successful write from
making the active connection unreachable before it can be verified.

Calendar/time and weekday-mask registers require dedicated date/time controls
and are not represented as misleading raw numeric values in this release.

## Upgrade

No configuration or entity migration is required. Update the integration and
restart Home Assistant. Newly supported configuration entities appear under
the device's Configuration section.
