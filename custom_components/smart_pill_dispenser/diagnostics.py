"""Useful protocol diagnostics without hardware identifiers or raw payloads."""

from homeassistant.core import HomeAssistant

from . import PillConfigEntry
from .ble import BLEStatus


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PillConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    status = coordinator.data
    result = {
        "integration_version": "0.1.0",
        "protocol_source": "PillCalendar Android 3.10.0; hardware unverified",
        "transport": "local_bluez_spp",
        "last_update_success": coordinator.last_update_success,
        "last_success": (
            coordinator.last_success.isoformat() if coordinator.last_success else None
        ),
    }
    if isinstance(status, BLEStatus):
        result.update(
            {
                "transport": "home_assistant_ble_local_or_proxy",
                "protocol_source": "Standard GATT; A1310 BLE profile unknown",
                "protocol_status": status.protocol_status,
                "services": status.services,
                "read_errors": status.read_errors,
                "status": {"firmware": status.firmware, "battery": status.battery},
            }
        )
    else:
        result["status"] = (
            {
                "firmware": status.firmware,
                "battery": status.battery,
                "volume": status.volume,
                "ringtone": status.ringtone,
            }
            if status
            else None
        )
    return result
