"""Build a native Sections dashboard from device presentations."""

from collections import defaultdict
from typing import Any

from custom_components.modbus_devices.const import Config
from custom_components.modbus_devices.presentation import async_build_device_card

from homeassistant.helpers import area_registry as ar, device_registry as dr

UNASSIGNED_TITLE = "Unassigned"


def _is_modbus_device(device: Any) -> bool:
    return any(domain == Config.DOMAIN for domain, _identifier in device.identifiers)


def _device_name(device: Any) -> str:
    return device.name_by_user or device.name or device.model or device.id


async def async_build_dashboard(hass) -> dict[str, Any]:
    """Build a fresh dashboard config without reading or writing Lovelace storage."""
    device_registry = dr.async_get(hass)
    area_registry = ar.async_get(hass)
    grouped: dict[str | None, list[tuple[Any, dict[str, Any]]]] = defaultdict(list)

    devices = sorted(
        (device for device in device_registry.devices.values() if _is_modbus_device(device)),
        key=lambda device: (_device_name(device).casefold(), device.id),
    )
    for device in devices:
        presentation = await async_build_device_card(hass, device.id)
        if presentation is not None:
            grouped[presentation.area_id].append((device, presentation.card))

    def area_key(area_id: str | None) -> tuple[int, str, str]:
        if area_id is None:
            return (1, "", "")
        area = area_registry.async_get_area(area_id)
        return (0, (area.name if area else area_id).casefold(), area_id)

    sections = []
    for area_id in sorted(grouped, key=area_key):
        area = area_registry.async_get_area(area_id) if area_id is not None else None
        cards = [
            card
            for _device, card in sorted(
                grouped[area_id],
                key=lambda item: (_device_name(item[0]).casefold(), item[0].id),
            )
        ]
        sections.append(
            {
                "type": "grid",
                "cards": [
                    {
                        "type": "heading",
                        "heading": area.name if area is not None else UNASSIGNED_TITLE,
                    },
                    *cards,
                ],
            }
        )

    return {
        "views": [
            {
                "title": Config.NAME,
                "path": Config.DOMAIN.replace("_", "-"),
                "type": "sections",
                "sections": sections,
            }
        ],
    }
