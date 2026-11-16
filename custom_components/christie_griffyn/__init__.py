"""Christie Griffyn (TruLife+) projector integration."""

from __future__ import annotations

try:
    import probatio as vol  # Home Assistant 2026.10+ validates with probatio
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .client import ChristieClient, ChristieError
from .const import (
    ATTR_COMMAND,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_TIMEOUT,
    DEFAULT_PORT,
    DOMAIN,
    LIST_TIMEOUT,
    SERVICE_SEND_COMMAND,
)
from .coordinator import ChristieConfigEntry, ChristieCoordinator, ChristieRuntimeData

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_COMMAND): vol.All(cv.string, vol.Length(min=3, max=512)),
        vol.Optional(ATTR_TIMEOUT, default=LIST_TIMEOUT): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=60)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the send_command service."""

    async def send_command(call: ServiceCall) -> ServiceResponse:
        entry = _entry_for_call(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        coordinator = entry.runtime_data.coordinator
        try:
            exchange = await coordinator.client.async_send_raw(
                call.data[ATTR_COMMAND], timeout=call.data[ATTR_TIMEOUT]
            )
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_command",
                translation_placeholders={"error": str(err)},
            ) from err
        except ChristieError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        coordinator.request_full_refresh()
        await coordinator.async_request_refresh()
        return {"command": exchange.command, "replies": list(exchange.messages)}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


def _entry_for_call(hass: HomeAssistant, entry_id: str | None) -> ChristieConfigEntry:
    entries: list[ChristieConfigEntry] = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if entry_id is not None:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_entry" if not entries else "choose_entry",
        )
    return entries[0]


async def async_setup_entry(hass: HomeAssistant, entry: ChristieConfigEntry) -> bool:
    """Set up a projector from a config entry."""
    client = ChristieClient(entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    coordinator = ChristieCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.async_close()
        raise

    entry.runtime_data = ChristieRuntimeData(client=client, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChristieConfigEntry) -> bool:
    """Unload a config entry and close the connection."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_close()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: ChristieConfigEntry) -> None:
    """Reload so a new scan interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)
