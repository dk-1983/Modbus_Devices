"""Tests for the independently modelled C2000-VTI family."""

import pytest

from custom_components.modbus_devices.equipment.bolid import C2000VTI, C2000VT
from custom_components.modbus_devices.equipment.equipment import get_gateway_device_metadata
from custom_components.modbus_devices.gateway import DPLSSubIdentity


def test_vti_is_not_a_c2000_vt_subclass():
    assert not issubclass(C2000VTI, C2000VT)


@pytest.mark.parametrize(("variant", "count"), [("vti", 2), ("vti_01", 3)])
def test_variant_topology(variant, count):
    assert C2000VTI.variant_dpls_address_counts[variant] == count
    assert DPLSSubIdentity(128 - count, count).address_count == count


def test_co_and_sounder_only_on_vti_01():
    plain = C2000VTI.variants[C2000VTI.Variant.VTI].device_metadata
    extended = C2000VTI.variants[C2000VTI.Variant.VTI_01].device_metadata
    assert plain["co_sensor"] is False
    assert plain["local_sounder"] is False
    assert extended["co_sensor"] is True
    assert extended["local_sounder"] is True
    assert extended["remote_sounder_control"] is False
    assert "co_concentration" in C2000VTI.numeric_kinds


def test_s2000_pp_numeric_transport_is_explicitly_rejected():
    metadata = get_gateway_device_metadata("bolid", "C2000VTI")
    assert metadata["gateway_transport_supported"] is False
    assert "does not confirm" in metadata["gateway_transport_limitation"]
    assert C2000VTI(None, 1).attr_serial_number is None
    assert C2000VTI(None, 1).attr_software_version is None
