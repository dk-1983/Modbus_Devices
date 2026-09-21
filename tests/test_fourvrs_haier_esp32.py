"""Tests for the 4VRS Haier-ESP32 Modbus profile."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from pymodbus.exceptions import ModbusException

from homeassistant.components.climate import HVACMode
from homeassistant.const import Platform

from custom_components.modbus_devices.equipment.fourvrs import HaierESP32
from custom_components.modbus_devices.climate import ModbusClimateEntity
from custom_components.modbus_devices.coordinator import ModbusDeviceCoordinator
from custom_components.modbus_devices.modbus_client import SerializedModbusClient
from custom_components.modbus_devices.select import ModBusSelectEntity
from custom_components.modbus_devices.switch import ModBusDescribedSwitchEntity


def response(
    function_code,
    *,
    registers=None,
    bits=None,
    address=None,
    value=None,
    exception_code=None,
    error=False,
    dev_id=7,
):
    return SimpleNamespace(
        function_code=function_code,
        registers=registers,
        bits=bits,
        address=address,
        value=value,
        exception_code=exception_code,
        dev_id=dev_id,
        isError=lambda: error,
    )


class FakeClient:
    def __init__(self):
        self.calls = []
        self.coils = [True, False, True]
        self.holding = [23, 1, 4, 1, 3, 2, 12, 7]
        self.inputs = [19, 0, 0, 195, 4, 0x5678, 0x1234, 2, 0x0007]
        self.command_statuses = []
        self.main_exception = None
        self.write_response = None
        self.readback_override = None

    async def read_coils(self, **kwargs):
        self.calls.append(("read_coils", kwargs))
        address = kwargs["address"]
        count = kwargs["count"]
        if self.main_exception is not None and address == 0 and count == 3:
            return self.main_exception
        return response(1, bits=self.coils[address : address + count])

    async def read_holding_registers(self, **kwargs):
        self.calls.append(("read_holding_registers", kwargs))
        address = kwargs["address"]
        count = kwargs["count"]
        if self.readback_override is not None and count == 1:
            return response(3, registers=[self.readback_override])
        return response(3, registers=self.holding[address : address + count])

    async def read_input_registers(self, **kwargs):
        self.calls.append(("read_input_registers", kwargs))
        address = kwargs["address"]
        count = kwargs["count"]
        if address == 7 and count == 1 and self.command_statuses:
            return response(4, registers=[self.command_statuses.pop(0)])
        return response(4, registers=self.inputs[address : address + count])

    async def write_register(self, **kwargs):
        self.calls.append(("write_register", kwargs))
        if self.write_response is not None:
            return self.write_response
        self.holding[kwargs["address"]] = kwargs["value"]
        return response(6, address=kwargs["address"], value=kwargs["value"])

    async def write_coil(self, **kwargs):
        self.calls.append(("write_coil", kwargs))
        if self.write_response is not None:
            return self.write_response
        self.coils[kwargs["address"]] = kwargs["value"]
        return response(5, address=kwargs["address"], value=kwargs["value"])


class BlockingConfirmationClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.confirmation_read_started = asyncio.Event()
        self.release_confirmation = asyncio.Event()

    async def read_input_registers(self, **kwargs):
        if kwargs["address"] == 7 and kwargs["count"] == 1:
            self.calls.append(("read_input_registers", kwargs))
            self.confirmation_read_started.set()
            await self.release_confirmation.wait()
            return response(4, registers=[2])
        return await super().read_input_registers(**kwargs)


@pytest.mark.asyncio
async def test_snapshot_reads_diagnostics_separately_and_decodes_all_tables():
    raw = FakeClient()
    device = HaierESP32(SerializedModbusClient(raw), 7)

    snapshot = await device.async_get_snapshot()

    assert device.attr_platforms == [
        Platform.CLIMATE,
        Platform.SWITCH,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
    ]
    assert snapshot["climate"] == {
        "hvac_mode": HVACMode.COOL,
        "target_temperature": 23,
        "current_temperature": 19.5,
        "fan_mode": "auto",
        "swing_mode": "both",
        "preset_mode": "sleep",
        "diagnostics": {
            "fault_code": 0,
            "lock_state": 1,
            "compatibility_unit_number": 0,
            "legacy_room_temperature": 19,
            "raw_mode": 1,
            "raw_fan": 4,
            "raw_vertical_position": 12,
            "raw_horizontal_position": 7,
            "fresh_telemetry": True,
        },
    }
    assert snapshot["switches"] == {
        "quiet": {"state": False},
        "display": {"state": True},
    }
    assert snapshot["selects"]["vertical_position"]["state"] == "auto"
    assert snapshot["selects"]["horizontal_position"]["state"] == "auto"
    assert snapshot["numeric_sensors"]["status_age_seconds"]["value"] == 4
    assert snapshot["numeric_sensors"]["status_count"]["value"] == 0x12345678
    assert snapshot["numeric_sensors"]["link_flags"]["value"] == 7
    assert snapshot["state_sensors"]["command_status"]["state"] == "confirmed"
    assert snapshot["binary_sensors"] == {
        "fresh_link": {"state": True},
        "rtu_enabled": {"state": True},
        "tcp_enabled": {"state": True},
    }
    assert raw.calls == [
        (
            "read_input_registers",
            {"address": 4, "count": 5, "device_id": 7},
        ),
        ("read_coils", {"address": 0, "count": 3, "device_id": 7}),
        (
            "read_holding_registers",
            {"address": 0, "count": 8, "device_id": 7},
        ),
        (
            "read_input_registers",
            {"address": 0, "count": 4, "device_id": 7},
        ),
    ]


@pytest.mark.asyncio
async def test_correlated_no_fresh_link_keeps_diagnostics_available():
    raw = FakeClient()
    raw.main_exception = response(
        0x81,
        exception_code=0x0B,
        error=True,
    )
    device = HaierESP32(SerializedModbusClient(raw), 7)

    snapshot = await device.async_get_snapshot()

    assert snapshot["numeric_sensors"]["status_age_seconds"]["value"] == 4
    assert snapshot["climate"]["hvac_mode"] is None
    assert snapshot["switches"]["quiet"]["state"] is None


@pytest.mark.asyncio
async def test_wrong_exception_identity_is_not_classified_as_offline():
    raw = FakeClient()
    raw.main_exception = response(
        0x81,
        exception_code=0x0B,
        error=True,
        dev_id=99,
    )
    device = HaierESP32(SerializedModbusClient(raw), 7)

    with pytest.raises(ModbusException, match="Modbus error response"):
        await device.async_get_snapshot()


async def _completed():
    return None


@pytest.mark.asyncio
async def test_confirmed_register_write_polls_then_reads_back(monkeypatch):
    raw = FakeClient()
    raw.command_statuses = [1, 2]
    device = HaierESP32(SerializedModbusClient(raw), 7)
    monkeypatch.setattr(
        "custom_components.modbus_devices.equipment.fourvrs.asyncio.sleep",
        lambda _delay: _completed(),
    )

    assert await device.async_set_preset_mode("boost") == "boost"

    assert raw.calls == [
        ("write_register", {"address": 5, "value": 1, "device_id": 7}),
        (
            "read_input_registers",
            {"address": 7, "count": 1, "device_id": 7},
        ),
        (
            "read_input_registers",
            {"address": 7, "count": 1, "device_id": 7},
        ),
        (
            "read_holding_registers",
            {"address": 5, "count": 1, "device_id": 7},
        ),
    ]


@pytest.mark.asyncio
async def test_confirmed_coil_write_reads_actual_state():
    raw = FakeClient()
    raw.command_statuses = [2]
    device = HaierESP32(SerializedModbusClient(raw), 7)

    assert await device.async_set_switch("quiet", True) is True
    assert raw.calls[-1] == (
        "read_coils",
        {"address": 1, "count": 1, "device_id": 7},
    )


@pytest.mark.asyncio
async def test_write_echo_and_readback_must_both_match():
    raw = FakeClient()
    raw.write_response = response(6, address=99, value=1)
    device = HaierESP32(SerializedModbusClient(raw), 7)

    with pytest.raises(ModbusException, match="Wrong FC06 address"):
        await device.async_set_preset_mode("boost")
    assert not any(call[0].startswith("read_") for call in raw.calls)

    raw = FakeClient()
    raw.command_statuses = [2]
    raw.readback_override = 2
    device = HaierESP32(SerializedModbusClient(raw), 7)
    with pytest.raises(ModbusException, match="readback mismatch"):
        await device.async_set_preset_mode("boost")


@pytest.mark.asyncio
async def test_busy_is_terminal_and_has_no_poll_or_retry():
    raw = FakeClient()
    raw.write_response = response(
        0x86,
        exception_code=6,
        error=True,
    )
    device = HaierESP32(SerializedModbusClient(raw), 7)

    with pytest.raises(ModbusException, match="Modbus error response"):
        await device.async_set_target_temperature(22)
    assert [call[0] for call in raw.calls] == ["write_register"]


@pytest.mark.asyncio
async def test_timeout_status_and_unexpected_idle_fail_without_readback():
    for status, message in ((3, "timed out"), (0, "Unexpected")):
        raw = FakeClient()
        raw.command_statuses = [status]
        device = HaierESP32(SerializedModbusClient(raw), 7)
        with pytest.raises(ModbusException, match=message):
            await device.async_set_target_temperature(22)
        assert [call[0] for call in raw.calls] == [
            "write_register",
            "read_input_registers",
        ]


def test_read_only_louvre_states_are_displayable_but_not_selectable():
    vertical, horizontal = HaierESP32.get_select_descriptions()

    assert "auto" not in vertical["options"]
    assert "auto_special" not in vertical["options"]
    assert "max_down" not in vertical["options"]
    assert "auto" not in horizontal["options"]
    assert HaierESP32._REGISTER_TO_VERTICAL[12] == "auto"
    assert HaierESP32._REGISTER_TO_HORIZONTAL[7] == "auto"


@pytest.mark.asyncio
async def test_mode_and_power_are_two_confirmed_commands_under_one_lock():
    raw = FakeClient()
    raw.command_statuses = [2, 2]
    client = SerializedModbusClient(raw)
    device = HaierESP32(client, 7)

    assert await device.async_set_hvac_mode(HVACMode.HEAT) == {
        "hvac_mode": HVACMode.HEAT
    }
    assert [call[0] for call in raw.calls] == [
        "write_register",
        "read_input_registers",
        "read_holding_registers",
        "write_coil",
        "read_input_registers",
        "read_coils",
    ]
    assert not client.request_lock.locked()


@pytest.mark.asyncio
async def test_polling_and_another_write_cannot_interleave_confirmation_sequence():
    raw = BlockingConfirmationClient()
    device = HaierESP32(SerializedModbusClient(raw), 7)

    first = asyncio.create_task(device.async_set_target_temperature(22))
    await raw.confirmation_read_started.wait()
    polling = asyncio.create_task(device.async_get_snapshot())
    second = asyncio.create_task(device.async_set_switch("display", False))
    await asyncio.sleep(0)

    assert raw.calls == [
        ("write_register", {"address": 0, "value": 22, "device_id": 7}),
        (
            "read_input_registers",
            {"address": 7, "count": 1, "device_id": 7},
        ),
    ]

    raw.release_confirmation.set()
    assert await first == 22
    await polling
    assert await second is False
    first_readback = raw.calls.index(
        (
            "read_holding_registers",
            {"address": 0, "count": 1, "device_id": 7},
        )
    )
    first_competing_request = min(
        index
        for index, call_item in enumerate(raw.calls)
        if index > 1
        and call_item
        in (
            (
                "read_input_registers",
                {"address": 4, "count": 5, "device_id": 7},
            ),
            (
                "write_coil",
                {"address": 2, "value": False, "device_id": 7},
            ),
        )
    )
    assert first_readback < first_competing_request


def entity_device(**methods):
    return SimpleNamespace(
        attr_manufactures_name="4VRS",
        attr_model_name="Haier-ESP32",
        attr_description="4VRS Haier ESP32 Modbus controller",
        attr_serial_number=None,
        attr_hardware_version=None,
        attr_software_version=None,
        get_climate_description=lambda: {
            "hvac_modes": [HVACMode.OFF, HVACMode.COOL],
            "fan_modes": ["auto"],
            "swing_modes": ["off", "both"],
            "preset_modes": ["none", "boost", "sleep"],
            "min_temp": 16,
            "max_temp": 30,
            "writes_are_readback_confirmed": True,
        },
        **methods,
    )


def entity_coordinator(data):
    coordinator = Mock(last_update_success=True)
    coordinator.data = data
    coordinator.async_apply_confirmed_write = Mock()
    coordinator.async_apply_optimistic_write = Mock()
    return coordinator


@pytest.mark.asyncio
async def test_climate_uses_confirmed_path_for_preset_and_not_optimistic():
    device = entity_device(
        async_set_preset_mode=AsyncMock(return_value="boost"),
    )
    coordinator = entity_coordinator(
        {"climate": {"hvac_mode": HVACMode.COOL, "preset_mode": "none"}}
    )
    entity = ModbusClimateEntity(
        coordinator,
        device,
        SimpleNamespace(entry_id="fourvrs-1"),
    )

    await entity.async_set_preset_mode("boost")

    coordinator.async_apply_confirmed_write.assert_called_once_with(
        ("climate", "preset_mode"), "boost"
    )
    coordinator.async_apply_optimistic_write.assert_not_called()


@pytest.mark.asyncio
async def test_switch_and_select_publish_only_protocol_confirmed_readback():
    device = entity_device(
        async_set_switch=AsyncMock(return_value=True),
        async_set_select=AsyncMock(return_value="up"),
    )
    coordinator = entity_coordinator(
        {
            "switches": {"quiet": {"state": False}},
            "selects": {"vertical_position": {"state": "center"}},
        }
    )
    entry = SimpleNamespace(entry_id="fourvrs-1")
    switch = ModBusDescribedSwitchEntity(
        coordinator,
        device,
        entry,
        {"switch_id": "quiet", "name": "Quiet"},
    )
    select = ModBusSelectEntity(
        coordinator,
        device,
        entry,
        {
            "select_id": "vertical_position",
            "name": "Vertical position",
            "options": ["up", "center"],
        },
    )

    await switch.async_turn_on()
    await select.async_select_option("up")

    assert coordinator.async_apply_confirmed_write.call_args_list == [
        call(("switches", "quiet", "state"), True),
        call(("selects", "vertical_position", "state"), "up"),
    ]
    coordinator.async_apply_optimistic_write.assert_not_called()


def test_confirmed_readback_generation_blocks_an_older_poll():
    coordinator = object.__new__(ModbusDeviceCoordinator)
    coordinator.data = {"switches": {"quiet": {"state": False}}}
    coordinator._write_generation = 0
    coordinator._pending_write_patches = {}
    published = []
    coordinator.async_set_updated_data = published.append

    coordinator.async_apply_confirmed_write(
        ("switches", "quiet", "state"),
        True,
    )
    stale = {"switches": {"quiet": {"state": False}}}
    coordinator._reconcile_pending_writes(stale, update_generation=0)

    assert published[-1]["switches"]["quiet"]["state"] is True
    assert stale["switches"]["quiet"]["state"] is True
