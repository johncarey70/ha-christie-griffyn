"""Sensors: power state, hours, signal, temperatures, fans and health."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import POWER_STATE_KEYS
from .coordinator import ChristieConfigEntry, ChristieCoordinator, ProjectorData
from .entity import ChristieEntity
from .protocol import StatusItem, parse_float, parse_hours, parse_temperature_c

PARALLEL_UPDATES = 0

type SensorValue = str | int | float | None


@dataclass(frozen=True, kw_only=True)
class ChristieSensorDescription(SensorEntityDescription):
    """A sensor computed from the projector data."""

    value_fn: Callable[[ProjectorData], SensorValue]
    attrs_fn: Callable[[ProjectorData], dict[str, Any]] | None = None


def _status(
    key: str, parse: Callable[[str | None], SensorValue]
) -> Callable[[ProjectorData], SensorValue]:
    return lambda data: parse(data.status_value(key))


def _text(value: str | None) -> str | None:
    return value or None


def _frame_delay_ms(data: ProjectorData) -> float | None:
    reply = data.value("FRD+TIME")
    return parse_float(reply.text) if reply else None


def _signal_attr(name: str) -> Callable[[ProjectorData], SensorValue]:
    def value(data: ProjectorData) -> SensorValue:
        signal = data.active_signal
        return getattr(signal, name) if signal else None

    return value


SENSORS: tuple[ChristieSensorDescription, ...] = (
    ChristieSensorDescription(
        key="power_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(POWER_STATE_KEYS.values()),
        value_fn=lambda data: data.power_state_key,
    ),
    ChristieSensorDescription(
        key="laser_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=_status("LGHT_186", parse_hours),
    ),
    ChristieSensorDescription(
        key="laser_standby_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("LGHT_185", parse_hours),
    ),
    ChristieSensorDescription(
        key="laser_on_cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status(
            "LGHT_187", lambda v: int(n) if (n := parse_float(v)) is not None else None
        ),
    ),
    ChristieSensorDescription(
        key="projector_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status("SYST_000", parse_hours),
    ),
    ChristieSensorDescription(
        key="diffuser_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("SYST_226", parse_hours),
    ),
    ChristieSensorDescription(
        key="light_source_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status("LGHT_000", _text),
    ),
    ChristieSensorDescription(
        key="litelock_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status("LGHT_103", _text),
    ),
    ChristieSensorDescription(
        key="signal",
        value_fn=_signal_attr("description"),
        attrs_fn=lambda data: {
            "port_type": s.port_type if (s := data.active_signal) else None,
            "note": s.note if s else None,
        },
    ),
    ChristieSensorDescription(key="resolution", value_fn=_signal_attr("resolution")),
    ChristieSensorDescription(
        key="frame_rate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=3,
        value_fn=_signal_attr("frame_rate"),
    ),
    ChristieSensorDescription(key="color_format", value_fn=_signal_attr("color_format")),
    ChristieSensorDescription(key="bit_depth", value_fn=_signal_attr("bit_depth")),
    ChristieSensorDescription(key="dynamic_range", value_fn=_signal_attr("dynamic_range")),
    ChristieSensorDescription(
        key="output_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=3,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status("SIGN_050", parse_float),
    ),
    ChristieSensorDescription(
        key="frame_delay_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_frame_delay_ms,
    ),
    ChristieSensorDescription(
        key="inlet_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("SYST_027", parse_float),
    ),
    ChristieSensorDescription(
        key="psu_output_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("SYST_096", parse_float),
    ),
    ChristieSensorDescription(
        key="diffuser_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("SYST_100", parse_float),
    ),
    ChristieSensorDescription(
        key="pitch_roll",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("SYST_001", _text),
    ),
    ChristieSensorDescription(
        key="laser_cpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("LGHT_101", parse_temperature_c),
    ),
    ChristieSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=["ok", "warning", "error"],
        value_fn=lambda data: data.health,
        attrs_fn=lambda data: {
            "problems": [f"{item.description}: {item.value}" for item in data.problems],
        },
    ),
)

# Temperatures enabled by default; the rest are added disabled.
DEFAULT_TEMPERATURES = {"TEMP_002", "TEMP_011", "TEMP_124"}
_TEMP_SUFFIX = re.compile(r"\s*\(Temp \d+\)$")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChristieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add fixed sensors, then one per temperature and fan the projector reports."""
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [ChristieSensor(coordinator, d) for d in SENSORS]
    entities.append(ChristieLastMessageSensor(coordinator))
    async_add_entities(entities)

    known: set[str] = set()

    @callback
    def add_status_sensors() -> None:
        new: list[SensorEntity] = []
        for item in coordinator.data.status.values():
            if item.key in known:
                continue
            if item.group == "TEMP":
                new.append(ChristieTemperatureSensor(coordinator, item))
            elif item.group == "COOL" and item.value.upper().endswith("RPM"):
                new.append(ChristieFanSensor(coordinator, item))
            else:
                continue
            known.add(item.key)
        if new:
            async_add_entities(new)

    add_status_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_status_sensors))


class ChristieSensor(ChristieEntity, SensorEntity):
    """A sensor described by ChristieSensorDescription."""

    entity_description: ChristieSensorDescription

    def __init__(
        self, coordinator: ChristieCoordinator, description: ChristieSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> SensorValue:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)


class _StatusItemSensor(ChristieEntity, SensorEntity):
    """A sensor for one status item, named after the projector's description."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ChristieCoordinator, item: StatusItem) -> None:
        super().__init__(coordinator, item.key.lower())
        self._key = item.key
        self._attr_name = _TEMP_SUFFIX.sub("", item.description) or item.key

    def _item(self) -> StatusItem | None:
        return self.coordinator.data.status.get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self._item() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        item = self._item()
        if item is None:
            return None
        return {"raw_value": item.value, "status": ("ok", "warning", "error")[min(item.state, 2)]}


class ChristieTemperatureSensor(_StatusItemSensor):
    """A temperature from the status system, always reported in °C."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: ChristieCoordinator, item: StatusItem) -> None:
        super().__init__(coordinator, item)
        self._attr_entity_registry_enabled_default = item.key in DEFAULT_TEMPERATURES

    @property
    def native_value(self) -> float | None:
        item = self._item()
        return parse_temperature_c(item.value) if item else None


class ChristieFanSensor(_StatusItemSensor):
    """A fan or pump speed from the status system."""

    _attr_native_unit_of_measurement = REVOLUTIONS_PER_MINUTE
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:fan"

    @property
    def native_value(self) -> float | None:
        item = self._item()
        return parse_float(item.value) if item else None


class ChristieLastMessageSensor(ChristieEntity, SensorEntity):
    """The latest asynchronous FYI/ERR message the projector sent."""

    _attr_translation_key = "last_message"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ChristieCoordinator) -> None:
        super().__init__(coordinator, "last_message")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.events:
            return None
        return self.coordinator.events[0].text[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.events:
            return None
        event = self.coordinator.events[0]
        return {
            "kind": event.kind,
            "number": event.number,
            "time": event.time.isoformat(),
            "recent": [
                f"{e.time.isoformat()} {e.kind}{e.number:05d} {e.text}"
                for e in self.coordinator.events
            ],
        }
