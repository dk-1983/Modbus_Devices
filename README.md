# Modbus Devices for Home Assistant

**[English](README.md) | [Русский](README_RU.md)**

Modbus Devices is a custom Home Assistant integration for explicitly supported industrial and building-automation equipment. Each equipment model defines its own Modbus-visible capabilities, entities, validation rules, and, where required, gateway mapping.

The integration is a local-polling hub. It currently supports direct Modbus equipment from Bolid and Owen, plus Bolid Orion devices exposed through a С2000-ПП gateway.

## Key features

- Modbus TCP, Modbus UDP, and serial Modbus RTU connections.
- Equipment-driven creation of sensors, binary sensors, switches, and datetime entities.
- Typed equipment variants and topology-dependent capabilities.
- С2000-ПП gateway support for Orion, С2000-КДЛ, and downstream DPLS equipment.
- Manual and configuration-assisted gateway mapping.
- Authoritative multistate Orion values with primary, expanded, and raw state codes.
- Documented numeric measurements, including temperature and humidity where the С2000-ПП path supports them.
- Relay/output control with validated writes, optimistic synchronization, and protection from stale poll results.
- Explicit communication and malformed-response error handling: failures are not reported as normal or off states.
- Backward-compatible loading of legacy Config Entries while presenting canonical manufacturer and model names.

Support is model-specific. Selecting a manufacturer does not imply support for every device or every physical function from that manufacturer.

## Architecture

```text
Manufacturer
  → Equipment model
    → Transport or gateway
      → Resolved mapping
        → Coordinator snapshot
          → Home Assistant Device and entities
```

Direct equipment is polled over its configured Modbus connection. Gateway-backed Bolid equipment uses an additional mapping layer that separates a physical device identity from the С2000-ПП table rows used to read or control it.

### Bolid Orion and DPLS path

```text
Home Assistant
  ← Modbus
    ← С2000-ПП
      ← Orion
        ← С2000-КДЛ
          ← DPLS device
```

Radio devices remain individual KDL-visible DPLS objects:

```text
radio device ↔ С2000Р-АРР125
             → KDL-visible DPLS object
             → С2000-КДЛ
             → С2000-ПП
             → Home Assistant
```

The radio expander is not added to a radio device's stable identity. Within one gateway, a downstream identity is based on the KDL Orion address and the device's DPLS address.

## Supported transports

| Transport | Configuration |
|---|---|
| Modbus TCP | Host, port, and Modbus unit ID |
| Modbus UDP | Host, port, and Modbus unit ID |
| Serial Modbus RTU | Serial port, baud rate, byte size, parity, stop bits, and unit ID |

Transport support still depends on the selected equipment and its physical interface.

## Supported equipment

The following table is generated from the canonical equipment registry in the current source tree. Model names are user-facing manufacturer names, not Python class keys.

### Bolid — direct Modbus and С2000-ПП gateway

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Bolid | [M3000-BB-1020](https://bolid.ru/production/disp/inout-modules/m3000_vv_1020.html) | Direct Modbus | 12 binary inputs, 6 relay switches, device clock | Runtime service information is read from the device |
| Bolid | [С2000-ПП](https://bolid.ru/production/s2000-pp.html) | Direct Modbus | Gateway diagnostic binary sensors | Orion master mode/communication, enclosure tamper, and power fault; device service information where exposed |
| Bolid | С2000-КПБ | С2000-ПП → Orion | Configured output switches and multistate sensors | Up to 6 outputs/circuit states, 2 technological inputs, and device state; entities follow the configured subset |

### Bolid — С2000-КДЛ and wired DPLS equipment

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Bolid | [С2000-КДЛ](https://bolid.ru/production/s2000-kdl.html) | С2000-ПП → Orion | Multistate diagnostic sensor | Only the controller-owned type-3/local-0 state; downstream rows remain separate devices |
| Bolid | ДИП-34А-05 | С2000-ПП → С2000-КДЛ → DPLS | Operational multistate detector state | One DPLS address; no synthetic smoke/dust sensors |
| Bolid | С2000-ИП-03 | С2000-ПП → С2000-КДЛ → DPLS | Multistate detector state; optional temperature sensor | Type-1 state-only or type-6 state-and-temperature mapping; both modes use one DPLS identity |
| Bolid | [С2000-ДЗ](https://bolid.ru/production/s_2000_dz.html) | С2000-ПП → С2000-КДЛ → DPLS | Multistate water-leak state | Static variants 1.06, 1.10, and 1.13; no derived moisture binary sensor |
| Bolid | С2000-ВТ / С2000-ВТ исп.01 | С2000-ПП → С2000-КДЛ → DPLS | Temperature and relative-humidity sensors | Numeric values use the documented С2000-ПП numeric request lifecycle |
| Bolid | С2000-ВТИ / С2000-ВТИ исп.01 | С2000-ПП → С2000-КДЛ → DPLS | No currently available entities through this path | Models are registered, but numeric transport through the current С2000-ПП path is not confirmed and configuration is blocked |
| Bolid | [С2000-СП4](https://bolid.ru/production/s2000-sp4.html) | С2000-ПП → С2000-КДЛ → DPLS | Configured actuator switch and multistate position/circuit sensors | Supported variants are listed below; entities follow the configured mapping subset |

Supported С2000-СП4 variants:

- С2000-СП4/24
- С2000-СП4/24 исп.01
- С2000-СП4/220
- С2000-СП4/220 исп.01

**С2000-СП4/220 исп.02 is not supported.**

### Bolid — radio equipment represented as DPLS objects

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Bolid | [С2000Р-АРР125](https://bolid.ru/production/s2r_arr125.html) | С2000-ПП → С2000-КДЛ → DPLS | Aggregate multistate expander state | Hardware variants 1.0 and 14.0; enrolled radio devices are not owned by this equipment model |
| Bolid | С2000Р-ДИП | С2000-ПП → С2000-КДЛ → DPLS | Operational multistate detector/radio state | Battery, tamper, and communication conditions remain multistate values; no RSSI entity |
| Bolid | С2000Р-ИП | С2000-ПП → С2000-КДЛ → DPLS | Operational multistate detector/radio state | Physical temperature capability exists, but numeric temperature through the current PP path is not confirmed |
| Bolid | С2000Р-РМ / С2000Р-РМ исп.01 | С2000-ПП → С2000-КДЛ → DPLS | Two independent relay switches; optional controlled-circuit state | Standard variant supports two-output or two-output-plus-input topology; исп.01 is outputs-only |
| Bolid | С2000Р-Сирена | С2000-ПП → С2000-КДЛ → DPLS | Independent Light and Sound switches | No combined switch, pattern, duration, or radio-service controls |

### Owen — direct Modbus equipment

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Owen | [TRM-138](https://owen.ru/product/trm138) | Direct Modbus | 8 temperature sensors | Current implementation reads the eight configured measurement channels |
| Owen | [ПЛК110-24.60.К-М](https://files.owen.ru/catalog/product.php?cat=plc&prod=plk110_m02&sub=programmiruemie_logicheskie_kontrolleri) | Direct Modbus | 36 binary inputs and 24 output switches | User-defined CODESYS Modbus bit layout; configurable DI area, base/stride, and DO base/stride |

## Equipment examples

The photographs below are local, optimized copies from official manufacturer product pages. They illustrate representative architecture and DPLS equipment rather than every supported variant.

<p align="center">
  <img src="pictures/equipment/s2000_pp.png" alt="С2000-ПП" width="30%">
  <img src="pictures/equipment/s2000_kdl.png" alt="С2000-КДЛ" width="30%">
  <img src="pictures/equipment/s2000r_arr125.png" alt="С2000Р-АРР125" width="30%">
</p>
<p align="center">
  <img src="pictures/equipment/s2000_sp4.png" alt="С2000-СП4" width="38%">
  <img src="pictures/equipment/s2000_dz.png" alt="С2000-ДЗ" width="38%">
</p>

## Mapping modes for С2000-ПП equipment

### Manual mapping

The user selects the equipment model and supplies the relevant configured С2000-ПП table rows. The equipment class validates exact object kind, local object number, zone type, and required capability combinations.

### Configuration-assisted mapping

The integration reads the configured С2000-ПП zone and relay tables, filters them through the selected equipment's exact capability definitions, and validates the result. The user still selects the physical model.

This is **not hardware discovery**: the configuration tables do not provide a reliable physical model identifier for every downstream object.

Configuration tables are cached and are not read during every normal polling cycle.

## Configuration

1. In Home Assistant, open **Settings → Devices & services**.
2. Select **Add integration** and search for **Modbus Devices**.
3. Choose Modbus TCP, UDP, or serial transport.
4. Select the canonical manufacturer and physical equipment model.
5. Enter the network or serial connection settings and Modbus unit ID.
6. Complete model-specific configuration when requested.

For Bolid downstream equipment, select or create the С2000-ПП gateway context, then provide:

- the С2000-КДЛ Orion address;
- the device DPLS address or base address, when applicable;
- a supported hardware/model variant or topology, when applicable;
- manual or configuration-assisted mapping.

The UI presents physical model names and capability choices; internal class names, object kinds, register addresses, and derived local numbers are not normal user inputs.

## Installation

This repository must currently be installed as a **HACS custom repository** or manually. It is not documented as part of the HACS Default repository list.

### HACS custom repository

1. Open HACS and its custom repositories dialog.
2. Add `https://github.com/dk-1983/Modbus_Devices` with category **Integration**.
3. Find and install **Modbus Devices**.
4. Restart Home Assistant.
5. Add the integration from **Settings → Devices & services**.

See the [project releases](https://github.com/dk-1983/Modbus_Devices/releases) for published packages and version history.

### Manual installation

Copy:

```text
custom_components/modbus_devices
```

to:

```text
/config/custom_components/modbus_devices
```

Restart Home Assistant, then add **Modbus Devices** from **Settings → Devices & services**.

## Limitations and boundaries

- Configuration-assisted mapping is a lookup of configured С2000-ПП rows, not hardware discovery.
- Gateway visibility determines what Home Assistant can expose; a physical device capability may exist without a documented Modbus path.
- Serial number, firmware, hardware revision, protocol information, radio identifier, RSSI, voltage, and other service values are exposed only when the current transport actually provides them.
- Radio numeric values are implemented only when current С2000-ПП documentation confirms their transport path.
- Device variants are not assumed compatible merely because their names or enclosures are similar.
- New equipment models are added after checking current official manuals, protocol descriptions, register maps, and compatibility information.

## Development

Equipment implementations live in `custom_components/modbus_devices/equipment/<manufacturer>.py`.

```text
equipment class
  → model capabilities and variants
    → direct I/O or gateway mappings
      → entity descriptions and snapshots
        → focused and regression tests
```

One physical model is normally represented by one equipment class. Small reusable bases provide common protocol mechanics without merging distinct physical devices. Changes should preserve persisted Config Entries, stable device identifiers, entity unique IDs, and existing mapping serialization whenever possible.

## Validation and quality

Project changes are checked with:

- pytest, including focused equipment and regression coverage;
- Home Assistant Hassfest integration validation;
- Ruff correctness checks;
- Python bytecode compilation and Git whitespace checks.

No fixed test count is documented because the suite grows with supported equipment.

## Project links

- [Source repository](https://github.com/dk-1983/Modbus_Devices)
- [Issues](https://github.com/dk-1983/Modbus_Devices/issues)
- [Releases](https://github.com/dk-1983/Modbus_Devices/releases)
- [Bolid](https://bolid.ru/)
- [Owen](https://owen.ru/)
- [License](LICENSE.md)

## Author

[Dmitry Krivolap](https://4vrs.online)
