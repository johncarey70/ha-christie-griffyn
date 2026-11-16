"""Config and options flow for the projector."""

from __future__ import annotations

import logging
from typing import Any

try:
    import probatio as vol  # Home Assistant 2026.10+ validates with probatio
except ImportError:  # pragma: no cover - older Home Assistant
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac

from .client import ChristieClient, ChristieConnectionError, ChristieError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import ChristieConfigEntry, async_read_identity

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


class ChristieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a projector by host and port, checked with read-only queries."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            client = ChristieClient(host, port)
            try:
                identity = await async_read_identity(client)
            except ChristieConnectionError:
                errors["base"] = "cannot_connect"
            except ChristieError:
                errors["base"] = "not_christie"
            except Exception:
                _LOGGER.exception("Unexpected error while checking %s:%s", host, port)
                errors["base"] = "unknown"
            else:
                unique_id = format_mac(identity.mac) if identity.mac else identity.serial_number
                if unique_id is None:
                    errors["base"] = "no_id"
                else:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                    return self.async_create_entry(
                        title=user_input[CONF_NAME].strip() or identity.model or DEFAULT_NAME,
                        data={CONF_HOST: host, CONF_PORT: port},
                    )
            finally:
                await client.async_close()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ChristieConfigEntry) -> OptionsFlow:
        return ChristieOptionsFlow()


class ChristieOptionsFlow(OptionsFlow):
    """Change how often the projector is polled."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
