"""Experimental local integration for the Quin A1310 pill dispenser."""

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback

from .ble import A1310BLEClient
from .client import A1310Client
from .const import CONF_ADAPTER, CONF_TRANSPORT, DOMAIN, TRANSPORT_BLE
from .coordinator import PillCoordinator
from .transport import BlueZTransport

type PillConfigEntry = ConfigEntry[PillCoordinator]

BLE_PLATFORMS = [Platform.SENSOR, Platform.BUTTON]
SPP_PLATFORMS = [*BLE_PLATFORMS, Platform.NUMBER, Platform.SELECT]


def platforms(entry: ConfigEntry) -> list[Platform]:
    """Do not expose unsupported controls on the BLE discovery path."""
    return (
        BLE_PLATFORMS
        if entry.data.get(CONF_TRANSPORT) == TRANSPORT_BLE
        else SPP_PLATFORMS
    )


@callback
def get_transport(hass: HomeAssistant) -> BlueZTransport:
    """Share one SPP registration lock, including config flows."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = BlueZTransport(asyncio.Lock())
    return hass.data[DOMAIN]


async def async_setup_entry(hass: HomeAssistant, entry: PillConfigEntry) -> bool:
    """Validate a device before exposing its entities."""
    if entry.data.get(CONF_TRANSPORT) == TRANSPORT_BLE:
        client = A1310BLEClient(hass, entry.data[CONF_ADDRESS])
    else:
        client = A1310Client(
            get_transport(hass), entry.data[CONF_ADDRESS], entry.data[CONF_ADAPTER]
        )
    coordinator = PillCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, platforms(entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PillConfigEntry) -> bool:
    """Unload entities; each transaction owns and closes its connection."""
    return await hass.config_entries.async_unload_platforms(entry, platforms(entry))
