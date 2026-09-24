# Modbus Devices 1.7.1 — ERMAN device identity fix

Modbus Devices 1.7.1 fixes Home Assistant device grouping for ERMAN
ER-G-220-05 configuration controls.

## Fixed

- The 25 numeric `Pxxx` configuration entities now use the same stable physical
  device identifier as runtime sensors, selects, switches and buttons.
- A newly configured ER-G-220-05 is represented by one Home Assistant device
  instead of a main device plus a duplicate “Variable-frequency drive”.
- A regression test now requires numeric and enumerated controls to resolve to
  the same device-registry identifier.
- Numeric and enumerated ERMAN parameter names now honor Home Assistant's
  English/Russian locale instead of a hard-coded English fallback name.

## Upgrade

No integration reconfiguration is required. Update and restart Home Assistant.
The numeric entities will move to the main ERMAN device. If Home Assistant keeps
an empty orphaned device-registry record, it can be removed safely from the UI.
