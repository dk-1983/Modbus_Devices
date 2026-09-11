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

## Release preparation

- Add the model to README.md and README_RU.md.
- Include the model in the release notes as new device support.
- Record hardware-validation results separately; current support is covered by
  automated protocol and Home Assistant regression tests but is not yet marked
  as hardware validated.
- Do not claim support for undocumented registers or configuration workflows.
