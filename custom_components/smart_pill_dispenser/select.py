"""A1310 tone selection with device readback."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PillConfigEntry
from .const import RINGTONES
from .entity import PillEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PillConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PillRingtone(entry.runtime_data, "ringtone")])


class PillRingtone(PillEntity, SelectEntity):
    """Select an existing tone; no audio upload is performed."""

    _attr_translation_key = "ringtone"
    _attr_options = list(RINGTONES)
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    @property
    def current_option(self) -> str:
        return RINGTONES[self.coordinator.data.ringtone]

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set(ringtone=RINGTONES.index(option))
