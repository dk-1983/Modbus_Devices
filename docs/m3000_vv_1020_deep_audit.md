# M3000-BB-1020 documentation-driven audit

Authoritative source: Bolid, `M3000-BB-1020` operation manual
ACDR.421459.003 REp, revision 3, 2025-09-03:
<https://bolid.ru/files/373/566/m3000_vv_1020_rep_sep_25.pdf>.

The addresses below are protocol data addresses, not human-facing register
numbers. `n` is zero-based unless stated otherwise. FC03/04 rows contain
16-bit unsigned register values; FC01/02 rows contain bits.

## Register and capability matrix

| Register/function | Address | Access | Type | Meaning | Current implementation | HA capability | Status |
|---|---:|---|---|---|---|---|---|
| FC03/06/16/22/23 | 0x7000 | R/W | holding | RS-485 baud code | none | none | Configuration; do not expose |
| FC03/06/16/22/23 | 0x7001 | R/W | holding | RTU/ASCII and character format | none | none | Configuration; do not expose |
| FC03/06/16/22/23 | 0x7004 | R/W | holding | RS-485 device address | integration connection setting, not read from this register | config entry | Do not mutate at runtime |
| FC03/06/16/22/23 | 0x7008 | R/W | holding | network timeout, 0 or 1..600 s | none | none | Safety configuration; do not expose |
| FC03/06/16/22/23 | 0x700A | R/W | holding | standard/transparent interface mode | none | none | Gateway semantics; do not expose |
| FC01/05/15 | `0x0001 + 0x80*n`, n=0..11 | R/write command | coil | pulse-counter reset for input 1..12 | none | none | Destructive command; do not expose |
| FC01/05/15 | `0x0002 + 0x80*n`, n=0..5 | R/W | coil | 24 V input debounce: basic 1 kHz / extended 90 Hz | none | none | Configuration; hardware validation needed |
| FC02 | `0x0000 + 0x80*n`, n=0..11 | R | discrete input | input state: 24 V inputs 1..6, then 220 V inputs 1..6 | `get_input(s)`; one sparse read per channel | 12 binary sensors | Implemented |
| FC04 | `0x0001 + 0x80*n`, n=0..11 | R | input register | 16-bit rising-edge counter, reset on reboot/overflow/command | none | none | Useful read-only candidate; hardware validation needed |
| FC01/05/15 | `0x1000 + 0x80*n`, n=0..5 | R/W | coil | current/direct state of relay 1..6 | `get_output(s)`, `set_output(s)` | 6 switches | Implemented |
| FC03/06/16/22/23 | `0x1005 + 0x80*n`, n=0..5 | R/W | holding | live PWM duty, 0..1000 = 0..100% | none | none | Writable control; separate review required |
| FC03/06/16/22/23 | `0x1008 + 0x80*n`, n=0..5 | R/W | holding | PWM period, 0.1..6553.5 s | none | none | Persistent configuration; do not expose automatically |
| FC03/06/16/22/23 | `0x1009 + 0x80*n`, n=0..5 | R/W | holding | safe PWM duty, 0..1000 | none | none | Safety configuration; do not expose |
| FC03/06/16/22/23 | table 7 blocks, output 1..6 | R/W | holding | logic type, X/Y source, edge delay type and duration | none | none | Interdependent persistent configuration; do not expose |
| FC01/05/15 | table 7 inversion bit, output 1..6 | R/W | coil | invert logic result | none | none | Interdependent configuration; do not expose |
| FC03/06/16/22/23 | 0x8000..0x8005 | R/W | holding | year, month, day, hour, minute, second | represented by single-request aliases 60007..60012 | read-only Device time; backend-authoritative correction | Implemented through documented aliases |
| FC03/06/16/22/23 | 0x9000 | write command | holding | reboot command 0x55AA | none | none | Destructive command; do not expose |
| FC03/06/16/22/23 | 0x9001 | R/W | holding | Wi-Fi watchdog timeout | none | none | Device configuration; do not expose |
| FC04 | 0x9000..0x9005 | R | input registers | type, hardware version, serial words, software version | aliases 60001..60006 used | device metadata | Implemented through documented aliases |

### Documented single-request holding-register map (table 10)

The manual explicitly provides 60000..60082 as a contiguous optimization map
and permits FC03/06/16/22/23. The implementation deliberately reads only the
small stable prefix needed by the existing snapshot.

| Address(es) | Access | Meaning | Current implementation / HA | Status |
|---:|---|---|---|---|
| 60000 | command | reboot with 0x55AA | none | Do not expose |
| 60001 | R | device type | `_get_runtime_header` / device metadata | Implemented |
| 60002 | R | software version | `_get_runtime_header` / device metadata | Implemented |
| 60003 | R | hardware version | `_get_runtime_header` / device metadata | Implemented |
| 60004..60006 | R | serial-number words, bytes 5..0 | `_get_runtime_header` / device metadata | Implemented; identity unchanged |
| 60007..60012 | R/W | calendar fields | `_get_runtime_header`, `get_time`, `set_time` / Device time | Implemented; HA time authoritative |
| 60013..60017 | R/W | baud, format, address, timeout, interface mode | none | Do not expose |
| 60018 | R/W | packed input debounce settings | none | Configuration; hardware validation needed |
| `60019 + 7*n` .. `60025 + 7*n`, n=0..5 | R/W | per-relay PWM period, safe duty, logic type, X/Y, delay type/value | none | Interdependent persistent configuration; do not expose |
| 60061 | R/W | packed relay logic inversion bits | none | Interdependent configuration; do not expose |
| 60062 | R/W | packed direct relay state | none; existing FC05 per relay retained | Needs hardware validation; no behavior change |
| 60063..60068 | R/W | live PWM duty for relays 1..6 | none | Writable controls; separate review required |
| 60069 | write command | packed input counter reset | none | Destructive command; do not expose |
| 60070 | R | packed relay states (manual wording repeats “direct set”) | none; existing FC01 per relay retained | Ambiguous wording; hardware validation required |
| 60071..60082 | R | input pulse counters: 24 V 1..6, 220 V 1..6 | none | Best read-only candidate; hardware validation recommended |

The manual warns that firmware functionality changes can shift addresses in
the single-request map. New use of that map therefore needs firmware/hardware
coverage, even when the equivalent sparse register is already documented.

## Home Assistant exposure decision

The runtime removes the legacy writable datetime entity with unique ID
`<entry_id>_clock_1` and exposes the clock as the read-only sensor
`<entry_id>_device_time`. This is an intentional safety migration, but existing
automations and dashboards referencing the former entity require user updates.
The six relay switches and twelve binary-input entity identities are unchanged.

### Safe/useful to add after separate review

- Read-only pulse counters 1..12. They are meaningful HA measurements, but
  reset on reboot, overflow at 65535, and are not lifetime totals.
- Optionally read-only communication/logic diagnostics, only if a concrete HA
  troubleshooting use case is agreed; they should be diagnostic entities, not
  controls.

### Needs hardware validation

- FC04 counter reads and the 60071..60082 aliases, including rollover behavior.
- Packed debounce, relay-state and counter-reset words 60018/60062/60069/60070.
- PWM and logic values while direct FC05 relay control is active.
- Compatibility of table 10 aliases across firmware revisions.

### Do not expose

- Reboot, counter-reset, RS-485 address/format/baud, transparent mode, network
  timeout, Wi-Fi watchdog, safe relay states, and persistent logic settings.
- PWM/logic writable controls without a separate UX, safety and migration
  review. Their parameters interact, and direct relay writes overwrite live PWM
  duty with 0% or 100%.

## Pymodbus method classification

| Method | Classification | Reason |
|---|---|---|
| `get_device_info` | B: generic operation + device parameters | FC03 read/validation is generic; address layout and metadata application are M3000-specific |
| `get_time` | C: M3000-specific semantics | device address and six-field wall-clock decoding are specific |
| `set_time` | C: M3000-specific semantics | register layout, backend-authoritative policy and cooldown contract are specific |
| `get_input(s)` | B + C | FC02 single-bit read is generic; sparse map, channel meaning and local state are specific |
| `get_output(s)` | B + C | FC01 single-bit read is generic; sparse relay map and state model are specific |
| `set_output(s)` | B + C | FC05 echo validation is generic; channel map, direct-control meaning and state update are specific |
| `read_holding_registers` call | A transport, B at wrapper boundary | pymodbus transport is generic; count/address/operation belong to M3000 |
| `read_discrete_inputs`, `read_coils` calls | A transport, B at wrapper boundary | transport is generic; documented sparse addresses prevent generic bulk grouping here |
| `write_coil`, `write_registers` calls | A transport, B/C at method boundary | transport/echo validation are generic; write meaning and post-write state are device-specific |

Generic response, payload-length, function-code and FC05/FC16 echo validation
already lives in `modbus_validation.py` and is used by multiple direct equipment
implementations. A new direct-device base class is not justified: it would add
an inheritance contract while addresses, grouping rules, decoding and state
updates remain device-specific. The small private FC03 wrapper is intentionally
local, matching the existing DN310 private pattern without coupling the classes.

## Snapshot transaction plan

Before this refactor an ordinary/first coordinator snapshot performed 20 reads:
12 sparse FC02 input reads, 6 sparse FC01 relay reads, one FC03 metadata read at
60001..60006, and one FC03 RTC read at 60007..60012. A correction adds one FC16
write only when the established clock policy calls for it.

After this refactor the snapshot performs 19 reads: the same 18 sparse bit reads
and one documented contiguous FC03 read at 60001..60012. Clock correction write
behavior is unchanged. Sparse bit ranges are not combined because the manual
assigns unrelated registers inside the 0x80 gaps. No FC23 transaction or broad
60001..60082 read is introduced.
