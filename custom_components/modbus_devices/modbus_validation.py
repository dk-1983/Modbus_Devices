"""Generic Modbus response and protocol validation."""

from __future__ import annotations

from typing import Any

from pymodbus.exceptions import ModbusException


def validate_modbus_response(
    response: Any,
    operation: str,
    *,
    expected_function: int | None = None,
) -> Any:
    """Validate the common response contract and optional function code."""
    if response is None:
        raise ModbusException(f"Empty Modbus response for {operation}")
    is_error = getattr(response, "isError", None)
    if not callable(is_error):
        raise ModbusException(f"Invalid Modbus response for {operation}")
    if is_error():
        raise ModbusException(f"Modbus error response for {operation}: {response}")
    if (
        expected_function is not None
        and getattr(response, "function_code", None) != expected_function
    ):
        raise ModbusException(
            f"Wrong Modbus function response for {operation}: "
            f"expected {expected_function}, got {getattr(response, 'function_code', None)}"
        )
    return response


def _validate_response_device_id(
    response: Any,
    expected_device_id: int | None,
    operation: str,
) -> None:
    if expected_device_id is None:
        return
    for attribute in ("dev_id", "device_id", "slave_id", "unit_id"):
        actual = getattr(response, attribute, None)
        if actual is not None and actual != expected_device_id:
            raise ModbusException(
                f"Wrong Modbus device id for {operation}: "
                f"expected {expected_device_id}, got {actual}"
            )


def _echoed_value(response: Any) -> Any:
    value = getattr(response, "value", None)
    if value is not None:
        return value
    registers = getattr(response, "registers", None)
    if isinstance(registers, (list, tuple)) and registers:
        return registers[0]
    return None


def _echoed_coil_value(response: Any) -> Any:
    value = getattr(response, "value", None)
    if value is not None:
        return value
    bits = getattr(response, "bits", None)
    if isinstance(bits, (list, tuple)) and bits:
        return bits[0]
    return None


def validate_fc05_response(
    response: Any,
    *,
    address: int,
    value: bool,
    operation: str,
    device_id: int | None = None,
) -> None:
    """Validate the complete FC05 single-coil echo contract."""
    validate_modbus_response(response, operation, expected_function=5)
    if getattr(response, "address", None) != address:
        raise ModbusException(f"Wrong FC05 address echo for {operation}")
    echoed = _echoed_coil_value(response)
    allowed = {True, 0xFF00} if value else {False, 0x0000}
    if echoed not in allowed:
        raise ModbusException(f"Wrong FC05 value echo for {operation}")
    _validate_response_device_id(response, device_id, operation)


def validate_fc06_response(
    response: Any,
    *,
    address: int,
    value: int,
    operation: str,
    device_id: int | None = None,
) -> None:
    """Validate the complete FC06 single-register echo contract."""
    validate_modbus_response(response, operation, expected_function=6)
    if getattr(response, "address", None) != address:
        raise ModbusException(f"Wrong FC06 address echo for {operation}")
    if _echoed_value(response) != value:
        raise ModbusException(f"Wrong FC06 value echo for {operation}")
    _validate_response_device_id(response, device_id, operation)


def validated_registers(
    response: Any,
    expected: int,
    operation: str,
    *,
    expected_function: int | None = None,
) -> list[int]:
    """Validate a register-read response and exact payload length."""
    validate_modbus_response(
        response, operation, expected_function=expected_function
    )
    registers = getattr(response, "registers", None)
    if not isinstance(registers, (list, tuple)):
        raise ModbusException(f"Missing registers in response for {operation}")
    if len(registers) != expected:
        raise ModbusException(
            f"Short Modbus response for {operation}: expected {expected}, "
            f"got {len(registers)}"
        )
    if any(
        type(register) is not int or not 0 <= register <= 0xFFFF
        for register in registers
    ):
        raise ModbusException(f"Invalid register payload for {operation}")
    return list(registers)


def validated_bits(
    response: Any,
    expected: int,
    operation: str,
    *,
    expected_function: int | None = None,
) -> list[bool]:
    """Validate a bit-read response while allowing protocol byte padding."""
    validate_modbus_response(
        response, operation, expected_function=expected_function
    )
    bits = getattr(response, "bits", None)
    if not isinstance(bits, (list, tuple)) or len(bits) < expected:
        actual = 0 if not isinstance(bits, (list, tuple)) else len(bits)
        raise ModbusException(
            f"Short Modbus response for {operation}: expected at least {expected}, "
            f"got {actual}"
        )
    return [bool(bit) for bit in bits[:expected]]
