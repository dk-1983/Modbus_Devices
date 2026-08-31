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

DIP34A05_PROFILE = PresentationProfile(
    profile_id="bolid_dip34a05",
    roles=(PresentationRole("detector_state"),),
)

C2000R_DIP_PROFILE = PresentationProfile(
    profile_id="bolid_c2000r_dip",
    roles=(
        PresentationRole("detector_state"),
        PresentationRole(
            "enclosure_tamper",
            PresentationSection.DIAGNOSTIC,
            entity_domain="binary_sensor",
        ),
        PresentationRole("main_battery_state", PresentationSection.DIAGNOSTIC),
        PresentationRole("reserve_battery_state", PresentationSection.DIAGNOSTIC),
    ),
)

C2000R_IP_PROFILE = PresentationProfile(
    profile_id="bolid_c2000r_ip",
    roles=(
        PresentationRole("detector_state"),
        PresentationRole(
            "enclosure_tamper",
            PresentationSection.DIAGNOSTIC,
            entity_domain="binary_sensor",
        ),
        PresentationRole("main_battery_state", PresentationSection.DIAGNOSTIC),
        PresentationRole("reserve_battery_state", PresentationSection.DIAGNOSTIC),
        PresentationRole(
            "measurement_fault",
            PresentationSection.DIAGNOSTIC,
            entity_domain="binary_sensor",
        ),
    ),
)

C2000R_ST_01_PROFILE = PresentationProfile(
    profile_id="bolid_c2000r_st_01",
    roles=(
        PresentationRole("glass_break_state"),
        PresentationRole("glass_break", entity_domain="binary_sensor"),
        PresentationRole(
            "enclosure_tamper",
            PresentationSection.DIAGNOSTIC,
            entity_domain="binary_sensor",
        ),
        PresentationRole("main_battery_state", PresentationSection.DIAGNOSTIC),
    ),
)

C2000_ST_04_PROFILE = PresentationProfile(
    profile_id="bolid_c2000_st_04",
    roles=(
        PresentationRole("glass_break_state"),
        PresentationRole("glass_break", entity_domain="binary_sensor"),
        PresentationRole(
            "enclosure_tamper",
            PresentationSection.DIAGNOSTIC,
            entity_domain="binary_sensor",
        ),
        PresentationRole(
            "equipment_fault",
            PresentationSection.DIAGNOSTIC,
            entity_domain="binary_sensor",
        ),
    ),
)

C2000_VT_PROFILE = PresentationProfile(
    profile_id="bolid_c2000_vt",
    roles=(
        PresentationRole("temperature_state"),
        PresentationRole("temperature"),
        PresentationRole("humidity_state"),
        PresentationRole("humidity"),
    ),
)

C2000R_VTI_PROFILE = PresentationProfile(
    profile_id="bolid_c2000r_vti",
    roles=(
        PresentationRole("temperature_state"),
        PresentationRole("temperature"),
        PresentationRole("humidity_state"),
        PresentationRole("humidity"),
        PresentationRole("main_battery_state"),
    ),
)

C2000_DZ_PROFILE = PresentationProfile(
    profile_id="bolid_c2000_dz",
    roles=(
        PresentationRole("water_leak", entity_domain="binary_sensor"),
        PresentationRole("water_leak_state", PresentationSection.DIAGNOSTIC),
    ),
)

C2000R_DZ_PROFILE = PresentationProfile(
    profile_id="bolid_c2000r_dz",
    roles=(
        PresentationRole("water_leak", entity_domain="binary_sensor"),
        PresentationRole("main_battery_state"),
        PresentationRole("reserve_battery_state"),
        PresentationRole("water_leak_state", PresentationSection.DIAGNOSTIC),
    ),
)

C2000_SMK_04_PROFILE = PresentationProfile(
    profile_id="bolid_c2000_smk_04",
    roles=(
        PresentationRole("opening", entity_domain="binary_sensor"),
        PresentationRole("opening_state", PresentationSection.DIAGNOSTIC),
    ),
)

C2000R_SMK_PROFILE = PresentationProfile(
    profile_id="bolid_c2000r_smk",
    roles=(
        PresentationRole("opening", entity_domain="binary_sensor"),
        PresentationRole("battery_state"),
        PresentationRole("external_input_state", PresentationSection.DIAGNOSTIC),
        PresentationRole(
            "tamper",
            PresentationSection.DIAGNOSTIC,
            entity_domain="binary_sensor",
        ),
        PresentationRole("opening_state", PresentationSection.DIAGNOSTIC),
    ),
)

MIP24_ISP20_PROFILE = PresentationProfile(
    profile_id="bolid_mip24_isp20",
    roles=(
        PresentationRole("tamper", entity_domain="binary_sensor"),
        PresentationRole("output_power_state"),
        PresentationRole("output_voltage"),
        PresentationRole("output_load_state"),
        PresentationRole("output_current"),
        PresentationRole("battery_state"),
        PresentationRole("battery_voltage"),
        PresentationRole("charger_state"),
        PresentationRole("battery_charge"),
        PresentationRole("mains_state"),
        PresentationRole("mains_voltage"),
        PresentationRole("device_state", PresentationSection.DIAGNOSTIC),
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
        "DIP34A05",
        DIP34A05_PROFILE,
        models=("ДИП-34А-05",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000RDIP",
        C2000R_DIP_PROFILE,
        models=("С2000Р-ДИП",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000RIP",
        C2000R_IP_PROFILE,
        models=("С2000Р-ИП",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000RST01",
        C2000R_ST_01_PROFILE,
        models=("С2000Р-СТ исп.01",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000ST04",
        C2000_ST_04_PROFILE,
        models=("С2000-СТ исп.04",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000DZ",
        C2000_DZ_PROFILE,
        models=("С2000-ДЗ",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000RDZ",
        C2000R_DZ_PROFILE,
        models=("С2000Р-ДЗ",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000SMK",
        C2000_SMK_04_PROFILE,
        models=("С2000-СМК", "С2000-СМК исп.04"),
    )
    registry.register_equipment(
        "Bolid",
        "C2000RSMK",
        C2000R_SMK_PROFILE,
        models=("С2000Р-СМК",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000VT",
        C2000_VT_PROFILE,
        models=("С2000-ВТ", "С2000-ВТ исп.01"),
    )
    registry.register_equipment(
        "Bolid",
        "C2000VTI",
        C2000_VT_PROFILE,
        models=("С2000-ВТИ",),
    )
    registry.register_equipment(
        "Bolid",
        "C2000RVTI",
        C2000R_VTI_PROFILE,
        models=("С2000Р-ВТИ",),
    )
    registry.register_equipment(
        "Bolid",
        "MIP24Isp20",
        MIP24_ISP20_PROFILE,
        models=("МИП-24 исп.20",),
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
