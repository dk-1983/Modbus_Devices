# Modbus Devices 1.3.0 — 4VRS Haier-ESP32 climate control

Modbus Devices 1.3.0 adds a dedicated equipment profile for the
[Haier-ESP32-Modbus](https://github.com/dk-1983/Haier-ESP32-Modbus) controller
under the new 4VRS manufacturer.

## Haier-ESP32

Haier-ESP32 is a separate 4VRS device. Its register map was developed from the
factory YCJ-A002 register set as a compatible base and extended with additional
registers required by the new functionality. The existing Haier YCJ-A002
equipment profile remains unchanged.

- Adds climate power, HVAC mode, target and room temperature, fan mode, swing,
  and preset control.
- Adds quiet and display switches plus selectable fixed vertical and horizontal
  louvre positions. Read-only automatic louvre states remain visible but cannot
  be selected as commands.
- Exposes command status, status age, a low-word-first 32-bit packet counter,
  transport flags, and Haier-link state.
- Reads the diagnostic Input 4…8 block independently so it remains available
  when stale primary telemetry returns Modbus exception 0x0B.
- Serializes every write on the physical Modbus client, waits for controller
  confirmation, and performs an exact FC01 or FC03 readback before publishing
  the state in Home Assistant.
- Treats exception 0x06 Busy and protocol, timeout, confirmation, or readback
  failures as terminal; it never converts an unconfirmed write into optimistic
  success.

The basic YCJ-A002 communication and operating path was validated with physical
equipment on the development test bench. Full hardware validation of the new
Haier-ESP32 registers, confirmation state machine, louvre functions, quiet and
display controls is deferred until the production PCB is available.

## Upgrade

No configuration or entity migration is required. Update the integration and
restart Home Assistant. Existing configurations remain compatible.

Equipment details and official references are documented in the
[English README](../README.md) and [Russian README](../README_RU.md).
