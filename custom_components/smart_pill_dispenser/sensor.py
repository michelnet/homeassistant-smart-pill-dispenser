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
from homeassistant.util import dt as dt_util

from . import PillConfigEntry
from .ble import BLEStatus
from .ble_protocol import PROTOCOL_STATES
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

BLE_DESCRIPTIONS = (
    SensorEntityDescription(
        key="service_count",
        translation_key="service_count",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="protocol_status",
        translation_key="protocol_status",
        device_class=SensorDeviceClass.ENUM,
        options=PROTOCOL_STATES,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

LOCAL_DESCRIPTIONS = (
    SensorEntityDescription(
        key="intake_status",
        translation_key="intake_status",
        device_class=SensorDeviceClass.ENUM,
        options=["not_recorded", "taken", "skipped"],
    ),
    SensorEntityDescription(
        key="last_intake_record",
        translation_key="last_intake_record",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

SCHEDULE_DESCRIPTION = SensorEntityDescription(
    key="schedule_status",
    translation_key="schedule_status",
    device_class=SensorDeviceClass.ENUM,
    options=[
        "not_configured",
        "transferring",
        "sent_unverified",
        "transfer_failed",
        "transfer_interrupted",
    ],
)


async def async_setup_entry(
    hass: HomeAssistant, entry: PillConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add status sensors."""
    descriptions = DESCRIPTIONS
    if isinstance(entry.runtime_data.data, BLEStatus):
        descriptions += BLE_DESCRIPTIONS
    async_add_entities(PillSensor(entry.runtime_data, desc) for desc in descriptions)
    local_descriptions = LOCAL_DESCRIPTIONS
    if isinstance(entry.runtime_data.data, BLEStatus):
        local_descriptions += (SCHEDULE_DESCRIPTION,)
    async_add_entities(
        PillLocalSensor(entry.runtime_data, desc) for desc in local_descriptions
    )


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


class PillLocalSensor(PillSensor):
    """Show HA records, explicitly separate from observed device readings."""

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        value = self.coordinator.local_state[self.entity_description.key]
        if self.entity_description.key == "last_intake_record":
            return dt_util.parse_datetime(value) if value else None
        return value

    @property
    def extra_state_attributes(self):
        state = self.coordinator.local_state
        if self.entity_description.key == "schedule_status":
            return {
                "requested_daily_times": state["times"],
                "sent_at": state["schedule_sent_at"],
                "timezone": state["schedule_timezone"],
                "device_confirmed": False,
            }
        return {"source": "manual", "recorded_at": state["last_intake_record"]}
