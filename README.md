# Modbus Devices for Home Assistant

**[English](README.md) | [Русский](README_RU.md)**

Modbus Devices is a custom Home Assistant integration for explicitly supported industrial and building-automation equipment. Each equipment model defines its own Modbus-visible capabilities, entities, validation rules, and, where required, gateway mapping.

The integration is a local-polling hub for Modbus-compatible equipment from multiple manufacturers, using direct connections or supported gateway/topology mappings. The canonical registry currently contains Bolid, Dyna Drive, and Owen equipment.

## Key features

- Modbus TCP/IP, native Modbus UDP/IP, serial Modbus, and Modbus RTU over UDP connections.
- Equipment-driven creation of sensor, binary sensor, switch, datetime, and button entities.
- Typed equipment variants and topology-dependent capabilities.
- С2000-ПП gateway support for Orion, С2000-КДЛ, and downstream DPLS equipment.
- Manual and configuration-assisted gateway mapping.
- Authoritative multistate Orion values with primary, expanded, and raw state codes.
- Documented numeric measurements, including temperature and humidity where the С2000-ПП path supports them.
- Relay/output control with validated writes, optimistic synchronization, and protection from stale poll results.
- Explicit communication and malformed-response error handling: failures are not reported as normal or off states.
- Centralized coordinator polling, grouped reads where possible, serialized requests per client, and strict common response validation.
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
| Modbus TCP/IP | Host, port, and Modbus unit ID |
| Modbus UDP/IP | Host, port, and Modbus unit ID |
| Serial Modbus RTU | Serial port, baud rate, byte size, parity, stop bits, and unit ID |
| Modbus RTU over UDP | Remote host/port, fixed local UDP port, timeout, optional local bind address, and downstream device ID |

Native Modbus UDP/IP and Modbus RTU over UDP are different wire protocols. Native UDP carries Modbus application framing over UDP. RTU over UDP carries a raw Modbus RTU ADU, including its CRC, inside a UDP datagram and does not use an MBAP header.

Transport support still depends on the selected equipment and its physical interface.

## Supported equipment

The canonical registry in the current source tree contains **30 models: Bolid 27, Dyna Drive 1, and Owen 2**. Model names below are user-facing manufacturer names, not Python class keys.

### Bolid — direct Modbus and С2000-ПП gateway

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Bolid | [M3000-BB-1020](https://bolid.ru/production/disp/inout-modules/m3000_vv_1020.html) | Direct Modbus | 12 binary inputs, 6 relay switches, device clock | Runtime service information is read from the device |
| Bolid | [С2000-ПП](https://bolid.ru/production/s2000-pp.html) | Direct Modbus | Gateway diagnostic binary sensors | Orion master mode/communication, enclosure tamper, and power fault; device service information where exposed |
| Bolid | С2000-КПБ | С2000-ПП → Orion | Configured output switches and multistate sensors | Up to 6 outputs/circuit states, 2 technological inputs, and device state; entities follow the configured subset |
| Bolid | С2000-2 | С2000-ПП → Orion | Read-only device and configured input/access states | Direct Orion model; no door-control commands are published |
| Bolid | С2000-4 | С2000-ПП → Orion | Read-only device state and up to four configured input states | Relay control is intentionally not published |
| Bolid | Сигнал-20М | С2000-ПП → Orion | Read-only device state and up to 20 configured input states | This class does not cover Сигнал-20П, Сигнал-20П исп.01, or Сигнал-20 сер.04 |
| Bolid | С2000-БКИ | С2000-ПП → Orion | Read-only diagnostic state of the unit itself | External partitions/indicators are not duplicated; С2000-БКИ 2RS485 is not covered by this class |
| Bolid | [МИП-24 исп.20](https://bolid.ru/production/mip-24_20.html) | С2000-ПП / Orion RS-485 | Device, output power, output load, battery, charger, and mains multistate sensors | Full designation МИП-24-2/П5-Р-RS; device state is required and the other five states follow the configured mapping subset; physical numeric measurements are not exposed because their current С2000-ПП Modbus path is not confirmed |

### Bolid — С2000-КДЛ and wired DPLS equipment

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Bolid | [С2000-КДЛ](https://bolid.ru/production/s2000-kdl.html) | С2000-ПП → Orion | Multistate diagnostic sensor | Only the controller-owned type-3/local-0 state; downstream rows remain separate devices |
| Bolid | ДИП-34А-05 | С2000-ПП → С2000-КДЛ → DPLS | Operational multistate detector state | One DPLS address; no synthetic smoke/dust sensors |
| Bolid | С2000-ИП-03 | С2000-ПП → С2000-КДЛ → DPLS | Multistate detector state; optional temperature sensor | Type-1 state-only or type-6 state-and-temperature mapping; both modes use one DPLS identity |
| Bolid | [С2000-ДЗ](https://bolid.ru/production/s_2000_dz.html) | С2000-ПП → С2000-КДЛ → DPLS | Multistate water-leak state | Static variants 1.06, 1.10, and 1.13; no derived moisture binary sensor |
| Bolid | [С2000-СТ исп.04](https://bolid.ru/production/s2_st_04.html) | С2000-ПП → С2000-КДЛ → DPLS | Operational glass-break multistate state | Wired one-address DPLS detector; DPLS service voltage is not exposed as a numeric entity through the current С2000-ПП path |
| Bolid | [С2000-СМК](https://bolid.ru/production/amrs/addr-amrs-detection-hdw/) | С2000-ПП → С2000-КДЛ → DPLS | Opening multistate state | Wired one-address model; discontinued by the manufacturer but documented and supported by the integration |
| Bolid | С2000-ВТ / С2000-ВТ исп.01 | С2000-ПП → С2000-КДЛ → DPLS | Temperature and relative-humidity sensors | Numeric values use the documented С2000-ПП numeric request lifecycle |
| Bolid | С2000-ВТИ / С2000-ВТИ исп.01 | С2000-ПП → С2000-КДЛ → DPLS | No currently available entities through this path | Models are registered, but numeric transport through the current С2000-ПП path is not confirmed and configuration is blocked |
| Bolid | [С2000-СП4/24(220)](https://bolid.ru/production/s2000-sp4.html) | С2000-ПП → С2000-КДЛ → DPLS | Configured actuator switch and multistate position/circuit sensors | Supported variants are listed below; entities follow the configured mapping subset |
| Bolid | С2000-СП2 | С2000-ПП → С2000-КДЛ → DPLS | Read-only relay-state representation | One- or two-output topology; no control entities. This class does not claim исп.02 or исп.03 |
| Bolid | СВК15-3-2-Б | С2000-ПП → С2000-КДЛ → DPLS | Water-meter state/count data exposed by the implemented mapping | Exact registered model only |
| Bolid | СВК15-3-8-1-Б3 | С2000-ПП → С2000-КДЛ → DPLS | Water-meter state/count data exposed by the implemented mapping | Exact registered model only |

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
| Bolid | [С2000Р-СТ исп.01](https://bolid.ru/production/s2000r-st_01.html) | С2000-ПП → С2000-КДЛ → DPLS via С2000Р-АРР125 | Operational glass-break multistate state | Battery, tamper, and radio communication remain Orion multistate semantics; no RSSI entity |
| Bolid | [С2000Р-СМК](https://bolid.ru/production/s2000r_smk.html) | С2000-ПП → С2000-КДЛ → DPLS via С2000Р-АРР125 | Opening multistate state; optional External input multistate state | Uses one or two DPLS addresses according to the configured topology; no derived opening binary sensor |

### Owen — direct Modbus equipment

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Owen | [TRM-138](https://owen.ru/product/trm138) | Direct Modbus | 8 temperature sensors | Current implementation reads the eight configured measurement channels |
| Owen | [ПЛК110-24.60.К-М](https://files.owen.ru/catalog/product.php?cat=plc&prod=plk110_m02&sub=programmiruemie_logicheskie_kontrolleri) | Direct Modbus | 36 binary inputs and 24 output switches | User-defined CODESYS Modbus bit layout; configurable DI area, base/stride, and DO base/stride |

### Dyna Drive — direct Modbus equipment

| Manufacturer | Model | Connection / gateway | Home Assistant entities / capabilities | Notes |
|---|---|---|---|---|
| Dyna Drive | DN310 | Direct Modbus | Read-only runtime diagnostics, authoritative running state, fault decoding, and command buttons | Commands: Forward run, Reverse run, Coast stop, Decelerate stop, and Fault reset. Writable frequency setpoint and jog are not implemented; the integration does not automatically modify persistent drive parameters |

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
3. Choose Modbus TCP/IP, Modbus UDP/IP, serial Modbus, or Modbus RTU over UDP.
4. Select the canonical manufacturer and physical equipment model.
5. Enter the network or serial connection settings and Modbus unit ID.
6. Complete model-specific configuration when requested.

For Bolid downstream equipment, select or create the С2000-ПП gateway context, then provide:

- the С2000-КДЛ Orion address;
- the device DPLS address or base address, when applicable;
- a supported hardware/model variant or topology, when applicable;
- manual or configuration-assisted mapping.

The UI presents physical model names and capability choices; internal class names, object kinds, register addresses, and derived local numbers are not normal user inputs.

## Adding a device

These screenshots show a real Home Assistant Config Flow. Start from **Settings → Devices & services → Modbus Devices**, then select **Add hub**.

### 1. Select the transport

Choose ModBus TCP/IP, ModBus UDP/IP, SerialPort, or Modbus RTU over UDP according to the device connection. The screenshot predates the RTU-over-UDP option; use the current UI labels.

<p align="center"><img src="pictures/config-flow/MD_menu_step1.jpg" alt="Modbus Devices transport selection" width="78%"></p>

### 2. Select the manufacturer

Choose the canonical manufacturer: Bolid, Dyna Drive, or Owen. The screenshot predates Dyna Drive; use the current registry shown in the UI.

<p align="center"><img src="pictures/config-flow/MD_menu_step2.jpg" alt="Modbus Devices manufacturer selection" width="78%"></p>

### 3. Select the equipment model

Choose the physical model by its manufacturer-facing display name. This list is built from the supported equipment registry.

<p align="center"><img src="pictures/config-flow/MD_menu_step3.jpg" alt="Modbus Devices equipment model selection" width="78%"></p>

### 4. Configure the connection

Enter the transport and device settings. The TCP/IP example below uses host, port, device ID, and name.

<p align="center"><img src="pictures/config-flow/MD_menu_step4.jpg" alt="Modbus Devices TCP/IP connection settings" width="78%"></p>

Further steps depend on the selected model and its transport or gateway. Bolid equipment behind С2000-ПП may additionally request gateway selection, Orion/KDL/DPLS addresses, topology, mapping source, and manual or configuration-assisted mapping.

Config Flow is localized in English and Russian. YAML configuration is not supported.

### 5. Result

After successful setup, Home Assistant creates one Device and the entities supported by its equipment class. This example shows an M3000-BB-1020 with its device information, controls, and sensors; other models create their own documented entity sets.

<p align="center"><img src="pictures/config-flow/MD_menu_result.jpg" alt="M3000-BB-1020 Home Assistant Device and generated entities" width="92%"></p>

## Modbus RTU over UDP

This production transport supports FC01, FC02, FC03, FC04, FC05, FC06, and FC16. It uses one persistent UDP socket, a fixed local UDP port, split-datagram accumulation, timeout handling, CRC validation, and source/slave/function validation. Requests pass through the same per-client serialization layer as the other transports.

Example (use values from your gateway configuration):

```text
Transport: Modbus RTU over UDP
Remote host: 192.0.2.10
Remote UDP port: 40000
Local UDP port: 40000
Timeout: 3 seconds
Local bind address: 0.0.0.0 (optional)
Downstream device ID: 1
```

For a gateway with a static UDP peer, the local UDP port must match the destination peer port configured in the gateway. С2000-Ethernet can be used as a prospective transport gateway in Transparent mode, with compatibility set to “Other devices” and a suitable UDP peer configuration. It is not an equipment class: the Home Assistant Device represents the downstream Modbus equipment.

RTU-over-UDP is implemented and covered by automated tests. Live packet capture has verified correct transmission of a raw RTU frame. End-to-end response validation through С2000-Ethernet is still pending confirmation of the gateway configuration; full hardware compatibility is therefore not yet claimed.

## Troubleshooting

- **Cannot connect:** verify host/port or serial device availability, firewall/routing, and that the selected transport matches the gateway protocol.
- **Wrong device ID:** use the downstream Modbus slave/unit ID, not an unrelated gateway address.
- **UDP mismatch:** native Modbus UDP/IP is not raw RTU over UDP; select the mode matching the actual framing.
- **RTU-over-UDP static peer:** make the configured gateway destination port equal to the integration's local UDP port and verify the optional bind address belongs to the Home Assistant host.
- **Serial connection:** verify baud rate, byte size, parity, stop bits, wiring, and slave ID.
- **Entity unavailable after a response:** a timeout, malformed frame, wrong source/slave/function, CRC error, or invalid payload is rejected deliberately. Fix the transport/device configuration; do not disable validation.

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
- DN310 writable frequency setpoint is not implemented.
- Some Bolid relay controls are intentionally read-only where ownership or tactic safety cannot be established.
- С2000-Ethernet RTU-over-UDP receive/end-to-end validation is still pending.
- New equipment models are added after checking current official manuals, protocol descriptions, register maps, and compatibility information.

Modbus Devices exposes write controls only where command semantics are explicitly implemented. Physical relay presence alone does not make an output writable in Home Assistant.

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

The runtime uses typed `entry.runtime_data`, coordinator-owned polling, grouped reads where supported, a `SerializedModbusClient` per connection, common strict Modbus response validation, and explicit manufacturer/equipment registries.

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
- [Dyna Drive](https://www.dninno.com/)
- [Owen](https://owen.ru/)
- [License](LICENSE.md)

## Author

[Dmitry Krivolap](https://4vrs.online)
