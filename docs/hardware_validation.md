# Hardware validation

This document records development inputs observed on physical hardware. It does
not authorize production deployment or actuator writes.

## RTU over UDP

The transport is hardware validated with a persistent UDP socket and raw Modbus
RTU ADUs carried directly in UDP payloads. The tested gateway requires symmetric
local and remote UDP port 40000; using local source port 40001 timed out. Slave
ID 1, FC01, FC03, FC04, and FC06 were observed, and RTU CRC16 validation passed.
The remote IP is validated. The gateway may reply from a dynamic source port, so
`strict_source_port=False` matches the validated hardware behavior.

## S2000-SP4/24

Four physical S2000-SP4/24 devices were validated as positive controls. Device
creation, stable identity, `via_device`, mapping, relay rows, state, and the
absence of duplicate identity/read evidence were confirmed. No actuator writes
were performed.

## MIP-24 isp.20 (MIP-24-2/P5-R-RS)

A physical MIP-24 isp.20 was detected behind S2000-PP. At Orion unit address 2,
one physical device occupies six consecutive S2000-PP zone-table rows:

| PP row | MIP input | Documented meaning | Integration output | Hardware status |
| ---: | ---: | --- | --- | --- |
| 20 | 0 | Device/global and enclosure tamper state | multistate plus tamper binary sensor | row/input/type confirmed; live state transition deferred |
| 21 | 1 | Output voltage | multistate plus voltage sensor | row/input confirmed; live values deferred |
| 22 | 2 | Output/load current | multistate plus current sensor | row/input confirmed; live values deferred |
| 23 | 3 | Battery voltage and battery condition | multistate plus voltage sensor | row/input confirmed; live values deferred |
| 24 | 4 | Charger condition and battery charge | multistate plus charge sensor | row/input confirmed; live values deferred |
| 25 | 5 | Mains condition and mains voltage | multistate plus voltage sensor | row/input confirmed; live values deferred |

The DEVELOPMENT model treats six consecutive rows as one downstream device. Input 0
is the required type-3 device/global-state row; inputs 1-5 are required type-8
state/numeric rows using
the documented S2000-PP type-8 numeric transaction (FC06 selector 46181 followed
by FC03 result 46328). Values are decoded as unsigned direct-code Q8.8. The
six state, five numeric, and one tamper binary entities share the same stable
device identifier and S2000-PP `via_device`; no control writes are implemented. The six-row
identity/footprint is hardware-derived. State meanings, numeric units and
scales are documentation-derived and have now been confirmed on the local hardware
stand described below.

The MIP manual documents input 0 as the external enclosure-opening detector and
defines case-open and case-restored events. The hardware-confirmed row 20/type 3
provides the lossless primary/expanded state source. The integration preserves
the generic device-state sensor and also derives a dedicated tamper binary
sensor: documented case-open code 149 is on, case-restored code 152 is off, and
absence of either state is unknown. A closed-enclosure/restored state has been
observed on hardware; a live open/restore transition remains deferred because no
tamper operation was authorized.

### Local MIP-24 isp.20 validation

A controlled read-only validation was performed on a local, non-production
S2000-PP 3.01 connected through Modbus RTU on COM3 at 115200 baud, 8N1, slave
ID 2. The live zone table returned the following six rows for one physical MIP
at Orion address 2:

| PP row | Orion address | Input | Partition | PP zone type |
| ---: | ---: | ---: | ---: | ---: |
| 6 | 2 | 0 | 14 | 3 |
| 7 | 2 | 1 | 14 | 8 |
| 8 | 2 | 2 | 14 | 8 |
| 9 | 2 | 3 | 14 | 8 |
| 10 | 2 | 4 | 14 | 8 |
| 11 | 2 | 5 | 14 | 8 |

The grouped primary-state response for rows 6-11 was
`02 03 0C 98 FB C1 C7 C3 FB C8 FB C5 FB 01 FB 08 FC`. The Input 0 expanded
block contained codes 152, 251, and 111. Code 152 confirms the documented
case-restored state for the currently closed enclosure; no tamper transition
was performed.

Each type-8 row was selected once through FC06 register 46181 and read through
FC03 register 46328. All frames below passed RTU CRC validation:

| Input / measurement | Selector TX = RX | Result RX | Raw | Unsigned Q8.8 |
| --- | --- | --- | ---: | ---: |
| 1 / output voltage | `02 06 B4 65 00 07 FF D4` | `02 03 02 1B 30 F6 A0` | `0x1B30` | 27.1875 V |
| 2 / output current | `02 06 B4 65 00 08 BF D0` | `02 03 02 00 70 FD A0` | `0x0070` | 0.4375 A |
| 3 / battery voltage | `02 06 B4 65 00 09 7E 10` | `02 03 02 1B 20 F7 6C` | `0x1B20` | 27.125 V |
| 4 / battery charge | `02 06 B4 65 00 0A 3E 11` | `02 03 02 00 00 FC 44` | `0x0000` | 0.0 % |
| 5 / mains voltage | `02 06 B4 65 00 0B FF D1` | `02 03 02 D4 00 A3 44` | `0xD400` | 212.0 V |

Inputs 3 and 4 initially returned pending response `02 83 0F F1 34`. After a
controlled one-second pause, repeating only FC03 returned the successful values
shown above; no new selector was sent. The other three results were immediately
available. Individual RTU request/response latency was approximately 4.5-6.9 ms;
the grouped state reads took approximately 8 ms for primary and 26-49 ms for the
96-register expanded response. One sequential pass over all five numeric inputs
did not produce an observed S2000-PP/KDL stability problem.

This confirms the selector, result register, input-to-entity mapping and unsigned
Q8.8 decoder without proving that five complete numeric transactions every five
seconds are safe. The DEVELOPMENT implementation therefore uses a device-specific
one-input-per-refresh round-robin. Grouped primary and expanded state remain on
the five-second coordinator cadence. At most one new numeric selector/result pair
is started per refresh, in Input 1-to-5 order, so each measurement normally
refreshes about every 25 seconds while confirmed values for the other inputs stay
cached. A pending selector session remains on the same input and subsequent
refreshes repeat only FC03 until terminal completion.

Before this mitigation, a single MIP could issue 120 numeric Modbus requests per
minute: five selectors and five result reads on each five-second refresh. The
round-robin steady state is approximately 24 numeric requests per minute. With
the two grouped state requests per refresh, total steady-state load is reduced
from approximately 144 to 48 Modbus requests per minute. This cadence is an
integration design choice supported by the observed hardware behavior, not an
official Bolid minimum interval.

The MIP manual also lists temperature, reserve/test duration, measured battery
capacity and remaining battery service time under input 0. The current
S2000-PP documentation does not define Modbus result registers for those MIP
service values, so the integration does not publish synthetic entities for
them.

### MIP device metadata and state-semantics audit

The MIP manual documents software release history (including a target/current
manual release), but this is not evidence of the firmware installed in a
particular connected unit. The S2000-PP 3.01 Modbus service registers 46152 and
46153 identify the S2000-PP itself (type 36 and its firmware version). Its
documented downstream zone table contains Orion address, input, partition and
zone type, while the downstream runtime paths expose state and selected numeric
values. No documented S2000-PP Modbus path was found for the MIP's firmware,
hardware revision, serial number, or exact protocol model ID. Consequently no
metadata probe was sent to the local stand, no MIP version is hardcoded, and
these native Home Assistant DeviceInfo fields remain absent until a documented
per-device read path is available. This limitation adds zero Modbus requests.

The local hardware fixture also protects the input ownership of the observed
primary states. Rows 6-11 decoded respectively to enclosure restored (input 0),
output voltage connected (input 1), output overload restored (input 2), battery
restored (input 3), charger restored (input 4), and mains restored (input 5).
These codes agree with the official input table. In particular, overload state
belongs to input 2, battery state to input 3, charger state to input 4, and
mains state to input 5. A live UI showing those labels on different named
inputs indicates a stale or shifted saved row mapping rather than a different
event-code meaning; the six-row mapping should be revalidated before changing
the state table.

## S2000R-ARR125

State communication was observed with firmware 1.31 after the firmware update.
This is an empirical correlation from the tested chain, not a claim that the
firmware update is the proven sole cause.

## SVK15-3-8-1-B3

Communication and primary/expanded Orion state are hardware validated through
S2000-PP 3.01, an ordinary S2000-KDL at Orion address 20 with current firmware
2.36, and S2000R-ARR125 1.31. This chain does not use S2000-KDL-2I. DPLS
addresses 2 through 5 mapped to S2000-PP rows 1 through 4 on the separately
tested serial gateway; the S2000-KDL firmware version is known and is not a
remaining validation gap.
The observed primary register was `0x27C8`; expanded state included equipment
normal, battery restored, DPLS restored, input communication restored, device
communication restored, and input control enabled.

The numeric water measurement remains unresolved. For valid rows 1 through 4,
the downstream chain accepted the FC06 selector at register 46180 and returned
Modbus exception code 3 for the FC03 read of three registers at 46332. This
confirms communication but does not provide a numeric payload to decode. The
integration therefore preserves a valid state snapshot and publishes the water
measurement as unknown when this exact optional result-read response occurs;
it clears any stale prior measurement and does not synthesize zero or another
value. Other Modbus errors retain their existing failure semantics.

Exception code 3 was also reproduced independently of Home Assistant, Modbus
Devices, RTU over UDP, and the production network path. A local physical
S2000-PP with Modbus slave ID 2, connected locally over COM3, was queried
manually with Modbus Poll for PP zone 1. The selector returned an exact FC06
echo:

```text
Tx: 02 06 B4 64 00 01 2E 16
Rx: 02 06 B4 64 00 01 2E 16
```

The subsequent counter-result request returned exception code 3:

```text
Tx: 02 03 B4 FC 00 03 E2 38
Rx: 02 83 03 F1 31
```

Repeating the FC03 result read after waiting produced the same exception. This
evidence separates the unresolved downstream counter/configuration response
from the integration polling-rate issue; reducing the polling rate is not
expected to make exception code 3 itself succeed.

A controlled local serial diagnostic subsequently reconstructed the complete
S2000-PP zone table read-only. The local endpoint was COM3 at 115200 baud, 8N1,
Modbus slave ID 2. Holding registers identified device type 36 and firmware
301, confirming S2000-PP 3.01. The relevant configured rows were:

| PP row | Orion address | Input | Partition | PP zone type |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 20 | 2 | 1 | 7 |
| 2 | 20 | 3 | 1 | 7 |
| 3 | 20 | 4 | 1 | 7 |
| 4 | 20 | 5 | 1 | 7 |

Row 5 was a separate type-6 numeric object at Orion address 3, input 51. It
provided a positive control: both the documented 46179/46328 selector path and
direct register 30004 returned Q8.8 value `0x14B0` (20.6875), while the IEEE754
register pair at 31008 returned the same value. This confirms that the local
Modbus link, S2000-PP numeric selector machinery, and Orion numeric retrieval
work in general.

All four configured type-7 rows were tested individually without cyclic
polling. Rows 1, 2, and 4 initially returned exact FC06 selector echoes. Row 3,
which was then in device-communication-lost state, initially returned exception
code 15 to the selector; after its primary state recovered to `0x27C8`, the same
selector returned an exact echo. Every counter-result read for rows 1 through 4
returned the same exception response:

```text
Tx: 02 03 B4 FC 00 03 E2 38
Rx: 02 83 03 F1 31
```

For valid-state row 2, independent selector/result series used immediate,
approximately 1-second, 5-second, 15-second, and 60-second delays. Every result
was the same exception code 3; no six-byte counter payload was obtained. This
rules out preparation time up to 60 seconds and a simple PP-row numbering error.
Response times remained approximately 105–131 ms. Isolated requests caused no
observed KDL slowdown or loss of responsiveness. During the diagnostic, rows 3
and 4 recovered from device-communication-lost to primary `0x27C8`; row 1
remained in device-communication-lost state.

The Modbus read-only interface cannot establish whether the KDL currently holds
an accumulated counter total for each ASR1. The next diagnostic boundary is to
verify in ARM Resource that each radio meter has a current reading, initial
reading, serial identity, and recent transfer through ARR125, and that the KDL
counter total changes after the configured threshold is crossed. No
undocumented protocol was used to imitate those Resource operations.

During hardware validation, adding an SVK device was reproducibly correlated
with instability of the ordinary S2000-KDL 2.36; removing the device restored
stable operation. The previous integration behavior started the optional
counter selector transaction on every five-second coordinator refresh. With
four SVK devices this could produce up to 48 new counter selectors, or 96
physical counter-path Modbus requests, per minute.

As a DEVELOPMENT mitigation for the next hardware-validation stage, primary
and expanded state remain on the five-second cadence while each SVK starts a
new optional counter transaction no more than once per 60 seconds. This reduces
the expected steady-state maximum for four SVK devices to approximately four
new selectors per minute. Pending transactions may still retry only their
result read on the normal coordinator cadence. The 60-second interval is a
validation policy, not an official Bolid timing requirement. The final interval
will be reconsidered after numeric measurements work and hardware stability is
confirmed.
# С2000-ВТ development audit

Official Bolid documentation identifies one physical С2000-ВТ (or
С2000-ВТ исп.01) as two logical DPLS devices: `С2000-ВТ Т` for temperature and
`С2000-ВТ В` for relative humidity. Their addresses are always adjacent, with
the humidity address equal to the temperature address plus one. The integration
therefore treats the lower temperature address as the stable physical base and
requires both S2000-PP zone-type-6 rows before exposing the device.

The documented S2000-PP numeric path is selector register 46179 followed by one
register at 46328. The returned temperature or humidity value is signed Q8.8.
State reads remain grouped on the normal 5-second coordinator cadence. Numeric
reads use a device-specific two-channel round robin: at most one new
selector/result transaction per refresh, so each value is normally refreshed
about every 10 seconds. A pending result is completed on later refreshes without
sending a second selector. This cadence is an integration load policy, not an
official Bolid minimum interval.

Previous partial mappings could expose only temperature or only humidity and
could lead users to attempt a second overlapping Config Flow. Setup now repairs
a single old partial entry only when the current read-only S2000-PP table contains
one unambiguous adjacent pair for the saved Orion address and DPLS base. Missing
or ambiguous pairs require reconfiguration instead of guessed ownership.

Documentation confirms temperature range -30…+55 °C, humidity range 0…100%,
and measurements produced once per second by the physical sensor. No downstream
firmware, hardware revision, or serial-number path is documented through the
S2000-PP mapping used here, so native DeviceInfo metadata remains unset. The
current official product/manual does not document an enclosure tamper exposed
through these two measurement channels; no synthetic tamper entity is created.

The controlled validation below records the two PP rows, primary and expanded
states, one selector/result exchange for each channel, raw Q8.8 values, pending
responses and transaction latency. No configuration or actuator writes were
performed.

### Local С2000-ВТ / С2000-ВТИ validation

A controlled non-production Modbus RTU validation was completed against a local
S2000-PP 3.01 at 115200 baud, 8N1, slave ID 2. The read-only FC04 configuration
response confirmed the following actual table; ownership is based on Orion plus
DPLS identity, not on assumed PP-row adjacency:

| Physical device | PP row | Orion | DPLS | Partition | PP zone type |
| --- | ---: | ---: | ---: | ---: | ---: |
| С2000-ВТ #1 temperature | 5 | 3 | 51 | 1 | 6 |
| С2000-ВТ #1 humidity | 6 | 3 | 52 | 1 | 6 |
| С2000-ВТ #2 temperature | 7 | 3 | 53 | 1 | 6 |
| С2000-ВТ #2 humidity | 8 | 3 | 54 | 1 | 6 |
| С2000-ВТИ temperature | 9 | 3 | 55 | 1 | 6 |
| С2000-ВТИ humidity | 10 | 3 | 56 | 1 | 6 |

The grouped primary registers for rows 5-10 were respectively `4EC8`, `48C8`,
`4E2F`, `482F`, `4E2F`, and `482F`. Expanded state blocks preserved the separate
temperature/humidity routing. Rows 5/6 included codes 78/72, 200, 47, 188, 251,
111; rows 7-10 included 78/72, 47, 188, 251, 111.

All six documented FC06 46179 → FC03 46328 transactions returned valid signed
Q8.8 measurements:

| Device/channel | Raw | Decoded |
| --- | ---: | ---: |
| С2000-ВТ #1 temperature | `0x13F0` | 19.9375 °C |
| С2000-ВТ #1 humidity | `0x3960` | 57.375 % |
| С2000-ВТ #2 temperature | `0x1440` | 20.25 °C |
| С2000-ВТ #2 humidity | `0x3CC0` | 60.75 % |
| С2000-ВТИ temperature | `0x1440` | 20.25 °C |
| С2000-ВТИ humidity | `0x3C40` | 60.25 % |

The first VT temperature result was ready immediately. Rows 6-10 returned
exception code 15 on the immediate result read and were ready after one
result-only retry about 500 ms later; no selector was repeated. Complete response
latency was approximately 4-12 ms after the first transaction, with the initial
selector taking about 24 ms. CRC was valid for every logged request and response.
This supports the 5-second, two-channel round robin without an additional
cooldown: a pending result remains parked and is completed on the next refresh.

The ordinary two-address С2000-ВТИ therefore shares the validated VT state,
numeric, pending and presentation lifecycle. С2000-ВТИ исп.01 is a distinct
three-address model whose third channel is CO; it remains explicitly unsupported
until that full footprint and CO numeric path are separately hardware validated.
No case-open/tamper channel or downstream firmware/serial metadata path was
observed or documented through these PP rows.

# C2000-DZ / C2000R-DZ quiescent validation

Official Bolid documentation and a controlled read-only local S2000-PP capture
confirm that the wired `C2000DZ` and ordinary radio `C2000RDZ` are distinct
physical products. The radio product is not a firmware variant of the wired
product. `C2000R-DZ isp.01` is also distinct and remains unsupported until its
S2000-PP footprint is validated.

The FC04 configuration table at address 40 confirmed these rows:

| PP rows | Product | Orion | DPLS | Partition | PP zone type |
| --- | --- | ---: | --- | ---: | ---: |
| 11-12 | two ordinary C2000R-DZ units | 20 | 53-54 | 20 | 1 |
| 13-14 | two wired C2000-DZ 1.10 units | 20 | 55-56 | 24 | 1 |

Partition values 20 and 24 are configuration grouping only and are not used as
equipment identity. Both products use one observed zone-type-1 row per physical
detector.

Both ordinary radio units returned primary `0x50C8` (codes 80 and 200) and
expanded states `80, 200, 213, 47, 188, 251, 111`. This hardware-confirms the
quiescent main-battery-restored code 200 and reserve-battery-restored code 213
for ordinary C2000R-DZ through the current downstream chain. Both wired 1.10
units returned primary `0x502F` (codes 80 and 47) and expanded states
`80, 47, 188, 251, 111`; no battery entities are exposed for the wired product.

The implementation preserves a raw multistate sensor for both products and
adds the documented 79/80 water semantic. Ordinary C2000R-DZ additionally
exposes separate unknown-preserving main and reserve battery state sensors.
Documented candidate low/fault codes remain mapping definitions only; no active
battery transition has been hardware validated.

Flood, tamper, communication-loss, main-battery fault/low, reserve-battery low,
and transition priority behavior remain deferred for a separate controlled
active-validation session. Earlier attempts made with the wrong physical
detectors are permanently excluded from hardware evidence and regression
fixtures. The later quiescent reading of the correct rows is not evidence of
active flood behavior.

# C2000-SMK isp.04 / C2000R-SMK quiescent validation

Official Bolid documentation and a controlled read-only local S2000-PP capture
confirm that wired `C2000SMK` (`С2000-СМК исп.04`) and radio `C2000RSMK`
(`С2000Р-СМК`) are separate physical products. The wired execution uses one
DPLS address and has no battery, reserve battery, radio, or documented tamper
capability. The radio detector is represented through an ARR/KDL chain, has one
ER14505M 3.6 V battery, and supports additional physical capabilities whose
S2000-PP routing has not yet been actively validated. Neither documented
firmware family is published as runtime `sw_version` because the downstream
firmware is not read through this path.

The FC04 configuration table confirmed these rows:

| PP row | Product | Orion | DPLS | Partition | PP zone type |
| ---: | --- | ---: | ---: | ---: | ---: |
| 15 | C2000-SMK isp.04 | 3 | 33 | 8 | 1 |
| 16 | C2000-SMK isp.04 | 3 | 34 | 8 | 1 |
| 17 | C2000R-SMK | 3 | 35 | 11 | 1 |
| 18 | C2000R-SMK | 3 | 36 | 12 | 1 |

Partition is configuration grouping only and is not product identity. All four
observed contact rows use PP zone type 1. Persisted mappings are reconciled at
setup by exact Orion and DPLS identity plus zone type, using the shared cached
configuration snapshot; no request is added to the five-second polling loop.

Both wired units returned primary `0x6D2F` (codes 109 and 47) and expanded
states `109, 47, 188, 251, 111`. Both radio units returned primary `0x6DC8`
(codes 109 and 200) and expanded states `109, 200, 47, 188, 251, 111`. Code 200
(`battery_restored`) is therefore hardware-confirmed in the quiescent state for
both radio detectors; reserve-battery code 213 was absent, consistently with
the documented single-battery product. Codes 47, 188, and 251 remain generic
downstream communication states and are not presented as radio-quality data.

All four configured inputs were disarmed during the capture. Consequently code
109 is preserved losslessly but is not treated as hardware evidence of the
physical magnet/contact position. Phase 1 exposes no derived opening binary
sensor. The radio product adds one unknown-preserving battery-state sensor;
codes 202 and 211 are documentation-derived candidates and have not been
hardware-confirmed in active fault transitions. There is no reserve-battery
entity.

Active opening/closing, tamper, anti-sabotage, radio-loss, battery-fault/low and
optional external-input routing remain deferred for a controlled validation
session. No active-transition fixture or semantic claim is derived from this
quiescent capture.

# C2000R-VTI five-device quiescent and numeric validation

Official Bolid documentation and a controlled native Modbus RTU capture on
COM3 confirm that `C2000RVTI` (`С2000Р-ВТИ`) is a separate radio product, not a
variant or alias of wired `C2000VTI`. One ordinary physical device owns two
consecutive DPLS zones: the base address is temperature and base+1 is humidity.
Both capabilities use PP zone type 6 on the validated S2000-PP path. The radio
product has one ER14505 3.6 V battery; no reserve-battery entity is created.

The FC04 configuration table contained five physical devices:

| Unit | PP temperature/humidity rows | Orion | DPLS pair | Partition | PP type |
| ---: | --- | ---: | --- | ---: | ---: |
| 1 | 19 / 20 | 8 | 4 / 5 | 0 | 6 / 6 |
| 2 | 21 / 22 | 8 | 6 / 7 | 0 | 6 / 6 |
| 3 | 23 / 24 | 8 | 8 / 9 | 0 | 6 / 6 |
| 4 | 25 / 26 | 8 | 10 / 11 | 0 | 6 / 6 |
| 5 | 27 / 28 | 8 | 12 / 13 | 0 | 6 / 6 |

Orion 8 and partition 0 describe this stand only. Runtime reconciliation uses
the configured Orion address, base/base+1 DPLS identities, and zone type 6;
partition and PP-row adjacency are not identity.

Temperature rows returned primary `0x4EC8`, while humidity rows returned
`0x48C8`. Expanded states contained temperature-normal code 78 or level-normal
code 72, battery-restored code 200, and generic downstream codes 47 and 188.
Codes 251 and 111 were present where captured; code 251 remains the generic
device-communication-restored state and is not relabelled as radio quality.
Reserve-battery-restored code 213 was absent. Code 200 was present on both
logical rows of all five devices and is aggregated into one physical
`main_battery_state` entity.

Numeric acquisition used FC06 register 46179 with the actual PP row, followed
by FC03 register 46328 count 1. Signed Q8.8 values included `0x1A00 = 26.0 °C`,
`0x2000 = 32.0 %`, `0x17C0 = 23.75 °C`, and `0x2630 = 38.1875 %`. Immediate
result reads normally returned documented exception 15; result-only retries
became ready in approximately 0.52-0.70 seconds in the typical cases, with a
worst successful observation of 1.852 seconds. These observations do not add a
fixed delay to runtime polling; the shared S2000-PP selector session is used.

Native serial FC03 exception 4 was reproduced after `15 -> 15`; another
result-only read remained exception 4, while a fresh selector in a later
transaction recovered to READY. It remains a terminal typed protocol error,
not PENDING: grouped states and the last-known-good numeric cache are preserved,
the matching selector owner is released, and a later coordinator cycle can
start a fresh acquisition. FC03 exception 3 was observed previously in
production RTU-over-UDP but was not reproduced in this COM3 phase; its root
cause remains unresolved. The exact device-side cause of exception 4 also
remains unresolved.

Active battery-low/fault transitions, product-specific radio loss/quality,
tamper routing, runtime firmware/serial metadata, and `С2000Р-ВТИ исп.01`
CO/sounder capabilities remain deferred. No active-transition fixture or
radio-quality entity is inferred from the quiescent generic state codes.
