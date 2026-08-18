"""Mapping providers for gateway-connected equipment."""

from __future__ import annotations

from typing import Protocol

from .gateway import (
    DPLSSubIdentity,
    DownstreamDeviceIdentity,
    DownstreamDeviceMetadata,
    GatewayContext,
    MappingSource,
    ResolvedDeviceMapping,
    ResolvedObjectMapping,
)
from .s2000_pp import (
    S2000PPConfigurationCache,
    S2000PPConfigurationReader,
    resolve_relay_row,
    resolve_zone_row,
)


class DeviceMappingNotFoundError(ValueError):
    """Raised when no configuration rows belong to the requested device."""


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
    ) -> ResolvedDeviceMapping:
        """Read configuration and resolve rows for one Orion device."""
        configuration = await self._cache.async_get_or_load(
            gateway.stable_id,
            self._reader.async_read,
        )
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
