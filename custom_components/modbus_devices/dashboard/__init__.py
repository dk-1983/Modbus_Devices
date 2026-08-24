"""Dynamic native dashboard support for Modbus Devices."""

from .builder import async_build_dashboard
from .frontend import async_register_dashboard_frontend

__all__ = ("async_build_dashboard", "async_register_dashboard_frontend")
