"""Poll coordination and explicit setting changes."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import A1310Client
from .const import DOMAIN
from .protocol import ProtocolError, Status
from .transport import TransportError

_LOGGER = logging.getLogger(__name__)
DEVICE_ERRORS = (TransportError, ProtocolError, TimeoutError, OSError)


class PillCoordinator(DataUpdateCoordinator[Status]):
    """A successful poll represents a fresh snapshot, never assumed ingestion."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: A1310Client
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.client = client
        self.last_success = None
        self._transaction_lock = asyncio.Lock()

    async def _async_update_data(self) -> Status:
        async with self._transaction_lock:
            try:
                status = await self.client.read_status()
            except DEVICE_ERRORS as err:
                raise UpdateFailed(str(err)) from err
            self.last_success = dt_util.utcnow()
            return status

    async def async_set(
        self, *, volume: int | None = None, ringtone: int | None = None
    ) -> None:
        """Publish a setting only after the device reports the new value."""
        async with self._transaction_lock:
            try:
                status = await self.client.read_status(volume=volume, ringtone=ringtone)
            except DEVICE_ERRORS as err:
                self.async_set_update_error(UpdateFailed(str(err)))
                raise HomeAssistantError(
                    "The device did not confirm the change. Wake the dispenser, "
                    "close PillCalendar and refresh before trying again."
                ) from err
            self.last_success = dt_util.utcnow()
            self.async_set_updated_data(status)
