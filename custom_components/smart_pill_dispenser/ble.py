"""Standard GATT and experimental A1310 status queries via ESPHome proxies."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .ble_protocol import query_a1310
from .transport import TransportError

BATTERY_SERVICE = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION = "0000180a-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION = "00002a26-0000-1000-8000-00805f9b34fb"


class NoConnectableDevice(TransportError):
    """No active proxy/local adapter can connect to the device."""


@dataclass(frozen=True)
class BLEStatus:
    """Standard GATT readings and metadata, not a medication status."""

    battery: int | None
    firmware: str | None
    services: tuple[dict, ...]
    read_errors: tuple[str, ...] = ()
    protocol_status: str = "awaiting_device_profile"
    notification_count: int = 0
    notification_bytes: int = 0
    queries_sent: tuple[str, ...] = ()
    control_notifications: int = 0

    @property
    def service_count(self) -> int:
        return len(self.services)


class A1310BLEClient:
    """Use HA BLEDevice objects so a proxy works without a local USB radio."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self._lock = asyncio.Lock()

    async def read_status(self, **settings) -> BLEStatus:
        """Enumerate GATT and read standards, then release the proxy slot."""
        if any(value is not None for value in settings.values()):
            raise TransportError("The proprietary A1310 BLE profile is not verified")
        async with self._lock:
            device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is None:
                raise NoConnectableDevice("No active proxy can reach the dispenser")
            client = None
            try:
                async with asyncio.timeout(45):
                    client = await establish_connection(
                        BleakClientWithServiceCache,
                        device,
                        "Smart Pill Dispenser A1310",
                        max_attempts=2,
                    )
                    services = tuple(
                        {
                            "uuid": service.uuid,
                            "characteristics": [
                                {
                                    "uuid": char.uuid,
                                    "properties": sorted(char.properties),
                                    "descriptors": [d.uuid for d in char.descriptors],
                                }
                                for char in service.characteristics
                            ],
                        }
                        for service in client.services
                    )
                    if not services:
                        raise TransportError("Device returned no GATT services")
                    errors = []
                    battery_raw = await self._read_standard(
                        client, BATTERY_SERVICE, BATTERY_LEVEL, errors
                    )
                    firmware_raw = await self._read_standard(
                        client, DEVICE_INFORMATION, FIRMWARE_REVISION, errors
                    )
                    battery = None
                    if battery_raw is not None:
                        if len(battery_raw) == 1 and battery_raw[0] <= 100:
                            battery = battery_raw[0]
                        else:
                            errors.append("invalid_standard_battery")
                    firmware = None
                    if firmware_raw is not None:
                        try:
                            value = firmware_raw.rstrip(b"\x00").decode("utf-8")
                            if value and value.isprintable() and len(value) <= 128:
                                firmware = value
                            else:
                                errors.append("invalid_standard_firmware")
                        except UnicodeDecodeError:
                            errors.append("invalid_standard_firmware")
                    vendor = await query_a1310(client)
                    errors.extend(vendor.errors)
                    return BLEStatus(
                        vendor.battery if vendor.battery is not None else battery,
                        vendor.firmware if vendor.firmware is not None else firmware,
                        services,
                        tuple(errors),
                        vendor.state,
                        vendor.notification_count,
                        vendor.notification_bytes,
                        tuple(vendor.queries_sent),
                        vendor.control_notifications,
                    )
            except (BleakError, OSError, TimeoutError) as err:
                raise TransportError("BLE connection or GATT discovery failed") from err
            finally:
                if client is not None:
                    with suppress(BleakError, OSError, TimeoutError):
                        async with asyncio.timeout(10):
                            await client.disconnect()

    async def _read_standard(self, client, service_uuid, char_uuid, errors):
        """Read a known characteristic only inside its expected SIG service."""
        for service in client.services:
            if service.uuid != service_uuid:
                continue
            for characteristic in service.characteristics:
                if (
                    characteristic.uuid == char_uuid
                    and "read" in characteristic.properties
                ):
                    try:
                        async with asyncio.timeout(5):
                            return bytes(await client.read_gatt_char(characteristic))
                    except BleakError, TimeoutError:
                        errors.append(f"read_failed:{char_uuid}")
                        return None
        return None
