# Next release documentation notes

This file records DEVELOPMENT changes that must be reflected in the public
documentation and release notes at the next release.

## New equipment

### Haier YCJ-A002

- Add Haier to the supported-manufacturer list.
- Add YCJ-A002 to the supported-equipment table.
- Document the climate entity: power, HVAC mode, target/current temperature,
  and fan mode.
- Document Modbus RTU defaults from the manufacturer manual: 19200 baud, 8N1,
  and zero-based register addressing.
- Mention that device fault and lock information is exposed as diagnostic
  climate attributes.

### Daikin RTD-RA

- Add Daikin to the supported-manufacturer list.
- Add RTD-RA to the supported-equipment table.
- Document the climate entity: power, HVAC mode, target/current temperature,
  fan mode, and louvre swing.
- Document the diagnostic coil-inlet temperature sensor and fault/status
  attributes.
- Document that RTD-RA manual references are already zero-based PDU addresses:
  H0001 → address 1, H0005 → address 5, I0121 → address 121, and
  I0131 → address 131.
- Warn that the RTD-RA Modbus master-timeout option must be configured
  deliberately; the integration does not generate artificial keepalive
  writes.

## Release preparation

- README.md contains the preliminary supported-equipment, register-map,
  generated-card, and official-source documentation.
- Add the corresponding Russian text to README_RU.md at release preparation.
- Include both models in the release notes as new device support.
- Record hardware-validation results separately; current support is covered by
  automated protocol and Home Assistant regression tests but is not yet marked
  as hardware validated.
- Do not claim support for undocumented registers or configuration workflows.
