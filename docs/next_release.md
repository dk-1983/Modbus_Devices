# Modbus Devices 1.7.0 — Samsung MIM-B19N(T)

Modbus Devices 1.7.0 adds a shared Samsung MIM-B19N/MIM-B19NT Modbus interface
profile, shown as **MIM-B19N(T)** under Climate control and cooling.

## Scope

- Standard Samsung register map from manual DB68-07538A-03.
- Climate control: power, Auto/Cool/Dry/Fan/Heat modes, 16–30 °C target,
  Auto/Low/Medium/High fan and vertical airflow.
- Current temperature plus gateway, outdoor-unit and selected-unit diagnostics.
- Separate setup values for the MIM Modbus slave address and Samsung-side unit
  address 0–47. Connected air-conditioner model selection is not required.
- Strict FC04 payload/function/device validation and strict FC06 mirrored-write
  validation.
- English and Russian setup localization and protocol-level automated tests.

## Hardware status

The profile is derived from Samsung's common MIM-B19N/MIM-B19NT manual and is
covered by an emulated register map. A physical board has not yet been tested;
field feedback is welcome. The advanced custom MessageSet registration area at
6000/7000 is deliberately outside this release.

## Upgrade

Existing configurations require no migration. Update the integration and
restart Home Assistant, then add the new Samsung device from the UI.
