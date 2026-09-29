"""BLE proxy setup by default, with optional local Classic Bluetooth."""

import sys

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from . import get_transport
from .ble import A1310BLEClient, NoConnectableDevice
from .client import A1310Client
from .const import (
    CONF_ADAPTER,
    CONF_TRANSPORT,
    DEFAULT_ADAPTER,
    DOMAIN,
    TRANSPORT_BLE,
    TRANSPORT_SPP,
)
from .coordinator import DEVICE_ERRORS
from .transport import device_path, normalize_address


class PillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Validate the selected connection before creating an entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._address = ""

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        if not discovery_info.name.startswith("A1310"):
            return self.async_abort(reason="not_supported")
        self._address = normalize_address(discovery_info.address)
        await self.async_set_unique_id(self._address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": "A1310"}
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """BLE works via HA's connectable ESPHome proxies; no OS-specific socket."""
        errors = {}
        if user_input is not None:
            try:
                self._address = normalize_address(user_input[CONF_ADDRESS])
            except ValueError:
                errors["base"] = "invalid_address"
            else:
                await self.async_set_unique_id(self._address)
                self._abort_if_unique_id_configured()
                if user_input[CONF_TRANSPORT] == TRANSPORT_SPP:
                    return await self.async_step_classic()
                try:
                    await A1310BLEClient(self.hass, self._address).read_status()
                except NoConnectableDevice:
                    errors["base"] = "no_connectable_device"
                except DEVICE_ERRORS:
                    errors["base"] = "cannot_connect_ble"
                else:
                    return self.async_create_entry(
                        title="Smart Pill Dispenser A1310",
                        data={
                            CONF_ADDRESS: self._address,
                            CONF_TRANSPORT: TRANSPORT_BLE,
                        },
                    )
        if not self._address:
            for info in bluetooth.async_discovered_service_info(
                self.hass, connectable=False
            ):
                if info.name.startswith("A1310"):
                    self._address = info.address
                    break
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS, default=self._address): str,
                    vol.Required(CONF_TRANSPORT, default=TRANSPORT_BLE): vol.In(
                        {
                            TRANSPORT_BLE: "BLE / ESPHome proxy (discovery)",
                            TRANSPORT_SPP: "Local Classic / SPP (experimental)",
                        }
                    ),
                }
            ),
        )

    async def async_step_classic(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Optional Android-derived SPP implementation, separate from BLE."""
        if sys.platform != "linux":
            return self.async_abort(reason="linux_required")
        errors = {}
        if user_input is not None:
            adapter = user_input[CONF_ADAPTER].strip()
            try:
                device_path(self._address, adapter)
            except ValueError:
                errors["base"] = "invalid_address"
            else:
                try:
                    await A1310Client(
                        get_transport(self.hass), self._address, adapter
                    ).read_status()
                except DEVICE_ERRORS:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title="Smart Pill Dispenser A1310",
                        data={
                            CONF_ADDRESS: self._address,
                            CONF_ADAPTER: adapter,
                            CONF_TRANSPORT: TRANSPORT_SPP,
                        },
                    )
        return self.async_show_form(
            step_id="classic",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADAPTER, default=DEFAULT_ADAPTER): str,
                }
            ),
        )
