"""Public Config Flow defaults must not expose development-bench endpoints."""

from homeassistant.const import CONF_HOST, CONF_PORT
import pytest

from custom_components.modbus_devices.config_flow import ModbusDevicesConfigFlow
from custom_components.modbus_devices.const import Config


def _schema_fields(result):
    return {marker.schema: marker for marker in result["data_schema"].schema}


@pytest.mark.asyncio
async def test_native_network_defaults_use_documentation_endpoint():
    """Use an IANA documentation address and the standard Modbus port."""
    fields = _schema_fields(await ModbusDevicesConfigFlow().async_step_network())

    assert fields[CONF_HOST].default() == "192.0.2.1"
    assert fields[CONF_PORT].default() == 502


@pytest.mark.asyncio
async def test_rtu_over_udp_default_host_is_not_a_bench_endpoint():
    """Keep gateway-specific ports while using a neutral public host default."""
    fields = _schema_fields(await ModbusDevicesConfigFlow().async_step_rtu_over_udp())

    assert fields[CONF_HOST].default() == "192.0.2.1"
    assert fields[Config.CONF_REMOTE_PORT].default() == 40000
    assert fields[Config.CONF_LOCAL_UDP_PORT].default() == 40000
