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
