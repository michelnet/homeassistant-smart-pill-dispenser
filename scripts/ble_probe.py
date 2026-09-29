"""Inspect a nearby A1310 directly from a Mac/Linux computer.

Uses bleak only, without starting Home Assistant. --query opts into the two
experimental status requests; default mode only enumerates services.
"""

import argparse
import asyncio
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError


def load_query():
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
    return importlib.import_module(f"{name}.ble_protocol").query_a1310


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
    async with asyncio.timeout(40):
        async with BleakClient(device, timeout=20) as client:
            report = {
                "tool_version": "0.1.1",
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
                    await load_query()(
                        client, on_notification=capture if args.capture else None
                    )
                )
                if args.capture:
                    report["notification_samples"] = samples
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
        "--capture",
        action="store_true",
        help="Include bounded raw replies in the local debug report",
    )
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout must be between 1 and 60 seconds")
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
