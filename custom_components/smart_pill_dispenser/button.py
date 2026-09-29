"""Refresh a sleeping dispenser after waking it manually."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PillConfigEntry
from .entity import PillEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PillConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            PillRefresh(entry.runtime_data, "refresh"),
            PillRecordIntake(entry.runtime_data, "record_intake"),
        ]
    )


class PillRefresh(PillEntity, ButtonEntity):
    """Remain usable even when a previous poll failed."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class PillRecordIntake(PillEntity, ButtonEntity):
    """A manual journal entry, independent of the radio or physical dispenser."""

    _attr_translation_key = "record_intake"
    _attr_icon = "mdi:check"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_record_intake()
