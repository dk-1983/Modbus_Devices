"""Zuked equipment presentation profiles."""

from .profile import PresentationProfile, PresentationRole, PresentationSection

ZUKED_310_4_0S1_PROFILE = PresentationProfile(
    profile_id="zuked_310_4_0s1",
    roles=(
        PresentationRole("drive_status"),
        PresentationRole("running_frequency"),
        PresentationRole("set_frequency"),
        PresentationRole("output_voltage"),
        PresentationRole("output_current"),
        PresentationRole("output_power"),
        PresentationRole("output_torque"),
        PresentationRole("bus_voltage"),
        PresentationRole("current_fault_code", section=PresentationSection.DIAGNOSTIC),
        PresentationRole("fault_information", section=PresentationSection.DIAGNOSTIC),
        PresentationRole(
            "current_running_time", section=PresentationSection.DIAGNOSTIC
        ),
        PresentationRole(
            "current_power_on_time", section=PresentationSection.DIAGNOSTIC
        ),
    ),
)


def register_profiles(registry) -> None:
    """Register Zuked profiles."""
    registry.register_equipment(
        "Zuked",
        "Zuked3104S1",
        ZUKED_310_4_0S1_PROFILE,
        models=("310-4.0S1",),
    )
