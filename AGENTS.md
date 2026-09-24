# Modbus Devices development rules

## English and Russian localization

- Maintain English and Russian localization together for every user-visible
  change.
- Add matching keys to `custom_components/modbus_devices/strings.json`,
  `translations/en.json`, and `translations/ru.json` whenever a config-flow,
  entity, selector, error, or state label is introduced or changed.
- Update both `README.md` and `README_RU.md` when release documentation or user
  instructions change.
- Preserve technical model names, register names, and protocol identifiers in
  the form used by the manufacturer documentation when translating them would
  make identification ambiguous.
- Do not publish a release until localization-key parity, JSON validation, and
  hassfest all pass.
