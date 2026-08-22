"""Tests for generic strict Modbus response validation."""

from __future__ import annotations

import pytest
from pymodbus.exceptions import ModbusException
from pymodbus.pdu.bit_message import WriteSingleCoilResponse
from pymodbus.pdu.register_message import (
    WriteMultipleRegistersResponse,
    WriteSingleRegisterResponse,
)

from custom_components.modbus_devices.modbus_validation import (
    validate_fc05_response,
    validate_fc06_response,
    validate_fc16_response,
    validated_bits,
    validated_registers,
)


class Response:
    def __init__(self, *, function_code=None, address=None, value=None, registers=None,
                 bits=None, error=False, device_id=None):
        self.function_code = function_code
        self.address = address
        self.value = value
        self.registers = registers
        self.bits = bits
        self._error = error
        if device_id is not None:
            self.device_id = device_id

    def isError(self):
        return self._error


def test_fc05_valid_echo():
    validate_fc05_response(
        Response(function_code=5, address=12, value=True, device_id=3),
        address=12,
        value=True,
        device_id=3,
        operation="coil",
    )


def test_fc06_valid_echo():
    validate_fc06_response(
        Response(function_code=6, address=20, value=0x1234, device_id=4),
        address=20,
        value=0x1234,
        device_id=4,
        operation="register",
    )


def test_real_pymodbus_fc05_and_fc06_response_contracts():
    validate_fc05_response(
        WriteSingleCoilResponse(dev_id=3, address=12, bits=[True]),
        address=12,
        value=True,
        device_id=3,
        operation="real coil",
    )
    validate_fc06_response(
        WriteSingleRegisterResponse(dev_id=4, address=20, registers=[0x1234]),
        address=20,
        value=0x1234,
        device_id=4,
        operation="real register",
    )
    validate_fc16_response(
        WriteMultipleRegistersResponse(dev_id=5, address=30, count=6),
        address=30,
        count=6,
        device_id=5,
        operation="real registers",
    )


@pytest.mark.parametrize("response", [None, object(), Response(error=True)])
def test_fc05_rejects_missing_invalid_and_error_responses(response):
    with pytest.raises(ModbusException):
        validate_fc05_response(response, address=1, value=True, operation="coil")


@pytest.mark.parametrize("response", [None, object(), Response(error=True)])
def test_fc06_rejects_missing_invalid_and_error_responses(response):
    with pytest.raises(ModbusException):
        validate_fc06_response(
            response, address=1, value=7, operation="register"
        )


@pytest.mark.parametrize(
    "response",
    [
        Response(function_code=6, address=1, value=True),
        Response(function_code=5, address=2, value=True),
        Response(function_code=5, address=1, value=False),
        Response(function_code=5, address=1, value=True, device_id=2),
    ],
)
def test_fc05_rejects_wrong_function_address_value_and_slave(response):
    with pytest.raises(ModbusException):
        validate_fc05_response(
            response, address=1, value=True, device_id=1, operation="coil"
        )


@pytest.mark.parametrize(
    "response",
    [
        Response(function_code=5, address=1, value=7),
        Response(function_code=6, address=2, value=7),
        Response(function_code=6, address=1, value=8),
        Response(function_code=6, address=1, value=7, device_id=2),
    ],
)
def test_fc06_rejects_wrong_function_address_value_and_slave(response):
    with pytest.raises(ModbusException):
        validate_fc06_response(
            response, address=1, value=7, device_id=1, operation="register"
        )


@pytest.mark.parametrize(
    "response",
    [
        None,
        object(),
        Response(error=True),
        Response(function_code=6, address=1),
        Response(function_code=16, address=2),
        Response(function_code=16, address=1),
        Response(function_code=16, address=1, device_id=2),
    ],
)
def test_fc16_rejects_missing_error_and_mismatched_echo(response):
    if isinstance(response, Response) and response.function_code == 16:
        response.count = 6 if response.address != 1 or hasattr(response, "device_id") else 5
    with pytest.raises(ModbusException):
        validate_fc16_response(
            response,
            address=1,
            count=6,
            device_id=1,
            operation="registers",
        )


def test_read_validators_require_exact_registers_and_sufficient_bits():
    assert validated_registers(
        Response(function_code=3, registers=[1, 2]), 2, "read", expected_function=3
    ) == [1, 2]
    assert validated_bits(
        Response(function_code=1, bits=[True, False, False, False]),
        2,
        "bits",
        expected_function=1,
    ) == [True, False]


@pytest.mark.parametrize(
    "response",
    [
        None,
        object(),
        Response(error=True),
        Response(registers=None),
        Response(registers=[1]),
        Response(function_code=4, registers=[1, 2]),
        Response(function_code=3, registers=[1, -1]),
    ],
)
def test_register_reads_reject_missing_error_and_truncated_payload(response):
    with pytest.raises(ModbusException):
        validated_registers(response, 2, "read", expected_function=3)
