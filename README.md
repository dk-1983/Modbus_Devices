<p align="center">
  <img src="pictures/modbus_devices_logo.png" alt="Modbus Devices" width="100%">
</p>

# Modbus Devices for Home Assistant

[English](README.md) | [Русский](README_RU.md)

Modbus Devices is a local Home Assistant integration for explicitly supported industrial and building-automation equipment. Each physical instrument becomes one Home Assistant device with useful entities, validated communication, and model-specific behavior.

## Key features

- Modbus TCP/IP, native Modbus UDP/IP, serial Modbus RTU, and Modbus RTU over UDP.
- Explicit equipment models from Bolid, Owen, Zuked, and Dyna Drive.
- Direct Modbus devices and equipment connected through supported gateways.
- Bolid S2000-PP, Orion, KDL, DPLS, and S2000R-ARR topologies.
- Model-appropriate sensors, binary sensors, switches, and buttons.
- Strict response validation and grouped/coordinated polling where appropriate.
- Safe explicit write controls only for equipment with a supported command contract.
- UI-only setup, English/Russian localization, and an optional native card generator.

## Supported transports

| Transport | Typical use |
|---|---|
| Modbus TCP/IP | Native Modbus TCP equipment and gateways |
| Modbus UDP/IP | Native Modbus messages over UDP |
| Serial Modbus RTU | Direct RS-485/serial connections |
| Modbus RTU over UDP | Complete RTU frames carried inside UDP datagrams |

Native Modbus UDP and RTU-over-UDP use different wire formats. Select the transport that matches the equipment or gateway.

## Supported equipment

Support is model-specific; a listed manufacturer does not imply support for every product or variant.

### Bolid — direct and Orion equipment

| Model | Connection | Main capabilities |
|---|---|---|
| M3000-BB-1020 | Direct Modbus | Binary inputs, relay outputs, device time, and diagnostics |
| S2000-PP | Direct Modbus gateway | Gateway state and downstream equipment mapping |
| S2000-KPB | S2000-PP / Orion | Configured output and circuit states with supported control |
| S2000-2 | S2000-PP / Orion | Device, input, and access states |
| S2000-4 | S2000-PP / Orion | Device and configured input states |
| Signal-20M | S2000-PP / Orion | Device and configured input states |
| S2000-BKI | S2000-PP / Orion | Device diagnostic state |
| MIP-24 isp.20 | S2000-PP / Orion | Power-system multistate diagnostics |

### Bolid — wired KDL/DPLS equipment through S2000-PP

| Model | Connection | Main capabilities |
|---|---|---|
| S2000-KDL | S2000-PP / Orion | Controller state and DPLS topology |
| DIP-34A-05 | S2000-PP / DPLS | Smoke-detector state and dynamic status |
| S2000-IP-03 | S2000-PP / DPLS | Heat-detector state and supported measurements |
| S2000-DZ | S2000-PP / DPLS | Smoke-zone state and diagnostics |
| S2000-ST isp.04 | S2000-PP / DPLS | Glass-break state, alarm, tamper, and fault diagnostics |
| S2000-SMK isp.04 | S2000-PP / DPLS | Opening state and intrusion indication |
| S2000-VT | S2000-PP / DPLS | Temperature measurement and state |
| S2000-VTI | S2000-PP / DPLS | Temperature, humidity, and state |
| S2000-SP4/24(220) | S2000-PP / DPLS | Actuator state and supported control |
| S2000-SP2 | S2000-PP / DPLS | Read-only relay/output state |
| SVK15-3-2-B | S2000-PP / DPLS | Water-meter state and supported count data |
| SVK15-3-8-1-B3 | S2000-PP / DPLS | Water-meter state; automatic counter polling is safety-disabled |

### Bolid — radio equipment represented through KDL/DPLS

| Model | Connection | Main capabilities |
|---|---|---|
| S2000R-ARR125 | S2000-PP / KDL | Radio-controller state |
| S2000R-DIP | S2000-PP / ARR/KDL | Smoke state, enclosure tamper, main/reserve battery diagnostics |
| S2000R-IP | S2000-PP / ARR/KDL | Heat state, tamper, main/reserve batteries, measurement fault |
| S2000R-RM | S2000-PP / ARR/KDL | Relay/output state and supported control |
| S2000R-Sirena | S2000-PP / ARR/KDL | Sounder state and diagnostics |
| S2000R-ST isp.01 | S2000-PP / ARR/KDL | Glass-break state/alarm, tamper, and battery diagnostics |
| S2000R-SMK | S2000-PP / ARR/KDL | Contact state/alarm, tamper, battery, and external-input state |
| S2000R-DZ | S2000-PP / ARR/KDL | Smoke-zone state and diagnostics |
| S2000R-VTI | S2000-PP / ARR/KDL | Temperature, humidity, and diagnostics |

Some documented Bolid events require matching ARR/KDL/S2000M/PProg/S2000-PP configuration and retransmission. If an entity does not change, first verify that the event is configured to reach S2000-PP; this alone does not prove a device or integration defect.

### Owen

| Model | Connection | Main capabilities |
|---|---|---|
| PLC110-24.60.K-M | Direct Modbus | User-mapped binary inputs and output switches |
| TRM-138 | Direct Modbus | Eight-channel temperature monitoring and diagnostics |

### Zuked

| Model | Connection | Main capabilities |
|---|---|---|
| 310-4.0S1 | Direct Modbus | Read-only AC-drive runtime monitoring and fault diagnostics |

### Dyna Drive

| Model | Connection | Main capabilities |
|---|---|---|
| DN310 | Direct Modbus | Experimental drive monitoring, diagnostics, and explicit command buttons |

## Installation

### HACS (recommended)

Modbus Devices is available in the default HACS integration catalog:

1. Open **HACS → Integrations**.
2. Search for **Modbus Devices**.
3. Install it and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Modbus Devices**.

### Manual installation

Copy `custom_components/modbus_devices` into the `custom_components` directory of your Home Assistant configuration, restart Home Assistant, and add **Modbus Devices** from **Devices & services**.

## Adding equipment

Configuration is performed entirely in the Home Assistant UI.

### Option 1 — Direct Modbus device

1. Add **Modbus Devices** and choose **Add a new hub**.
2. Select TCP, UDP, serial RTU, or RTU over UDP.
3. Select the manufacturer and exact model.
4. Enter the host/port or serial settings and Modbus unit ID.
5. Finish setup; one Home Assistant device is created for the physical instrument.

<p align="center"><img src="pictures/config-flow/MD_menu_step1.jpg" alt="Choose a Modbus transport" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_step2.jpg" alt="Choose a manufacturer" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_step3.jpg" alt="Choose an equipment model" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_step4.jpg" alt="Enter direct connection settings" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_result.jpg" alt="Created direct Home Assistant device" width="92%"></p>

### Option 2 — Equipment via an existing S2000-PP

Add and verify the S2000-PP gateway first. Then add **Modbus Devices** again and choose **Via existing S2000-PP**.

1. Select the correct S2000-PP gateway.
2. Select the downstream physical model.
3. Enter the KDL Orion address and the device's DPLS base address.
4. Use configuration-assisted mapping when available, or select the PP row manually.
5. Repeat the flow for each additional physical device.

Configuration-assisted mapping reads the selected S2000-PP configuration table and offers compatible unused rows. It does not identify the physical model automatically, so always select the actual model first. If no single compatible mapping is found, manual mapping lets you enter the known zone/relay table row and required capability details; the integration still validates them against the chosen model.

<p align="center"><img src="pictures/config-flow/MD_menu_step1_gateway.jpg" alt="Choose Via existing S2000-PP" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_step3_gateway_select.jpg" alt="Choose an S2000-PP gateway" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_step4_gateway_equipment.jpg" alt="Choose downstream Bolid equipment" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_step5_gateway_identity.jpg" alt="Enter Orion and DPLS identity" width="78%"></p>

<p align="center"><img src="pictures/config-flow/MD_menu_step6_gateway_manual_mapping.jpg" alt="Map S2000-PP capabilities manually" width="78%"></p>

The Orion and DPLS addresses identify the physical device; the PP row is its current gateway projection. One physical instrument is represented by one Home Assistant device, even when it provides several entities.

<p align="center"><img src="pictures/config-flow/MD_device_s2000_vt.jpg" alt="Created downstream Home Assistant device" width="92%"></p>

## Optional device-card generator

1. Edit a dashboard and choose **Add card**.
2. Select **Modbus Device**.
3. Choose the physical device.
4. Review the generated entities and save the card.

<p align="center"><img src="pictures/custom_card/add_card.jpg" alt="Add a dashboard card" width="88%"></p>

<p align="center"><img src="pictures/custom_card/select_modbus_device.png" alt="Choose Modbus Device" width="88%"></p>

<p align="center"><img src="pictures/custom_card/entities_preview.jpg" alt="Review the generated native Entities card" width="88%"></p>

<p align="center"><img src="pictures/custom_card/dashboard_result.jpg" alt="Saved native Entities card" width="88%"></p>

After saving, the result is a standard native Home Assistant `type: entities` card. There is no permanent Modbus Devices runtime wrapper, and the card can be edited normally afterward.

## Architecture

```text
Manufacturer → Equipment model → Transport or gateway → Coordinator
                                                       → HA Device and entities
```

```text
Home Assistant ← Modbus ← S2000-PP ← Orion ← S2000-KDL ← DPLS device
                                                   ↖ S2000R-ARR radio infrastructure
```

## Modbus RTU over UDP

RTU-over-UDP carries complete Modbus RTU frames, including address and CRC, inside UDP datagrams. It is not native Modbus UDP. Configure the gateway host, UDP port, unit ID, and response timeout; fixed-peer gateways may also require Home Assistant to originate traffic from the expected endpoint.

## Troubleshooting

- Verify host, port, unit ID, and serial parameters against the equipment configuration.
- Confirm that the selected transport matches the gateway; native UDP and RTU-over-UDP are not interchangeable.
- For S2000-PP equipment, verify the model, Orion/DPLS addresses, PP mapping, and Bolid-side event retransmission.
- A timeout, Modbus exception, or malformed response makes affected entities unavailable rather than falsely normal.
- Ensure another application is not holding an exclusive serial port.

## Limitations and boundaries

- Support and entity sets are defined per exact model; similar variants are not assumed compatible.
- A physical feature is exposed only when a truthful path exists through the supported Modbus topology.
- Runtime firmware, serial, radio address, RSSI, and similar metadata are shown only when actually readable.
- Write controls exist only for explicitly supported commands; some equipment is intentionally read-only.
- Zuked 310-4.0S1 provides monitoring only, without motor-control or configuration writes.
- Dyna Drive DN310 remains experimental; verify its profile against the target hardware.

## Development and deep documentation

Equipment implementations are manufacturer- and model-specific. Validation uses focused and regression pytest coverage, Ruff, Hassfest, compilation, and whitespace checks. Detailed protocol decisions, hardware evidence, and device-family audits are in [`docs/`](docs/).

## Project links

- [GitHub repository](https://github.com/dk-1983/Modbus_Devices)
- [Issues](https://github.com/dk-1983/Modbus_Devices/issues)
- [Releases](https://github.com/dk-1983/Modbus_Devices/releases)
- [License](LICENSE.md)
- [Bolid](https://bolid.ru/)
- [Dyna Drive](https://www.dninno.com/)
- [Owen](https://owen.ru/)

## Author

[Dmitry Krivolap](https://4vrs.online)
