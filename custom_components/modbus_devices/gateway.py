"""Typed gateway and downstream device mapping models."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GatewayType(str, Enum):
    """Supported gateway families."""

    S2000_PP = "s2000_pp"


class MappingSource(str, Enum):
    """Source used to resolve a gateway mapping."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"


class ObjectKind(str, Enum):
    """Gateway-neutral downstream object kinds."""

    RELAY = "relay"
    INPUT = "input"
    ANALOG = "analog"
    ZONE = "zone"
    SENSOR = "sensor"


class ModbusDataArea(str, Enum):
    """Modbus address spaces used by resolved objects."""

    COIL = "coil"
    DISCRETE_INPUT = "discrete_input"
    INPUT_REGISTER = "input_register"
    HOLDING_REGISTER = "holding_register"


class CapabilityRequirement(str, Enum):
    """Requirement of a model capability in one gateway configuration."""

    REQUIRED_FOR_BASE_OPERATION = "required_for_base_operation"
    OPTIONAL_IF_CONFIGURED = "optional_if_configured"


@dataclass(frozen=True, slots=True)
class GatewayCapabilitySpec:
    """Equipment-owned description of one gateway-mappable capability."""

    key: str
    name: str
    object_kind: ObjectKind
    local_object_number: int
    requirement: CapabilityRequirement
    zone_type: int | None = None
    local_object_offset: int | None = None
    alternative_group: str | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.name:
            raise ValueError("Gateway capability key and name must not be empty")
        if self.local_object_number < 0:
            raise ValueError("Capability local object number must not be negative")
        if self.object_kind is ObjectKind.ZONE and self.zone_type is None:
            raise ValueError("Zone capability must declare its S2000-PP zone type")
        if self.object_kind is not ObjectKind.ZONE and self.zone_type is not None:
            raise ValueError("Only zone capabilities may declare a zone type")
        if self.local_object_offset is not None and self.local_object_offset < 0:
            raise ValueError("Capability local object offset must not be negative")
        if self.alternative_group is not None and not self.alternative_group.strip():
            raise ValueError("Capability alternative group must not be empty")

    def resolved_local_object_number(self, dpls_base_address: int | None) -> int:
        """Resolve an exact local number, optionally relative to a DPLS base."""
        if self.local_object_offset is None:
            return self.local_object_number
        if dpls_base_address is None:
            raise ValueError("DPLS base address is required for this capability")
        return dpls_base_address + self.local_object_offset


@dataclass(frozen=True, slots=True)
class GatewayContext:
    """Stable identity and transport context of one gateway."""

    gateway_type: GatewayType
    gateway_id: str
    connection_key: str
    modbus_unit_id: int

    def __post_init__(self) -> None:
        if not self.gateway_id.strip():
            raise ValueError("Gateway identity must not be empty")
        if not self.connection_key.strip():
            raise ValueError("Gateway connection key must not be empty")

    @property
    def stable_id(self) -> str:
        """Return an identity stable across Config Entry recreation."""
        return (
            f"{self.gateway_type.value}:"
            f"{self.connection_key}:"
            f"{self.modbus_unit_id}:"
            f"{self.gateway_id}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Config Entry storage."""
        return {
            "gateway_type": self.gateway_type.value,
            "gateway_id": self.gateway_id,
            "connection_key": self.connection_key,
            "modbus_unit_id": self.modbus_unit_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GatewayContext:
        """Restore from Config Entry storage."""
        return cls(
            gateway_type=GatewayType(data["gateway_type"]),
            gateway_id=str(data["gateway_id"]),
            connection_key=str(data["connection_key"]),
            modbus_unit_id=int(data["modbus_unit_id"]),
        )


@dataclass(frozen=True, slots=True)
class DPLSSubIdentity:
    """Stable identity of an addressable device behind an Orion KDL."""

    base_address: int
    address_count: int

    def __post_init__(self) -> None:
        if not 1 <= self.base_address <= 127:
            raise ValueError("DPLS base address must be between 1 and 127")
        if self.address_count < 1 or self.base_address + self.address_count - 1 > 127:
            raise ValueError("DPLS address range must fit within 1..127")

    def to_dict(self) -> dict[str, int]:
        return {"base_address": self.base_address, "address_count": self.address_count}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DPLSSubIdentity:
        return cls(
            base_address=int(data["base_address"]),
            address_count=int(data["address_count"]),
        )


@dataclass(frozen=True, slots=True)
class DownstreamDeviceMetadata:
    """Typed configuration metadata that is not part of physical addressing."""

    variant: str | None = None
    topology: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {"variant": self.variant}
        if self.topology is not None:
            data["topology"] = self.topology
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DownstreamDeviceMetadata:
        return cls(variant=data.get("variant"), topology=data.get("topology"))


@dataclass(frozen=True, slots=True)
class DownstreamDeviceIdentity:
    """Identity of a physical device behind a gateway."""

    gateway: GatewayContext
    model: str
    orion_address: int
    dpls: DPLSSubIdentity | None = None
    metadata: DownstreamDeviceMetadata = DownstreamDeviceMetadata()

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Downstream model must not be empty")
        if self.orion_address < 0:
            raise ValueError("Orion address must not be negative")

    @property
    def stable_id(self) -> str:
        """Return the physical identity independent of mapping source."""
        stable_id = f"{self.gateway.stable_id}:orion:{self.orion_address}"
        if self.dpls is not None:
            stable_id += f":dpls:{self.dpls.base_address}"
        return stable_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Config Entry storage."""
        return {
            "gateway": self.gateway.to_dict(),
            "model": self.model,
            "orion_address": self.orion_address,
            "dpls": None if self.dpls is None else self.dpls.to_dict(),
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DownstreamDeviceIdentity:
        """Restore from Config Entry storage."""
        dpls = data.get("dpls")
        return cls(
            gateway=GatewayContext.from_dict(data["gateway"]),
            model=str(data["model"]),
            orion_address=int(data["orion_address"]),
            dpls=None if dpls is None else DPLSSubIdentity.from_dict(dpls),
            metadata=DownstreamDeviceMetadata.from_dict(data.get("metadata", {})),
        )


def dpls_ranges_overlap(
    first: DownstreamDeviceIdentity,
    second: DownstreamDeviceIdentity,
) -> bool:
    """Return whether two devices claim overlapping DPLS addresses on one KDL."""
    if (
        first.dpls is None
        or second.dpls is None
        or first.gateway.stable_id != second.gateway.stable_id
        or first.orion_address != second.orion_address
    ):
        return False
    first_end = first.dpls.base_address + first.dpls.address_count - 1
    second_end = second.dpls.base_address + second.dpls.address_count - 1
    return max(first.dpls.base_address, second.dpls.base_address) <= min(
        first_end, second_end
    )


@dataclass(frozen=True, slots=True)
class ResolvedZoneDetails:
    """Gateway-resolved metadata for a downstream zone object."""

    zone_type: int
    partition_number: int
    partition_id: int | None
    expanded_state_address: int
    expanded_state_data_area: ModbusDataArea = ModbusDataArea.INPUT_REGISTER

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Config Entry storage."""
        return {
            "zone_type": self.zone_type,
            "partition_number": self.partition_number,
            "partition_id": self.partition_id,
            "expanded_state_address": self.expanded_state_address,
            "expanded_state_data_area": self.expanded_state_data_area.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResolvedZoneDetails:
        """Restore from Config Entry storage."""
        partition_id = data.get("partition_id")
        return cls(
            zone_type=int(data["zone_type"]),
            partition_number=int(data["partition_number"]),
            partition_id=None if partition_id is None else int(partition_id),
            expanded_state_address=int(data["expanded_state_address"]),
            expanded_state_data_area=ModbusDataArea(
                data.get(
                    "expanded_state_data_area",
                    ModbusDataArea.INPUT_REGISTER.value,
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ResolvedObjectMapping:
    """Resolved address of one object belonging to a downstream device."""

    object_kind: ObjectKind
    data_area: ModbusDataArea
    local_object_number: int
    gateway_object_number: int
    modbus_address: int
    zone_details: ResolvedZoneDetails | None = None

    def __post_init__(self) -> None:
        if self.local_object_number < 0:
            raise ValueError("Local object number must not be negative")
        if self.gateway_object_number < 0:
            raise ValueError("Gateway object number must not be negative")
        if self.modbus_address < 0:
            raise ValueError("Modbus address must not be negative")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Config Entry storage."""
        return {
            "object_kind": self.object_kind.value,
            "data_area": self.data_area.value,
            "local_object_number": self.local_object_number,
            "gateway_object_number": self.gateway_object_number,
            "modbus_address": self.modbus_address,
            "zone_details": (
                None if self.zone_details is None else self.zone_details.to_dict()
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResolvedObjectMapping:
        """Restore from Config Entry storage."""
        zone_data = data.get("zone_details")
        return cls(
            object_kind=ObjectKind(data["object_kind"]),
            data_area=ModbusDataArea(data["data_area"]),
            local_object_number=int(data["local_object_number"]),
            gateway_object_number=int(data["gateway_object_number"]),
            modbus_address=int(data["modbus_address"]),
            zone_details=(
                None
                if zone_data is None
                else ResolvedZoneDetails.from_dict(zone_data)
            ),
        )


@dataclass(frozen=True, slots=True)
class ResolvedDeviceMapping:
    """Complete resolved mapping consumed by an equipment instance."""

    identity: DownstreamDeviceIdentity
    source: MappingSource
    objects: tuple[ResolvedObjectMapping, ...]

    def __post_init__(self) -> None:
        if not self.objects:
            raise ValueError("Resolved device mapping must contain objects")

        keys = {
            (
                item.object_kind,
                item.local_object_number,
                None if item.zone_details is None else item.zone_details.zone_type,
            )
            for item in self.objects
        }
        if len(keys) != len(self.objects):
            raise ValueError("Duplicate local object mapping")

        gateway_keys = {
            (item.data_area, item.gateway_object_number)
            for item in self.objects
        }
        if len(gateway_keys) != len(self.objects):
            raise ValueError("Duplicate gateway object mapping")

        modbus_keys = {
            (item.data_area, item.modbus_address)
            for item in self.objects
        }
        if len(modbus_keys) != len(self.objects):
            raise ValueError("Duplicate resolved Modbus address")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Config Entry storage."""
        return {
            "identity": self.identity.to_dict(),
            "source": self.source.value,
            "objects": [item.to_dict() for item in self.objects],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResolvedDeviceMapping:
        """Restore from Config Entry storage."""
        return cls(
            identity=DownstreamDeviceIdentity.from_dict(data["identity"]),
            source=MappingSource(data["source"]),
            objects=tuple(
                ResolvedObjectMapping.from_dict(item)
                for item in data["objects"]
            ),
        )

    def objects_for(
        self,
        object_kind: ObjectKind,
        data_area: ModbusDataArea,
    ) -> tuple[ResolvedObjectMapping, ...]:
        """Return mappings for one equipment capability."""
        return tuple(
            item
            for item in self.objects
            if item.object_kind is object_kind and item.data_area is data_area
        )


def compatible_gateway_contexts(
    serialized_mappings: Iterable[Mapping[str, Any] | None],
    *,
    gateway_type: GatewayType,
    connection_key: str,
    modbus_unit_id: int,
) -> dict[str, GatewayContext]:
    """Return reusable gateway contexts matching one transport endpoint."""
    contexts: dict[str, GatewayContext] = {}
    for mapping_data in serialized_mappings:
        if not mapping_data:
            continue
        try:
            mapping = ResolvedDeviceMapping.from_dict(dict(mapping_data))
        except (KeyError, TypeError, ValueError):
            continue
        gateway = mapping.identity.gateway
        if (
            gateway.gateway_type is gateway_type
            and gateway.connection_key == connection_key
            and gateway.modbus_unit_id == modbus_unit_id
        ):
            contexts[gateway.stable_id] = gateway
    return contexts
