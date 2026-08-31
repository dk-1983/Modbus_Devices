"""Document-derived tests for the Zuked 310-4.0S1."""

from custom_components.modbus_devices.equipment.equipment import get_class
from custom_components.modbus_devices.equipment.zuked import (
    FAULTS,
    NUMERIC_PARAMETERS,
    U0_BY_PARAMETER,
    U0_REGISTERS,
    Zuked3104S1,
)
from custom_components.modbus_devices.presentation import DEFAULT_REGISTRY
from custom_components.modbus_devices.presentation.profile import PresentationIdentity
from pymodbus.exceptions import ModbusException
import pytest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform


class Response:
    """Minimal pymodbus read response fixture."""

    def __init__(self, registers=None, *, error=False, function_code=3):
        """Initialize a synthetic FC03 response."""
        self.registers = registers
        self._error = error
        self.function_code = function_code

    def isError(self):
        """Return the synthetic protocol error flag."""
        return self._error


class Client:
    """Record the exact conservative read plan."""

    def __init__(self):
        """Provide the accepted hardware-derived fixture."""
        self.reads = []
        self.responses = {
            0x7000: Response([0, 147, 3055, 0, 0, 0, 0]),
            0x7019: Response([61]),
            0x701A: Response([125]),
            0x702D: Response([123]),
            0x703D: Response([0]),
            0x703E: Response([0]),
        }

    async def read_holding_registers(self, **kwargs):
        """Return one configured FC03 response."""
        self.reads.append(kwargs)
        response = self.responses[kwargs["address"]]
        if isinstance(response, Exception):
            raise response
        return response


def documented_fixture(**overrides):
    """Build a complete synthetic fixture from documented U0 words."""
    values = dict.fromkeys(NUMERIC_PARAMETERS, 0)
    values.update({"U0-45": 0, "U0-61": 7, "U0-62": 16})
    values.update(overrides)
    return values


def test_registration_identity_and_no_fabricated_runtime_metadata():
    """Register the real manufacturer/model without invented identity."""
    assert get_class("Zuked", "Zuked3104S1") is Zuked3104S1
    device = Zuked3104S1(None, 1)
    assert device.attr_manufactures_name == "Zuked"
    assert device.attr_model_name == "310-4.0S1"
    assert device.attr_platforms == [Platform.SENSOR]
    assert device.attr_serial_number is None
    assert device.attr_software_version is None
    assert device.attr_hardware_version is None


def test_complete_documented_u0_metadata_preserves_addresses_and_retains():
    """Keep the complete manual map while excluding Retain words."""
    assert U0_REGISTERS[0].address == 0x7000
    assert U0_BY_PARAMETER["U0-62"].address == 0x703E
    assert U0_BY_PARAMETER["U0-65"].address == 0x7041
    assert {item.parameter for item in U0_REGISTERS if item.name == "Retain"} == {
        "U0-08",
        "U0-39",
        "U0-40",
        "U0-42",
    }
    assert all(not item.exposed for item in U0_REGISTERS if item.name == "Retain")


def test_documented_scaling_and_u0_04_current_interpretation():
    """Apply every selected scale, including the documented U0-04 ampere unit."""
    snapshot = Zuked3104S1.decode_documented_snapshot(
        documented_fixture(
            **{
                "U0-00": 5012,
                "U0-01": 5000,
                "U0-02": 5371,
                "U0-03": 380,
                "U0-04": 1234,
                "U0-05": 42,
                "U0-06": 987,
                "U0-25": 61,
                "U0-26": 125,
            }
        )
    )
    values = snapshot["numeric_sensors"]
    assert values["running_frequency"]["value"] == 50.12
    assert values["set_frequency"]["value"] == 50.0
    assert values["bus_voltage"]["value"] == 537.1
    assert values["output_voltage"]["value"] == 380
    assert values["output_current"]["value"] == 12.34
    assert values["output_power"]["value"] == 4.2
    assert values["output_torque"]["value"] == 98.7
    assert values["current_power_on_time"]["value"] == 61
    assert values["current_running_time"]["value"] == 12.5


def test_entity_metadata_units_classes_icons_and_precision():
    """Expose truthful Home Assistant metadata for engineering values."""
    descriptions = {
        item["sensor_id"]: item
        for item in Zuked3104S1.get_numeric_sensor_descriptions()
    }
    assert (
        descriptions["running_frequency"]["device_class"] is SensorDeviceClass.FREQUENCY
    )
    assert (
        descriptions["running_frequency"]["state_class"] is SensorStateClass.MEASUREMENT
    )
    assert descriptions["running_frequency"]["precision"] == 2
    assert descriptions["output_current"]["device_class"] is SensorDeviceClass.CURRENT
    assert descriptions["output_current"]["icon"] == "mdi:current-ac"
    assert descriptions["output_voltage"]["precision"] == 0
    assert descriptions["current_running_time"]["precision"] == 1
    fault = {
        item["sensor_id"]: item for item in Zuked3104S1.get_state_sensor_descriptions()
    }["current_fault_code"]
    assert fault["state_icons"]["communication_fault"] == "mdi:alert-circle"
    assert fault["unknown_state_icon"] == "mdi:help-circle-outline"


@pytest.mark.parametrize(("code", "state"), sorted(FAULTS.items()))
def test_manual_fault_table(code, state):
    """Decode each ErrXX entry printed by this exact manual."""
    assert Zuked3104S1.decode_fault(code) == state


@pytest.mark.parametrize("code", [0, 1, 12, 20, 65535])
def test_unknown_fault_codes_are_lossless(code):
    """Preserve every undocumented fault word."""
    assert Zuked3104S1.decode_fault(code) == f"unknown_fault_{code}"


def test_u0_45_u0_61_and_u0_62_remain_distinct_and_lossless():
    """Do not merge three undocumented or differently documented words."""
    states = Zuked3104S1.decode_documented_snapshot(
        documented_fixture(**{"U0-45": 123, "U0-61": 9, "U0-62": 43})
    )["state_sensors"]
    assert states["fault_information"]["state"] == "fault_information_123"
    assert states["drive_status"]["state"] == "unknown_9"
    assert states["current_fault_code"]["state"] == "motor_overspeed"
    assert [item["primary_code"] for item in states.values()] == [9, 123, 43]


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {**documented_fixture(), "extra": 1},
        {**documented_fixture(), "U0-00": -1},
        {**documented_fixture(), "U0-00": 65536},
        {**documented_fixture(), "U0-00": True},
    ],
)
def test_snapshot_contract_rejects_missing_extra_or_malformed_words(invalid):
    """Reject incomplete and non-word synthetic responses."""
    with pytest.raises(ValueError):
        Zuked3104S1.decode_documented_snapshot(invalid)


@pytest.mark.asyncio
async def test_hardware_verified_fc03_direct_address_and_grouped_core_contract():
    """Use FC03 direct addresses, one core group, and isolated diagnostics."""
    client = Client()
    snapshot = await Zuked3104S1(client, 3).async_get_snapshot()
    assert client.reads == [
        {"address": 0x7000, "count": 7, "device_id": 3},
        {"address": 0x7019, "count": 1, "device_id": 3},
        {"address": 0x701A, "count": 1, "device_id": 3},
        {"address": 0x702D, "count": 1, "device_id": 3},
        {"address": 0x703D, "count": 1, "device_id": 3},
        {"address": 0x703E, "count": 1, "device_id": 3},
    ]
    values = snapshot["numeric_sensors"]
    assert values["running_frequency"]["value"] == 0.0
    assert values["set_frequency"]["value"] == 1.47
    assert values["bus_voltage"]["value"] == 305.5
    assert values["output_voltage"]["value"] == 0
    assert values["output_current"]["value"] == 0.0
    assert values["output_power"]["value"] == 0.0
    assert values["output_torque"]["value"] == 0.0
    assert snapshot["state_sensors"]["drive_status"]["state"] == "unknown_0"
    assert snapshot["state_sensors"]["current_fault_code"]["state"] == (
        "unknown_fault_0"
    )


@pytest.mark.parametrize(
    "response",
    [
        None,
        object(),
        Response(error=True),
        Response([0] * 7, function_code=4),
        Response([]),
        Response([0] * 6),
        Response([0] * 8),
        Response([0, 0, 0, 0, 0, 0, 65536]),
        Response([0, 0, 0, 0, 0, 0, True]),
    ],
)
@pytest.mark.asyncio
async def test_grouped_response_is_strictly_validated(response):
    """Reject exceptions, wrong FC, malformed and non-word grouped payloads."""
    client = Client()
    client.responses[0x7000] = response
    with pytest.raises(ModbusException):
        await Zuked3104S1(client, 3).async_get_snapshot()


@pytest.mark.asyncio
async def test_transport_exception_propagates_without_fallback_probe():
    """Propagate transport failure without FC04 or minus-one retries."""
    client = Client()
    client.responses[0x7000] = RuntimeError("transport failed")
    with pytest.raises(RuntimeError, match="transport failed"):
        await Zuked3104S1(client, 3).async_get_snapshot()
    assert client.reads == [{"address": 0x7000, "count": 7, "device_id": 3}]


def test_no_write_or_control_surface_exists():
    """Do not expose motor or persistent-configuration writes."""
    device = Zuked3104S1(None, 1)
    assert not hasattr(device, "async_send_command")
    assert not hasattr(device, "get_button_descriptions")
    assert not hasattr(device, "get_switch_descriptions")
    assert not hasattr(device, "get_number_descriptions")


def test_dedicated_native_presentation_profile_has_semantic_order():
    """Generate a native card through a dedicated semantic profile."""
    profile = DEFAULT_REGISTRY.resolve(
        PresentationIdentity("Zuked", "Zuked3104S1", "310-4.0S1")
    )
    assert profile.profile_id == "zuked_310_4_0s1"
    assert profile.card_type == "entities"
    assert [role.key for role in profile.roles] == [
        "drive_status",
        "running_frequency",
        "set_frequency",
        "output_voltage",
        "output_current",
        "output_power",
        "output_torque",
        "bus_voltage",
        "current_fault_code",
        "fault_information",
        "current_running_time",
        "current_power_on_time",
    ]
