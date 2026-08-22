"""Mapping providers for gateway-connected equipment."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from .gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayCapabilitySpec,
    GatewayContext,
    MappingSource,
    ObjectKind,
    ResolvedDeviceMapping,
    ResolvedObjectMapping,
    dpls_ranges_overlap,
)
from .s2000_pp import (
    S2000PPConfigurationCache,
    S2000PPConfigurationReader,
    manual_relay_mapping,
    manual_zone_mapping,
    resolve_relay_row,
    resolve_zone_row,
)


class DeviceMappingNotFoundError(ValueError):
    """Raised when no configuration rows belong to the requested device."""


class AmbiguousDeviceMappingError(ValueError):
    """Raised when multiple mutually exclusive capability rows match."""


class DeviceMappingProvider(Protocol):
    """Resolve one downstream device into the common mapping model."""

    source: MappingSource

    async def async_resolve(
        self,
        gateway: GatewayContext,
        model: str,
        orion_address: int,
        objects: tuple[ResolvedObjectMapping, ...] = (),
        dpls: DPLSSubIdentity | None = None,
        metadata: DownstreamDeviceMetadata = DownstreamDeviceMetadata(),
        capabilities: tuple[GatewayCapabilitySpec, ...] = (),
    ) -> ResolvedDeviceMapping:
        """Return a validated resolved device mapping."""


class ManualDeviceMappingProvider:
    """Build a resolved mapping from explicit user-supplied object rows."""

    source = MappingSource.MANUAL

    async def async_resolve(
        self,
        gateway: GatewayContext,
        model: str,
        orion_address: int,
        objects: tuple[ResolvedObjectMapping, ...] = (),
        dpls: DPLSSubIdentity | None = None,
        metadata: DownstreamDeviceMetadata = DownstreamDeviceMetadata(),
        capabilities: tuple[GatewayCapabilitySpec, ...] = (),
    ) -> ResolvedDeviceMapping:
        """Validate and return manual mapping data."""
        return ResolvedDeviceMapping(
            identity=DownstreamDeviceIdentity(
                gateway=gateway,
                model=model,
                orion_address=orion_address,
                dpls=dpls,
                metadata=metadata,
            ),
            source=self.source,
            objects=objects,
        )


class AutomaticDeviceMappingProvider:
    """Resolve mappings from documented С2000-ПП configuration tables."""

    source = MappingSource.AUTOMATIC

    def __init__(
        self,
        reader: S2000PPConfigurationReader,
        cache: S2000PPConfigurationCache,
    ) -> None:
        self._reader = reader
        self._cache = cache

    async def async_resolve(
        self,
        gateway: GatewayContext,
        model: str,
        orion_address: int,
        objects: tuple[ResolvedObjectMapping, ...] = (),
        dpls: DPLSSubIdentity | None = None,
        metadata: DownstreamDeviceMetadata = DownstreamDeviceMetadata(),
        capabilities: tuple[GatewayCapabilitySpec, ...] = (),
    ) -> ResolvedDeviceMapping:
        """Read configuration and resolve rows for one Orion device."""
        configuration = await self._cache.async_get_or_load(
            gateway.stable_id,
            self._reader.async_read,
        )
        capability_keys = {
            (
                spec.object_kind,
                spec.resolved_local_object_number(
                    None if dpls is None else dpls.base_address
                ),
                spec.zone_type,
            )
            for spec in capabilities
        }
        relay_objects = tuple(
            resolve_relay_row(row)
            for row in configuration.relays_for_device(orion_address)
            if dpls is None
            or dpls.base_address <= row.local_relay_number
            < dpls.base_address + dpls.address_count
        )
        zone_objects = tuple(
            resolve_zone_row(
                row,
                configuration.partition_id(row.partition_number),
            )
            for row in configuration.zones_for_device(orion_address)
            if dpls is None
            or dpls.base_address <= row.local_zone_number
            < dpls.base_address + dpls.address_count
        )
        if capability_keys:
            relay_objects = tuple(
                item
                for item in relay_objects
                if (item.object_kind, item.local_object_number, None)
                in capability_keys
            )
            zone_objects = tuple(
                item
                for item in zone_objects
                if (
                    item.object_kind,
                    item.local_object_number,
                    item.zone_details.zone_type,
                )
                in capability_keys
            )
        matched_keys = {
            (item.object_kind, item.local_object_number,
             None if item.zone_details is None else item.zone_details.zone_type)
            for item in relay_objects + zone_objects
        }
        for group in {
            spec.alternative_group
            for spec in capabilities
            if spec.alternative_group is not None
        }:
            matches = [
                spec for spec in capabilities
                if spec.alternative_group == group
                and (
                    spec.object_kind,
                    spec.resolved_local_object_number(
                        None if dpls is None else dpls.base_address
                    ),
                    spec.zone_type,
                ) in matched_keys
            ]
            if len(matches) > 1:
                raise AmbiguousDeviceMappingError(
                    f"Multiple S2000-PP rows match alternative capability group {group}"
                )
        if not relay_objects and not zone_objects:
            raise DeviceMappingNotFoundError(
                f"No S2000-PP rows found for Orion address {orion_address}"
            )
        return ResolvedDeviceMapping(
            identity=DownstreamDeviceIdentity(
                gateway=gateway,
                model=model,
                orion_address=orion_address,
                dpls=dpls,
                metadata=metadata,
            ),
            source=self.source,
            objects=relay_objects + zone_objects,
        )


def capability_key_for_mapping(
    mapping: ResolvedObjectMapping,
    capabilities: tuple[GatewayCapabilitySpec, ...],
    dpls: DPLSSubIdentity | None,
) -> str:
    """Return the equipment capability represented by a resolved object."""
    zone_type = None if mapping.zone_details is None else mapping.zone_details.zone_type
    dpls_base = None if dpls is None else dpls.base_address
    for spec in capabilities:
        if (
            spec.object_kind is mapping.object_kind
            and spec.resolved_local_object_number(dpls_base)
            == mapping.local_object_number
            and spec.zone_type == zone_type
        ):
            return spec.key
    raise ValueError("Manual mapping does not match an equipment capability")


def available_gateway_capabilities(
    capabilities: tuple[GatewayCapabilitySpec, ...],
    mappings: Iterable[ResolvedObjectMapping],
    dpls: DPLSSubIdentity | None,
) -> dict[str, GatewayCapabilitySpec]:
    """Return unmapped capabilities while enforcing alternative groups."""
    mapped_keys = {
        capability_key_for_mapping(mapping, capabilities, dpls)
        for mapping in mappings
    }
    mapped_groups = {
        spec.alternative_group
        for spec in capabilities
        if spec.key in mapped_keys and spec.alternative_group is not None
    }
    return {
        spec.key: spec
        for spec in capabilities
        if spec.key not in mapped_keys and spec.alternative_group not in mapped_groups
    }


def manual_mapping_for_capability(
    capability: GatewayCapabilitySpec,
    table_number: int,
    dpls: DPLSSubIdentity | None,
) -> ResolvedObjectMapping:
    """Build one manual S2000-PP row for an equipment capability."""
    local_number = capability.resolved_local_object_number(
        None if dpls is None else dpls.base_address
    )
    if capability.object_kind is ObjectKind.RELAY:
        return manual_relay_mapping(local_number, table_number)
    if capability.object_kind is ObjectKind.ZONE:
        return manual_zone_mapping(
            local_number,
            table_number,
            capability.zone_type,
            0,
            None,
        )
    raise ValueError("Unsupported gateway capability object kind")


def has_overlapping_dpls_mapping(
    identity: DownstreamDeviceIdentity,
    serialized_mappings: Iterable[dict],
) -> bool:
    """Return whether persisted mappings overlap one downstream identity."""
    for mapping_data in serialized_mappings:
        try:
            existing = ResolvedDeviceMapping.from_dict(mapping_data).identity
        except (KeyError, TypeError, ValueError):
            continue
        if dpls_ranges_overlap(identity, existing):
            return True
    return False
