"""Switches: power, shutter and on/off settings."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import POST_POWER_REFRESH_DELAY
from .coordinator import ChristieConfigEntry, ChristieCoordinator
from .entity import ChristieEntity
from .helpers import async_run_command

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ChristieSwitchDescription(SwitchEntityDescription):
    """A setting toggled with ``(CODE on_value)`` / ``(CODE off_value)``."""

    code: str
    on_value: int = 1
    off_value: int = 0


SETTING_SWITCHES: tuple[ChristieSwitchDescription, ...] = (
    # (SHU 0) opens the shutter, (SHU 1) closes it.
    ChristieSwitchDescription(key="shutter_open", code="SHU", on_value=0, off_value=1),
    ChristieSwitchDescription(key="freeze", code="FRZ"),
    ChristieSwitchDescription(key="osd", code="OSD", entity_category=EntityCategory.CONFIG),
    ChristieSwitchDescription(
        key="realblack", code="RBK+SLCT", entity_category=EntityCategory.CONFIG
    ),
    ChristieSwitchDescription(
        key="stealth_mode", code="STH+MODE", entity_category=EntityCategory.CONFIG
    ),
    ChristieSwitchDescription(
        key="camera_friendly_color",
        code="LAS+CFCM",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="enhanced_healing",
        code="ENH+SLCT",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="auto_power_on",
        code="APW",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="electronics_on_in_standby",
        code="PWR+ELEC",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="film_mode_detect",
        code="FMD",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="video_thumbnails",
        code="THM",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="lens_lock",
        code="LCB+LOCK",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="front_ir",
        code="KEN+FRNT",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="rear_ir",
        code="KEN+REAR",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="wired_keypad",
        code="KEN+WIRE",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="invert_3d",
        code="TDN",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="keystone_gain_compensation",
        code="WRP+KGAN",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSwitchDescription(
        key="black_level_offsets",
        code="BLO+SLCT",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChristieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the power switch and the setting switches."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SwitchEntity] = [ChristiePowerSwitch(coordinator)]
    entities.extend(ChristieSettingSwitch(coordinator, d) for d in SETTING_SWITCHES)
    async_add_entities(entities)


class ChristiePowerSwitch(ChristieEntity, SwitchEntity):
    """Projector power. On while on or warming up; off in standby or cooling down."""

    _attr_translation_key = "power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: ChristieCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.is_on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"power_state": self.coordinator.data.power_state_key}

    async def _async_power(self, on: bool) -> None:
        # Power changes can take a while to acknowledge, so only an ERR
        # reply counts as failure here; the state is read back afterwards.
        await async_run_command(
            self.coordinator.client.async_set("PWR", 1 if on else 0, wait_for_ack=False)
        )
        self.coordinator.begin_power_grace(POST_POWER_REFRESH_DELAY)
        await asyncio.sleep(POST_POWER_REFRESH_DELAY)
        self.coordinator.end_power_grace()
        self.coordinator.request_full_refresh(static=True)
        await self.coordinator.async_read_back("PWR")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_power(False)


class ChristieSettingSwitch(ChristieEntity, SwitchEntity):
    """A setting with two values."""

    entity_description: ChristieSwitchDescription

    def __init__(
        self, coordinator: ChristieCoordinator, description: ChristieSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data.value(self.entity_description.code) is not None
        )

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.number(self.entity_description.code)
        if value is None:
            return None
        return value == self.entity_description.on_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        d = self.entity_description
        await async_run_command(self.coordinator.async_set(d.code, d.on_value))

    async def async_turn_off(self, **kwargs: Any) -> None:
        d = self.entity_description
        await async_run_command(self.coordinator.async_set(d.code, d.off_value))
