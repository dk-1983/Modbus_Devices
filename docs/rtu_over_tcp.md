# Modbus RTU over TCP — v1.1.0 validation

## Scope

Transport implementation: `8f4bc60`, introduced in v1.1.0. Development baseline:
`41ffb7e`. Relevant local history:

- `6bd2b62`: YCJ-A002 climate support, zero-based map and serialized mode/power writes.
- `d31026a`: RTU-over-UDP stale-response recovery; this transport remains unchanged.
- `c502823`: runtime architecture update.

The new `rtu_over_tcp` mode uses a separate `ModbusRtuOverTcpClient`, wrapped by
the existing `SerializedModbusClient`. It sends full RTU ADUs, including CRC,
through the configured RAW TCP endpoint. There is no MBAP header. No changes to
YCJ-A002 register addressing or equipment behavior are needed.

Existing configurations require no migration. The new transport is an additional
config-flow choice; existing TCP, UDP and serial entries retain their transport.

The TCP module keeps its codec independent of the UDP implementation to avoid
changing UDP behavior in this narrowly scoped addition. CRC wire order and RTU
ADU limits follow the [Modbus serial line specification](https://www.modbus.org/file/secure/modbusoverserial.pdf).

## Framing and recovery

- Supports FC01/02/03/04 reads and FC05/06/16 writes.
- Buffers fragments across TCP reads; caps retained input at 257 bytes
  (one maximum RTU ADU plus an overflow marker byte).
- Validates response length, CRC, slave ID, function, requested byte count,
  bit padding, exception code, and write address/value/count echo.
- Uses one deadline for connection establishment and the complete exchange.
- Closes the stream on invalid/trailing data, timeout, cancellation, or
  incomplete EOF. No automatic request retries, including writes.
- Reconnects for the next independent request. Explicit `close()` prevents
  implicit reopening until `connect()` is called.
- Rejects buffered unsolicited data before sending a new request.

RTU carries no transaction ID and read responses do not echo the requested
address. Arbitrarily late identical responses cannot be distinguished from
current responses. Closing TCP discards the old stream, but cannot prevent a
gateway from forwarding an old serial response onto a new connection. The
gateway must preserve request/response association and the bus must have one
master. A successful TCP config-flow connection is not a device protocol probe.

## Automated coverage

`tests/test_rtu_over_tcp.py` uses real loopback TCP sockets, including:

- Every response split position and byte-by-byte YCJ-A002 replies.
- CRC reference vector, all supported functions and maximum register reads.
- Wrong slave/function/byte count, bad CRC, MBAP, coalesced duplicate frames,
  trailing data, overflow, invalid exception code and invalid bit padding.
- FC05/06/16 acknowledgement mismatch.
- Timeout, partial response, EOF and cancellation for reads and writes;
  reconnect and no replay; slow fragments under one total deadline.
- Shared client serialization, unsolicited idle data and explicit close.
- YCJ-A002 FC01/03/04 snapshot and FC06+FC05 mode/power sequence through
  `connect_modbus` and `SerializedModbusClient`.

`tests/test_rtu_over_tcp_config_flow.py` covers routing, input validation,
canonical identity, persisted fields, connection failure, cleanup and EN/RU
translations. Existing UDP, common validation, lifecycle and serialization tests
are included in regression runs.

Transport validation on 2026-09-15 (before release preparation):

- Python 3.14, Home Assistant 2026.9.2, pymodbus 3.15.0.
- Full suite: **1336 passed**, five dependency deprecation warnings.
- New TCP transport/config-flow tests: **84 cases** included in that suite.
- Ruff gate: **99 correctness files**, **51 format-clean files**, passed.
  The user-owned untracked probe was excluded from the gate's file inventory;
  all other files and the `HEAD` format-debt comparison were checked.
- `git diff --check`: passed. `rtu_over_udp.py` has no diff.
- Command: `ha-venv/Scripts/python.exe -m pytest tests -q --tb=short --basetemp=.pytest_cache/rtu-tcp-full-314-approved`.
- The full suite required execution outside the Windows sandbox because
  pytest temporary-directory access was denied inside it; the test directory
  remained inside this repository.
- Earlier Python 3.13 / HA 2026.2.3 checks passed the focused transport and
  equipment tests, but that HA version lacked APIs used by existing card tests.
  The successful full-suite result above uses the newer environment.

## Hardware status

Hardware validation confirmed by the user on 2026-09-15:

- A physical YCJ-A002 successfully operates through Modbus RTU over TCP.
- 4VRS Gateway RAW TCP endpoint: `10.0.2.13:502`; slave ID: `1`.
- Home Assistant successfully uses the new integration transport.
- The displayed `rtu_over_tcp` label was caused by the frontend cache and
  was corrected after refreshing the page.
- Production configuration was not changed.
- `scripts/haier_ycj_a002_tcp_probe.py` remains untracked and is excluded
  from this change.
