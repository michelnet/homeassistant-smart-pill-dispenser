"""Inspect a nearby A1310 directly from a Mac/Linux computer.

Uses bleak only, without starting Home Assistant. --query opts into the two
status requests; default mode only enumerates services. --listen captures
uninterpreted notifications to investigate possible device events.
"""

import argparse
import asyncio
import importlib
import json
import sys
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from types import ModuleType

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

MAX_OBSERVATION_SECONDS = 300


def load_protocol():
    """Load the shared pure protocol modules without HA's package initializer."""
    name = "_a1310_probe"
    package = ModuleType(name)
    package.__path__ = [
        str(
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "smart_pill_dispenser"
        )
    ]
    sys.modules.setdefault(name, package)
    return importlib.import_module(f"{name}.ble_protocol")


async def listen_notifications(
    client,
    duration: float,
    disconnected: asyncio.Event | None = None,
    *,
    read_state: bool = False,
) -> dict:
    """Capture spontaneous FF03 packets without guessing event meanings."""
    endpoints = load_protocol().find_endpoints(client.services)
    if endpoints is None:
        raise RuntimeError("Kein eindeutiges A1310-Notify-Profil gefunden")
    loop = asyncio.get_running_loop()
    started = loop.time()
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "requested_duration_seconds": duration,
        "notification_count": 0,
        "notification_bytes": 0,
        "dropped_samples": 0,
        "samples": [],
    }
    active = True
    read_task = None

    async def sample_state():
        chars = [
            char
            for service in client.services
            if service.uuid == "0000ff00-0000-1000-8000-00805f9b34fb"
            for char in service.characteristics
            if char.uuid == "0000ff01-0000-1000-8000-00805f9b34fb"
            and "read" in char.properties
        ]
        report["read_samples"] = []
        if len(chars) != 1:
            report["read_error"] = "missing_or_ambiguous_ff01"
            return
        for _ in range(min(MAX_OBSERVATION_SECONDS, ceil(duration))):
            try:
                async with asyncio.timeout(3):
                    data = bytes(await client.read_gatt_char(chars[0]))
            except BleakError, OSError, TimeoutError:
                report["read_error"] = "ff01_read_failed"
                return
            report["read_samples"].append(
                {
                    "offset_ms": round((loop.time() - started) * 1000),
                    "hex": data[:64].hex(),
                    "length": len(data),
                    "truncated": len(data) > 64,
                }
            )
            await asyncio.sleep(1)

    def receive(_char, data):
        if not active:
            return
        report["notification_count"] += 1
        report["notification_bytes"] += len(data)
        if len(report["samples"]) >= 256:
            report["dropped_samples"] += 1
            return
        report["samples"].append(
            {
                "offset_ms": round((loop.time() - started) * 1000),
                "hex": bytes(data[:64]).hex(),
                "length": len(data),
                "truncated": len(data) > 64,
            }
        )

    subscribed = False
    try:
        async with asyncio.timeout(5):
            await client.start_notify(endpoints[1], receive)
        subscribed = True
        if read_state:
            read_task = asyncio.create_task(sample_state())
        print(
            f"Aufzeichnung läuft für {duration:g} Sekunden. "
            "Bluetooth-Nachrichten werden jetzt protokolliert.",
            file=sys.stderr,
            flush=True,
        )
        if client.is_connected:
            try:
                async with asyncio.timeout(duration):
                    await (disconnected or asyncio.Event()).wait()
            except TimeoutError:
                pass
        report["disconnected_early"] = not client.is_connected
        report["elapsed_seconds"] = round(loop.time() - started, 3)
    finally:
        active = False
        if read_task is not None:
            read_task.cancel()
            with suppress(asyncio.CancelledError):
                await read_task
        if subscribed:
            try:
                async with asyncio.timeout(3):
                    await client.stop_notify(endpoints[1])
            except BleakError, OSError, TimeoutError:
                report["cleanup_error"] = "stop_notify_failed"
    return report


async def probe(args) -> dict:
    """Scan for one chosen device; never connect to all nearby devices."""
    found = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
    devices = [
        device
        for device, adv in found.values()
        if (
            device.address.lower() == args.address.lower()
            if args.address
            else (adv.local_name or device.name or "").startswith("A1310")
        )
    ]
    if not devices:
        raise RuntimeError(
            "Kein A1310 gefunden. Spender aufwecken, in Reichweite stellen und "
            "PillCalendar schließen. Bei Bedarf HA-Integration kurz deaktivieren."
        )
    if len(devices) > 1:
        raise RuntimeError(
            "Mehrere A1310 gefunden. Mit --address auswählen: "
            + ", ".join(device.address for device in devices)
        )
    device = devices[0]
    disconnected = asyncio.Event()
    async with asyncio.timeout(40 + args.listen):
        async with BleakClient(
            device, timeout=20, disconnected_callback=lambda _: disconnected.set()
        ) as client:
            report = {
                "tool_version": "0.2.1",
                "transport": "local_ble",
                "services": [
                    {
                        "uuid": service.uuid,
                        "characteristics": [
                            {
                                "uuid": c.uuid,
                                "properties": sorted(c.properties),
                                "descriptors": [d.uuid for d in c.descriptors],
                            }
                            for c in service.characteristics
                        ],
                    }
                    for service in client.services
                ],
            }
            if args.query:
                samples = []

                def capture(data):
                    if len(samples) < 16:
                        samples.append(data[:64].hex())

                report["queries"] = asdict(
                    await load_protocol().query_a1310(
                        client, on_notification=capture if args.capture else None
                    )
                )
                if args.capture:
                    report["notification_samples"] = samples
            if args.listen:
                report["observation"] = await listen_notifications(
                    client, args.listen, disconnected, read_state=args.read_state
                )
            return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="MAC or macOS Bluetooth UUID, if needed")
    parser.add_argument(
        "--timeout", type=float, default=12, help="Scan duration (seconds)"
    )
    parser.add_argument(
        "--query", action="store_true", help="Query firmware and battery"
    )
    parser.add_argument("--output", type=Path, help="Save a shareable JSON report")
    parser.add_argument(
        "--listen",
        type=int,
        default=0,
        help="Capture spontaneous notifications for 1–300 seconds (raw debug data)",
    )
    parser.add_argument(
        "--read-state",
        action="store_true",
        help="During --listen also sample the readable FF01 value once per second",
    )
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Include bounded raw replies in the local debug report",
    )
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60 seconds")
    if args.listen and not 1 <= args.listen <= MAX_OBSERVATION_SECONDS:
        parser.error("--listen must be between 1 and 300 seconds")
    if args.read_state and not args.listen:
        parser.error("--read-state requires --listen")
    try:
        report = asyncio.run(probe(args))
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(text)
        print(text, end="")
    except (BleakError, OSError, RuntimeError, TimeoutError) as err:
        print(f"BLE-Diagnose fehlgeschlagen: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
