# Zuked 310-4.0S1 deep protocol audit

## Evidence and scope

**DOCUMENTED FACT.** The canonical source is the user-supplied scan
`Zuked_310-4.0S1_User_Manual_A4.pdf`, *General-purpose AC Drive*, document
XM-H0127, version V1.4, start date 2023-09-23. The audited file has SHA-256
`744a44bd47008c5f30b915eccb01af1c1adb554a92680d6cfb1c59d6f0085f6b`.
No register map from another drive or Internet source was used.

**CURRENT IMPLEMENTATION.** One physical drive is one `Zuked3104S1`
equipment object and one Home Assistant Device. Manufacturer is `Zuked`, model
is `310-4.0S1`; manual version is reference evidence and is not runtime
firmware. Serial, firmware and hardware revision are not fabricated.

## Physical and communication contract

**DOCUMENTED FACT.** RS-485 terminals are `A+` and `B-`. Group `Pd`
(manual pp.31–32) documents:

- Pd-00: 300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600 or
  115200 baud;
- Pd-01: 8N2, 8E1, 8O1 or 8N1;
- Pd-02: address 0 for broadcast and 1–247 for a slave;
- Pd-03: response delay 0–20 ms;
- Pd-04: communication timeout disabled at 0.0 or 0.1–60.0 s;
- Pd-05: non-standard or standard Modbus mode;
- Pd-06: current-reading resolution, 0.01 A (up to 55 kW) or 0.1 A.

The scan therefore contradicts descriptions of Pd-06 as a response setting.
It also maps Pd-00 value 5 to 9600 baud and value 6 to 19200 baud. The supplied
statement that 19200 corresponds to Pd-00=5 is not supported by this canonical
scan and cannot be treated as a powered-device fixture.
No communication parameter is read or written automatically.

## Hardware-verified Modbus read boundary

**HARDWARE VERIFIED, 2026-09-01.** A powered 310-4.0S1 was observed through
native Modbus TCP/MBAP at `10.0.2.13:510`, unit ID 3. Four minimal probes
established one unambiguous contract:

| Probe | Result |
|---|---|
| FC03, PDU `0x7000`, count 1 | normal response, raw 0 |
| FC04, PDU `0x7000`, count 1 | exception 1 (illegal function) |
| FC03, PDU `0x6fff`, count 1 | exception 2 (illegal address) |
| FC04, PDU `0x6fff`, count 1 | exception 1 (illegal function) |

The implementation therefore uses FC03 and the manual's hexadecimal address
directly as the PDU address. It has no FC04 or minus-one fallback and does not
probe alternatives during normal polling.

The lossless capture is outside the repository at
`C:\Users\Dmitriy\AppData\Local\Temp\zuked_310_4_0s1_phase1_unit3_20260901.jsonl`,
SHA-256
`B4F497E4B48D517574BAFFC55F23898E4F5123C55DD9C690CFEEA4F1492F4436`.

## U0 monitoring map

**DOCUMENTED FACT.** Manual pp.34–35 define U0-00…U0-65. The complete
address/scale catalogue is retained in `equipment/zuked.py`. Reserved `Retain`
words U0-08, U0-39, U0-40 and U0-42 are never entities. Core entities are:

| Parameter | Address | Entity | Scale/unit |
|---|---:|---|---|
| U0-00 | 7000H | Running frequency | 0.01 Hz |
| U0-01 | 7001H | Set frequency | 0.01 Hz |
| U0-02 | 7002H | Bus voltage | 0.1 V |
| U0-03 | 7003H | Output voltage | 1 V |
| U0-04 | 7004H | Output current | 0.01 A |
| U0-05 | 7005H | Output power | 0.1 kW |
| U0-06 | 7006H | Output torque | 0.1 % |
| U0-25 | 7019H | Current power-on time | 1 min |
| U0-26 | 701AH | Current running time | 0.1 min |
| U0-45 | 702DH | Fault information | raw/lossless |
| U0-61 | 703DH | Drive status | raw/lossless |
| U0-62 | 703EH | Current fault code | ErrXX decoder |

Advanced U0 values remain documented metadata rather than an uncontrolled
register dump.

### U0-04 translation inconsistency

**INFERENCE FROM THE SAME MANUAL.** U0-04 is labelled “Output power (A)”, but
its unit and resolution are amperes while adjacent U0-05 is explicitly output
power in kW. The truthful semantic candidate is output current. A final
non-zero keypad comparison remains an optional semantic confirmation.

Hardware proved that `0x7004` is readable and returned raw 0 on the stopped,
unloaded drive. This does not yet prove the non-zero current scale against a
running motor; that optional validation does not block the documented entity.

### Status and faults

**DOCUMENTED FACT.** U0-61 is named “Frequency converter status”, but the
manual supplies no value table. Values therefore remain `unknown_<raw>`; no
running/stopped/direction state is invented.

**DOCUMENTED FACT.** Chapter Five (manual pp.36–40) defines Err02–Err19,
Err21, Err23, Err26–Err31, Err40–Err43, Err55 and Err64–Err66. U0-62 decodes
only those values and preserves every other word as `unknown_fault_<raw>`.
U0-45 “Fault information” has no documented relationship to U0-62 and remains
a distinct lossless diagnostic (`fault_information_<raw>`).

## Hardware fixtures, grouping and read safety

Individual FC03 reads returned U0-00=0, U0-01=146, U0-02=3047, U0-03=0,
U0-04=0, U0-05=0, U0-06=0, U0-61=0 and U0-62=0. The non-zero bus-voltage
fixture decodes to 304.7 V and is strong evidence for register identity and
the documented 0.1 V scale. Raw U0-61 zero remains `unknown_0`; raw U0-62 zero
remains `unknown_fault_0`, because the manual does not define either enum.

A single FC03 `0x7000` count-7 request was accepted and returned
`[0, 147, 3055, 0, 0, 0, 0]`. The immediately preceding individual fixture was
`[0, 146, 3047, 0, 0, 0, 0]`; set frequency and bus voltage are live values and
changed between sequential snapshots. This is temporal drift, not an address
or ordering mismatch. Production polling uses this verified core block, plus
individual reads for the selected non-contiguous monitoring words. No large
read across `Retain`, reserved or undocumented gaps was attempted or added.

All hardware operations were reads. Modbus writes and motor commands were
both zero.

## Write safety and omitted capabilities

The supplied manual does not establish a sufficiently precise Modbus command
register/value contract for RUN, STOP, direction, frequency setpoint or fault
reset. The integration exposes no buttons, switches, numbers or startup writes.
Persistent Pd/P* configuration is also deliberately absent. Runtime
temperature is omitted because no direct U0 communication address is
documented.

## Presentation

Profile `zuked_310_4_0s1` generates a native Home Assistant entities card in
semantic order: drive status, frequencies, output electrical values, torque,
bus voltage, fault diagnostics, running time and power-on time. No custom
runtime dashboard wrapper is introduced.
