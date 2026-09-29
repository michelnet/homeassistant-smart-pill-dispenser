"""Poll coordination and explicit setting changes."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .ble import A1310BLEClient, BLEStatus
from .client import A1310Client
from .const import DOMAIN
from .protocol import ProtocolError, Status
from .schedule import validate_times
from .transport import TransportError

_LOGGER = logging.getLogger(__name__)
DEVICE_ERRORS = (TransportError, ProtocolError, TimeoutError, OSError)


class PillCoordinator(DataUpdateCoordinator[Status | BLEStatus]):
    """A successful poll represents a fresh snapshot, never assumed ingestion."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: A1310Client | A1310BLEClient,
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
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.local")
        self.local_state = {
            "schedule_status": "not_configured",
            "times": [],
            "schedule_sent_at": None,
            "schedule_timezone": None,
            "intake_status": "not_recorded",
            "last_intake_record": None,
        }

    async def async_load_local_state(self) -> None:
        """Restore local records; never resend a schedule during startup."""
        if saved := await self._store.async_load():
            self.local_state.update(saved)
        if self.local_state["schedule_status"] == "transferring":
            self.local_state["schedule_status"] = "transfer_interrupted"
            await self._store.async_save(self.local_state)

    async def _save_local_state(self) -> None:
        await self._store.async_save(dict(self.local_state))
        self.async_update_listeners()

    async def async_program_schedule(self, times: list[str]) -> None:
        """Explicitly replace the plan; persist uncertainty across restarts."""
        times = validate_times(times)
        if not isinstance(self.client, A1310BLEClient):
            raise HomeAssistantError("Schedule programming currently requires BLE")
        async with self._transaction_lock:
            self.local_state.update(
                schedule_status="transferring",
                times=times,
                schedule_sent_at=None,
                schedule_timezone=self.hass.config.time_zone,
            )
            # Persist before any write, including when HA exits during transfer.
            await self._save_local_state()
            try:
                await self.client.program_schedule(times)
            except asyncio.CancelledError:
                self.local_state["schedule_status"] = "transfer_interrupted"
                await self._save_local_state()
                raise
            except DEVICE_ERRORS as err:
                self.local_state["schedule_status"] = "transfer_failed"
                await self._save_local_state()
                raise HomeAssistantError(
                    "Schedule transfer failed. The device may contain a partial plan; "
                    "check it before explicitly sending the complete plan again."
                ) from err
            self.local_state.update(
                schedule_status="sent_unverified",
                schedule_sent_at=dt_util.utcnow().isoformat(),
            )
            await self._save_local_state()

    async def async_record_intake(self, status: str = "taken") -> None:
        """Record a person's input; never infer intake from an alarm or BLE."""
        if status not in ("taken", "skipped"):
            raise ValueError("Intake status must be taken or skipped")
        async with self._transaction_lock:
            self.local_state.update(
                intake_status=status,
                last_intake_record=dt_util.utcnow().isoformat(),
            )
            await self._save_local_state()
            self.hass.bus.async_fire(
                f"{DOMAIN}_intake_recorded",
                {
                    "entry_id": self.config_entry.entry_id,
                    "status": status,
                    "recorded_at": self.local_state["last_intake_record"],
                    "source": "manual",
                },
            )

    async def _async_update_data(self) -> Status | BLEStatus:
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
