"""Read-only device information."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PillConfigEntry
from .entity import PillEntity

DESCRIPTIONS = (
    SensorEntityDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_success",
        translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PillConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add status sensors."""
    async_add_entities(PillSensor(entry.runtime_data, desc) for desc in DESCRIPTIONS)


class PillSensor(PillEntity, SensorEntity):
    """Display only values returned by the device."""

    def __init__(self, coordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        if self.entity_description.key == "last_success":
            return self.coordinator.last_success
        return getattr(self.coordinator.data, self.entity_description.key)
