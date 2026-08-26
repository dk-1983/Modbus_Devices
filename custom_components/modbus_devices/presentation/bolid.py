"""Bolid equipment presentation profiles."""

from .profile import PresentationProfile, PresentationRole, PresentationSection
from .registry import DevicePresentationRegistry

M3000_BB_1020_PROFILE = PresentationProfile(
    profile_id="bolid_m3000_bb_1020",
    roles=(
        PresentationRole("device_time", entity_domain="sensor"),
        *(
            PresentationRole(str(number), entity_domain="switch")
            for number in range(1, 7)
        ),
        *(
            PresentationRole(
                f"input_{number}",
                entity_domain="binary_sensor",
                match_unique_id_suffix=True,
            )
            for number in range(1, 13)
        ),
    ),
)

C2000_VT_PROFILE = PresentationProfile(
    profile_id="bolid_c2000_vt",
    roles=(
        PresentationRole("temperature"),
        PresentationRole("humidity"),
        PresentationRole("temperature_state", PresentationSection.DIAGNOSTIC),
        PresentationRole("humidity_state", PresentationSection.DIAGNOSTIC),
    ),
)

C2000_KPB_PROFILE = PresentationProfile(
    profile_id="bolid_c2000_kpb",
    roles=tuple(PresentationRole(f"output_{number}", entity_domain="switch") for number in range(1, 7)),
)

C2000_SP4_PROFILE = PresentationProfile(
    profile_id="bolid_c2000_sp4",
    roles=(
        PresentationRole("output_1", entity_domain="switch"),
        PresentationRole("actuator_state"),
        PresentationRole("working_output_circuit"),
        PresentationRole("initial_output_circuit"),
        PresentationRole("working_limit_switch"),
        PresentationRole("initial_limit_switch"),
    ),
)


def register_profiles(registry: DevicePresentationRegistry) -> None:
    """Register Bolid profiles through the public manufacturer extension API."""
    registry.register_equipment(
        "Bolid",
        "M3000BB1020",
        M3000_BB_1020_PROFILE,
        models=("M3000-BB-1020",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000VT",
        C2000_VT_PROFILE,
        models=("С2000-ВТ", "С2000-ВТ исп.01"),
    )
    registry.register_equipment(
        "Bolid",
        "C2000KPB",
        C2000_KPB_PROFILE,
        models=("С2000-КПБ",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000SP4",
        C2000_SP4_PROFILE,
        models=(
            "С2000-СП4/24(220)",
            "С2000-СП4/24",
            "С2000-СП4/24 исп.01",
            "С2000-СП4/220",
            "С2000-СП4/220 исп.01",
        ),
    )
