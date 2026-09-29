"""Useful protocol diagnostics without hardware identifiers or raw payloads."""

from homeassistant.core import HomeAssistant

from . import PillConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PillConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    status = coordinator.data
    return {
        "integration_version": "0.1.0",
        "protocol_source": "PillCalendar Android 3.10.0; hardware unverified",
        "transport": "local_bluez_spp",
        "last_update_success": coordinator.last_update_success,
        "last_success": (
            coordinator.last_success.isoformat() if coordinator.last_success else None
        ),
        "status": {
            "firmware": status.firmware,
            "battery": status.battery,
            "volume": status.volume,
            "ringtone": status.ringtone,
        }
        if status
        else None,
    }
