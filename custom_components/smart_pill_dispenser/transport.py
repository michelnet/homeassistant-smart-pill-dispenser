"""Short-lived BlueZ SPP client sessions using the system D-Bus.

BlueZ resolves the RFCOMM channel through SDP. No guessed channel, pairing PIN,
BLE characteristic or privileged shell command is used.
"""

import asyncio
import os
import re
import socket
from contextlib import asynccontextmanager, suppress

from dbus_fast import BusType, DBusError, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

from .const import SPP_UUID

PROFILE_PATH = "/org/homeassistant/smart_pill_dispenser/spp"
CONNECT_TIMEOUT = 20


class TransportError(Exception):
    """The local BlueZ SPP connection failed."""


def normalize_address(address: str) -> str:
    """Accept only full Bluetooth MAC addresses."""
    address = address.strip().upper()
    if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address):
        raise ValueError("Invalid Bluetooth address")
    return address


def device_path(address: str, adapter: str) -> str:
    """Build a validated BlueZ object path."""
    if not re.fullmatch(r"hci[0-9]+", adapter):
        raise ValueError("Invalid local adapter")
    return f"/org/bluez/{adapter}/dev_{normalize_address(address).replace(':', '_')}"


class SerialProfile(ServiceInterface):
    """Receive the connected RFCOMM file descriptor from BlueZ."""

    def __init__(self, expected_device: str) -> None:
        super().__init__("org.bluez.Profile1")
        self.expected_device = expected_device
        self.ready = asyncio.get_running_loop().create_future()
        self.connection: socket.socket | None = None

    @method()
    def NewConnection(self, device: "o", fd: "h", properties: "a{sv}"):
        """Take ownership only of the explicitly selected device's socket."""
        if device != self.expected_device or self.ready.done():
            os.close(fd)
            raise DBusError("org.bluez.Error.Rejected", "Unexpected connection")
        try:
            self.connection = socket.socket(fileno=fd)
            self.connection.setblocking(False)
        except OSError:
            os.close(fd)
            raise
        self.ready.set_result(self.connection)

    @method()
    def RequestDisconnection(self, device: "o"):
        """Release our descriptor when BlueZ disconnects."""
        if device == self.expected_device:
            self.close()

    @method()
    def Release(self):
        """Release resources when the profile is removed."""
        self.close()

    def close(self) -> None:
        """Close the descriptor on every exit path."""
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if not self.ready.done():
            self.ready.set_exception(TransportError("SPP profile disconnected"))
            # Mark observed even when ConnectProfile failed before awaiting ready.
            self.ready.exception()


async def call(
    bus: MessageBus,
    path: str,
    interface: str,
    member: str,
    signature: str = "",
    body: list | None = None,
) -> list:
    """Call BlueZ and turn D-Bus failures into transport errors."""
    response = await bus.call(
        Message(
            destination="org.bluez",
            path=path,
            interface=interface,
            member=member,
            signature=signature,
            body=body or [],
        )
    )
    if response is None or response.message_type == MessageType.ERROR:
        error = response.error_name if response else "no_reply"
        raise TransportError(f"BlueZ {member}: {error}")
    return response.body


class BlueZTransport:
    """Serialize SPP registrations across all entries and setup flows."""

    def __init__(self, lock: asyncio.Lock) -> None:
        self.lock = lock

    @asynccontextmanager
    async def session(self, address: str, adapter: str):
        """Connect briefly, then unregister even after failure/cancellation."""
        path = device_path(address, adapter)
        async with self.lock:
            bus = None
            profile = SerialProfile(path)
            registered = False
            try:
                async with asyncio.timeout(CONNECT_TIMEOUT):
                    bus = MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True)
                    await bus.connect()
                    bus.export(PROFILE_PATH, profile)
                    await call(
                        bus,
                        "/org/bluez",
                        "org.bluez.ProfileManager1",
                        "RegisterProfile",
                        "osa{sv}",
                        [
                            PROFILE_PATH,
                            SPP_UUID,
                            {
                                "Name": Variant("s", "Smart Pill Dispenser"),
                                "Role": Variant("s", "client"),
                                "RequireAuthentication": Variant("b", False),
                                "RequireAuthorization": Variant("b", False),
                                "AutoConnect": Variant("b", False),
                            },
                        ],
                    )
                    registered = True
                    await call(
                        bus,
                        path,
                        "org.bluez.Device1",
                        "ConnectProfile",
                        "s",
                        [SPP_UUID],
                    )
                    connection = await profile.ready
                yield connection
            except (OSError, DBusError, TimeoutError) as err:
                raise TransportError("Local Bluetooth SPP connection failed") from err
            finally:
                profile.close()
                if bus is not None:
                    if registered:
                        with suppress(TransportError, OSError, TimeoutError, DBusError):
                            async with asyncio.timeout(3):
                                await call(
                                    bus,
                                    "/org/bluez",
                                    "org.bluez.ProfileManager1",
                                    "UnregisterProfile",
                                    "o",
                                    [PROFILE_PATH],
                                )
                    bus.unexport(PROFILE_PATH)
                    bus.disconnect()
