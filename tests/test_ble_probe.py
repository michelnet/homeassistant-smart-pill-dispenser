"""Read-only event observation preserves unknown packets and bounds raw data."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError

from scripts.ble_probe import listen_notifications


@pytest.fixture
def observing_client():
    client = SimpleNamespace(
        services=[],
        is_connected=True,
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
    )
    protocol = SimpleNamespace(find_endpoints=lambda _: ("writer", "reader"))
    with patch("scripts.ble_probe.load_protocol", return_value=protocol):
        yield client


async def test_unknown_notifications_preserved_without_writes(observing_client):
    client = observing_client

    async def start(_char, callback):
        callback(None, b"\x01\x01")
        callback(None, b"unknown_event")

    client.start_notify.side_effect = start
    result = await listen_notifications(client, 0.01)
    assert result["notification_count"] == 2
    assert result["samples"][1]["hex"] == b"unknown_event".hex()
    assert result["samples"][1]["offset_ms"] >= 0
    assert not result["disconnected_early"]
    assert "intake" not in result
    client.write_gatt_char.assert_not_called()
    client.stop_notify.assert_awaited_once_with("reader")


async def test_capture_bounded_and_disconnect_reported(observing_client):
    client = observing_client

    async def start(_char, callback):
        for _ in range(300):
            callback(None, b"x" * 1000)
        client.is_connected = False

    client.start_notify.side_effect = start
    result = await listen_notifications(client, 1)
    assert result["disconnected_early"]
    assert result["notification_count"] == 300
    assert result["notification_bytes"] == 300000
    assert len(result["samples"]) == 256
    assert result["dropped_samples"] == 44
    assert len(result["samples"][0]["hex"]) == 128
    assert result["samples"][0]["truncated"]


async def test_cancelled_observation_stops_notify(observing_client):
    client = observing_client
    started = asyncio.Event()

    async def start(*args):
        started.set()

    client.start_notify.side_effect = start
    task = asyncio.create_task(listen_notifications(client, 60))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.stop_notify.assert_awaited_once_with("reader")
    client.write_gatt_char.assert_not_called()


async def test_unknown_profile_not_subscribed(observing_client):
    client = observing_client
    protocol = SimpleNamespace(find_endpoints=lambda _: None)
    with patch("scripts.ble_probe.load_protocol", return_value=protocol):
        with pytest.raises(RuntimeError, match="Notify-Profil"):
            await listen_notifications(client, 1)
    client.start_notify.assert_not_called()
    client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
async def test_readable_state_sampling_is_read_only(observing_client, fails):
    client = observing_client
    char = SimpleNamespace(
        uuid="0000ff01-0000-1000-8000-00805f9b34fb", properties=["read"]
    )
    client.services = [
        SimpleNamespace(
            uuid="0000ff00-0000-1000-8000-00805f9b34fb", characteristics=[char]
        )
    ]
    client.read_gatt_char = AsyncMock(
        return_value=b"opaque_state",
        side_effect=BleakError("read failed") if fails else None,
    )
    result = await listen_notifications(client, 0.01, read_state=True)
    client.read_gatt_char.assert_awaited_once_with(char)
    if fails:
        assert result["read_error"] == "ff01_read_failed"
    else:
        assert result["read_samples"][0]["hex"] == b"opaque_state".hex()
    client.stop_notify.assert_awaited_once()
    client.write_gatt_char.assert_not_called()


async def test_long_observation_reads_beyond_first_minute(observing_client):
    client = observing_client
    client.services = [
        SimpleNamespace(
            uuid="0000ff00-0000-1000-8000-00805f9b34fb",
            characteristics=[
                SimpleNamespace(
                    uuid="0000ff01-0000-1000-8000-00805f9b34fb", properties=["read"]
                )
            ],
        )
    ]
    disconnected = asyncio.Event()
    original_sleep = asyncio.sleep
    count = 0

    async def read(_char):
        nonlocal count
        count += 1
        if count == 65:
            client.is_connected = False
            disconnected.set()
        return b""

    async def advance(_delay):
        await original_sleep(0)

    client.read_gatt_char = AsyncMock(side_effect=read)
    async with asyncio.timeout(1):
        with patch("scripts.ble_probe.asyncio.sleep", side_effect=advance):
            result = await listen_notifications(
                client, 120, disconnected, read_state=True
            )
    assert len(result["read_samples"]) == 65
    assert result["disconnected_early"]
    client.stop_notify.assert_awaited_once()
    client.write_gatt_char.assert_not_called()
