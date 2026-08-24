"""Immutable declarations for native Home Assistant device presentations."""

from dataclasses import dataclass
from enum import StrEnum


class PresentationSection(StrEnum):
    """Semantic section inside one physical device card."""

    PRIMARY = "primary"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True)
class PresentationRole:
    """One stable equipment capability and its preferred position."""

    key: str
    section: PresentationSection = PresentationSection.PRIMARY
    entity_domain: str | None = None


@dataclass(frozen=True, slots=True)
class PresentationProfile:
    """Declarative policy for presenting one equipment model."""

    profile_id: str
    roles: tuple[PresentationRole, ...] = ()
    card_type: str = "entities"
    include_unknown: bool = True
    include_diagnostic: bool = True
    include_config: bool = False


@dataclass(frozen=True, slots=True)
class PresentationIdentity:
    """Manufacturer-agnostic identity used to select a profile."""

    manufacturer: str | None
    equipment_class: str | None
    model: str | None


@dataclass(frozen=True, slots=True)
class DevicePresentation:
    """One indivisible native card plus hierarchy metadata for future strategies."""

    device_id: str
    area_id: str | None
    profile_id: str
    card: dict
