"""Daily A1310 alarm encoding, derived from PillCalendar 3.10.0.

The device has no known alarm readback/acknowledgement. These commands are
not hardware verified. See docs/PROTOCOL.md before extending this format.
"""

import re
from datetime import datetime

MAX_ALARMS = 6


def validate_times(value: list[str]) -> list[str]:
    """Validate an entire replacement schedule before touching the device."""
    if not isinstance(value, list) or len(value) > MAX_ALARMS:
        raise ValueError("Expected a list of zero to six daily times")
    if any(
        not isinstance(item, str)
        or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", item) is None
        for item in value
    ):
        raise ValueError("Each daily time must use HH:MM (24-hour format)")
    if len(set(value)) != len(value):
        raise ValueError("Duplicate alarm times are not allowed")
    return sorted(value)


def encode_schedule(times: list[str], now: datetime) -> list[bytes]:
    """Sync local wall clock and replace all six slots, disabling unused slots.

    A1310Box.setBoxAlarmClock uses e8.f.d(slot, false, model), which always
    encodes daily repeat=1. g9.c.c pads A1310 schedules to six disabled slots.
    """
    times = validate_times(times)
    if not 2000 <= now.year <= 2099:
        raise ValueError("Device clock year must be between 2000 and 2099")
    commands = [
        b"#S\x02\x00",  # Clock format, matching syncBoxTime(true, true).
        b"#S\x01"
        + bytes(
            (now.year - 2000, now.month, now.day, now.hour, now.minute, now.second)
        ),
    ]
    for slot in range(1, MAX_ALARMS + 1):
        if slot <= len(times):
            hour, minute = map(int, times[slot - 1].split(":"))
            payload = (slot, 1, 1, now.year - 2000, now.month, now.day, hour, minute, 0)
        else:
            payload = (slot, 0, 1, 1, 1, 1, 1, 1, 0)
        commands.append(b"#S\x03" + bytes(payload))
    return commands
