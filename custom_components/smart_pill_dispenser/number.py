"""A1310 speaker volume with device readback."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PillConfigEntry
from .entity import PillEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PillConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PillVolume(entry.runtime_data, "volume")])


class PillVolume(PillEntity, NumberEntity):
    """Raw level 0..3; requires explicit enablement during hardware validation."""

    _attr_translation_key = "volume"
    _attr_native_min_value = 0
    _attr_native_max_value = 3
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float:
        return self.coordinator.data.volume

    async def async_set_native_value(self, value: float) -> None:
        if value not in (0, 1, 2, 3):
            raise ValueError("Volume must be a whole number between 0 and 3")
        await self.coordinator.async_set(volume=int(value))
