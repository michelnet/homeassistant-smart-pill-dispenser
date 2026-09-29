"""Use real Home Assistant classes with simulated device responses."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.smart_pill_dispenser.protocol import Status


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def status():
    return Status("A1310TEST0000001", "1.2.3", 75, 2, 1)


@pytest.fixture
def mock_client(status):
    with patch(
        "custom_components.smart_pill_dispenser.client.A1310Client.read_status",
        new_callable=AsyncMock,
        return_value=status,
    ) as mock:
        yield mock
