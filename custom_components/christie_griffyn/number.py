"""Numbers: laser power, image settings and lens position."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ChristieConfigEntry, ChristieCoordinator
from .entity import ChristieEntity
from .helpers import async_run_command

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ChristieNumberDescription(NumberEntityDescription):
    """A numeric setting. The projector uses integers; ``scale`` converts.

    For example laser power 750 on the wire is 75.0 % with ``scale=0.1``.
    When ``range_code`` is set, the min/max come from ``(CODE?m)``.
    """

    code: str
    scale: float = 1.0
    range_code: str | None = None


NUMBERS: tuple[ChristieNumberDescription, ...] = (
    # LiteLOC can drop lasers at 30% or below; the wire range is 300-1000.
    ChristieNumberDescription(
        key="laser_power",
        code="LAS+POWR",
        scale=0.1,
        native_min_value=30,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
    ),
    ChristieNumberDescription(
        key="red_laser",
        code="LAS+REDP",
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="green_laser",
        code="LAS+GRNP",
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="blue_laser",
        code="LAS+BLUP",
        scale=0.1,
        native_min_value=0,
        native_max_value=100,
        native_step=0.1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="white_x",
        code="LAS+WHTX",
        scale=0.0001,
        native_min_value=0.25,
        native_max_value=0.45,
        native_step=0.0001,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="white_y",
        code="LAS+WHTY",
        scale=0.0001,
        native_min_value=0.25,
        native_max_value=0.45,
        native_step=0.0001,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="sharpness",
        code="DTL",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    ),
    ChristieNumberDescription(
        key="gamma",
        code="GAM",
        scale=0.001,
        native_min_value=1.0,
        native_max_value=3.0,
        native_step=0.001,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    ChristieNumberDescription(
        key="max_luminance",
        code="GAM+MAXL",
        native_min_value=100,
        native_max_value=2000,
        native_step=1,
        native_unit_of_measurement="cd/m²",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="min_luminance",
        code="GAM+MINL",
        native_min_value=0,
        native_max_value=1000,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="pq_white_level",
        code="GAM+PQWL",
        native_min_value=50,
        native_max_value=2000,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="frame_delay",
        code="FRD",
        scale=0.001,
        native_min_value=1.0,
        native_max_value=3.0,
        native_step=0.001,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="realblack_delay",
        code="RBK+TIME",
        scale=0.1,
        native_min_value=0,
        native_max_value=2.5,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="realblack_threshold",
        code="RBK+LOSL",
        native_min_value=0,
        native_max_value=255,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    # Lens moves change the picture position on screen, so these are off
    # by default; ranges come from the last lens calibration.
    ChristieNumberDescription(
        key="lens_horizontal",
        code="LHO",
        range_code="LHO",
        native_min_value=-2000,
        native_max_value=2000,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="lens_vertical",
        code="LVO",
        range_code="LVO",
        native_min_value=-2000,
        native_max_value=2000,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="lens_zoom",
        code="ZOM",
        range_code="ZOM",
        native_min_value=-2000,
        native_max_value=2000,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieNumberDescription(
        key="lens_focus",
        code="FCS",
        range_code="FCS",
        native_min_value=-2000,
        native_max_value=2000,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChristieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the numbers."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(ChristieNumber(coordinator, description) for description in NUMBERS)


class ChristieNumber(ChristieEntity, NumberEntity):
    """A numeric setting."""

    entity_description: ChristieNumberDescription

    def __init__(
        self, coordinator: ChristieCoordinator, description: ChristieNumberDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    def _range(self) -> tuple[int, int] | None:
        code = self.entity_description.range_code
        return self.coordinator.data.ranges.get(code) if code else None

    @property
    def native_min_value(self) -> float:
        if (limits := self._range()) is not None:
            return limits[0] * self.entity_description.scale
        return super().native_min_value

    @property
    def native_max_value(self) -> float:
        if (limits := self._range()) is not None:
            return limits[1] * self.entity_description.scale
        return super().native_max_value

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data.number(self.entity_description.code) is not None
        )

    @property
    def native_value(self) -> float | None:
        raw = self.coordinator.data.number(self.entity_description.code)
        if raw is None:
            return None
        scale = self.entity_description.scale
        return raw if scale == 1 else round(raw * scale, 4)

    async def async_set_native_value(self, value: float) -> None:
        raw = round(value / self.entity_description.scale)
        await async_run_command(self.coordinator.async_set(self.entity_description.code, raw))
