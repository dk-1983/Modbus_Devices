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
S2000-PP 3.01, S2000-KDL, and S2000R-ARR125 1.31. DPLS addresses 2 through 5
mapped to S2000-PP rows 1 through 4 on the separately tested serial gateway.
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
