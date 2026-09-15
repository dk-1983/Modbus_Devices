# Modbus Devices 1.1.0 — Climate Control and RTU over TCP

Modbus Devices 1.1.0 introduces its first Home Assistant **climate entities**,
bringing climate control to the integration alongside its existing industrial
and building-automation devices.

## Climate control

- **Haier YCJ-A002:** power, HVAC mode, target and current temperature, fan
  mode, and fault/lock diagnostics.
- **Daikin RTD-RA:** power, HVAC mode, target and current temperature, automatic
  fan mode and five fan speeds, louvre swing, fault diagnostics, and a separate
  diagnostic coil-inlet temperature sensor.
- **Dedicated device-card profiles:** YCJ-A002 presents its primary climate
  control; RTD-RA places climate control first and coil-inlet temperature in
  the diagnostic section. Cards are added manually through the optional
  Modbus Device card generator.

## Modbus RTU over TCP

The new transport supports transparent **RAW TCP gateways**, carrying complete
Modbus RTU ADUs with CRC and no MBAP header. It handles TCP fragmentation and
strictly validates response framing, CRC, slave ID, function, byte count and
write acknowledgements. Requests retain the existing `SerializedModbusClient`
serialization; failed commands are not automatically replayed.

Existing Modbus RTU over UDP behavior is unchanged.

## Hardware validation

A physical **Haier YCJ-A002 successfully operates in Home Assistant through
the new Modbus RTU over TCP transport** using
[4VRS Gateway](https://github.com/dk-1983/moxa-serial-server) in RAW TCP mode
at `10.0.2.13:502`, slave ID `1`. These are validation-setup parameters, not
required defaults for other installations.

The displayed `rtu_over_tcp` translation key was a frontend-cache issue and
resolved after refreshing the page. Production configuration was not changed.

Both climate models have automated protocol, entity and device-card coverage.
Daikin RTD-RA has not yet been hardware-validated.

## Upgrade

**No configuration migration is required.** Update the integration and restart
Home Assistant. Existing entries retain their current transport and configuration.
Select Modbus RTU over TCP when adding equipment through a transparent RAW TCP
gateway. Refresh the browser page if it shows a cached transport label.

Equipment setup and register references are documented in the
[English README](../README.md) and [Russian README](../README_RU.md).
The [RTU-over-TCP validation record](rtu_over_tcp.md) describes framing and
recovery behavior and the confirmed hardware setup.
