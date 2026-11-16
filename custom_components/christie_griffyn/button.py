"""Buttons for one-shot projector actions."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ChristieConfigEntry, ChristieCoordinator
from .entity import ChristieEntity
from .helpers import async_run_command

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ChristieButtonDescription(ButtonEntityDescription):
    """An action sent as a fixed command, e.g. ``(LCB 1)``."""

    code: str
    values: tuple[int, ...] = ()


BUTTONS: tuple[ChristieButtonDescription, ...] = (
    ChristieButtonDescription(
        key="refresh",
        code="",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ChristieButtonDescription(
        key="lens_calibrate",
        code="LCB",
        values=(1,),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieButtonDescription(
        key="lens_home",
        code="LCB+HOME",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChristieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the buttons."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(ChristieButton(coordinator, description) for description in BUTTONS)


class ChristieButton(ChristieEntity, ButtonEntity):
    """Send one command when pressed; ``refresh`` re-reads everything instead."""

    entity_description: ChristieButtonDescription

    def __init__(
        self, coordinator: ChristieCoordinator, description: ChristieButtonDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    async def async_press(self) -> None:
        d = self.entity_description
        if d.code:
            await async_run_command(self.coordinator.client.async_set(d.code, *d.values))
        self.coordinator.request_full_refresh()
        await self.coordinator.async_request_refresh()
