"""Proxy routing with no local adapter, GATT metadata and cleanup."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.smart_pill_dispenser.ble import (
    BATTERY_LEVEL,
    BATTERY_SERVICE,
    DEVICE_INFORMATION,
    FIRMWARE_REVISION,
    A1310BLEClient,
    NoConnectableDevice,
)
from custom_components.smart_pill_dispenser.transport import TransportError


def characteristic(uuid, properties):
    return SimpleNamespace(uuid=uuid, properties=properties, descriptors=[])


def service(uuid, *chars):
    return SimpleNamespace(uuid=uuid, characteristics=list(chars))


@pytest.fixture
def proxy():
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", details={"source": "proxy"})
    client = SimpleNamespace(
        services=[
            service(BATTERY_SERVICE, characteristic(BATTERY_LEVEL, ["read"])),
            service(DEVICE_INFORMATION, characteristic(FIRMWARE_REVISION, ["read"])),
            service(
                "vendor-service", characteristic("vendor-char", ["write", "notify"])
            ),
        ],
        read_gatt_char=AsyncMock(side_effect=[b"\x4b", b"1.2.3"]),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )
    with (
        patch(
            "custom_components.smart_pill_dispenser.ble.bluetooth.async_ble_device_from_address",
            return_value=device,
        ) as lookup,
        patch(
            "custom_components.smart_pill_dispenser.ble.establish_connection",
            new_callable=AsyncMock,
            return_value=client,
        ) as connect,
    ):
        yield client, lookup, connect, device


async def test_proxy_without_local_adapter(hass, proxy):
    client, lookup, connect, device = proxy
    status = await A1310BLEClient(hass, device.address).read_status()
    lookup.assert_called_once_with(hass, device.address, connectable=True)
    assert connect.call_args.args[1] is device
    assert status.battery == 75
    assert status.firmware == "1.2.3"
    assert status.service_count == 3
    assert status.protocol_status == "awaiting_device_profile"
    assert client.read_gatt_char.await_count == 2
    client.write_gatt_char.assert_not_called()
    client.start_notify.assert_not_called()
    client.disconnect.assert_awaited_once()


async def test_unknown_profile_still_exports_metadata(hass, proxy):
    client, _, _, device = proxy
    client.services = client.services[2:]
    status = await A1310BLEClient(hass, device.address).read_status()
    assert status.battery is None and status.firmware is None
    assert status.services[0]["characteristics"][0]["uuid"] == "vendor-char"
    client.read_gatt_char.assert_not_called()
    client.write_gatt_char.assert_not_called()


async def test_passive_proxy_rejected(hass, proxy):
    _, lookup, connect, device = proxy
    lookup.return_value = None
    with pytest.raises(NoConnectableDevice):
        await A1310BLEClient(hass, device.address).read_status()
    connect.assert_not_called()


async def test_invalid_or_failed_standard_reads(hass, proxy):
    client, _, _, device = proxy
    client.read_gatt_char.side_effect = [b"\xff", BleakError("not permitted")]
    status = await A1310BLEClient(hass, device.address).read_status()
    assert status.battery is None and status.firmware is None
    assert len(status.read_errors) == 2
    client.disconnect.assert_awaited_once()


async def test_empty_services_fail_and_disconnect(hass, proxy):
    client, _, _, device = proxy
    client.services = []
    with pytest.raises(TransportError):
        await A1310BLEClient(hass, device.address).read_status()
    client.disconnect.assert_awaited_once()


async def test_cancellation_releases_proxy_slot(hass, proxy):
    client, _, _, device = proxy
    started = asyncio.Event()

    async def stall(*args):
        started.set()
        await asyncio.Event().wait()

    client.read_gatt_char.side_effect = stall
    task = asyncio.create_task(A1310BLEClient(hass, device.address).read_status())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.disconnect.assert_awaited_once()


async def test_settings_rejected_without_writing(hass, proxy):
    client, _, connect, device = proxy
    with pytest.raises(TransportError, match="not verified"):
        await A1310BLEClient(hass, device.address).read_status(volume=1)
    connect.assert_not_called()
    client.write_gatt_char.assert_not_called()
