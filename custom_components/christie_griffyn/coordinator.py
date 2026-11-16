"""Polling coordinator and data model for the projector."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import (
    ChristieClient,
    ChristieCommandError,
    ChristieConnectionError,
    ChristieError,
    ChristieTimeoutError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_MESSAGE,
    FAST_QUERIES,
    LIST_QUERIES,
    POWER_ON,
    POWER_STATE_KEYS,
    POWER_WARMING,
    RANGE_QUERIES,
    SIGNAL_GROUP,
    SLOW_EVERY,
    SLOW_QUERIES,
    STATIC_EVERY,
    STATIC_GROUPS,
    STATUS_GROUPS,
    scan_interval_from_seconds,
)
from .protocol import (
    ListOption,
    Reply,
    SignalInfo,
    StatusItem,
    StatusState,
    SystemMessage,
    list_option_from_reply,
    parse_signal,
    status_item_from_reply,
)

_LOGGER = logging.getLogger(__name__)

MAX_EVENTS = 20


@dataclass(frozen=True, slots=True)
class ProjectorEvent:
    """An asynchronous message from the projector."""

    time: datetime
    kind: str
    number: int
    text: str


@dataclass(slots=True)
class ProjectorData:
    """Everything read from the projector."""

    power: Reply
    values: dict[str, Reply] = field(default_factory=dict)
    """Latest single-value replies by code; a code is absent if not answered."""
    status: dict[str, StatusItem] = field(default_factory=dict)
    """Status items by key, e.g. ``TEMP_002``."""
    lists: dict[str, tuple[ListOption, ...]] = field(default_factory=dict)
    ranges: dict[str, tuple[int, int]] = field(default_factory=dict)
    mac: str | None = None
    firmware: str | None = None

    @property
    def power_state(self) -> int | None:
        """Raw power state number (0, 1, 10, 11)."""
        return self.power.number

    @property
    def power_state_key(self) -> str | None:
        """Power state as ``standby``, ``on``, ``cooling_down`` or ``warming_up``."""
        state = self.power.number
        if state is None:
            return None
        return POWER_STATE_KEYS.get(state)

    @property
    def is_on(self) -> bool:
        """True when on or warming up."""
        return self.power.number in (POWER_ON, POWER_WARMING)

    def value(self, code: str) -> Reply | None:
        """Reply for a code, if the projector answered it."""
        return self.values.get(code)

    def number(self, code: str) -> int | None:
        """First number of the reply for a code."""
        reply = self.values.get(code)
        return reply.number if reply else None

    def status_value(self, key: str) -> str | None:
        """Value text of a status item, e.g. ``status_value("LGHT_186")``."""
        item = self.status.get(key)
        return item.value if item else None

    def status_group(self, group: str) -> list[StatusItem]:
        """All items of one status group, in index order."""
        prefix = f"{group}_"
        return [item for key, item in sorted(self.status.items()) if key.startswith(prefix)]

    @property
    def model(self) -> str | None:
        """Projector model, e.g. ``Griffyn 4K35-RGB``."""
        return self.status_value("CONF_000")

    @property
    def serial_number(self) -> str | None:
        """Projector serial number."""
        return self.status_value("CONF_001")

    @property
    def problems(self) -> list[StatusItem]:
        """Status items currently in a warning or error state."""
        return [item for item in self.status.values() if item.state != StatusState.OK]

    @property
    def health(self) -> str:
        """``ok``, ``warning`` or ``error`` across all status items read."""
        states = {item.state for item in self.status.values()}
        if StatusState.ERROR in states:
            return "error"
        if StatusState.WARNING in states:
            return "warning"
        return "ok"

    @property
    def active_signal(self) -> SignalInfo | None:
        """The primary input signal, parsed from the signal status group."""
        candidates = [
            item
            for item in self.status_group(SIGNAL_GROUP)
            if item.index >= 5000 and "(Primary)" in item.value
        ]
        if not candidates:
            return None
        return parse_signal(candidates[0].value)


@dataclass(slots=True)
class ChristieRuntimeData:
    """Objects kept on the config entry while it is loaded."""

    client: ChristieClient
    coordinator: ChristieCoordinator


type ChristieConfigEntry = ConfigEntry[ChristieRuntimeData]


class ChristieCoordinator(DataUpdateCoordinator[ProjectorData]):
    """Reads the projector in tiers: every poll, every few polls, and rarely."""

    config_entry: ChristieConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ChristieConfigEntry,
        client: ChristieClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=scan_interval_from_seconds(
                entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.events: deque[ProjectorEvent] = deque(maxlen=MAX_EVENTS)
        self.last_profile: int | None = None
        self._poll_count = 0
        self._force_full = True
        self._force_static = False
        self._power_grace_until: float | None = None
        client.set_system_message_callback(self._handle_system_message)

    @callback
    def _handle_system_message(self, message: SystemMessage) -> None:
        event = ProjectorEvent(dt_util.utcnow(), message.kind, message.number, message.text)
        self.events.appendleft(event)
        self.hass.bus.async_fire(
            EVENT_MESSAGE,
            {
                "config_entry_id": self.config_entry.entry_id,
                "kind": message.kind,
                "number": message.number,
                "text": message.text,
            },
        )
        # A status change usually means something worth re-reading.
        self._force_full = True

    def request_full_refresh(self, *, static: bool = False) -> None:
        """Read all settings and status (and lists, if ``static``) on the next poll."""
        self._force_full = True
        self._force_static = self._force_static or static

    def begin_power_grace(self, seconds: float) -> None:
        """Keep last data during the post-power wait so entities stay available."""
        self._power_grace_until = time.monotonic() + seconds

    def end_power_grace(self) -> None:
        """Resume normal polling after the post-power wait."""
        self._power_grace_until = None

    def in_power_grace(self) -> bool:
        """True while a post-power wait is still running."""
        return self._power_grace_until is not None and time.monotonic() < self._power_grace_until

    async def _async_update_data(self) -> ProjectorData:
        if self.in_power_grace() and self.data is not None:
            return self.data
        try:
            return await self._async_read()
        except ChristieError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_read(self) -> ProjectorData:
        previous = self.data
        power = await self.client.async_query("PWR")
        power_changed = previous is None or previous.power.number != power.number

        data = (
            ProjectorData(power=power)
            if previous is None
            else replace(
                previous,
                power=power,
                values=dict(previous.values),
                status=dict(previous.status),
                lists=dict(previous.lists),
                ranges=dict(previous.ranges),
            )
        )
        data.values["PWR"] = power

        full = self._force_full or power_changed or self._poll_count % SLOW_EVERY == 0
        static = (
            self._force_static
            or previous is None
            or power_changed
            or self._poll_count % STATIC_EVERY == 0
        )
        self._poll_count += 1
        self._force_full = False
        self._force_static = False

        reader = _TierReader(self.client, data)
        await reader.values(FAST_QUERIES)
        await reader.group(SIGNAL_GROUP)
        if full:
            await reader.values(SLOW_QUERIES)
            for group in STATUS_GROUPS:
                await reader.group(group)
        if static:
            await reader.static()
        if reader.timed_out:
            # The projector is busy (e.g. warming up); finish next time.
            self._force_full = True
            self._force_static = self._force_static or static
        return data

    async def async_set(self, code: str, *values: int | str, wait_for_ack: bool = True) -> None:
        """Send a set command, then read the value back."""
        await self.client.async_set(code, *values, wait_for_ack=wait_for_ack)
        await self.async_read_back(code)

    async def async_read_back(self, code: str) -> None:
        """Re-read one value after a command and publish it."""
        if self.data is None:
            return
        try:
            reply = await self.client.async_query(code)
        except ChristieError as err:
            _LOGGER.debug("Read-back of %s failed: %s", code, err)
            await self.async_request_refresh()
            return
        data = replace(self.data, values={**self.data.values, code: reply})
        if code == "PWR":
            data = replace(data, power=reply)
        self.async_set_updated_data(data)


class _TierReader:
    """Reads groups of queries into ``data``, tolerating per-query errors.

    A rejected query (e.g. a control disabled in standby) removes the stale
    value. A timeout stops the rest of the poll, keeping earlier values, so a
    busy projector is not flooded. A connection error aborts the poll.
    """

    def __init__(self, client: ChristieClient, data: ProjectorData) -> None:
        self._client = client
        self._data = data
        self.timed_out = False

    async def values(self, codes: tuple[str, ...]) -> None:
        for code in codes:
            if self.timed_out:
                return
            try:
                self._data.values[code] = await self._client.async_query(code)
            except ChristieCommandError:
                self._data.values.pop(code, None)
            except ChristieTimeoutError:
                self.timed_out = True

    async def group(self, group: str) -> None:
        if self.timed_out:
            return
        try:
            replies = await self._client.async_query_group(f"SST+{group}")
        except ChristieCommandError:
            return
        except ChristieTimeoutError:
            self.timed_out = True
            return
        prefix = f"{group}_"
        for key in [key for key in self._data.status if key.startswith(prefix)]:
            del self._data.status[key]
        for reply in replies:
            if item := status_item_from_reply(reply):
                self._data.status[item.key] = item

    async def static(self) -> None:
        for group in STATIC_GROUPS:
            await self.group(group)
        for code in LIST_QUERIES:
            if self.timed_out:
                return
            try:
                replies = await self._client.async_query_list(code)
            except ChristieCommandError:
                continue
            except ChristieTimeoutError:
                self.timed_out = True
                return
            options = tuple(
                option for reply in replies if (option := list_option_from_reply(reply))
            )
            if options:
                self._data.lists[code] = options
        for code in RANGE_QUERIES:
            if self.timed_out:
                return
            try:
                reply = await self._client.async_query_range(code)
            except ChristieCommandError:
                continue
            except ChristieTimeoutError:
                self.timed_out = True
                return
            if len(reply.numbers) >= 2:
                self._data.ranges[code] = (reply.numbers[0], reply.numbers[1])
        await self._identity()

    async def _identity(self) -> None:
        if self.timed_out:
            return
        try:
            mac = await self._client.async_query("NET+MAC0")
            if mac.text:
                self._data.mac = mac.text.lower()
        except ChristieCommandError:
            pass
        except ChristieTimeoutError:
            self.timed_out = True
            return
        try:
            ping = await self._client.async_query("PNG")
            if len(ping.numbers) >= 4:
                self._data.firmware = ".".join(str(n) for n in ping.numbers[1:4])
        except ChristieCommandError:
            pass
        except ChristieTimeoutError:
            self.timed_out = True


@dataclass(frozen=True, slots=True)
class ProjectorIdentity:
    """What the config flow learns about a projector."""

    power: Reply
    mac: str | None
    model: str | None
    serial_number: str | None


async def async_read_identity(client: ChristieClient) -> ProjectorIdentity:
    """Read power state, MAC, model and serial number (queries only)."""
    power = await client.async_query("PWR")
    mac: str | None = None
    model: str | None = None
    serial: str | None = None
    try:
        mac_reply = await client.async_query("NET+MAC0")
        mac = mac_reply.text.lower() if mac_reply.text else None
    except ChristieCommandError:
        pass
    try:
        for reply in await client.async_query_group("SST+CONF"):
            item = status_item_from_reply(reply)
            if item is None:
                continue
            if item.index == 0:
                model = item.value
            elif item.index == 1:
                serial = item.value
    except ChristieCommandError:
        pass
    return ProjectorIdentity(power, mac, model, serial)


__all__ = [
    "ChristieConfigEntry",
    "ChristieConnectionError",
    "ChristieCoordinator",
    "ChristieRuntimeData",
    "ProjectorData",
    "ProjectorEvent",
    "ProjectorIdentity",
]
