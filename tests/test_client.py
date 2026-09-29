"""Exercise the actual async stream client through local socket pairs."""

import asyncio
import socket
from contextlib import asynccontextmanager

import pytest

from custom_components.smart_pill_dispenser.client import A1310Client
from custom_components.smart_pill_dispenser.protocol import ProtocolError
from custom_components.smart_pill_dispenser.transport import TransportError


class FakeTransport:
    """A socket pair replaces only the physical radio transport."""

    def __init__(self, *, confirm=True, disconnect=False, stall=False):
        self.commands = []
        self.confirm = confirm
        self.disconnect = disconnect
        self.stall = stall
        self.closed = False

    @asynccontextmanager
    async def session(self, address, adapter):
        client, server = socket.socketpair()
        client.setblocking(False)
        server.setblocking(False)
        task = asyncio.create_task(self.serve(server))
        try:
            yield client
        finally:
            client.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            server.close()
            self.closed = True

    async def serve(self, server):
        loop = asyncio.get_running_loop()
        volume = 2
        while True:
            command = b""
            while len(command) < 4:
                data = await loop.sock_recv(server, 4 - len(command))
                if not data:
                    return
                command += data
            self.commands.append(command)
            if self.disconnect:
                server.close()
                return
            if self.stall:
                await asyncio.Event().wait()
            if command[:2] == b"#S":
                if self.confirm:
                    volume = command[3]
                continue
            payload = {
                4: b"A1310TEST0000001",
                6: b"\x01\x02\x03",
                8: b"\x00\x00K",
                10: bytes([volume]),
                13: b"\x01",
            }
            response = b"@G\x03\x11&G" + command[2:3] + payload[command[2]]
            await loop.sock_sendall(server, response[:2])
            await asyncio.sleep(0)
            await loop.sock_sendall(server, response[2:])


async def test_poll_is_read_only_and_closes_socket():
    transport = FakeTransport()
    client = A1310Client(transport, "AA:BB:CC:DD:EE:FF", "hci0")
    assert (await client.read_status()).battery == 75
    assert all(command[:2] == b"#G" for command in transport.commands)
    assert transport.closed


async def test_setting_requires_readback():
    transport = FakeTransport()
    client = A1310Client(transport, "AA:BB:CC:DD:EE:FF", "hci0")
    assert (await client.read_status(volume=3)).volume == 3
    assert transport.commands.count(b"#S\x0d\x03") == 1
    transport = FakeTransport(confirm=False)
    client = A1310Client(transport, "AA:BB:CC:DD:EE:FF", "hci0")
    with pytest.raises(ProtocolError, match="confirm"):
        await client.read_status(volume=3)
    assert transport.commands.count(b"#S\x0d\x03") == 1
    assert transport.closed


async def test_disconnect_closes_session():
    transport = FakeTransport(disconnect=True)
    with pytest.raises(TransportError):
        await A1310Client(transport, "AA:BB:CC:DD:EE:FF", "hci0").read_status()
    assert transport.closed


async def test_cancellation_closes_session():
    transport = FakeTransport(stall=True)
    task = asyncio.create_task(
        A1310Client(transport, "AA:BB:CC:DD:EE:FF", "hci0").read_status()
    )
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.closed
