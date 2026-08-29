# Equipment metadata audit

Audit baseline: Home Assistant Core 2026.10.0.dev0 and the equipment registry at
Modbus Devices 0.6.0 plus post-release DEVELOPMENT changes.

`model_id` below means a documented protocol device-type identifier exposed
through the shared DeviceInfo builder. A manual's firmware history is never a
runtime value.

| Equipment | Firmware | Hardware revision | Serial | Protocol source | HA exposure / action |
| --- | --- | --- | --- | --- | --- |
| M3000-BB-1020 | yes | yes | yes | direct documented FC03 service block; device type is in the same block | cached equipment attributes are exposed as native `model_id`, `sw_version`, `hw_version`, and `serial_number`; no new request |
| S2000-PP | yes, gateway itself | no | no | FC03 46152, two registers: type 36 and PP firmware | native `model_id` and `sw_version`; service read is cached after the first coordinator snapshot instead of repeated every five seconds |
| MIP-24 isp.20 | no downstream path | no downstream path | no downstream path | S2000-PP row/state/numeric map only | keep all optional fields `None`; do not expose manual target 5.10 |
| C2000-2, C2000-4, C2000-BKI, Signal-20M | no downstream path | no downstream path | no downstream path | modeled behind S2000-PP rows | keep optional fields `None`; audit a native Orion path only if the architecture later supports it |
| C2000-KPB, C2000-KDL, C2000R-ARR125 | no downstream path | no downstream path | no downstream path | modeled behind S2000-PP rows | keep optional fields `None`; documented firmware compatibility belongs to validation docs, not DeviceInfo |
| DPLS detectors: DIP-34A-05, C2000R-DIP, C2000-IP-03, C2000R-IP, C2000R-ST-01, C2000-ST-04, C2000R-SMK, C2000-SMK | no downstream path | variant may be configuration-known, not protocol-read | no downstream path | KDL/ARR state rows through S2000-PP | keep runtime fields `None`; do not turn configured variants into read hardware revisions |
| DPLS outputs: C2000R-RM, C2000R-Sirena, C2000-SP2, C2000-SP4 | no downstream path | variant may be configuration-known, not protocol-read | no downstream path | KDL/ARR state/relay rows through S2000-PP | keep runtime fields `None`; preserve variant in canonical model/presentation only |
| DPLS numeric: C2000-VT, C2000-VTI | no downstream path | configured variant only | no downstream path | numeric/state rows through S2000-PP | keep runtime fields `None` |
| SVK15-3-2-B, SVK15-3-8-1-B3 | no downstream path | no downstream path | no downstream path | KDL/ARR state plus optional counter selector through S2000-PP | keep runtime fields `None`; meter identity in Resource is not exposed by the current Modbus path |
| C2000-DZ | no downstream path | no downstream path | no downstream path | S2000-PP state rows | keep runtime fields `None` |
| DN310 | not implemented | not implemented | not implemented | current direct Modbus model has no documented metadata read | keep optional fields `None`; future audit required |
| PLC110-24.60-K-M | not implemented | not implemented | not implemented | current user-defined I/O mapping has no metadata read | keep optional fields `None`; future audit required |
| TRM138 | not implemented | not implemented | not implemented | current bulk measurement path has no metadata read | placeholders removed; keep optional fields `None`; future official-protocol audit required |

All entity platforms use `device_info_for_entry`; there is no remaining
platform-specific DeviceInfo construction. The shared builder normalizes cached
metadata once per equipment runtime and gives every entity of the physical
device the same native fields and stable identifiers.
