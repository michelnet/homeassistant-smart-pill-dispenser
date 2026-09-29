"""Experimental FF00 query transport using GATT observed on the user's A1310.

The GATT endpoints are hardware-observed. The command framing comes from the
Android SPP client and still requires confirmation over BLE. Only firmware and
battery queries are sent, never settings, time, alarms or dispensing commands.
"""

import asyncio
from dataclasses import dataclass, field

from bleak.exc import BleakError

from .protocol import QUERY_BATTERY, QUERY_FIRMWARE, FrameDecoder, ProtocolError

A1310_SERVICE = "0000ff00-0000-1000-8000-00805f9b34fb"
A1310_WRITE = "0000ff02-0000-1000-8000-00805f9b34fb"
A1310_NOTIFY = "0000ff03-0000-1000-8000-00805f9b34fb"
QUERY_TIMEOUT = 5
PROTOCOL_STATES = [
    "awaiting_device_profile", "readings_received", "partial_readings",
    "no_response", "unexpected_response", "communication_error",
]


@dataclass
class QueryResult:
    """Keep useful failure evidence without recording notification payloads."""

    battery: int | None = None
    firmware: str | None = None
    state: str = "awaiting_device_profile"
    errors: list[str] = field(default_factory=list)
    notification_count: int = 0
    notification_bytes: int = 0
    queries_sent: list[str] = field(default_factory=list)


def find_endpoints(services):
    """Match an unambiguous pair in the observed service only."""
    candidates = []
    for service in services:
        if service.uuid != A1310_SERVICE:
            continue
        writers = [c for c in service.characteristics if c.uuid == A1310_WRITE
                   and ("write" in c.properties or "write-without-response" in c.properties)]
        readers = [c for c in service.characteristics if c.uuid == A1310_NOTIFY
                   and "notify" in c.properties]
        if len(writers) != 1 or len(readers) != 1:
            return None
        candidates.append((writers[0], readers[0]))
    return candidates[0] if len(candidates) == 1 else None


async def query_a1310(client) -> QueryResult:
    """Subscribe before querying; validate replies and always stop notifications."""
    result = QueryResult()
    endpoints = find_endpoints(client.services)
    if endpoints is None:
        return result
    writer, reader = endpoints
    queue = asyncio.Queue(maxsize=32)
    decoder = FrameDecoder()
    overflow = False
    subscribed = False
    active = True

    def receive(_characteristic, data):
        nonlocal overflow
        if not active:
            return
        result.notification_count += 1
        result.notification_bytes += len(data)
        if len(data) > 512 or queue.full():
            overflow = True
            # Wake a waiting query even if the oversized notification was first.
            if not queue.full():
                queue.put_nowait(b"")
            return
        queue.put_nowait(bytes(data))

    async def query(command):
        # Command spacing matches the app; the write response is not the
        # application reply. Only a matching FF03 notification satisfies a query.
        await asyncio.sleep(0.05)
        async with asyncio.timeout(QUERY_TIMEOUT):
            result.queries_sent.append(command.hex())
            await client.write_gatt_char(
                writer, command, response="write" in writer.properties
            )
            expected = b"&G" + command[2:3]
            while True:
                data = await queue.get()
                if overflow:
                    raise ProtocolError("Notification buffer overflow")
                frames = decoder.feed(data)
                for header, payload in frames:
                    if header == expected:
                        return payload

    try:
        async with asyncio.timeout(QUERY_TIMEOUT):
            await client.start_notify(reader, receive)
        subscribed = True
        firmware = await query(QUERY_FIRMWARE)
        result.firmware = ".".join(str(value) for value in firmware)
        battery = await query(QUERY_BATTERY)
        if battery[2] > 100:
            raise ProtocolError("Battery outside 0..100")
        result.battery = battery[2]
        result.state = "readings_received"
    except TimeoutError:
        result.state = "partial_readings" if result.firmware else "no_response"
        result.errors.append("ff00_response_timeout")
    except ProtocolError:
        result.state = "unexpected_response"
        result.errors.append("ff00_invalid_response")
    except BleakError, OSError:
        result.state = "communication_error"
        result.errors.append("ff00_communication_failed")
    finally:
        active = False
        if subscribed:
            try:
                async with asyncio.timeout(3):
                    await client.stop_notify(reader)
            except BleakError, OSError, TimeoutError:
                result.errors.append("ff00_stop_notify_failed")
    return result
