"""Observed GATT metadata, synthetic replies; not captured firmware responses."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.smart_pill_dispenser.ble_protocol import (
    A1310_NOTIFY,
    A1310_WRITE,
    find_endpoints,
    query_a1310,
)


@pytest.fixture
def vendor():
    metadata = json.loads(
        (Path(__file__).parent / "fixtures/a1310_gatt.json").read_text()
    )
    services = [
        SimpleNamespace(
            uuid=s["uuid"],
            characteristics=[SimpleNamespace(**c) for c in s["characteristics"]],
        )
        for s in metadata
    ]
    client = SimpleNamespace(
        services=services,
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
    )
    callback = None

    async def subscribe(char, cb):
        nonlocal callback
        assert char.uuid == A1310_NOTIFY
        callback = cb

    async def send(char, command, *, response):
        assert callback is not None  # Subscribe before either query.
        assert char.uuid == A1310_WRITE and response is True
        assert command in (b"#G\x06\x00", b"#G\x08\x00")
        payload = b"\x01\x02\x03" if command[2] == 6 else b"\x00\x00K"
        wire = b"@G\x03\x11&G" + command[2:3] + payload
        callback(char, bytearray(wire[:2]))
        callback(char, bytearray(wire[2:]))

    client.start_notify.side_effect = subscribe
    client.write_gatt_char.side_effect = send
    return client


async def test_observed_endpoints_and_fragmented_replies(vendor):
    result = await query_a1310(vendor)
    assert result.firmware == "1.2.3" and result.battery == 75
    assert result.state == "readings_received"
    assert result.queries_sent == ["23470600", "23470800"]
    assert result.notification_count == 4
    assert not result.errors
    vendor.stop_notify.assert_awaited_once()


async def test_other_service_not_probed(vendor):
    vendor.services[1].uuid = "unrelated"
    assert find_endpoints(vendor.services) is None
    result = await query_a1310(vendor)
    assert result.state == "awaiting_device_profile"
    vendor.start_notify.assert_not_called()
    vendor.write_gatt_char.assert_not_called()


async def test_ambiguous_characteristics_not_probed(vendor):
    vendor.services[1].characteristics.append(vendor.services[1].characteristics[1])
    assert find_endpoints(vendor.services) is None


async def test_no_notification_is_not_a_successful_read(vendor):
    vendor.write_gatt_char.side_effect = None
    with patch(
        "custom_components.smart_pill_dispenser.ble_protocol.QUERY_TIMEOUT", 0.01
    ):
        result = await query_a1310(vendor)
    assert result.state == "no_response"
    assert result.battery is None and result.firmware is None
    assert result.queries_sent == ["23470600"]
    vendor.stop_notify.assert_awaited_once()


@pytest.mark.parametrize("payload", [b"\x00\x01\x02", b"x" * 513])
async def test_invalid_notifications_retained_as_error_only(vendor, payload):
    async def send(*args, **kwargs):
        vendor.start_notify.call_args.args[1](None, payload)

    vendor.write_gatt_char.side_effect = send
    result = await query_a1310(vendor)
    assert result.state == "unexpected_response"
    assert result.battery is None
    assert result.notification_bytes == len(payload)
    assert result.errors == ["ff00_invalid_response"]
    vendor.stop_notify.assert_awaited_once()


async def test_battery_out_of_range(vendor):
    send = vendor.write_gatt_char.side_effect

    async def bad_battery(char, command, **kwargs):
        if command[2] == 8:
            vendor.start_notify.call_args.args[1](None, b"&G\x08\x00\x00\xff")
        else:
            await send(char, command, **kwargs)

    vendor.write_gatt_char.side_effect = bad_battery
    result = await query_a1310(vendor)
    assert result.firmware == "1.2.3" and result.battery is None
    assert result.state == "unexpected_response"


async def test_subscribe_failure_sends_nothing(vendor):
    vendor.start_notify.side_effect = BleakError("failed")
    result = await query_a1310(vendor)
    assert result.state == "communication_error"
    vendor.write_gatt_char.assert_not_called()


async def test_cancellation_stops_notifications(vendor):
    sent = asyncio.Event()

    async def send(*args, **kwargs):
        sent.set()

    vendor.write_gatt_char.side_effect = send
    task = asyncio.create_task(query_a1310(vendor))
    await sent.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    vendor.stop_notify.assert_awaited_once()


async def test_cleanup_failure_keeps_received_readings(vendor):
    vendor.stop_notify.side_effect = BleakError("disconnected")
    result = await query_a1310(vendor)
    assert result.battery == 75
    assert result.errors == ["ff00_stop_notify_failed"]


async def test_real_a1310_capture(vendor):
    capture = json.loads(
        (Path(__file__).parent / "fixtures/a1310_ble_capture.json").read_text()
    )
    notifications = [bytes.fromhex(value) for value in capture["notifications"]]

    async def subscribe(char, callback):
        for data in notifications[:2]:
            callback(char, data)

    async def send(char, command, **kwargs):
        callback = vendor.start_notify.call_args.args[1]
        index = 2 if command[2] == 6 else 4
        for data in notifications[index : index + 2]:
            callback(char, data)

    vendor.start_notify.side_effect = subscribe
    vendor.write_gatt_char.side_effect = send
    result = await query_a1310(vendor)
    assert result.state == "readings_received"
    assert result.firmware == capture["expected_firmware"] == "2.0.0"
    assert result.battery == capture["expected_battery"] == 95
    assert result.control_notifications == 4
    assert result.queries_sent == capture["queries"]


async def test_firmware_fragment_matching_credit_is_not_discarded(vendor):
    original = vendor.write_gatt_char.side_effect

    async def send(char, command, **kwargs):
        if command[2] != 6:
            await original(char, command, **kwargs)
            return
        callback = vendor.start_notify.call_args.args[1]
        for data in (b"&G\x06", b"\x01\x01", b"\x02"):
            callback(char, data)

    vendor.write_gatt_char.side_effect = send
    result = await query_a1310(vendor)
    assert result.firmware == "1.1.2"
    assert result.battery == 75
