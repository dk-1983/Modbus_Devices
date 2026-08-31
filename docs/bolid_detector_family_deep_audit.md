# Bolid detector family deep audit

## 1. Executive Summary

This report is a research/forensic audit of four distinct Bolid products:

- `DIP34A05` — **ДИП-34А-05**, wired optical smoke detector;
- `C2000RDIP` — **С2000Р-ДИП**, radio optical smoke detector;
- `C2000RST01` — **С2000Р-СТ исп.01**, radio glass-break detector;
- `C2000ST04` — **С2000-СТ исп.04**, wired DPLS glass-break detector.

The evidence does **not** support treating the radio products as aliases of their
wired analogues. The radio detector is a physical device behind a separate
`С2000Р-АРР32/125` radio controller; the controller projects the radio unit into a
DPLS address, the KDL reports that address as an Orion input, and `С2000-ПП`
projects the configured input into one Modbus zone row.

The current implementations are **partially modern**. They already use one HA
Device per configured DPLS identity, exact zone mappings, grouped primary plus
expanded reads, stable entity keys, lossless unknown-code decoding, generic
Config Flow ownership checks, and the shared DeviceInfo path. They are not the
old direct-register classes implied by the original minimal feature set.

The main deficiency is semantic, not transport-level:

- **CURRENT CODE BEHAVIOR:** each detector exposes only one multistate sensor
  (`detector_state` or `glass_break_state`). Battery, tamper, communication and
  maintenance codes can be visible only inside that entity's
  `expanded_codes`/`expanded_states` attributes.
- **DOCUMENTED FACT:** the radio detectors and ARR controller know substantially
  more: battery state, case state and radio supervision; ARR configuration tools
  also show radio address, serial number, firmware/hardware versions and signal
  level/statistics.
- **DOCUMENTED FACT:** the public `С2000-ПП` Modbus contract exposes configured
  zone state and expanded zone state, but does not document registers for ARR
  inventory, radio address, RSSI/LQI, channel, route, radio-unit serial number or
  radio-unit firmware.
- **INFERENCE:** missing HA RSSI/identity entities are therefore not explained by
  the detector class hierarchy. Those values are on the ARR configuration plane,
  not the currently implemented `С2000-ПП` zone-state plane.
- **NEEDS HARDWARE VERIFICATION:** which battery/tamper/link codes are actually
  retained in the expanded state block for each product and PP firmware, and
  whether alarm and diagnostic conditions coexist without loss.

Recommended classifications:

| Model | Classification | Reason |
|---|---|---|
| ДИП-34А-05 | **SMALL FIX** | Physical topology is correct; firmware/input-type metadata and semantic entities/tests need correction. |
| С2000Р-ДИП | **REFACTOR** | One-row physical identity is plausible, but radio diagnostic states need model-specific aggregation/entities after hardware validation. |
| С2000Р-СТ исп.01 | **REFACTOR** | Same radio-plane limitation; one-battery and tamper/link semantics must be separated from the alarm state. |
| С2000-СТ исп.04 | **SMALL FIX** | Physical model is correct; authoritative state semantics, firmware tests and presentation are incomplete. |

No runtime source was changed by this audit.

## 2. Audit Baseline

**CURRENT CODE BEHAVIOR — recorded before research:**

- working directory: `C:\project\MD\Modbus_Devices`;
- branch: `master`, 18 commits ahead of `origin/master`;
- HEAD: `86da5fc785b7fa6dc18e9c9cf77d020cc7e5fc53` —
  `Disable unsafe automatic SVK counter polling`;
- integration version: `0.6.0` from
  `custom_components/modbus_devices/manifest.json`;
- development host exposes Windows Python 3.9, 3.11, 3.12, 3.13 and 3.14;
- Home Assistant Core development environment: `/workspaces/core` (runtime/test
  environment, not Git source of truth).

The baseline was not clean because of four pre-existing, user-owned branding
files. They are outside this audit and were not modified:

- `M custom_components/modbus_devices/brand/icon.png`
- `M custom_components/modbus_devices/brand/icon@2x.png`
- `?? custom_components/modbus_devices/brand/icon@2x_old.png`
- `?? pictures/modbus_devices_logo.png`

Recent history inspected includes `2eaee95` (`feat: add Bolid DPLS fire detector
family`) and `6031368` (`feat: add Bolid glass-break and magnetic contact
detectors`). These commits introduced the shared exact-zone base and then reused
it for the glass-break family. Their commit messages explicitly chose exact
mapping, lossless states and non-exposure of unsupported radio service data.

## 3. Official Documentation Sources

Only primary Bolid material is used for protocol and product facts below.

### 3.1 С2000Р-ДИП

- [Product page](https://bolid.ru/production/s2000r_dip.html).
- [Full operation manual](https://bolid.ru/files/373/566/s2000r_dip_rept_jan_2026.pdf),
  **АЦДР.425232.008 РЭп, Изм.6 от 23.12.2025**. Relevant parts: §1.1
  purpose and transmitted values; table 1.1 batteries/radio characteristics;
  §1.4 modes and dust/fault behavior; §2.2.4 power/radio enrollment; §3.4
  functional/link tests; §10 released versions.

### 3.2 ДИП-34А-05

- [Product page](https://bolid.ru/production/dip-34a-05.html).
- [Full operation manual](https://bolid.ru/files/373/566/dip_34a_05_rep_jan_2026.pdf),
  **АЦДР.425232.002-05 РЭп, Изм.9 от 26.01.2026**. Relevant parts: §1.1;
  §1.4.6 operating modes; configuration/functional-test sections; §10 firmware
  and KDL/input-type compatibility.

### 3.3 С2000Р-СТ исп.01

- [Product page](https://bolid.ru/production/s2000r-st_01.html), including
  characteristics and firmware table.
- [Operation manual](https://shop.bolid.ru/files/net_shop_files/2162031567.pdf),
  **АЦДР.425132.003-01 РЭп, Изм.3 от 16.09.2024**. The official shop PDF was
  identifiable but not machine-readable through the documentation fetcher;
  conclusions requiring exact manual wording remain marked for verification.
- [С2000Р-АРР125 manual](https://bolid.ru/files/373/566/s2000r_arr125_rep_fev_2026.pdf),
  **АЦДР.426461.016 РЭп, Изм.11 от 02.02.2026**, especially tables 1.4.1-1
  and 1.4.2-1, §2.3.3.2 inventory fields, §2.3.3.9.6 test control, and the
  permitted KDL input-type table.

### 3.4 С2000-СТ исп.04

- [Product page](https://bolid.ru/production/s2_st_04.html).
- [Operation manual](https://bolid.ru/files/373/566/s2000_st_04_ret_mar_25.pdf),
  **АЦДР.425132.001-04 РЭ, 2025**. Relevant parts: purpose/functions,
  setup/self-test/anti-masking, and §10 firmware history. Version 1.22 dated
  02.2025 fixes unstable operation with `С2000-КДЛ-2И`.

### 3.5 Common transport and topology documents

- [С2000-ПП v3.01 operation manual](https://bolid.ru/files/373/566/s2_pp_rep_v3_01_jule_2026.pdf),
  **АЦДР.426469.020 РЭп, Изм.18 от 29.05.2026**. §1.1.5 documents the
  simplified Modbus map, zone rows and primary/expanded state access. The manual
  states that 3.xx preserves the 1.32/2.01 Modbus formats.
- [С2000-ПП v1.31 operation manual](https://bolid.ru/files/373/566/s2000_pp_re_v.1.31_apr_18.pdf),
  **АЦДР.426469.020 РЭп, Изм.1 от 06.02.2018**. Tables 4–6 give the
  compound request/state/event formats and event-code table.
- [С2000-ПП product/firmware page](https://bolid.ru/production/s2000-pp.html).
  It records the 2.01 fixes for compound requests and stale zone/ADC results,
  and the 3.01 change to zone-state formation.
- [С2000Р-АРР32 manual, Изм.7](https://bolid.ru/files/373/566/s2000r_arr32_rep_may_25.pdf),
  **АЦДР.426461.009 РЭп, Изм.7 от 21.04.2025**.
- [С2000Р-АРР32 archived product page](https://bolid.ru/production/archive/s2000r_arr32.html).
- [С2000-КДЛ product page](https://bolid.ru/production/s2000-kdl.html) and the
  [official compatibility table](https://bolid.ru/files/373/566/tabl_sovm_jun_23.pdf).

### 3.6 Document contradictions and limits

- **DOCUMENTED FACT:** the current DIP manual's newest released firmware is
  1.22, while current code declares `documented_target_firmware = "1.24"`.
  No official source found in this pass supports DIP firmware 1.24.
- **DOCUMENTED FACT:** the S2000R-ST product page shows firmware 1.03 for both
  the 2022 repeater-support change and the 2025 radio-group change, while also
  marking 1.02 recommended. That page is internally ambiguous; do not infer a
  monotonic protocol contract from it.
- **DOCUMENTED FACT:** ARR configuration software displays detector inventory
  and signal details. **NOT DOCUMENTED:** an S2000-PP Modbus register that
  exposes those ARR configuration fields.
- Exact Orion event-to-state-code applicability is controller/KDL/PP firmware
  dependent. The generic PP event table establishes code names, not that every
  listed code is emitted and retained for every detector model.

## 4. Current Implementation Map

| Physical model | Registry class | Direct base | Required mapped row | Runtime entity |
|---|---|---|---|---|
| ДИП-34А-05 | `DIP34A05` | `BolidDPLSDetectorBase` | base DPLS, PP zone type 1 | `sensor.detector_state` |
| С2000Р-ДИП | `C2000RDIP` | `BolidDPLSDetectorBase` | base DPLS, PP zone type 1 | `sensor.detector_state` |
| С2000Р-СТ исп.01 | `C2000RST01` | `BolidDPLSDetectorBase` | base DPLS, PP zone type 1 | `sensor.glass_break_state` |
| С2000-СТ исп.04 | `C2000ST04` | `BolidDPLSDetectorBase` | base DPLS, PP zone type 1 | `sensor.glass_break_state` |

`C2000DIP` is a load-time legacy alias for `DIP34A05`; it is not a separately
selectable model.

The equipment base calls `S2000PPRuntimeReader.async_read_zone_states()`. That
reader obtains:

- FC03 holding register `40000 + PP-row - 1` for the primary, priority-packed
  zone state;
- FC04 input-register block `4096 + (PP-row - 1) * 16`, count 16, for the
  expanded zone state;
- exact validation of response function and length.

The sensor entity publishes the decoded primary name as its value and retains
`primary_code`, all 16 `expanded_codes`, and decoded non-zero
`expanded_states` as attributes.

## 5. Current Class / Inheritance Graph

```text
physical detector
  -> one of DIP34A05 / C2000RDIP / C2000RST01 / C2000ST04
    -> BolidDPLSDetectorBase
      -> GatewayCapabilitySpec / ResolvedDeviceMapping
      -> S2000PPRuntimeReader
        -> validated FC03 primary + FC04 expanded blocks
      -> C2000KPB.STATE_NAMES (shared generic Orion code dictionary)
      -> ModBusStateSensorEntity
        -> EquipmentCoordinator
        -> device_info_for_entry()
        -> one HA Device via the S2000-PP Config Entry
      -> generic presentation profile (no detector-family profile)
```

`BolidDPLSDetectorBase` is not itself an equipment class. It provides exact
one-or-more-row mechanics, physical DPLS identity, grouped reads and lossless
state transport. It does not encode smoke, glass-break or radio aggregation.

**CURRENT CODE BEHAVIOR:** `C2000RDIP` reuses `DIP34A05.capability_requirements`;
`C2000ST04` reuses `C2000RST01.capability_requirements` and
`state_sensor_definitions`. This is protocol-row reuse, not Python inheritance
between wired and radio products.

**ASSESSMENT:** the reuse is safe at the narrow “one exact type-1 zone” layer,
but the public tuples obscure product provenance and make it easy to assume
semantic equivalence. A future refactor should use named one-row capability
factories or a tiny immutable mapping constant, while retaining separate product
classes and separate diagnostic policies.

## 6. Physical Topology

### 6.1 ДИП-34А-05

```text
one wired detector
  <-> one DPLS address on С2000-КДЛ/КДЛ-2И
  <-> one configured С2000-ПП zone row
  <-> one ResolvedDeviceMapping / one equipment object
  <-> one HA Device / one current state entity
```

**DOCUMENTED FACT:** it stores one DPLS address. Older KDL firmware supports
input types 1/6/8; newer fire-oriented firmware supports 6/21.

### 6.2 С2000Р-ДИП

```text
one radio smoke detector (radio address + serial identity inside ARR)
  <-> С2000Р-АРР32/125 radio controller
  <-> one assigned DPLS address presented by ARR
  <-> С2000-КДЛ input at that DPLS address
  <-> one configured С2000-ПП zone row
  <-> one equipment object / one HA Device / one current state entity
```

**DOCUMENTED FACT:** ARR configuration lists DPLS address, radio address, type,
serial, hardware/software versions, power/case state and signal level per radio
unit. The detector supports KDL input types 1/6/8/21 depending on controller/KDL
configuration.

**CURRENT CODE BEHAVIOR:** HA models only the projected detector DPLS address.
ARR is not included in the detector's `via_device`; all downstream equipment is
attached directly to the S2000-PP gateway Device.

**INFERENCE:** the current identity is sufficient to avoid a second HA Device for
the same PP row, but it omits the real intermediate ARR topology because the
selected PP configuration table provides KDL Orion address and local DPLS address,
not the identity of the ARR that owns the radio unit.

### 6.3 С2000Р-СТ исп.01

Topology is the same radio projection as С2000Р-ДИП. Official ARR125
compatibility requires ARR firmware 1.25+, KDL 2.30+ or KDL-2I family 1.30+.
The official table permits type 5 (“охранный с контролем вскрытия корпуса”).
One physical unit is represented by one DPLS address/one PP row.

### 6.4 С2000-СТ исп.04

```text
one wired detector
  <-> one DPLS address
  <-> one KDL input
  <-> one С2000-ПП row
  <-> one equipment object / HA Device
```

Anti-masking, sensitivity, test mode and DPLS service voltage are detector/KDL
features; no separate Modbus row for them is documented.

### 6.5 Identity caveat

`DownstreamDeviceIdentity.stable_id` is gateway + Orion address + base DPLS
address. It intentionally omits model, PP row, partition and address count.
Config Flow prevents overlapping claims on one gateway/Orion DPLS range. Thus a
model replacement at the same physical address retains the stable HA identity.
Whether model should be part of physical identity is a project-wide design
decision; changing it only for this family would break established identity and
must not be done casually.

## 7. Wired vs Radio Architecture Comparison

| Concern | Wired DIP/ST | Radio RDIP/RST |
|---|---|---|
| Physical power | DPLS | autonomous battery/batteries |
| Intermediate device | KDL | ARR radio controller then KDL |
| PP footprint found | one zone row | one projected zone row |
| Alarm state path | detector -> KDL -> PP | detector -> ARR -> KDL -> PP |
| Battery/tamper/link | not applicable or local tamper | Orion state/event semantics may reach same expanded row |
| RSSI/channel/route | n/a | ARR configuration/statistics plane |
| Runtime DeviceInfo | static manufacturer/model only | same; ARR inventory is not read |
| Current HA entity | one lossless state sensor | one lossless state sensor with diagnostic codes only as attributes |

The correct shared abstraction is the exact DPLS-zone transport. Wired and radio
semantic aggregation should be separated above it.

## 8. Complete Capability / State Matrix

Classification key required by this audit:

- **A** — pollable through the implemented Modbus path;
- **B** — pollable through a documented command/register not implemented;
- **C** — available as expanded/secondary state;
- **D** — event only;
- **E** — available from ARR rather than the detector zone;
- **F** — documented by Bolid but not exposed through S2000-PP Modbus;
- **G** — unknown/insufficient documentation.

Codes below are canonical Orion/PP names present in the official PP event table
and current project dictionary. Applicability to a model must still be proven on
hardware unless the product manual explicitly names the condition.

| Capability/state | DIP34A05 | C2000RDIP | C2000RST01 | C2000ST04 | Evidence / path |
|---|---:|---:|---:|---:|---|
| normal/equipment normal | A/C | A/C | A/C | A/C | Primary/expanded configured zone |
| fire | A/C | A/C | n/a | n/a | code 37; fire detector manuals |
| warning/attention | C/G | C/G | n/a | n/a | codes 43/44; KDL type 21 supports Warning/Attention |
| Fire 2 | C/G | C/G | n/a | n/a | PP supports Fire 2 historically; exact code/model behavior needs capture |
| smoke chamber service required | C | C | n/a | n/a | code 204; manuals define “Требуется обслуживание” |
| smoke detector fault | A/C | A/C | n/a | n/a | code 41/other device fault; exact primary ordering needs capture |
| actual smoke/dust values | F/G | E/F/G | n/a | n/a | device manuals say values exist; PP numeric API documents temp/humidity/CO, not smoke/dust |
| intrusion/glass-break alarm | n/a | n/a | A/C | A/C | code 3 in current dictionary and tests |
| interference/restored | n/a | n/a | C/G | C/G | codes 4/6; may represent acoustic interference but requires capture |
| tamper/restored | n/a | C | C | C | 149/152; radio manuals and ST04 product document enclosure control |
| anti-masking | n/a | n/a | n/a | C/D/G | documented detector feature; exact Orion state code/path unproven |
| test / test start / finish | C | C | C | C | 19/20/21; product manuals document test modes |
| internal/automatic test failure | C/G | C/G | C/G | C/G | code 135; exact per-model emission unproven |
| generic device communication loss/restored | C | C | C | C | 250/251, PP-zone state |
| input communication loss/restored | C | C | C | C | 187/188, generic Orion input state |
| main battery low/fault/restored | n/a | C | C | n/a | 211/202/200; product manuals confirm battery monitoring |
| reserve battery low/restored | n/a | C | n/a | n/a | 212/213; RDIP has CR2032 reserve, RST has only CR123A |
| battery replacement required | n/a | C/G | C/G | n/a | code 186; exact model support needs capture |
| battery voltage | n/a | E/F | E/F | n/a | ARR shows source status; no PP Modbus voltage register documented for radio unit |
| radio link lost/restored | n/a | C/E | C/E | n/a | detector/ARR document supervision; likely projected communication codes; exact code requires capture |
| RSSI/signal quality | n/a | E/F | E/F | n/a | ARR Configurator/link test gives dBm, not PP zone Modbus |
| radio channel/group | n/a | E/F | E/F | n/a | ARR property, not per-zone PP register |
| repeater route/statistics | n/a | E/F | E/F | n/a | ARR Configurator tree/statistics only |
| jamming/interference of RF medium | n/a | E/F/G | E/F/G | n/a | ARR scans/channel management; per-detector PP state not documented |
| enrollment/binding | n/a | E/F | E/F | n/a | ARR configuration operation, not normal PP polling |
| radio address | n/a | E/F | E/F | n/a | ARR inventory field |
| serial number | F | E/F | E/F | F | newer devices support query; PP mapping does not expose it |
| firmware/hardware revision | F | E/F | E/F | F | ARR Configurator or KDL configuration plane, not current PP path |
| product cipher | F | E/F/G | E/F/G | F/G | current DIP firmware supports query; no PP Modbus field |
| DPLS service voltage | F/G | n/a | n/a | F | ST04 feature, no current PP numeric mapping documented |
| sensitivity/acoustic level | n/a | n/a | E/F | F | configuration commands, not PP state polling |

There is no evidence that a single zone primary code can represent all concurrent
conditions. Expanded state is therefore the authoritative lossless source for
diagnostic entity derivation; the primary value must remain available for audit.

## 9. Radio Capability Matrix

| Item | Bolid documentation | S2000-PP exposure | Current code | HA recommendation | Validation |
|---|---|---|---|---|---|
| RDIP main battery | ER14505, monitored | generic expanded codes plausibly exposed | decoded only as attribute | diagnostic multistate after exact-code capture | required |
| RDIP reserve battery | CR2032, monitored | 212/213 supported by PP table | decoded only as attribute | separate reserve-battery state if both transitions confirmed | required |
| RST battery | one CR123A, monitored | generic expanded codes | decoded only as attribute | one diagnostic battery-state entity | required |
| actual battery voltage | device/controller may know status; no Modbus value specified | no documented register | not read | no entity | vendor protocol evidence required |
| communication loss | detector and ARR supervise link | projected Orion zone state expected | expanded attribute | diagnostic link/communication state only after code provenance | required |
| RSSI/link-test dBm | ARR Configurator displays max/avg/min dBm and quality bands | not documented | not read | no entity via current architecture | alternative ARR API research |
| channel/group | ARR configuration property | not documented | not read | DeviceInfo only if runtime-readable, currently not | alternative API |
| radio address | ARR inventory property | not documented | not read | DeviceInfo candidate only if runtime-readable | alternative API |
| repeater route/statistics | ARR Configurator tree/statistics | not documented | not read | diagnostic data, not normal entity | alternative API |
| tamper | product documentation | generic expanded code 149/152 | attribute | binary tamper plus raw state, after transition capture | required |
| test | product documentation | zone state/event | attribute/primary | retain in raw state; optional diagnostic state | required |
| enrollment | ARR configuration action | not normal poll | not read | no entity | no |
| serial/firmware/hardware | ARR inventory displays them | not documented | DeviceInfo fields remain None | populate only through a proven runtime protocol | alternative API |

### Why HA currently shows little radio information

1. The classes intentionally expose one operational multistate sensor.
2. The shared PP reader already captures expanded states, but no product-specific
   reducer creates battery/tamper/link entities from them.
3. The generic code table decodes names but does not prove which physical source
   emitted a code. This conservative design avoids fabricating “RSSI” from a
   generic communication-restored event.
4. Rich ARR inventory and link statistics are visible to the vendor Configurator,
   not documented in the S2000-PP Modbus map.
5. The physical ARR intermediate is not represented in the selected PP mapping,
   so HA has no controller API from which to obtain radio inventory.

This is partly a missing semantic implementation (battery/tamper/link states) and
partly a genuine transport limitation (RSSI/channel/identity).

## 10. Current Entity Inventory

All four state entities are sensors, enabled by default, have no HA device class
or entity category, and use stable suffixes under the equipment identity.

| Model | Entity | Source | Meaning | Correct? | Recommendation |
|---|---|---|---|---|---|
| DIP34A05 | `sensor.detector_state` | primary + expanded row | full detector multistate | mostly | KEEP; rename only if translation policy demands “Smoke detector state” |
| C2000RDIP | `sensor.detector_state` | primary + expanded projected row | alarm plus radio diagnostics in attributes | incomplete | KEEP as raw/operational audit state; add proven diagnostics |
| C2000RST01 | `sensor.glass_break_state` | primary + expanded projected row | alarm plus radio diagnostics | incomplete | KEEP; add proven diagnostics |
| C2000ST04 | `sensor.glass_break_state` | primary + expanded row | alarm/tamper/anti-mask/test | mostly | KEEP; prove anti-mask semantics |

Current entity IDs are assigned by HA and are not hard-coded; stable unique IDs
are `<stable equipment identity>_detector_state` and
`<stable equipment identity>_glass_break_state`.

### Missing/questionable candidates

| Candidate | Models | Platform/category | Recommendation |
|---|---|---|---|
| fire/smoke binary sensor | DIP/RDIP | binary_sensor, safety semantics | NEEDS HARDWARE VERIFICATION; do not derive from a guessed list of primary codes |
| service/contamination state | DIP/RDIP | diagnostic sensor | recommended if code 204 and restoration behavior are confirmed |
| fault state | all | diagnostic sensor | use a documented, conservative multistate reducer; avoid conflating transport unavailable |
| tamper | RDIP/RST/ST04 | binary_sensor diagnostic | recommended after 149/152 capture per model |
| main battery state | RDIP/RST | diagnostic sensor | recommended from exact expanded states; no percentage/voltage |
| reserve battery state | RDIP only | diagnostic sensor | recommended only after separate 212/213 transitions confirmed |
| radio communication state | RDIP/RST | diagnostic sensor | recommended only when 187/188 vs 250/251 provenance is established |
| RSSI/LQI | radio models | diagnostic numeric sensor | NOT IMPLEMENTABLE through documented current PP path |
| radio channel/address | radio models | DeviceInfo/attribute | NOT IMPLEMENTABLE through documented current PP path |
| serial/firmware/hardware | all | DeviceInfo | do not publish static documented targets as runtime values |
| smoke/dust numeric values | DIP/RDIP | diagnostic numeric sensors | no documented PP numeric command; defer |
| DPLS voltage | ST04 | diagnostic numeric sensor | defer until a documented PP-accessible command exists |

## 11. DeviceInfo Audit

`device_info_for_entry()` correctly maps:

- manufacturer from `attr_manufactures_name` (`Bolid`);
- exact product model from `attr_model_name`;
- stable downstream identifier;
- `via_device` to the S2000-PP gateway Config Entry;
- serial, hardware and software fields only when runtime values exist.

For these four classes the runtime identity fields are all `None`, so HA does not
invent firmware, hardware or serial values. `documented_target_firmware` is only
an entity attribute in `attr_device_metadata`, not DeviceInfo firmware. That is
good separation, although the DIP target value is factually suspect.

All entities of one mapping share one HA Device. The current tests do not prove
this specifically for each of the four detectors; they rely on shared entity and
DeviceInfo tests.

The ARR is not represented as an intermediate `via_device`. Adding it would
require a stable runtime ARR identity and a verified topology relationship from
the gateway configuration; neither is currently available from the PP zone row.

## 12. Reconciliation / Physical Device Audit

The base validates exact object kind, local DPLS address, zone type, holding data
area and required capability count. Config Flow creates a `DPLSSubIdentity` and
rejects overlapping ranges on the same gateway and Orion controller.

However, these classes do not implement model-specific
`reconcile_gateway_mapping()`. On startup the common reconciliation hook therefore
cannot repair a stale PP table row by re-searching the current PP configuration;
it merely applies the stored resolved mapping. This is architecture drift from
newer models such as C2000RVTI, C2000DZ/RDZ and MIP24.

**PROPOSED CHANGE:** add a reusable exact-one-zone reconciliation policy that
searches by Orion address + base DPLS + permitted PP zone type, ignores partition
for physical identity, requires one unique match, and updates only the mutable PP
row/register mapping. Do not infer product identity from zone type alone.

**NEEDS HARDWARE VERIFICATION:** actual PP zone types in the newly installed
fixtures. Current code requires type 1 for all four even though official ARR/KDL
tables call the configured KDL input types 1/6/8/21 for RDIP and 5 for RST. PP
“zone type” and KDL “input type” are different configuration layers; current code
metadata conflates them in prose/tests and must be validated against UProg.

## 13. Primary / Expanded State Audit

Primary register decoding preserves both non-zero bytes in `priority_states` but
the equipment publishes only the first as `state`. Expanded read preserves all 16
register values. Unknown values become `unknown_<code>` and are not dropped.

Strengths:

- grouped primary then expanded reads;
- no normalization to false/zero;
- no model-specific destructive state table;
- raw codes are attributes;
- invalid/short/wrong-function responses remain coordinator-fatal.

Weaknesses:

- `expanded_states` filters zero but otherwise cannot distinguish alarm,
  battery, tamper and link domains;
- generic `C2000KPB.STATE_NAMES` contains many unrelated Orion states;
- primary and expanded blocks are separate Modbus reads and not an atomic Orion
  snapshot;
- no model-specific precedence or conflict policy exists;
- tests use synthetic combined codes, not hardware-derived tuples.

## 14. Unknown-Code Handling Audit

The current `unknown_<code>` contract is appropriate and must be retained in any
refactor. Dedicated semantic entities must be derived without removing raw codes
from the operational state. Unknown radio-product codes must not be silently
renamed “radio quality” or “battery” from context alone.

## 15. Firmware Variant Audit

### ДИП-34А-05

Official §10 lists 1.22 (05.2025, product-cipher query), 1.20 (07.2024,
serial-number query), 1.17, 1.15 and 1.01. Compatibility differs by KDL family and
version: older controllers accept 1/6/8; new fire revisions accept 6/21. Current
code's target 1.24 is not supported by the found official record.

### С2000Р-ДИП

Official current manual §10 distinguishes hardware generations and compatibility.
Hardware 2.x has newer power behavior and OTA requirements. The class does not ask
for a hardware variant and records a static target 1.29. State semantics across
hardware 1.x/2.x need hardware/controller matrix validation.

### С2000Р-СТ исп.01

Official page lists 1.02/1.03 history, repeater support and later radio groups, but
its version rows are ambiguous. ARR125 compatibility requires radio unit 1.0+,
ARR 1.25+, KDL 2.30+ (or corresponding KDL-2I 1.30+). No runtime firmware is read.

### С2000-СТ исп.04

Official §10: 1.00 (11.2020), 1.10/1.11/1.12, 1.20, 1.21, and 1.22
(02.2025). Version 1.22 fixes instability with KDL-2I. Current target 1.22 matches
that record.

## 16. Presentation / Card Generator Audit

None of the four classes has a Bolid presentation profile. They use the generic
profile, which includes enabled non-configuration entities and sorts them by
domain and semantic key. With one entity this is harmless, but it gives no stable
semantic order when diagnostics are added.

Recommended native-card order:

**DIP34A05:** detector/fire state; service/contamination; fault; raw diagnostic
state if a separate primary entity is introduced.

**C2000RDIP:** detector/fire state; service/contamination; tamper; main battery;
reserve battery; radio communication; fault/raw diagnostic.

**C2000RST01:** glass-break state; tamper; battery; radio communication;
fault/raw diagnostic.

**C2000ST04:** glass-break state; tamper; anti-masking; self-test/fault; raw
diagnostic.

These must remain ordinary generated `type: entities` cards. No runtime dashboard
wrapper is justified.

## 17. Test Coverage Audit

| Contract | DIP | RDIP | RST | ST04 | Finding |
|---|---:|---:|---:|---:|---|
| registry/model | yes | partial | yes | yes | present |
| exact one-row mapping | yes | yes | yes | yes | synthetic manual rows |
| legacy alias | yes | n/a | n/a | n/a | present |
| configuration-assisted equality | no | no | yes | yes | gap |
| stale PP-row reconciliation | no | no | no | no | major gap/runtime absent |
| wrong Orion rejection | indirect | indirect | indirect | indirect | no config-driven proof |
| grouped primary+expanded | weak | no runtime read | yes | no runtime read | gap |
| unknown code preservation | no | decoder only | yes | decoder only | gap |
| documented alarm modes | no | no | only intrusion code | only intrusion code | gap |
| battery/tamper/link transitions | n/a | decoder names only | synthetic tuple | n/a | no product hardware proof |
| one HA Device/DeviceInfo | shared only | shared only | shared only | shared only | model-specific gap |
| unique IDs | shared only | shared only | shared only | shared only | model-specific gap |
| presentation order | no | no | no | no | no profiles |
| firmware variants | no | no | no | no | gap |
| transport failures | no | no | yes | no | uneven |

The RDIP test asserting `211`, `149`, and `187` decode correctly proves only the
global dictionary, not that RDIP emits those codes. RST's synthetic expanded block
similarly proves transport losslessness but not product semantics. This is useful
unit coverage but must not be cited as hardware evidence.

## 18. Architecture Drift Findings

### Modern/current elements

- explicit equipment registry and generic Config Flow;
- DPLS physical identity and overlap protection;
- exact capability mapping;
- one coordinator snapshot per physical equipment object;
- grouped primary/expanded reads;
- raw/unknown preservation;
- DeviceInfo metadata only from runtime values;
- native generator-first presentation infrastructure.

### Drift/gaps

1. No startup reconciliation against the current PP configuration table.
2. All four hard-code PP zone type 1 without fixture evidence in this audit.
3. `supported_kdl_input_types` metadata is not actually readable through PP and
   is confused with PP zone type in tests/documentation.
4. Radio and wired classes share mapping constants but have no separate semantic
   reducers.
5. Rich radio states remain attributes of one operational sensor.
6. No model-specific presentation profiles.
7. Firmware targets are static metadata; DIP's value contradicts current official
   documentation.
8. No runtime ARR topology/identity plane exists.

Architecture generation verdict: **partially modern** for all four.

## 19. Proposed Target Architecture

```text
BolidExactDPLSZoneDeviceBase
  - exact identity, reconciliation, grouped raw state, unknown preservation
  |
  +-- BolidSmokeDetectorSemantics
  |     +-- DIP34A05 (wired)
  |     +-- C2000RDIP (radio diagnostics policy)
  |
  +-- BolidGlassBreakDetectorSemantics
        +-- C2000ST04 (wired anti-mask/test policy)
        +-- C2000RST01 (radio diagnostics policy)

optional, only if a proven runtime protocol is found:
BolidRadioInventoryProvider (ARR-scoped, read-only)
  - radio address/serial/firmware/RSSI/channel/route
  - separate from PP zone-state transport
```

The exact row base should not be named “fire detector”, because it already hosts
security glass-break/magnetic devices. Product-specific reducers should consume
the lossless expanded snapshot and publish only proven semantic entities. The raw
multistate entity remains the audit trail.

## 20. Proposed Implementation Phases

1. **Evidence correction, low risk:** correct DIP official firmware/input-type
   metadata; clarify PP-zone-type versus KDL-input-type; add official references.
2. **Hardware fixtures, no behavior change:** capture configuration rows and
   normal/alarm/test/tamper/battery/link-loss expanded tuples for all four models.
3. **One-row reconciliation, medium risk:** introduce generic unique
   Orion+DPLS+allowed-PP-type reconciliation; prove PP-row changes do not change
   HA identity.
4. **Wired semantic entities, medium risk:** add documented fire/glass-break,
   tamper/anti-mask/service entities only from confirmed code sets.
5. **Radio diagnostic aggregation, medium/high risk:** one/two battery states,
   tamper and communication state with explicit conflict/absence policy.
6. **Presentation profiles, low risk after entity contract:** stable native-card
   order.
7. **ARR inventory research, high uncertainty:** only after official protocol or
   controlled hardware proof; do not reverse-engineer by writing configuration.

## 21. Real Hardware Validation Matrix

All actions require an isolated development stand, approved fire/security test
procedures, one client per bus, exact TX/RX timestamps, PP primary raw word and all
16 expanded values. Never test on production life-safety operation.

| Model/action | Physical action | Bolid observation | Modbus observation | HA expectation | Restore |
|---|---|---|---|---|---|
| all / normal | leave detector quiescent | Orion normal | configuration tuple; repeated primary+expanded | stable normal state | none |
| DIP/RDIP / approved smoke test | manufacturer-approved aerosol/tester under authorized conditions | Warning/Attention/Fire sequence | exact PP codes and ordering | future fire state changes, raw preserved | ventilate/reset per manual |
| DIP/RDIP / service | use an already contaminated service specimen; do not contaminate a good detector | “Требуется обслуживание” | code 204 and restoration | diagnostic service state | clean per manual |
| all / built-in test | use documented light guide/button/remote test | test event/mode | primary/expanded/event persistence | raw/test diagnostic | allow timeout/end test |
| RDIP/RST/ST04 / tamper | authorized case switch operation | enclosure open/restored | 149/152 or observed codes | tamper entity; alarm remains independent | close enclosure |
| ST04 / anti-mask | approved non-damaging mask target at documented distance | mask/fault/restored | exact state/event and persistence | anti-mask diagnostic | remove target, reset if required |
| RST/ST04 / glass test | manufacturer-approved glass-break simulator, no real glass | alarm/test | exact 3/interference/test codes | glass-break state | stop simulator/rearm |
| RDIP / battery | first observe naturally low or use vendor-approved simulator; do not short/deep-discharge cells | main/reserve low separately | distinguish 211/212/200/213 | one main and one reserve state | install approved fresh cells |
| RST / battery | naturally low/vendor-approved simulator | one battery low/restored | exact code tuple | one battery state only | approved fresh CR123A |
| radio / temporary link loss | isolated stand only; power/controller method approved by operator, no jamming | ARR loss then restore | determine 187/188 vs 250/251 and delay | communication diagnostic | restore controller/path and verify normal |
| radio / link quality | Configurator read-only test | dBm min/avg/max and quality | simultaneously prove PP has no value change/register | no HA RSSI under current path | exit test |
| all / identity | read-only UProg/Configurator inventory | serial/fw/hw/product cipher | compare PP table/register availability | DeviceInfo stays None unless protocol proven | disconnect tool |
| reconciliation | move only a test PP row in backed-up fixture configuration, separate approved task | same Orion/DPLS on different PP row | old vs new registers | same HA Device after reconciliation | restore configuration backup |

Battery removal, deliberate RF jamming, destructive contamination and real glass
breakage are not recommended.

## 22. Documentation Gaps / Open Questions

1. Exact PP zone type and captured state tuples for each newly installed detector.
2. Whether RDIP smoke/dust measurements are forwarded to any KDL query that PP
   3.01 can expose, despite not being in the documented generic numeric selector.
3. Exact battery code separation for RDIP main/reserve sources.
4. Exact link-loss code: input communication 187/188, device communication
   250/251, or both under different failures.
5. Whether ARR tamper/link/battery events remain simultaneously in PP expanded
   state or are transient/event-only under some firmware.
6. ST04 anti-mask and acoustic-interference codes.
7. Fire 1/Fire 2/Warning/Attention primary priorities by KDL input type.
8. A read-only official ARR runtime protocol usable without competing with KDL.
9. Firmware differences across RDIP hardware 1.x/2.x and RST 1.02/1.03.
10. Whether the one-row assumption holds for every controller mode and firmware;
    current official topology strongly supports it, but fixture table evidence is
    still required.

## 23. Final Recommendation Per Model

### ДИП-34А-05 — SMALL FIX

The one-detector/one-DPLS/one-row model and lossless state entity are appropriate.
Correct unsupported firmware metadata, distinguish KDL input type from PP zone
type, add unique-row reconciliation and hardware-derived state tests. Add service
and fire semantics only after exact captures.

### С2000Р-ДИП — REFACTOR

Keep it a separate physical product and keep the one projected DPLS identity. Do
not inherit wired product identity. Add a radio-specific semantic layer for main
and reserve battery, tamper and communication after hardware validation, while
retaining the raw detector state. RSSI, channel, route and radio identity remain
out of scope until an official readable ARR protocol exists.

### С2000Р-СТ исп.01 — REFACTOR

Keep one physical device and one projected DPLS row. Separate glass-break alarm
from the one-battery, tamper and radio supervision diagnostics. Do not copy RDIP's
reserve-battery model. Preserve the generic state and add a profile only after
the semantic contract is proven.

### С2000-СТ исп.04 — SMALL FIX

The wired one-address topology is correct. Add unique-row reconciliation,
hardware-derived alarm/tamper/anti-mask/test state coverage, and a semantic native
card. Do not expose DPLS voltage, sensitivity or firmware until a documented
runtime read path exists.

## 24. Audit Boundary

This audit proposes no production operation and no runtime code change. Statements
about physical features come from official manuals; statements about Modbus
availability come from the official PP map and current source; proposed entities
remain proposals until the hardware matrix establishes exact state provenance.

## 25. S2000R-DIP Development Hardware Follow-up

### 25.1 PP projection and normal fixtures

**HARDWARE VERIFIED:** two independent С2000Р-ДИП units were observed on the
Windows COM3 development stand through an S2000-PP at 115200 8N1, unit ID 2:

| Unit | PP row | Orion/KDL address | DPLS input | PP zone type |
|---|---:|---:|---:|---:|
| experimental | 29 | 3 | 4 | 1 |
| control | 30 | 3 | 5 | 1 |

Both units repeatedly returned primary register `0x18C8` (priority codes
`24, 200`, primary `armed`) and the exact expanded tuple:

```text
24,200,213,47,188,251,111,0,0,0,0,0,0,0,0,0
```

This is direct product evidence for `battery_restored` (200) and
`reserve_battery_restored` (213) in the С2000Р-ДИП PP projection. A wired
ДИП-34А-05 control row returned `24,47,188,251,111,...` without 200/213.
Codes 202/211/212 retain their documented generic Orion meanings, but active
С2000Р-ДИП battery transitions were not produced during this validation.

Codes 188 and 251 also occurred on the wired control. They therefore remain
generic input/device communication states and are not renamed as radio-link
quality or radio-hop supervision.

### 25.2 Enclosure supervision hardware validation

**DOCUMENTED FACT:** С2000Р-ДИП officially supports configurable enclosure
supervision through the PCB tamper button, with messages `Взлом корпуса` and
`Восстановление корпуса`. Generic Orion meanings remain 149
`enclosure_tamper` and 152 `enclosure_tamper_restored`.

**HARDWARE VERIFIED historical negative observations:**

- removing the detector from its mounting base produced no PP change during
  approximately 22.4 seconds; this is a `REMOVED_FROM_MOUNTING_BASE` fixture,
  not a housing-open fixture;
- opening the actual detector housing and targeting the documented PCB switch
  produced no PP change: 585 row-29 housing-open samples, 591 stable row-30
  control samples, 1182 records total, one distinct raw state and zero
  non-baseline records over a confirmed-open interval longer than 90 seconds;
- 149, 152 and substitute codes were not observed under that older
  configuration.

**HARDWARE VERIFIED current projection:** after the suspect S2000M/PProg
setting was removed and the user independently changed Zone Modbus from 28 to
3, the same row-29 detector exposed the complete enclosure-tamper lifecycle.
The frozen mapping was Orion/KDL 3, DPLS input 4, Zone Modbus 3, PP type 1;
row 30 (Orion/KDL 3, DPLS input 5) was the untouched control.

Normal:

```text
FC03 0x18C8 (24,200)
FC04 24,200,213,47,188,251,111,0,0,0,0,0,0,0,0,0
```

Housing open, first observed at `00:51:02.306+07:00`:

```text
FC03 0x9518 (149,24)
RX 02 03 02 95 18 93 1E
FC04 149,24,200,213,47,188,251,111,0,0,0,0,0,0,0,0
RX 02 04 20 00 95 00 18 00 C8 00 D5 00 2F 00 BC 00 FB 00 6F
   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 50 CA
```

Housing restored, first observed at `00:54:50.730+07:00`:

```text
FC03 0x18C8 (24,200)
RX 02 03 02 18 C8 F7 D2
FC04 24,200,213,47,152,188,251,111,0,0,0,0,0,0,0,0
RX 02 04 20 00 18 00 C8 00 D5 00 2F 00 98 00 BC 00 FB 00 6F
   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 5F A4
```

Code 149 became primary and remained in expanded state for approximately
227.4 seconds. Code 152 was an expanded restore state while primary had
already returned to 24. All battery and generic communication/restoration
codes coexisted with both tamper states. Row 30 remained byte-identical for
413 complete control samples; no Modbus exception occurred.

Therefore 149 `enclosure_tamper` and 152
`enclosure_tamper_restored` are **DOCUMENTED + HARDWARE VERIFIED** for this
validated S2000R-DIP/S2000-PP projection.

**UNRESOLVED configuration causality:** two variables changed between the
negative and successful experiments: the suspect S2000M/PProg setting was
removed, and Zone Modbus was manually changed from 28 to 3. The successful
projection cannot be attributed to either individual change. In particular,
Zone Modbus 3 alone is not established as the cause.

### 25.3 Implemented conservative semantic boundary

The development model keeps one physical detector, one projected DPLS row and
one HA Device. The original lossless `detector_state` remains authoritative.
Two diagnostic multistate battery entities use the hardware-observed restore
states and documented active states without inventing a priority when multiple
different codes coexist.

The enclosure-tamper binary sensor is enabled by default and begins Unknown.
Only explicit 149 changes it to active and explicit 152 changes it to restored;
absence of both codes never fabricates a normal state. The last explicit state
is retained across unrelated snapshots for the lifetime of the equipment
object. Repeated 149/152 states are idempotent. This now reflects documented
and hardware-verified behavior rather than future-only decoding.

RSSI, LQI, radio channel, route, radio address, serial, actual firmware and
hardware revision remain unexposed because no runtime S2000-PP read path has
been established.
