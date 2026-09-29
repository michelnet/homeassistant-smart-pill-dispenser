"""Experimental local integration for the Quin A1310 pill dispenser."""

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback

from .client import A1310Client
from .const import CONF_ADAPTER, DOMAIN
from .coordinator import PillCoordinator
from .transport import BlueZTransport

type PillConfigEntry = ConfigEntry[PillCoordinator]

PLATFORMS = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT, Platform.BUTTON]


@callback
def get_transport(hass: HomeAssistant) -> BlueZTransport:
    """Share one SPP registration lock, including config flows."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = BlueZTransport(asyncio.Lock())
    return hass.data[DOMAIN]


async def async_setup_entry(hass: HomeAssistant, entry: PillConfigEntry) -> bool:
    """Validate a device before exposing its entities."""
    client = A1310Client(
        get_transport(hass), entry.data[CONF_ADDRESS], entry.data[CONF_ADAPTER]
    )
    coordinator = PillCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PillConfigEntry) -> bool:
    """Unload entities; each transaction owns and closes its connection."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
