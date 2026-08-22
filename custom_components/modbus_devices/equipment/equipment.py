"""Helpers for equipment discovery."""

from __future__ import annotations

from typing import Any

from ..gateway import GatewayCapabilitySpec, ResolvedDeviceMapping
from ..manufacturer import MANUFACTURERS, canonical_manufacturer_name, manufacturer_module_name

LEGACY_EQUIPMENT_CLASS_ALIASES: dict[str, str] = {
    "C2000DIP": "DIP34A05",
    "C2000IP": "C2000IP03",
}


def canonical_equipment_class_name(cls_name: str) -> str:
    """Normalize persisted legacy equipment class names at one boundary."""
    return LEGACY_EQUIPMENT_CLASS_ALIASES.get(cls_name, cls_name)


def get_class(module: str, cls_name: str) -> type[Any]:
    """Return an explicitly registered equipment class."""
    module_name = manufacturer_module_name(module)
    canonical_name = next(
        manufacturer.canonical_name
        for manufacturer in MANUFACTURERS
        if manufacturer.module_name == module_name
    )
    target_name = canonical_equipment_class_name(cls_name)
    for equipment_class in _get_equipment_classes(canonical_name):
        if equipment_class.__name__ == target_name:
            return equipment_class
    raise ValueError(
        f"Unsupported equipment class {cls_name!r} for {canonical_name}"
    )


def get_equipment_display_name(module: str, cls_name: str) -> str:
    """Return the physical model label for a canonical selector value."""
    equipment_class = get_class(module, cls_name)
    return equipment_class.equipment_model


def get_gateway_requirement(module: str, cls_name: str):
    """Return the gateway type declared by an equipment class, if any."""
    return getattr(get_class(module, cls_name), "required_gateway", None)


def get_manual_io_mapping_spec(module: str, cls_name: str) -> dict[str, Any] | None:
    """Return an equipment-owned direct Modbus I/O mapping specification."""
    specification = getattr(
        get_class(module, cls_name), "manual_io_mapping_spec", None
    )
    return None if specification is None else dict(specification)


def get_gateway_capabilities(
    module: str,
    cls_name: str,
    metadata: Any = None,
) -> tuple[GatewayCapabilitySpec, ...]:
    """Return equipment-owned gateway capability definitions."""
    equipment_class = get_class(module, cls_name)
    configured_reader = getattr(
        equipment_class, "get_gateway_capabilities_for_metadata", None
    )
    if metadata is not None and callable(configured_reader):
        return tuple(configured_reader(metadata))
    reader = getattr(equipment_class, "get_gateway_capabilities", None)
    return tuple(reader()) if callable(reader) else ()


def get_gateway_device_metadata(module: str, cls_name: str) -> dict[str, Any]:
    """Return declarative gateway-flow metadata owned by equipment."""
    equipment_class = get_class(module, cls_name)
    variant_reader = getattr(equipment_class, "get_variant_options", None)
    return {
        "uses_dpls_identity": bool(
            getattr(equipment_class, "uses_dpls_identity", False)
        ),
        "dpls_address_count": getattr(equipment_class, "dpls_address_count", None),
        "variants": dict(variant_reader()) if callable(variant_reader) else {},
        "variant_optional": bool(
            getattr(equipment_class, "variant_optional", False)
        ),
        "unsupported_variants": dict(
            getattr(equipment_class, "unsupported_variants", {})
        ),
        "variant_dpls_address_counts": dict(
            getattr(equipment_class, "variant_dpls_address_counts", {})
        ),
        "topologies": dict(getattr(equipment_class, "topologies", {})),
        "topology_dpls_address_counts": dict(
            getattr(equipment_class, "topology_dpls_address_counts", {})
        ),
        "gateway_transport_supported": bool(
            getattr(equipment_class, "gateway_transport_supported", True)
        ),
        "gateway_transport_limitation": getattr(
            equipment_class, "gateway_transport_limitation", None
        ),
    }


def validate_equipment_gateway_mapping(
    module: str,
    cls_name: str,
    mapping: ResolvedDeviceMapping,
) -> None:
    """Validate a resolved mapping against equipment-owned capabilities."""
    equipment_class = get_class(module, cls_name)
    equipment = equipment_class(None, mapping.identity.gateway.modbus_unit_id)
    apply_mapping = getattr(equipment, "apply_gateway_mapping", None)
    if not callable(apply_mapping):
        raise ValueError(f"{cls_name} does not support gateway mappings")
    apply_mapping(mapping)


def get_equipment_classes_by_manufacturer() -> dict[str, list[str]]:
    """Return explicitly registered equipment classes by manufacturer."""
    return {
        manufacturer.canonical_name: [
            equipment_class.__name__
            for equipment_class in _get_equipment_classes(
                manufacturer.canonical_name
            )
        ]
        for manufacturer in MANUFACTURERS
    }


def _get_equipment_classes(manufacturer: str) -> tuple[type[Any], ...]:
    """Load and validate a manufacturer's explicit equipment export."""
    canonical_name = canonical_manufacturer_name(manufacturer)
    module_name = manufacturer_module_name(canonical_name)
    module = __import__(
        name=module_name,
        globals=globals(),
        locals=locals(),
        level=1,
    )
    try:
        exported = module.EQUIPMENT_CLASSES
    except AttributeError as exc:
        raise RuntimeError(
            f"Equipment module {module_name!r} has no EQUIPMENT_CLASSES export"
        ) from exc
    return _validate_equipment_classes(
        canonical_name,
        module_name,
        exported,
    )


def _validate_equipment_classes(
    manufacturer: str,
    module_name: str,
    exported: object,
) -> tuple[type[Any], ...]:
    """Validate an explicit equipment-class registry without instantiation."""
    if not isinstance(exported, tuple):
        raise TypeError(f"{module_name}.EQUIPMENT_CLASSES must be a tuple")

    classes: list[type[Any]] = []
    seen_classes: set[type[Any]] = set()
    seen_models: set[str] = set()
    for entry in exported:
        if not isinstance(entry, type):
            raise TypeError(
                f"{module_name}.EQUIPMENT_CLASSES contains a non-class entry"
            )
        if entry.__module__.split(".")[-1] != module_name:
            raise TypeError(
                f"{entry.__name__} does not belong to equipment module {module_name}"
            )
        if entry in seen_classes:
            raise ValueError(f"Duplicate equipment class: {entry.__name__}")

        class_manufacturer = getattr(entry, "equipment_manufacturer", None)
        if class_manufacturer != manufacturer:
            raise ValueError(
                f"{entry.__name__} declares manufacturer {class_manufacturer!r}, "
                f"expected {manufacturer!r}"
            )
        model = getattr(entry, "equipment_model", None)
        if not isinstance(model, str) or not model:
            raise ValueError(f"{entry.__name__} has no canonical equipment_model")
        if model in seen_models:
            raise ValueError(f"Duplicate equipment model: {model}")

        seen_classes.add(entry)
        seen_models.add(model)
        classes.append(entry)

    return tuple(classes)
