"""A1310 request/reply client; all writes are explicit and read back."""

import asyncio
import socket

from .protocol import (
    QUERY_BATTERY,
    QUERY_FIRMWARE,
    QUERY_RINGTONE,
    QUERY_SERIAL,
    QUERY_VOLUME,
    FrameDecoder,
    ProtocolError,
    Status,
    decode_status,
    set_ringtone,
    set_volume,
)
from .transport import BlueZTransport, TransportError

RESPONSE_TIMEOUT = 5


class A1310Client:
    """Poll a device without changing its medication schedule or clock."""

    def __init__(self, transport: BlueZTransport, address: str, adapter: str) -> None:
        self.transport = transport
        self.address = address
        self.adapter = adapter

    async def _query(
        self, connection: socket.socket, decoder: FrameDecoder, command: bytes
    ) -> bytes:
        """Wait for the matching response, ignoring known unsolicited frames."""
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(RESPONSE_TIMEOUT):
            # The Android implementation spaces outgoing commands by 50 ms.
            await asyncio.sleep(0.05)
            await loop.sock_sendall(connection, command)
            expected = b"&G" + command[2:3]
            while True:
                data = await loop.sock_recv(connection, 1024)
                if not data:
                    raise TransportError("Device closed the connection")
                for header, payload in decoder.feed(data):
                    if header == expected:
                        return payload

    async def read_status(
        self, *, volume: int | None = None, ringtone: int | None = None
    ) -> Status:
        """Read identity first, optionally apply one setting, then verify it.

        Do not retry writes automatically. A lost response means the result is
        unknown and must be refreshed before another deliberate user action.
        """
        if volume is not None and ringtone is not None:
            raise ValueError("Only one setting per transaction")
        command = (
            set_volume(volume)
            if volume is not None
            else set_ringtone(ringtone)
            if ringtone is not None
            else None
        )
        replies = {}
        async with self.transport.session(self.address, self.adapter) as connection:
            decoder = FrameDecoder()
            for query in (QUERY_SERIAL, QUERY_FIRMWARE):
                replies[query[2]] = await self._query(connection, decoder, query)
            if command is not None:
                await asyncio.sleep(0.05)
                async with asyncio.timeout(RESPONSE_TIMEOUT):
                    await asyncio.get_running_loop().sock_sendall(connection, command)
            for query in (QUERY_BATTERY, QUERY_VOLUME, QUERY_RINGTONE):
                replies[query[2]] = await self._query(connection, decoder, query)
        status = decode_status(replies)
        if volume is not None and status.volume != volume:
            raise ProtocolError("Device did not confirm the requested volume")
        if ringtone is not None and status.ringtone != ringtone:
            raise ProtocolError("Device did not confirm the requested ringtone")
        return status
