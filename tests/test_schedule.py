"""Alarm protocol boundaries, proxy writes, persistence and manual records."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_pill_dispenser import async_remove_entry, async_setup
from custom_components.smart_pill_dispenser.ble import A1310BLEClient, BLEStatus
from custom_components.smart_pill_dispenser.button import PillRecordIntake
from custom_components.smart_pill_dispenser.const import DOMAIN
from custom_components.smart_pill_dispenser.coordinator import PillCoordinator
from custom_components.smart_pill_dispenser.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.smart_pill_dispenser.schedule import (
    encode_schedule,
    validate_times,
)
from custom_components.smart_pill_dispenser.sensor import (
    LOCAL_DESCRIPTIONS,
    SCHEDULE_DESCRIPTION,
    PillLocalSensor,
)
from custom_components.smart_pill_dispenser.transport import TransportError

NOW = datetime(2026, 9, 29, 14, 32, 5, tzinfo=ZoneInfo("Europe/Zurich"))


def test_complete_plan_matches_app_format():
    commands = encode_schedule(["20:00", "08:15"], NOW)
    assert [c.hex() for c in commands[:4]] == [
        "23530200",
        "2353011a091d0e2005",
        "2353030101011a091d080f00",
        "2353030201011a091d140000",
    ]
    assert len(commands) == 8
    assert commands[4].hex() == "235303030001010101010100"
    assert commands[-1].hex() == "235303060001010101010100"
    assert all(command[4] == 0 for command in encode_schedule([], NOW)[2:])
    assert all(
        command[4] == 1
        for command in encode_schedule(
            ["00:00", "04:00", "08:00", "12:00", "16:00", "23:59"], NOW
        )[2:]
    )


@pytest.mark.parametrize(
    "times",
    [
        "08:00",
        None,
        [8],
        [True],
        ["8:00"],
        ["24:00"],
        ["08:60"],
        ["08:00:00"],
        ["08:00", "08:00"],
        ["00:00"] * 7,
        ["０８:００"],
    ],
)
def test_invalid_plan_rejected(times):
    with pytest.raises(ValueError):
        validate_times(times)


@pytest.fixture
def radio(hass):
    metadata = json.loads(
        (Path(__file__).parent / "fixtures/a1310_gatt.json").read_text()
    )
    client = SimpleNamespace(
        services=[
            SimpleNamespace(
                uuid=s["uuid"],
                characteristics=[SimpleNamespace(**c) for c in s["characteristics"]],
            )
            for s in metadata
        ],
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
    )

    async def send(char, command, **kwargs):
        if command[:2] == b"#G":
            payload = b"\x02\x00\x00" if command[2] == 6 else b"\x01\x9c\x5f"
            client.start_notify.call_args.args[1](char, b"&G" + command[2:3] + payload)

    client.write_gatt_char.side_effect = send
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", details={"source": "proxy"})
    with (
        patch(
            "custom_components.smart_pill_dispenser.ble.bluetooth.async_ble_device_from_address",
            return_value=device,
        ) as lookup,
        patch(
            "custom_components.smart_pill_dispenser.ble.establish_connection",
            new_callable=AsyncMock,
            return_value=client,
        ) as connect,
    ):
        yield client, lookup, connect, device


async def test_schedule_over_proxy_and_local_clock(hass, radio):
    client, lookup, connect, device = radio
    with patch(
        "custom_components.smart_pill_dispenser.ble.dt_util.now", return_value=NOW
    ):
        await A1310BLEClient(hass, device.address).program_schedule(["08:15"])
    lookup.assert_called_once_with(hass, device.address, connectable=True)
    assert connect.call_args.args[1] is device
    calls = client.write_gatt_char.call_args_list
    assert [call.args[1] for call in calls] == [
        b"#G\x06\x00",
        b"#G\x08\x00",
        *encode_schedule(["08:15"], NOW),
    ]
    assert all(call.kwargs["response"] for call in calls)
    client.disconnect.assert_awaited_once()


async def test_failed_write_not_retried(hass, radio):
    client, _, connect, device = radio
    original = client.write_gatt_char.side_effect

    async def fail(char, command, **kwargs):
        if command[:3] == b"#S\x03":
            raise BleakError("connection lost after write")
        await original(char, command, **kwargs)

    client.write_gatt_char.side_effect = fail
    with pytest.raises(TransportError, match="partial plan"):
        await A1310BLEClient(hass, device.address).program_schedule(["08:00"])
    assert client.write_gatt_char.await_count == 5
    connect.assert_awaited_once()
    client.disconnect.assert_awaited_once()


async def test_invalid_input_does_not_connect(hass, radio):
    client, _, connect, device = radio
    with pytest.raises(ValueError):
        await A1310BLEClient(hass, device.address).program_schedule(["24:00"])
    connect.assert_not_called()
    client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("unconfirmed_writer", [False, True])
async def test_unexpected_profile_receives_no_settings(hass, radio, unconfirmed_writer):
    client, _, _, device = radio
    if unconfirmed_writer:
        for service in client.services:
            for char in service.characteristics:
                if char.uuid.startswith("0000ff02"):
                    char.properties = ["write-without-response"]
    else:
        client.services = []
    with pytest.raises(TransportError, match="endpoint"):
        await A1310BLEClient(hass, device.address).program_schedule(["08:00"])
    client.write_gatt_char.assert_not_called()
    client.disconnect.assert_awaited_once()


async def test_nonresponding_device_receives_no_settings(hass, radio):
    client, _, _, device = radio
    client.write_gatt_char.side_effect = None
    with patch(
        "custom_components.smart_pill_dispenser.ble_protocol.QUERY_TIMEOUT", 0.01
    ):
        with pytest.raises(TransportError, match="status check"):
            await A1310BLEClient(hass, device.address).program_schedule(["08:00"])
    assert client.write_gatt_char.await_count == 1
    assert client.write_gatt_char.call_args.args[1] == b"#G\x06\x00"
    client.disconnect.assert_awaited_once()


async def test_cancelled_transfer_disconnects(hass, radio):
    client, _, _, device = radio
    original = client.write_gatt_char.side_effect
    started = asyncio.Event()

    async def stall(char, command, **kwargs):
        if command[:2] == b"#S":
            started.set()
            await asyncio.Event().wait()
        await original(char, command, **kwargs)

    client.write_gatt_char.side_effect = stall
    task = asyncio.create_task(
        A1310BLEClient(hass, device.address).program_schedule(["08:00"])
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.write_gatt_char.await_count == 3
    client.disconnect.assert_awaited_once()


@pytest.fixture
async def configured(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AA:BB:CC:DD:EE:FF",
        data={"address": "AA:BB:CC:DD:EE:FF", "transport": "ble"},
    )
    entry.add_to_hass(hass)
    client = A1310BLEClient(hass, entry.data["address"])
    coordinator = PillCoordinator(hass, entry, client)
    coordinator.async_set_updated_data(BLEStatus(95, "2.0.0", ()))
    entry.runtime_data = coordinator
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    await async_setup(hass, {})
    with patch.object(client, "program_schedule", new_callable=AsyncMock) as program:
        yield entry, coordinator, program


async def test_actions_persist_manual_records_and_unverified_plan(hass, configured):
    entry, coordinator, program = configured
    events = []
    remove = hass.bus.async_listen(f"{DOMAIN}_intake_recorded", events.append)
    await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {"entry_id": entry.entry_id, "times": ["08:00"]},
        blocking=True,
    )
    program.assert_awaited_once_with(["08:00"])
    sensor = PillLocalSensor(coordinator, SCHEDULE_DESCRIPTION)
    assert sensor.native_value == "sent_unverified"
    assert sensor.extra_state_attributes["device_confirmed"] is False
    await hass.services.async_call(
        DOMAIN,
        "record_intake",
        {"entry_id": entry.entry_id, "status": "skipped"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(events) == 1 and events[0].data["source"] == "manual"
    assert events[0].data["status"] == "skipped"
    restored = PillCoordinator(hass, entry, coordinator.client)
    await restored.async_load_local_state()
    assert restored.local_state == coordinator.local_state
    assert restored.local_state["intake_status"] == "skipped"
    assert restored.local_state["last_intake_record"]
    program.assert_awaited_once()  # Loading never resends the device plan.
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "08:00" not in str(diagnostics)
    assert "last_intake_record" not in str(diagnostics)
    remove()


async def test_manual_button_available_when_device_offline(hass, configured):
    _, coordinator, program = configured
    coordinator.last_update_success = False
    button = PillRecordIntake(coordinator, "record_intake")
    assert button.available
    await button.async_press()
    sensor = PillLocalSensor(coordinator, LOCAL_DESCRIPTIONS[0])
    assert sensor.available and sensor.native_value == "taken"
    assert sensor.extra_state_attributes["source"] == "manual"
    program.assert_not_awaited()


async def test_transfer_failure_is_persistent(hass, configured):
    entry, coordinator, program = configured
    program.side_effect = TransportError("lost")
    with pytest.raises(HomeAssistantError, match="partial plan"):
        await coordinator.async_program_schedule(["08:00"])
    restored = PillCoordinator(hass, entry, coordinator.client)
    await restored.async_load_local_state()
    assert restored.local_state["schedule_status"] == "transfer_failed"
    assert restored.local_state["schedule_sent_at"] is None
    program.assert_awaited_once()


async def test_cancelled_plan_keeps_uncertainty(hass, configured):
    entry, coordinator, program = configured
    program.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await coordinator.async_program_schedule(["08:00"])
    restored = PillCoordinator(hass, entry, coordinator.client)
    await restored.async_load_local_state()
    assert restored.local_state["schedule_status"] == "transfer_interrupted"
    program.assert_awaited_once()


async def test_restart_after_interrupted_transfer_and_entry_removal(hass, configured):
    entry, coordinator, program = configured
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.local")
    await store.async_save({"schedule_status": "transferring", "times": ["08:00"]})
    await coordinator.async_load_local_state()
    assert coordinator.local_state["schedule_status"] == "transfer_interrupted"
    program.assert_not_awaited()
    await async_remove_entry(hass, entry)
    assert await store.async_load() is None


async def test_services_reject_invalid_and_unloaded_entries(hass, configured):
    entry, _, program = configured
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_schedule",
            {"entry_id": entry.entry_id, "times": ["24:00"]},
            blocking=True,
        )
    entry._async_set_state(hass, ConfigEntryState.NOT_LOADED, None)
    with pytest.raises(ServiceValidationError, match="not loaded"):
        await hass.services.async_call(
            DOMAIN,
            "set_schedule",
            {"entry_id": entry.entry_id, "times": []},
            blocking=True,
        )
    program.assert_not_awaited()


async def test_real_ha_entities_actions_and_reload(hass, mock_ble):
    """Exercise platform registration rather than only entity constructors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AA:BB:CC:DD:EE:FF",
        data={"address": "AA:BB:CC:DD:EE:FF", "transport": "ble"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sensors = hass.states.async_all("sensor")
    schedule = next(s for s in sensors if "device_confirmed" in s.attributes)
    assert schedule.state == "not_configured"
    assert schedule.attributes["device_confirmed"] is False
    assert hass.services.has_service(DOMAIN, "set_schedule")
    await hass.services.async_call(
        DOMAIN,
        "record_intake",
        {"entry_id": entry.entry_id, "status": "taken"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert any(s.state == "taken" for s in hass.states.async_all("sensor"))
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert any(s.state == "taken" for s in hass.states.async_all("sensor"))
    assert await hass.config_entries.async_unload(entry.entry_id)
