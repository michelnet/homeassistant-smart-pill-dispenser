"""Explicit schedule replacement and manual intake recording actions."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .schedule import validate_times


def _times(value):
    try:
        return validate_times(value)
    except ValueError as err:
        raise vol.Invalid(str(err)) from err


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register even when a device is offline or its entry is unloaded."""

    async def handle(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Select a Smart Pill Dispenser entry")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("The dispenser integration is not loaded")
        if call.service == "set_schedule":
            await entry.runtime_data.async_program_schedule(call.data["times"])
        else:
            await entry.runtime_data.async_record_intake(call.data["status"])

    hass.services.async_register(
        DOMAIN,
        "set_schedule",
        handle,
        schema=vol.Schema(
            {vol.Required("entry_id"): str, vol.Required("times"): _times}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "record_intake",
        handle,
        schema=vol.Schema(
            {
                vol.Required("entry_id"): str,
                vol.Required("status"): vol.In(("taken", "skipped")),
            }
        ),
    )
