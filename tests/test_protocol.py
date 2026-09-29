"""App-derived vectors: these are synthetic, not hardware captures."""

import pytest

from custom_components.smart_pill_dispenser.protocol import (
    QUERY_BATTERY,
    QUERY_FIRMWARE,
    QUERY_SERIAL,
    FrameDecoder,
    ProtocolError,
    decode_status,
    set_ringtone,
    set_volume,
)


def test_app_query_vectors():
    assert QUERY_SERIAL.hex() == "23470400"
    assert QUERY_FIRMWARE.hex() == "23470600"
    assert QUERY_BATTERY.hex() == "23470800"
    assert set_volume(3).hex() == "23530d03"
    assert set_ringtone(2).hex() == "23530f02"


@pytest.mark.parametrize("value", [-1, 4, 256, 1.5, True, "2"])
def test_invalid_settings(value):
    with pytest.raises(ValueError):
        set_volume(value)
    with pytest.raises(ValueError):
        set_ringtone(value)


@pytest.mark.parametrize("split", range(14))
def test_fragmented_and_coalesced_frames(split):
    wire = bytes.fromhex("4047031126470800004b26470a02")
    decoder = FrameDecoder()
    frames = decoder.feed(wire[:split]) + decoder.feed(wire[split:])
    assert frames == [
        (b"@G\x03", b"\x11"),
        (b"&G\x08", b"\x00\x00K"),
        (b"&G\x0a", b"\x02"),
    ]


def test_unknown_frame_fails_closed():
    with pytest.raises(ProtocolError):
        FrameDecoder().feed(b"&G\xff\x00&G\x08\x00\x00K")


def test_status_validation():
    replies = {
        4: b"A1310TEST0000001",
        6: b"\x01\x02\x03",
        8: b"\xaa\xbbK",
        10: b"\x02",
        13: b"\x01",
    }
    status = decode_status(replies)
    assert status.battery == 75  # Third payload byte, not the first two.
    assert status.firmware == "1.2.3"
    for key, invalid in [
        (8, b"\x00\x00\xff"),
        (10, b"\x04"),
        (4, b"\xff" * 15),
        (6, b"\x01"),
    ]:
        with pytest.raises(ProtocolError):
            decode_status(replies | {key: invalid})
