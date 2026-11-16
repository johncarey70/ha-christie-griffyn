"""Binary sensors: problem, signal and frame lock."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ChristieConfigEntry, ChristieCoordinator, ProjectorData
from .entity import ChristieEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ChristieBinarySensorDescription(BinarySensorEntityDescription):
    """A yes/no value computed from the projector data."""

    value_fn: Callable[[ProjectorData], bool | None]


def _frame_locked(data: ProjectorData) -> bool | None:
    value = data.status_value("SIGN_051")
    return None if value is None else value.lower() == "locked"


BINARY_SENSORS: tuple[ChristieBinarySensorDescription, ...] = (
    ChristieBinarySensorDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.health != "ok",
    ),
    ChristieBinarySensorDescription(
        key="signal_present",
        value_fn=lambda data: data.active_signal is not None,
    ),
    ChristieBinarySensorDescription(
        key="frame_locked",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_frame_locked,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChristieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(ChristieBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class ChristieBinarySensor(ChristieEntity, BinarySensorEntity):
    """A binary sensor described by ChristieBinarySensorDescription."""

    entity_description: ChristieBinarySensorDescription

    def __init__(
        self, coordinator: ChristieCoordinator, description: ChristieBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)
