"""HA config flow, failure handling, entities and diagnostics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_pill_dispenser import async_setup_entry, async_unload_entry
from custom_components.smart_pill_dispenser.button import PillRefresh
from custom_components.smart_pill_dispenser.const import DOMAIN
from custom_components.smart_pill_dispenser.coordinator import PillCoordinator
from custom_components.smart_pill_dispenser.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.smart_pill_dispenser.number import PillVolume
from custom_components.smart_pill_dispenser.sensor import DESCRIPTIONS, PillSensor
from custom_components.smart_pill_dispenser.transport import TransportError


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AA:BB:CC:DD:EE:FF",
        data={"address": "AA:BB:CC:DD:EE:FF", "adapter": "hci0"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_and_unload(hass, entry, mock_client):
    with patch.object(
        hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock
    ) as forward:
        assert await async_setup_entry(hass, entry)
    forward.assert_awaited_once()
    assert entry.runtime_data.data.battery == 75
    assert PillSensor(entry.runtime_data, DESCRIPTIONS[0]).native_value == 75
    assert not PillVolume(entry.runtime_data, "volume").entity_registry_enabled_default
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "AA:BB" not in str(diagnostics)
    assert "A1310TEST" not in str(diagnostics)
    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=AsyncMock,
        return_value=True,
    ):
        assert await async_unload_entry(hass, entry)


async def test_failures_and_recovery(hass, entry, status):
    client = SimpleNamespace(
        address="AA:BB:CC:DD:EE:FF", read_status=AsyncMock(return_value=status)
    )
    coordinator = PillCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    client.read_status.side_effect = TransportError("asleep")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert PillRefresh(coordinator, "refresh").available
    with pytest.raises(HomeAssistantError):
        await coordinator.async_set(volume=3)
    assert coordinator.data.volume == 2
    client.read_status.side_effect = None
    await coordinator.async_refresh()
    assert coordinator.last_update_success


async def test_config_flow_invalid_then_success(hass, mock_client):
    with (
        patch(
            "custom_components.smart_pill_dispenser.config_flow.sys",
            SimpleNamespace(platform="linux"),
        ),
        patch(
            "custom_components.smart_pill_dispenser.async_setup_entry",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] == "form"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": "bad", "adapter": "hci0"}
        )
        assert result["errors"] == {"base": "invalid_address"}
        mock_client.assert_not_awaited()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": "aa:bb:cc:dd:ee:ff", "adapter": "hci0"}
        )
        assert result["type"] == "create_entry"
        assert result["data"]["address"] == "AA:BB:CC:DD:EE:FF"
        await hass.async_block_till_done()


async def test_config_flow_duplicate(hass, entry, mock_client):
    with patch(
        "custom_components.smart_pill_dispenser.config_flow.sys",
        SimpleNamespace(platform="linux"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}, data=entry.data
        )
    assert result["reason"] == "already_configured"
    mock_client.assert_not_awaited()


async def test_no_connection_creates_no_entry(hass, mock_client):
    mock_client.side_effect = TransportError("no local adapter")
    with patch(
        "custom_components.smart_pill_dispenser.config_flow.sys",
        SimpleNamespace(platform="linux"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={"address": "AA:BB:CC:DD:EE:FF", "adapter": "hci0"},
        )
    assert result["errors"] == {"base": "cannot_connect"}
    assert not hass.config_entries.async_entries(DOMAIN)
