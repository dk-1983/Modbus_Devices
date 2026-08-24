"""Extensible registry of equipment presentation profiles."""

from .generic import GENERIC_PROFILE
from .profile import PresentationIdentity, PresentationProfile


def _normalized(value: str | None) -> str | None:
    return None if value is None else value.casefold()


class DevicePresentationRegistry:
    """Map stable equipment identities to immutable presentation profiles."""

    def __init__(self) -> None:
        """Initialize an empty extension registry."""
        self._equipment: dict[tuple[str, str], PresentationProfile] = {}
        self._models: dict[tuple[str, str], PresentationProfile] = {}

    def register_equipment(
        self,
        manufacturer: str,
        equipment_class: str,
        profile: PresentationProfile,
        *,
        models: tuple[str, ...] = (),
    ) -> None:
        """Register a profile without coupling the builder to a manufacturer."""
        manufacturer_key = manufacturer.casefold()
        self._equipment[(manufacturer_key, equipment_class.casefold())] = profile
        for model in models:
            self._models[(manufacturer_key, model.casefold())] = profile

    def resolve(self, identity: PresentationIdentity) -> PresentationProfile:
        """Resolve the most stable available identity or use the generic profile."""
        manufacturer = _normalized(identity.manufacturer)
        if manufacturer is None:
            return GENERIC_PROFILE
        if identity.equipment_class is not None:
            profile = self._equipment.get(
                (manufacturer, identity.equipment_class.casefold())
            )
            if profile is not None:
                return profile
        if identity.model is not None:
            profile = self._models.get((manufacturer, identity.model.casefold()))
            if profile is not None:
                return profile
        return GENERIC_PROFILE
