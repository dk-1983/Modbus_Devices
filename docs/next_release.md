# Modbus Devices 1.5.0 — equipment categories and scalable navigation

Modbus Devices 1.5.0 adds a functional equipment-category level to the setup
flow so the growing device catalog remains easy to navigate.

## Equipment categories

The setup sequence is now:

```text
connection type
  -> equipment category
    -> manufacturer
      -> model
        -> connection settings
```

Nine localized categories cover the current catalog:

- Building automation
- Climate control and cooling
- Engineering monitoring and protection
- Fire and security equipment
- Industrial automation
- Measurement and control equipment
- Metering equipment
- Power supplies and UPS
- Variable frequency drives

Each of the 38 supported equipment classes now declares one canonical category.
Categories belong to physical models, not manufacturers, transports, or Python
modules, so the same manufacturer can correctly appear in several sections.

The Bolid Orion family uses a combined Fire and security equipment category
because its shared infrastructure serves both purposes. Bolid M3000-BB-1020 is
classified as Building automation, water meters as Metering equipment, and
environmental/leak detectors as Engineering monitoring and protection.

## Compatibility and validation

- Categories are transient setup navigation and are not persisted in Home
  Assistant config entries.
- Existing configured devices require no migration and keep their entity IDs.
- The existing S2000-PP route shows only categories containing compatible
  downstream equipment.
- Registry validation rejects any future equipment class without a canonical
  category, making documentation-based classification mandatory for new models.
- English and Russian labels are included for the complete menu.

The release was validated with the complete automated test suite, Ruff,
compileall, JSON/localization checks, `git diff --check`, official Home Assistant
hassfest, and live Home Assistant UI verification.

The complete reviewed inventory and classification basis are recorded in
[`equipment_category_audit.md`](equipment_category_audit.md).

## Upgrade

No configuration or entity migration is required. Update the integration and
restart Home Assistant. Existing configurations remain compatible.

Setup instructions and the new category-selection screenshot are available in
the [English README](../README.md) and [Russian README](../README_RU.md).
