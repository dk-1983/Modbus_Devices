"""Daikin equipment presentation profiles."""

from .profile import PresentationProfile, PresentationRole, PresentationSection
from .registry import DevicePresentationRegistry

DAIKIN_RTD_RA_PROFILE = PresentationProfile(
    profile_id="daikin_rtd_ra",
    roles=(
        PresentationRole("climate", entity_domain="climate"),
        PresentationRole(
            "coil_inlet_temperature",
            section=PresentationSection.DIAGNOSTIC,
            entity_domain="sensor",
        ),
    ),
    include_unknown=False,
)


def register_profiles(registry: DevicePresentationRegistry) -> None:
    """Register Daikin profiles."""
    registry.register_equipment(
        "Daikin",
        "RTDRA",
        DAIKIN_RTD_RA_PROFILE,
        models=("RTD-RA",),
    )
