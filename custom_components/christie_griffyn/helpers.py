"""Shared helpers for entities that send commands."""

from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError

from .client import ChristieError
from .const import DOMAIN


async def async_run_command(action: Awaitable[None]) -> None:
    """Await a command, turning projector errors into Home Assistant errors."""
    try:
        await action
    except ChristieError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        ) from err
