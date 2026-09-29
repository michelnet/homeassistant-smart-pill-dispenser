"""SPP descriptor ownership and registration cleanup (BlueZ simulated)."""

import asyncio
import os
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dbus_fast import DBusError, MessageType

from custom_components.smart_pill_dispenser.transport import (
    BlueZTransport,
    SerialProfile,
    TransportError,
    device_path,
)


async def test_unexpected_device_rejected_and_fd_closed():
    left, right = socket.socketpair()
    fd = left.detach()
    profile = SerialProfile("/expected")
    try:
        with pytest.raises(DBusError):
            profile.NewConnection("/other", fd, {})
        with pytest.raises(OSError):
            os.fstat(fd)
    finally:
        profile.close()
        right.close()


@pytest.mark.parametrize("fail", [False, True])
async def test_session_cleanup(fail, socket_enabled):
    path = device_path("AA:BB:CC:DD:EE:FF", "hci0")
    left, right = socket.socketpair()
    profile = None
    members = []
    bus = MagicMock()
    bus.connect = AsyncMock()

    def export(path, interface):
        nonlocal profile
        profile = interface

    async def call(message):
        members.append(message.member)
        if message.member == "ConnectProfile":
            if fail:
                raise TransportError("unreachable")
            profile.NewConnection(path, left.detach(), {})
        return MagicMock(message_type=MessageType.METHOD_RETURN, body=[])

    bus.export.side_effect = export
    bus.call = AsyncMock(side_effect=call)
    with patch(
        "custom_components.smart_pill_dispenser.transport.MessageBus", return_value=bus
    ):
        try:
            if fail:
                with pytest.raises(TransportError):
                    async with BlueZTransport(asyncio.Lock()).session(
                        "AA:BB:CC:DD:EE:FF", "hci0"
                    ):
                        pytest.fail("Connection should not succeed")
            else:
                async with BlueZTransport(asyncio.Lock()).session(
                    "AA:BB:CC:DD:EE:FF", "hci0"
                ) as connection:
                    assert connection.fileno() >= 0
                assert connection.fileno() == -1
            assert members == ["RegisterProfile", "ConnectProfile", "UnregisterProfile"]
            bus.disconnect.assert_called_once()
            bus.unexport.assert_called_once()
        finally:
            left.close()
            right.close()
