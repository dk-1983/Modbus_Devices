# Modbus Devices 1.2.0 — APC monitoring and TRM-138 control

Modbus Devices 1.2.0 adds hardware-validated APC Smart-UPS monitoring and
improves Owen TRM-138 measurement and configuration support.

## APC Smart-UPS

- Adds a read-only **APC Smart-UPS 3000 RM XL** equipment profile over Modbus
  TCP through an AP9630 Network Management Card 2.
- Exposes electrical measurements, load, battery charge/voltage/runtime,
  internal temperature, power and battery states, AVR states, calibration
  state, and raw Status Word 3 diagnostics.
- Uses grouped FC03 reads only. UPS commands and configuration writes are not
  exposed.
- Follows Schneider Electric register map
  [990-5702A-EN](https://www.se.com/ae/en/download/document/Modbus_MGE_Galax_Smart_UPS/).

Hardware validation used an AP9630 hardware revision 05 updated from
AOS/SUMX 5.1.7 and Boot Monitor 1.0.2 to
[AOS/SUMX 7.2.2](https://www.se.com/us/en/download/document/APC_SUMX_EN/)
and Boot Monitor 1.0.9 with the official
apc_hw05_aos722_sumx722_bootmon109.exe package.

## Owen TRM-138

- Uses each channel's IEEE-754 measurement words as the published temperature,
  avoiding unstable legacy decimal-point/INT16 representations observed on
  real hardware.
- Preserves channel status handling and rejects non-finite measurements.
- Adds C.dr 1 through C.dr 8 configuration number entities.
- Reads registers 65 through 72 together with FC03.
- Writes one selected value with FC06 and strictly validates the returned
  function, slave identity, register address, and mirrored value.
- Accepts only documented integral values from 0 through 8.

The IEEE-754 temperature path was confirmed on a physical TRM-138. Direct
FC03/FC06 access to the C.dr registers and its physical output effect were
confirmed during hardware investigation.

## Upgrade

No configuration or entity migration is required. Update the integration and
restart Home Assistant. Existing configurations remain compatible.

Equipment details and official references are documented in the
[English README](../README.md) and [Russian README](../README_RU.md).
