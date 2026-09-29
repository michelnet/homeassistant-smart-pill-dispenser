"""A1310 wire format derived from PillCalendar 3.10.0 (not hardware verified).

The app writes these bytes directly to an RFCOMM stream. There is no additional
checksum or delimiter for these fixed-size commands. See docs/PROTOCOL.md.
"""

from dataclasses import dataclass


class ProtocolError(ValueError):
    """A reply could not be interpreted safely."""


@dataclass(frozen=True)
class Status:
    """A complete successful device poll."""

    serial: str
    firmware: str
    battery: int
    volume: int
    ringtone: int


QUERY_SERIAL = b"#G\x04\x00"
QUERY_FIRMWARE = b"#G\x06\x00"
QUERY_BATTERY = b"#G\x08\x00"
QUERY_VOLUME = b"#G\x0a\x00"
QUERY_RINGTONE = b"#G\x0d\x00"

# Response payload lengths from the app's parser (e8.f.c). Unsolicited
# low-battery/charging messages must be consumed even while awaiting a query.
REPLY_LENGTHS = {
    (0x26, 0x47, 0x02): 1,
    (0x26, 0x47, 0x03): 1,
    (0x26, 0x47, 0x04): 15,
    (0x26, 0x47, 0x05): 2,
    (0x26, 0x47, 0x06): 3,
    (0x26, 0x47, 0x08): 3,
    (0x26, 0x47, 0x0A): 1,
    (0x26, 0x47, 0x0C): 1,
    (0x26, 0x47, 0x0D): 1,
    (0x26, 0x47, 0x0E): 1,
    (0x26, 0x53, 0x08): 3,
    (0x26, 0x53, 0x09): 1,
    (0x26, 0x53, 0x0A): 1,
    (0x26, 0x53, 0x0B): 1,
    (0x26, 0x53, 0x0C): 1,
    (0x26, 0x53, 0x0F): 1,
    (0x40, 0x47, 0x02): 1,
    (0x40, 0x47, 0x03): 1,
}


class FrameDecoder:
    """Handle fragmented/coalesced stream frames without guessing boundaries."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def has_pending_data(self) -> bool:
        """Whether a notification continues an incomplete application frame."""
        return bool(self._buffer)

    def feed(self, data: bytes) -> list[tuple[bytes, bytes]]:
        """Return complete frames, retaining incomplete data.

        Unknown headers abort the session: scanning arbitrary payload bytes for
        a new header could silently manufacture an incorrect battery reading.
        """
        self._buffer.extend(data)
        frames = []
        while len(self._buffer) >= 3:
            header = bytes(self._buffer[:3])
            length = REPLY_LENGTHS.get(tuple(header))
            if length is None:
                self._buffer.clear()
                raise ProtocolError(f"Unsupported response header: {header.hex()}")
            if len(self._buffer) < length + 3:
                break
            frames.append((header, bytes(self._buffer[3 : length + 3])))
            del self._buffer[: length + 3]
        return frames


def set_volume(level: int) -> bytes:
    """Encode a raw device volume level, 0..3 (not a percentage)."""
    if type(level) is not int or not 0 <= level <= 3:
        raise ValueError("Volume must be an integer between 0 and 3")
    return bytes((0x23, 0x53, 0x0D, level))


def set_ringtone(tone: int) -> bytes:
    """Encode tone A, B, C or the existing custom tone."""
    if type(tone) is not int or not 0 <= tone <= 3:
        raise ValueError("Ringtone must be an integer between 0 and 3")
    return bytes((0x23, 0x53, 0x0F, tone))


def decode_status(replies: dict[int, bytes]) -> Status:
    """Validate all values before exposing them to Home Assistant."""
    for command in (4, 6, 8, 10, 13):
        if len(replies.get(command, b"")) != REPLY_LENGTHS[(0x26, 0x47, command)]:
            raise ProtocolError("Missing or truncated status response")
    try:
        serial = replies[4].rstrip(b"\x00 ").decode("ascii")
    except UnicodeDecodeError as err:
        raise ProtocolError("Invalid serial number encoding") from err
    if not serial or not serial.isprintable():
        raise ProtocolError("Invalid serial number")
    battery, volume, ringtone = replies[8][2], replies[10][0], replies[13][0]
    if battery > 100 or volume > 3 or ringtone > 3:
        raise ProtocolError("Status value outside the documented app range")
    return Status(
        serial=serial,
        firmware=".".join(str(value) for value in replies[6]),
        battery=battery,
        volume=volume,
        ringtone=ringtone,
    )
