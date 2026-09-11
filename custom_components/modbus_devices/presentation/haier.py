"""Haier equipment presentation profiles."""

from .profile import PresentationProfile, PresentationRole
from .registry import DevicePresentationRegistry

HAIER_YCJ_A002_PROFILE = PresentationProfile(
    profile_id="haier_ycj_a002",
    roles=(PresentationRole("climate", entity_domain="climate"),),
    include_unknown=False,
)


def register_profiles(registry: DevicePresentationRegistry) -> None:
    """Register Haier profiles."""
    registry.register_equipment(
        "Haier",
        "YCJA002",
        HAIER_YCJ_A002_PROFILE,
        models=("YCJ-A002",),
    )
