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
