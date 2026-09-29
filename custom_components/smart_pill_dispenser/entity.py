"""Shared device identity."""

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PillCoordinator


class PillEntity(CoordinatorEntity[PillCoordinator]):
    """An entity belonging to one physical A1310."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PillCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.client.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.client.address)},
            name="Smart Pill Dispenser A1310",
            manufacturer="Quin",
            model="A1310 (A1310-WHBL-1)",
            sw_version=coordinator.data.firmware,
        )
