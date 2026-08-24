"""Universal dynamic presentation framework for Modbus Devices."""

from .bolid import register_profiles as register_bolid_profiles
from .builder import async_build_device_card
from .profile import DevicePresentation, PresentationProfile, PresentationRole
from .registry import DevicePresentationRegistry

DEFAULT_REGISTRY = DevicePresentationRegistry()
register_bolid_profiles(DEFAULT_REGISTRY)

__all__ = (
    "DEFAULT_REGISTRY",
    "DevicePresentation",
    "DevicePresentationRegistry",
    "PresentationProfile",
    "PresentationRole",
    "async_build_device_card",
)
