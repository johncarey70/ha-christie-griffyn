"""Selects: input, profile, test pattern and multi-value settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import ChristieConfigEntry, ChristieCoordinator
from .entity import ChristieEntity
from .helpers import async_run_command
from .protocol import ListOption

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ChristieSelectDescription(SelectEntityDescription):
    """A setting chosen with ``(CODE value)``.

    Choices come from the projector's own ``?L`` list when ``list_code`` is
    set, otherwise from ``choices`` (values from Christie's reference).
    """

    code: str
    choices: dict[int, str] = field(default_factory=dict)
    list_code: str | None = None


SELECTS: tuple[ChristieSelectDescription, ...] = (
    ChristieSelectDescription(key="input", code="CHA", list_code="CHA"),
    ChristieSelectDescription(
        key="input_slot",
        code="SIN",
        list_code="SIN",
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="port_configuration",
        code="SIN+PORT",
        choices={
            1: "One-Port",
            2: "Two-Port",
            4: "Four-Port Quadrants",
            5: "One-Port, Dual-Input 3D",
            9: "Four-Port, 4 Viewer 2D",
            10: "Four-Port, 2 Viewer 3D",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="test_pattern", code="ITP", list_code="ITP", entity_category=EntityCategory.CONFIG
    ),
    ChristieSelectDescription(
        key="engine_test_pattern",
        code="ETP",
        choices={
            255: "Off",
            0: "Flat Black",
            1: "Green",
            2: "Red",
            3: "Blue",
            4: "White",
            5: "8x8 Green Checker",
            6: "8x8 Red Checker",
            7: "8x8 Blue Checker",
            8: "8x8 White Checker",
            9: "Convergence Border & Cross (Green)",
            10: "Convergence Border & Cross (Red)",
            11: "Convergence Border & Cross (Blue)",
            12: "Convergence Border & Cross (White)",
            13: "Convergence Border & Cross (Multi-color)",
            238: "Color Bars",
            243: "17 Point",
            247: "Diagonal Lines",
            248: "Dark Segmented Ramp",
            249: "Bright Segmented Ramp",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="litelock",
        code="LAS+MODE",
        choices={1: "Disabled", 3: "Enabled"},
        entity_category=EntityCategory.CONFIG,
    ),
    ChristieSelectDescription(
        key="fan_profile",
        code="TMC+MODE",
        choices={0: "Standard", 1: "Quiet", 2: "Performance"},
        entity_category=EntityCategory.CONFIG,
    ),
    ChristieSelectDescription(
        key="gamma_function",
        code="BGC",
        choices={
            0: "Auto Detect",
            1: "sRGB",
            2: "Power Law Function",
            3: "Classic",
            4: "ITU-R BT.1886",
            6: "HDR/PQ (SMPTE ST 2084)",
            7: "Raw PQ",
        },
        entity_category=EntityCategory.CONFIG,
    ),
    ChristieSelectDescription(
        key="color_space",
        code="CSP",
        choices={
            0: "Auto Detect",
            1: "RGB full range",
            2: "YCbCr HDTV (BT.709)",
            3: "RGB limited range",
            4: "YCbCr HDTV expanded range",
            5: "YCbCr JPEG full range",
            6: "YCbCr UHDTV (BT.2020)",
            7: "YCbCr UHDTV (BT.2020) full range",
            8: "XYZ",
        },
        entity_category=EntityCategory.CONFIG,
    ),
    ChristieSelectDescription(
        key="resize",
        code="SZP",
        choices={
            0: "Auto",
            1: "No Resizing",
            2: "Full Size",
            3: "Full Width",
            4: "Full Height",
        },
        entity_category=EntityCategory.CONFIG,
    ),
    ChristieSelectDescription(
        key="mode_3d",
        code="TDM",
        choices={
            0: "Off",
            1: "Auto Detect",
            2: "On",
            3: "Side-by-Side",
            5: "Top-and-Bottom",
            6: "Frame Packing",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="sync_out_3d",
        code="TDO",
        choices={0: "To Emitter", 1: "To Projector"},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="warp",
        code="WRP+SLCT",
        list_code="WRP+SLCT",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="edge_blend",
        code="EBL+SLCT",
        choices={0: "Off", 1: "Blend 1", 2: "Blend 2", 3: "Blend 3", 4: "Blend 4", 11: "Basic"},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="black_level_blend",
        code="EBB+SLCT",
        choices={0: "Off", 1: "Blend 1", 2: "Blend 2", 3: "Blend 3", 4: "Blend 4", 11: "Basic"},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="color_enable",
        code="CLE",
        choices={
            0: "White",
            1: "Red",
            2: "Green",
            3: "Blue",
            4: "Yellow",
            5: "Cyan",
            6: "Magenta",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="edid_frame_rate",
        code="EDO",
        choices={24: "24Hz", 25: "25Hz", 30: "30Hz", 50: "50Hz", 60: "60Hz", 120: "120Hz"},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="screen_orientation",
        code="SOR",
        choices={
            0: "Front Projection",
            1: "Rear Projection",
            2: "Front Projection Inverted",
            3: "Rear Projection Inverted",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="splash_color",
        code="SPS+COLR",
        choices={1: "Red", 2: "Green", 3: "Blue", 7: "Black"},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="osd_position",
        code="MSP",
        choices={
            0: "Top Left",
            1: "Top Center",
            2: "Top Right",
            3: "Center Left",
            4: "Center",
            5: "Center Right",
            6: "Bottom Left",
            7: "Bottom Center",
            8: "Bottom Right",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="christie_link_input",
        code="CHL+INPT",
        choices={0: "Input/Loop Out", 1: "Christie Link Port 1", 2: "Christie Link Port 2"},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="sdi_payload",
        code="SDI",
        choices={
            0: "Auto Detect",
            1: "Custom",
            2: "3G-A 1080p60",
            3: "3G-A 1080p59.94",
            4: "3G-A 1080p50",
            5: "3G-A 2K60",
            6: "3G-A 2K59.94",
            7: "3G-A 2K50",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="language",
        code="LOC+LANG",
        choices={
            0: "English",
            1: "French",
            2: "German",
            3: "Spanish",
            4: "Italian",
            5: "Chinese (Simplified)",
            6: "Japanese",
            7: "Korean",
            8: "Russian",
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ChristieSelectDescription(
        key="temperature_units",
        code="LOC+TEMP",
        choices={0: "Celsius", 1: "Fahrenheit"},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChristieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the selects."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SelectEntity] = [ChristieProfileSelect(coordinator)]
    entities.extend(ChristieSelect(coordinator, description) for description in SELECTS)
    async_add_entities(entities)


class ChristieSelect(ChristieEntity, SelectEntity):
    """A multi-value setting."""

    entity_description: ChristieSelectDescription

    def __init__(
        self, coordinator: ChristieCoordinator, description: ChristieSelectDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    def _choices(self) -> dict[int, str]:
        d = self.entity_description
        if d.list_code is not None:
            options = self.coordinator.data.lists.get(d.list_code, ())
            choices = {o.value: o.label for o in options if o.available and _selectable(d, o)}
        else:
            choices = dict(d.choices)
        # Show the current value even if it is not in the known list.
        reply = self.coordinator.data.value(d.code)
        if reply is not None and reply.number is not None and reply.number not in choices:
            choices[reply.number] = reply.text or str(reply.number)
        return _unique_labels(choices)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data.value(self.entity_description.code) is not None
        )

    @property
    def options(self) -> list[str]:
        return list(self._choices().values())

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.number(self.entity_description.code)
        if value is None:
            return None
        return self._choices().get(value)

    async def async_select_option(self, option: str) -> None:
        value = next(v for v, label in self._choices().items() if label == option)
        await async_run_command(self.coordinator.async_set(self.entity_description.code, value))


class ChristieProfileSelect(ChristieEntity, SelectEntity, RestoreEntity):
    """Recall a saved projector profile with ``(PRO x)``.

    The projector cannot report which profile is active, so this shows the
    last profile chosen here (assumed state).
    """

    _attr_translation_key = "profile"
    _attr_assumed_state = True

    def __init__(self, coordinator: ChristieCoordinator) -> None:
        super().__init__(coordinator, "profile")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator.last_profile is not None:
            return
        if (last := await self.async_get_last_state()) is None:
            return
        for value, label in self._choices().items():
            if label == last.state:
                self.coordinator.last_profile = value

    def _choices(self) -> dict[int, str]:
        options = self.coordinator.data.lists.get("PRO", ())
        return {
            o.value: f"{o.value}: {o.label}" for o in options if o.label and o.label != "(Empty)"
        }

    @property
    def options(self) -> list[str]:
        return list(self._choices().values())

    @property
    def current_option(self) -> str | None:
        if self.coordinator.last_profile is None:
            return None
        return self._choices().get(self.coordinator.last_profile)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"profile_number": self.coordinator.last_profile}

    async def async_select_option(self, option: str) -> None:
        value = next(v for v, label in self._choices().items() if label == option)
        await async_run_command(self.coordinator.client.async_set("PRO", value))
        self.coordinator.last_profile = value
        self.coordinator.request_full_refresh()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


def _selectable(description: ChristieSelectDescription, option: ListOption) -> bool:
    # "None" (input 0) is listed but is not a real input to switch to.
    return not (description.code == "SIN" and option.value == 0)


def _unique_labels(choices: dict[int, str]) -> dict[int, str]:
    """Make labels unique; the Griffyn lists two different "Two-Port DP" entries."""
    counts: dict[str, int] = {}
    for label in choices.values():
        counts[label] = counts.get(label, 0) + 1
    return {
        value: f"{label} ({value})" if counts[label] > 1 else label
        for value, label in choices.items()
    }
