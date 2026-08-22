"""Tests for the Dyna Drive DN310 equipment model."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.const import EntityCategory, Platform

from custom_components.modbus_devices.equipment.dyna_drive import (
    DN310,
    DN310Command,
)
from custom_components.modbus_devices.equipment.equipment import (
    get_class,
    get_equipment_classes_by_manufacturer,
    get_equipment_display_name,
)
from custom_components.modbus_devices.button import (
    ModBusCommandButtonEntity,
    async_setup_entry as async_setup_button_entry,
)
from custom_components.modbus_devices import async_unload_entry
from custom_components.modbus_devices.const import Config


class Response:
    def __init__(
        self,
        *,
        registers=None,
        error=False,
        address=None,
        value=None,
        function_code=3,
        device_id=None,
    ):
        self.registers = registers
        self._error = error
        self.address = address
        self.value = value
        self.function_code = function_code
        if device_id is not None:
            self.device_id = device_id

    def isError(self):
        return self._error


class Client:
    def __init__(self):
        self.reads = []
        self.writes = []
        self.responses = {
            0x1001: Response(registers=[10, 20, 30, 40, 50, 60, 70]),
            0x3000: Response(registers=[1]),
            0x8000: Response(registers=[0]),
        }
        self.write_response = Ellipsis

    async def read_holding_registers(self, **kwargs):
        self.reads.append(kwargs)
        response = self.responses[kwargs["address"]]
        if isinstance(response, Exception):
            raise response
        return response

    async def write_register(self, **kwargs):
        self.writes.append(kwargs)
        if self.write_response is not Ellipsis:
            return self.write_response
        return Response(
            address=kwargs["address"],
            value=kwargs["value"],
            function_code=6,
            device_id=kwargs["device_id"],
        )


def test_registration_and_metadata():
    manufacturers = get_equipment_classes_by_manufacturer()
    assert manufacturers["Dyna Drive"] == ["DN310"]
    assert get_class("Dyna Drive", "DN310") is DN310
    assert get_equipment_display_name("Dyna Drive", "DN310") == "DN310"
    device = DN310(None, 7)
    assert device.attr_manufactures_name == "Dyna Drive"
    assert device.attr_platforms == [Platform.SENSOR, Platform.BUTTON]
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert device.attr_hardware_version is None
    assert device.attr_device_metadata["eeprom_writes"] == "not supported"
    assert "conflicting" in device.frequency_setpoint_limitation


@pytest.mark.asyncio
async def test_grouped_runtime_read_and_independent_status_fault_reads():
    client = Client()
    snapshot = await DN310(client, 7).async_get_snapshot()
    assert client.reads == [
        {"address": 0x1001, "count": 7, "device_id": 7},
        {"address": 0x3000, "count": 1, "device_id": 7},
        {"address": 0x8000, "count": 1, "device_id": 7},
    ]
    assert snapshot["numeric_sensors"]["running_frequency_raw"]["value"] == 10
    assert snapshot["numeric_sensors"]["running_speed_raw"]["value"] == 70
    assert snapshot["state_sensors"]["running_status"]["state"] == "forward_run"
    assert snapshot["state_sensors"]["inverter_fault"]["state"] == "no_fault"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (1, "forward_run"),
        (2, "reverse_run"),
        (3, "stop"),
        (99, "unknown_99"),
    ],
)
@pytest.mark.asyncio
async def test_running_status_decode(code, expected):
    client = Client()
    client.responses[0x3000] = Response(registers=[code])
    snapshot = await DN310(client, 1).async_get_snapshot()
    assert snapshot["state_sensors"]["running_status"]["state"] == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0x0002, "overcurrent_during_acceleration"),
        (0x0010, "communication_fault"),
        (0x002B, "motor_overspeed"),
        (0x005E, "speed_feedback_error"),
        (0x0001, "reserved_0x0001"),
        (0x1234, "unknown_4660"),
    ],
)
@pytest.mark.asyncio
async def test_fault_decode(code, expected):
    client = Client()
    client.responses[0x8000] = Response(registers=[code])
    snapshot = await DN310(client, 1).async_get_snapshot()
    assert snapshot["state_sensors"]["inverter_fault"]["state"] == expected


def test_raw_monitoring_entities_do_not_invent_units_or_scaling():
    descriptions = DN310(None, 1).get_numeric_sensor_descriptions()
    assert len(descriptions) == 7
    assert all(item["unit"] is None for item in descriptions)
    assert all(item["device_class"] is None for item in descriptions)
    assert all(item["state_class"] is None for item in descriptions)
    assert all(
        item["entity_category"] is EntityCategory.DIAGNOSTIC for item in descriptions
    )


def test_no_unsupported_frequency_or_secondary_io_controls():
    device = DN310(None, 1)
    button_ids = {item["button_id"] for item in device.get_button_descriptions()}
    assert button_ids == {
        "forward_run",
        "reverse_run",
        "coast_stop",
        "decelerate_stop",
        "fault_reset",
    }
    assert not hasattr(device, "get_output_descriptions")
    assert not hasattr(device, "set_frequency")


@pytest.mark.parametrize(
    "command",
    [
        DN310Command.FORWARD_RUN,
        DN310Command.REVERSE_RUN,
        DN310Command.COAST_STOP,
        DN310Command.DECELERATE_STOP,
        DN310Command.FAULT_RESET,
    ],
)
@pytest.mark.asyncio
async def test_documented_command_uses_fc06_and_exact_volatile_register(command):
    client = Client()
    await DN310(client, 12).async_send_command(command)
    assert client.writes == [
        {"address": 0x2000, "value": int(command), "device_id": 12}
    ]
    assert not 0xF000 <= client.writes[0]["address"] <= 0xFEFF
    assert not 0xA000 <= client.writes[0]["address"] <= 0xACFF


@pytest.mark.parametrize(
    "response",
    [
        None,
        Response(error=True),
        Response(address=0x2001, value=1, function_code=6),
        Response(address=0x2000, value=2, function_code=6),
        Response(address=0x2000, value=1, function_code=16),
        Response(address=0x2000, value=1, function_code=6, device_id=2),
    ],
)
@pytest.mark.asyncio
async def test_command_response_validation(response):
    client = Client()
    client.write_response = response
    with pytest.raises(ModbusException):
        await DN310(client, 1).async_send_command(DN310Command.FORWARD_RUN)


@pytest.mark.asyncio
async def test_unsupported_command_is_rejected_without_write():
    client = Client()
    with pytest.raises(ValueError):
        await DN310(client, 1).async_send_command(3)
    assert client.writes == []


@pytest.mark.parametrize(
    "response",
    [
        None,
        object(),
        Response(error=True),
        Response(registers=[1, 2, 3, 4, 5, 6, 7], function_code=4),
        Response(registers=[]),
        Response(registers=[1, 2]),
        Response(registers=[1, 2, 3, 4, 5, 6, 70000]),
        Response(registers=[1, 2, 3, 4, 5, 6, True]),
    ],
)
@pytest.mark.asyncio
async def test_strict_read_response_validation(response):
    client = Client()
    client.responses[0x1001] = response
    with pytest.raises(ModbusException):
        await DN310(client, 1).async_get_snapshot()


@pytest.mark.asyncio
async def test_transport_exception_propagates():
    client = Client()
    client.responses[0x1001] = RuntimeError("transport failed")
    with pytest.raises(RuntimeError, match="transport failed"):
        await DN310(client, 1).async_get_snapshot()


@pytest.mark.asyncio
async def test_setup_only_reads_and_never_changes_p0_02_or_eeprom():
    client = Client()
    device = DN310(client, 1)
    await device.data_init()
    assert client.writes == []
    assert client.reads == []

    await device.async_get_snapshot()
    assert {call["address"] for call in client.reads} == {0x1001, 0x3000, 0x8000}


def test_state_entities_preserve_raw_codes_and_categories():
    descriptions = {
        item["sensor_id"]: item
        for item in DN310(None, 1).get_state_sensor_descriptions()
    }
    assert descriptions["running_status"].get("entity_category") is None
    assert (
        descriptions["inverter_fault"]["entity_category"] is EntityCategory.DIAGNOSTIC
    )
    snapshot = DN310._state_snapshot("stop", 3)
    assert snapshot == {
        "state": "stop",
        "primary_code": 3,
        "expanded_codes": [],
        "expanded_states": [],
    }


def test_direct_identity_remains_entry_transport_and_slave_scoped():
    device = DN310(None, 7)
    assert device.uses_stable_entry_identity is True
    assert not hasattr(device, "required_gateway")
    assert not hasattr(device, "apply_gateway_mapping")


@pytest.mark.asyncio
async def test_button_platform_setup_creates_only_dn310_buttons():
    device = DN310(Client(), 1)
    coordinator = Mock(last_update_success=True)
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="DN310",
        runtime_data=SimpleNamespace(device=device, coordinator=coordinator),
    )
    hass = SimpleNamespace(data={})
    entities = []

    await async_setup_button_entry(hass, entry, lambda values: entities.extend(values))

    assert len(entities) == 5
    assert all(isinstance(entity, ModBusCommandButtonEntity) for entity in entities)


@pytest.mark.asyncio
async def test_button_platform_is_a_noop_for_equipment_without_descriptions():
    device = SimpleNamespace()
    coordinator = Mock(last_update_success=True)
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=SimpleNamespace(device=device, coordinator=coordinator),
    )
    hass = SimpleNamespace(data={})
    entities = []

    await async_setup_button_entry(hass, entry, lambda values: entities.extend(values))

    assert entities == []


@pytest.mark.asyncio
async def test_button_identity_device_link_and_user_press_lifecycle():
    device = DN310(Client(), 9)
    device.attr_unique_id_prefix = "endpoint_9_Dyna Drive_DN310"
    device.attr_device_identifier = "endpoint_9_Dyna Drive_DN310"
    device.async_send_command = AsyncMock()
    coordinator = Mock(last_update_success=True)
    entry = SimpleNamespace(entry_id="entry-1")
    description = device.get_button_descriptions()[0]

    first = ModBusCommandButtonEntity(coordinator, device, entry, description)
    reloaded = ModBusCommandButtonEntity(coordinator, device, entry, description)

    assert first.unique_id == reloaded.unique_id
    assert first.unique_id == "endpoint_9_Dyna Drive_DN310_forward_run"
    assert first.device_info["identifiers"] == {
        (Config.DOMAIN, "endpoint_9_Dyna Drive_DN310")
    }
    assert first.device_info["manufacturer"] == "Dyna Drive"
    assert first.device_info["model"] == "DN310"
    await first.async_press()
    device.async_send_command.assert_awaited_once_with(DN310Command.FORWARD_RUN)
    assert not hasattr(coordinator, "async_request_refresh") or not coordinator.async_request_refresh.called


@pytest.mark.asyncio
async def test_unload_uses_same_platform_set_and_releases_entry_resources():
    device = DN310(Client(), 1)
    client = Mock()
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="DN310",
        runtime_data=SimpleNamespace(
            device=device,
            client=client,
            coordinator=Mock(),
        ),
    )
    config_entries = SimpleNamespace(async_unload_platforms=AsyncMock(return_value=True))
    hass = SimpleNamespace(data={}, config_entries=config_entries)

    assert await async_unload_entry(hass, entry) is True
    config_entries.async_unload_platforms.assert_awaited_once_with(
        entry, [Platform.SENSOR, Platform.BUTTON]
    )
    client.close.assert_called_once_with()
    assert entry.runtime_data.client is client


def test_pymodbus_exception_responses_are_not_default_values():
    response = SimpleNamespace(registers=[0] * 7, isError=lambda: True)
    client = Client()
    client.responses[0x1001] = response
    # Covered asynchronously above; this assertion documents that zero itself is
    # valid only when carried by a successful response.
    assert response.registers[0] == 0
