"""Diagnostics download for the projector."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import ChristieConfigEntry

TO_REDACT = {CONF_HOST, "mac", "serial_number", "unique_id"}
_SERIAL_WORDS = ("S/N", "Serial")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChristieConfigEntry
) -> dict[str, Any]:
    """Return what the integration last read, with addresses and serials removed."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    status = {
        key: {
            "state": item.state,
            "value": "**REDACTED**"
            if any(word in item.description for word in _SERIAL_WORDS)
            else item.value,
            "description": item.description,
        }
        for key, item in sorted(data.status.items())
    }
    return {
        "entry": async_redact_data(
            {
                "data": dict(entry.data),
                "options": dict(entry.options),
                "unique_id": entry.unique_id,
            },
            TO_REDACT,
        ),
        "power": data.power_state_key,
        "firmware": data.firmware,
        "model": data.model,
        "values": {
            code: f"({reply.code}!{reply.raw})" for code, reply in sorted(data.values.items())
        },
        "status": status,
        "lists": {
            code: [asdict(option) for option in options] for code, options in data.lists.items()
        },
        "ranges": data.ranges,
        "events": [
            {"time": e.time.isoformat(), "kind": e.kind, "number": e.number, "text": e.text}
            for e in coordinator.events
        ],
    }
