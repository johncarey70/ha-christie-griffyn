"""Base entity for the projector."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ChristieCoordinator


class ChristieEntity(CoordinatorEntity[ChristieCoordinator]):
    """Shared device info and unique-id scheme."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ChristieCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_id}_{key}"

        data = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            connections={(CONNECTION_NETWORK_MAC, data.mac)} if data.mac else set(),
            manufacturer=MANUFACTURER,
            model=data.model,
            serial_number=data.serial_number,
            name=entry.title,
            sw_version=data.firmware,
            configuration_url=None,
        )
