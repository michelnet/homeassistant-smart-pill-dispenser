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
        "integration_version": "0.2.0",
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
                "protocol_source": (
                    "FF00/FF02/FF03 firmware/battery queries verified "
                    "on A1310 firmware 2.0.0 via local BLE and user-confirmed HA proxy"
                ),
                "protocol_status": status.protocol_status,
                "services": status.services,
                "read_errors": status.read_errors,
                "notification_count": status.notification_count,
                "notification_bytes": status.notification_bytes,
                "control_notifications": status.control_notifications,
                "queries_sent": status.queries_sent,
                "status": {"firmware": status.firmware, "battery": status.battery},
                "features": {
                    "daily_schedule": "app_derived_not_hardware_verified",
                    "schedule_readback": False,
                    "intake": "manual_record_only",
                    "immediate_dispensing": "no_known_command",
                },
                "schedule_transfer_status": coordinator.local_state["schedule_status"],
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
