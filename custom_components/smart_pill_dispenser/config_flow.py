"""UI setup and BLE advertisement discovery for a Classic Bluetooth device."""

import sys

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from . import get_transport
from .client import A1310Client
from .const import CONF_ADAPTER, DEFAULT_ADAPTER, DOMAIN
from .coordinator import DEVICE_ERRORS
from .transport import device_path, normalize_address


class PillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Require a successful SPP exchange before creating an entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._address = ""

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """BLE discovery identifies the device; data uses local SPP."""
        if not discovery_info.name.startswith("A1310"):
            return self.async_abort(reason="not_supported")
        self._address = normalize_address(discovery_info.address)
        await self.async_set_unique_id(self._address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": "A1310"}
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Accept the physical Bluetooth address and local Linux adapter."""
        if sys.platform != "linux":
            return self.async_abort(reason="linux_required")
        errors = {}
        if user_input is not None:
            try:
                address = normalize_address(user_input[CONF_ADDRESS])
                adapter = user_input[CONF_ADAPTER].strip()
                device_path(address, adapter)
            except ValueError:
                errors["base"] = "invalid_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                client = A1310Client(get_transport(self.hass), address, adapter)
                try:
                    await client.read_status()
                except DEVICE_ERRORS:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title="Smart Pill Dispenser A1310",
                        data={CONF_ADDRESS: address, CONF_ADAPTER: adapter},
                    )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS, default=self._address): str,
                    vol.Required(CONF_ADAPTER, default=DEFAULT_ADAPTER): str,
                }
            ),
        )
