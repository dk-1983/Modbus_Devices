# Equipment category audit for 1.5.0

Status: implemented and validated for release 1.5.0. The category is owned by
the physical equipment model, not by its manufacturer, Python module, transport,
or gateway path.

## Contract

- Every concrete class exported through `EQUIPMENT_CLASSES` must declare exactly
  one canonical `equipment_category`.
- Category identifiers are stable English keys. User-facing labels are localized.
- Categories are registry metadata and are not persisted in Home Assistant config
  entries. Existing entries continue to resolve through manufacturer and class.
- A manufacturer may occur in several categories.
- New equipment requires category selection during the documentation audit; an
  unclassified class must fail the registry tests.
- Classification follows the primary physical purpose exposed by Modbus Devices.
  A transport adapter does not change the category of the downstream equipment.

## Canonical categories

| Key | Russian label | English label |
| --- | --- | --- |
| `building_automation` | Автоматизация зданий | Building automation |
| `climate_control` | Кондиционирование и охлаждение | Climate control and cooling |
| `engineering_monitoring` | Инженерный мониторинг и защита | Engineering monitoring and protection |
| `fire_and_security` | Противопожарное и охранное оборудование | Fire and security equipment |
| `industrial_automation` | Промышленная автоматизация | Industrial automation |
| `measurement_and_control` | Контрольно-измерительные приборы | Measurement and control equipment |
| `metering` | Приборы учёта | Metering equipment |
| `power_and_backup` | Электропитание и ИБП | Power supplies and UPS |
| `variable_frequency_drives` | Частотные преобразователи | Variable frequency drives |

## Reviewed model inventory

| Manufacturer | Class | Physical model | Category | Documentation basis |
| --- | --- | --- | --- | --- |
| 4VRS | `HaierESP32` | Haier-ESP32 | `climate_control` | Project register map: air-conditioner control derived from YCJ-A002 plus extensions |
| APC | `SmartUPS3000RMXL` | Smart-UPS 3000 RM XL | `power_and_backup` | Schneider/APC Smart-UPS and NMC2 Modbus documentation |
| Bolid | `C20002` | С2000-2 | `fire_and_security` | Official product page defines it as an access controller within the shared Orion security infrastructure |
| Bolid | `C20004` | С2000-4 | `fire_and_security` | Official page: fire/security control panel; integration exposes its Orion loops and outputs |
| Bolid | `C2000BKI` | С2000-БКИ | `fire_and_security` | Orion indication/control block used with fire/security sections |
| Bolid | `C2000DZ` | С2000-ДЗ | `engineering_monitoring` | Official page: addressable water-leak detector |
| Bolid | `C2000IP03` | С2000-ИП-03 | `fire_and_security` | Official detector documentation: addressable heat fire detector |
| Bolid | `C2000KDL` | С2000-КДЛ | `fire_and_security` | Official page: DPLS controller for fire and security Orion detectors |
| Bolid | `C2000KPB` | С2000-КПБ | `fire_and_security` | Official manual: supervised control/start outputs for fire automation |
| Bolid | `C2000RARR125` | С2000Р-АРР125 | `fire_and_security` | Official manual: radio expander for Orion fire/security devices |
| Bolid | `C2000RDZ` | С2000Р-ДЗ | `engineering_monitoring` | Official page: radio water-leak detector |
| Bolid | `C2000RDIP` | С2000Р-ДИП | `fire_and_security` | Official manual: radio optical smoke fire detector |
| Bolid | `C2000RIP` | С2000Р-ИП | `fire_and_security` | Official manual: radio heat fire detector |
| Bolid | `C2000RRM` | С2000Р-РМ | `fire_and_security` | Official radio-system documentation: relay module used by Orion automation |
| Bolid | `C2000RSMK` | С2000Р-СМК | `fire_and_security` | Official page: radio magnetic-contact security detector |
| Bolid | `C2000RST01` | С2000Р-СТ исп.01 | `fire_and_security` | Official page/manual: acoustic glass-break security detector |
| Bolid | `C2000RSirena` | С2000Р-Сирена | `fire_and_security` | Official radio-system documentation: audible annunciator |
| Bolid | `C2000RVTI` | С2000Р-ВТИ | `engineering_monitoring` | Official page: radio temperature/humidity/CO measuring device |
| Bolid | `C2000SMK` | С2000-СМК исп.04 | `fire_and_security` | Official manual: magnetic-contact security detector |
| Bolid | `C2000SP2` | С2000-СП2 | `fire_and_security` | Official Orion documentation: addressable relay/output module |
| Bolid | `C2000SP4` | С2000-СП4/24(220) | `fire_and_security` | Official documentation: actuator control for fire/smoke-protection systems |
| Bolid | `C2000ST04` | С2000-СТ исп.04 | `fire_and_security` | Official page/manual: acoustic glass-break security detector |
| Bolid | `C2000VT` | С2000-ВТ | `engineering_monitoring` | Official page: addressable temperature/humidity measurement |
| Bolid | `C2000VTI` | С2000-ВТИ | `engineering_monitoring` | Official page: indicated temperature/humidity/CO measurement |
| Bolid | `DIP34A05` | ДИП-34А-05 | `fire_and_security` | Official manual: addressable optical smoke fire detector |
| Bolid | `M3000BB1020` | M3000-BB-1020 | `building_automation` | Official building-automation I/O product family and model manual |
| Bolid | `MIP24Isp20` | МИП-24 исп.20 | `power_and_backup` | Official page: redundant 24 V supply for fire automation and detectors |
| Bolid | `Signal20M` | Сигнал-20М | `fire_and_security` | Official page: fire/security control and indicating equipment |
| Bolid | `S2000PP` | С2000-ПП | `fire_and_security` | Official page/manual: Modbus converter for the shared Orion fire/security system |
| Bolid | `SVK15_3_2_B` | СВК15-3-2-Б | `metering` | Official product documentation: water meter |
| Bolid | `SVK15_3_8_1_B3` | СВК15-3-8-1-Б3 | `metering` | Official product page/manual: universal hot/cold water meter |
| Daikin | `RTDRA` | RTD-RA | `climate_control` | Official RTD-RA installation and Modbus documentation |
| Dyna Drive | `DN310` | DN310 | `variable_frequency_drives` | Manufacturer drive protocol/manual and implemented frequency-drive controls |
| ERMAN | `ERG22005` | ER-G-220-05 | `variable_frequency_drives` | Official protocol: pump frequency-drive monitoring and commands; hardware confirmed |
| Haier | `YCJA002` | YCJ-A002 | `climate_control` | Official adapter manual: Haier air-conditioner Modbus control |
| Owen | `PLC110_24_60_K_M` | ПЛК110-24.60.К-М | `industrial_automation` | Official OWEN PLC family purpose and direct I/O mapping |
| Owen | `TRM138` | TRM-138 | `measurement_and_control` | Official manual: eight-channel measuring controller |
| Zuked | `Zuked3104S1` | 310-4.0S1 | `variable_frequency_drives` | Manufacturer manual XM-H0127: variable-frequency drive monitoring |

## Primary sources already retained by the project

- Bolid product pages and manuals collected in
  `docs/bolid_detector_family_deep_audit.md`,
  `docs/m3000_vv_1020_deep_audit.md`, and `docs/hardware_validation.md`.
- OWEN TRM-138 documentation collected in `docs/trm138t_deep_audit.md`.
- Zuked documentation collected in `docs/zuked_310_4_0s1_deep_audit.md`.
- Haier, Daikin, APC, 4VRS, ERMAN, Dyna Drive, and OWEN sources linked from
  `README.md` and `README_RU.md`.

## Menu projection

The config flow derives this projection at runtime:

```text
equipment category
  -> manufacturers that own at least one class in the category
    -> models from that manufacturer in the category
      -> existing transport/configuration steps
```

No category value is copied into an entry. A configured entry continues to use
the canonical manufacturer and equipment class, so the 1.5.0 menu change needs
no config-entry migration.
