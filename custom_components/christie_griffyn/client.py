"""Async TCP client for the Christie TruLife+ serial protocol (port 3002)."""

from __future__ import annotations

import asyncio
import codecs
from collections.abc import Callable
import contextlib
from dataclasses import dataclass
import logging
from typing import Final

from .const import (
    ACK_TIMEOUT,
    CONNECT_TIMEOUT,
    DEFAULT_PORT,
    LIST_TIMEOUT,
    NO_ACK_SETTLE,
    QUERY_TIMEOUT,
)
from .protocol import (
    ERROR_TEXT,
    Ack,
    Message,
    Reply,
    StreamParser,
    SystemMessage,
    Unknown,
    command_code,
    is_list_end,
    is_query,
    normalize_command,
)

_LOGGER = logging.getLogger(__name__)

# Sent after a status group query: its reply marks the end of the group,
# because group replies have no end marker of their own.
_SENTINEL: Final = "PNG"
_READ_SIZE: Final = 4096


class ChristieError(Exception):
    """Base error for the projector client."""


class ChristieConnectionError(ChristieError):
    """The projector could not be reached or closed the connection."""


class ChristieTimeoutError(ChristieError):
    """The projector did not answer in time."""


class ChristieCommandError(ChristieError):
    """The projector rejected a command (ERR reply or NAK)."""

    def __init__(self, command: str, number: int | None, text: str) -> None:
        self.command = command
        self.number = number
        super().__init__(f"{command}: {text}")


@dataclass(frozen=True, slots=True)
class RawExchange:
    """Messages received for a raw command (used by the send_command service)."""

    command: str
    messages: tuple[str, ...]


def render(message: Message) -> str:
    """Return a message in protocol form for logs and service responses."""
    match message:
        case Reply(code=code, raw=raw):
            return f"({code}!{raw})"
        case SystemMessage(kind=kind, number=number, text=text):
            return f'({kind}{number:05d} "{text}")'
        case Ack(ok=ok):
            return "$" if ok else "^"
        case Unknown(body=body):
            return f"({body})"
    return repr(message)


class ChristieClient:
    """One TCP connection to a projector, used one exchange at a time.

    A lock makes sure commands never interleave. Replies are matched to the
    command that asked for them by function code, so a late reply to an
    earlier, timed-out query is ignored instead of being taken as the answer.
    The connection is opened on demand and reopened after any failure.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        on_system_message: Callable[[SystemMessage], None] | None = None,
    ) -> None:
        self._host = host.strip()
        self._port = port
        self._on_system_message = on_system_message
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._parser = StreamParser()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    @property
    def host(self) -> str:
        """Host name or IP address of the projector."""
        return self._host

    @property
    def port(self) -> int:
        """TCP port of the serial-over-IP service."""
        return self._port

    @property
    def connected(self) -> bool:
        """True while a connection is open."""
        return self._writer is not None and not self._writer.is_closing()

    def set_system_message_callback(self, callback: Callable[[SystemMessage], None] | None) -> None:
        """Receive asynchronous FYI/ERR messages from the projector."""
        self._on_system_message = callback

    async def async_close(self) -> None:
        """Close the connection, if open."""
        async with self._lock:
            await self._async_close_locked()

    # --- Queries ---------------------------------------------------------

    async def async_query(self, code: str, *, timeout: float | None = None) -> Reply:
        """Ask for one value, e.g. ``async_query("LAS+POWR")`` sends ``(LAS+POWR?)``."""
        code = code.upper()
        timeout = QUERY_TIMEOUT if timeout is None else timeout

        def done(message: Message) -> Reply | None:
            if isinstance(message, Reply) and message.code == code and message.prefix is None:
                return message
            return None

        return await self._async_exchange(f"({code}?)", code, done, timeout, retry=True)

    async def async_query_range(self, code: str, *, timeout: float | None = None) -> Reply:
        """Ask for a min/max range, e.g. ``(ZOM?m)`` -> ``(ZOM!M-1093 1102)``."""
        code = code.upper()
        timeout = QUERY_TIMEOUT if timeout is None else timeout

        def done(message: Message) -> Reply | None:
            if isinstance(message, Reply) and message.code == code and message.prefix == "M":
                return message
            return None

        return await self._async_exchange(f"({code}?m)", code, done, timeout, retry=True)

    async def async_query_list(self, code: str, *, timeout: float | None = None) -> list[Reply]:
        """Read a list such as ``(CHA?L)`` up to its ``--END--`` entry."""
        code = code.upper()
        timeout = LIST_TIMEOUT if timeout is None else timeout
        entries: list[Reply] = []

        def done(message: Message) -> list[Reply] | None:
            if not isinstance(message, Reply) or message.code != code:
                return None
            if is_list_end(message):
                return entries
            entries.append(message)
            return None

        def reset() -> None:
            entries.clear()

        return await self._async_exchange(
            f"({code}?L)", code, done, timeout, retry=True, on_retry=reset
        )

    async def async_query_group(self, code: str, *, timeout: float | None = None) -> list[Reply]:
        """Read every reply to a multi-reply query such as ``(SST+TEMP?)``.

        A ``(PNG?)`` is sent right after; the projector handles requests in
        order, so the ping reply marks the end of the group.
        """
        code = code.upper()
        timeout = LIST_TIMEOUT if timeout is None else timeout
        replies: list[Reply] = []

        def done(message: Message) -> list[Reply] | None:
            if isinstance(message, Reply):
                if message.code == code:
                    replies.append(message)
                elif message.code == _SENTINEL:
                    return replies
            return None

        def reset() -> None:
            replies.clear()

        return await self._async_exchange(
            f"({code}?)({_SENTINEL}?)", code, done, timeout, retry=True, on_retry=reset
        )

    # --- Commands --------------------------------------------------------

    async def async_set(
        self,
        code: str,
        *values: int | str,
        wait_for_ack: bool = True,
        timeout: float | None = None,
    ) -> None:
        """Send a set command, e.g. ``async_set("LAS+POWR", 500)``.

        With ``wait_for_ack`` the command is sent as ``($CODE value)`` and the
        projector's ``$`` (done) or ``^`` (failed) is awaited. If no
        acknowledgement arrives in time the command is assumed to be still
        running and no error is raised. Without it, only an ERR reply within
        a short window counts as failure.
        """
        code = code.upper()
        args = " ".join(_format_value(value) for value in values)
        body = f"{code} {args}".strip()
        if wait_for_ack:
            await self._async_command(
                f"(${body})", code, ACK_TIMEOUT if timeout is None else timeout
            )
        else:
            await self._async_command(f"({body})", code, NO_ACK_SETTLE, expect_ack=False)

    async def async_send_raw(self, command: str, *, timeout: float | None = None) -> RawExchange:
        """Send any command and return what the projector answered.

        Queries are followed by ``(PNG?)`` to know when the answer is
        complete; set commands ask for an acknowledgement.
        """
        normalized = normalize_command(command)
        code = command_code(normalized)
        timeout = LIST_TIMEOUT if timeout is None else timeout
        collected: list[Message] = []

        if is_query(normalized):
            sentinel_only = code == _SENTINEL

            def done_query(message: Message) -> list[Message] | None:
                if isinstance(message, Reply) and message.code == _SENTINEL:
                    if sentinel_only and not collected:
                        collected.append(message)
                        return None
                    return collected
                collected.append(message)
                return None

            await self._async_exchange(
                f"{normalized}({_SENTINEL}?)",
                code,
                done_query,
                timeout,
                retry=False,
                raise_errors=False,
            )
        else:
            payload = normalized
            if normalized[1:2] not in ("$", "#", "&"):
                payload = "($" + normalized[1:]

            def done_set(message: Message) -> list[Message] | None:
                collected.append(message)
                if isinstance(message, Ack):
                    return collected
                if isinstance(message, SystemMessage) and message.is_command_error:
                    return collected
                return None

            try:
                await self._async_exchange(
                    payload, code, done_set, timeout, retry=False, raise_errors=False
                )
            except ChristieTimeoutError:
                # Commands sent with a # or & prefix may never get a bare ack.
                if not collected:
                    raise
        return RawExchange(normalized, tuple(render(message) for message in collected))

    async def _async_command(
        self, payload: str, code: str, timeout: float, *, expect_ack: bool = True
    ) -> None:
        def done(message: Message) -> bool | None:
            if isinstance(message, Ack):
                if not message.ok:
                    raise ChristieCommandError(code, None, "Not acknowledged")
                return True
            return None

        try:
            await self._async_exchange(payload, code, done, timeout, retry=False)
        except ChristieTimeoutError:
            if expect_ack:
                _LOGGER.debug("No acknowledgement for %s within %ss", payload, timeout)
            # Without an ack request, silence means accepted.

    # --- Core --------------------------------------------------------------

    async def _async_exchange[T](
        self,
        payload: str,
        code: str,
        done: Callable[[Message], T | None],
        timeout: float,
        *,
        retry: bool,
        raise_errors: bool = True,
        on_retry: Callable[[], None] | None = None,
    ) -> T:
        """Send ``payload`` and read messages until ``done`` returns a result."""
        async with self._lock:
            attempts = 2 if retry else 1
            for attempt in range(attempts):
                try:
                    return await self._async_exchange_locked(
                        payload, code, done, timeout, raise_errors
                    )
                except ChristieConnectionError:
                    await self._async_close_locked()
                    if attempt + 1 >= attempts:
                        raise
                    _LOGGER.debug("Connection lost during %s; reconnecting once", payload)
                    if on_retry:
                        on_retry()
            raise AssertionError("unreachable")

    async def _async_exchange_locked[T](
        self,
        payload: str,
        code: str,
        done: Callable[[Message], T | None],
        timeout: float,
        raise_errors: bool,
    ) -> T:
        writer = await self._async_ensure_connected()
        _LOGGER.debug("-> %s", payload)
        try:
            writer.write(payload.encode("ascii", errors="strict"))
            await writer.drain()
        except UnicodeEncodeError as err:
            raise ValueError(f"Command must be ASCII: {payload!r}") from err
        except OSError as err:
            raise ChristieConnectionError(f"Write to {self._host} failed: {err!r}") from err

        try:
            async with asyncio.timeout(timeout):
                while True:
                    for message in await self._async_read_messages():
                        if self._handle_system(message, code, raise_errors):
                            continue
                        result = done(message)
                        if result is not None:
                            return result
        except TimeoutError as err:
            raise ChristieTimeoutError(f"No reply to {payload} within {timeout}s") from err

    def _handle_system(self, message: Message, code: str, raise_errors: bool) -> bool:
        """Deal with ERR/FYI messages. Returns True if the message is consumed."""
        if isinstance(message, Unknown):
            _LOGGER.debug("Ignoring unrecognised message (%s)", message.body)
            return True
        if not isinstance(message, SystemMessage):
            return False
        if message.is_command_error:
            subject = message.subject
            if subject is None or subject == code:
                if raise_errors:
                    raise ChristieCommandError(
                        code, message.number, message.text or ERROR_TEXT.get(message.number, "")
                    )
                return False
            _LOGGER.debug("Ignoring error for earlier command: %s", message.text)
            return True
        # Asynchronous FYI messages and status-change ERR00000 messages.
        if self._on_system_message:
            self._on_system_message(message)
        return True

    async def _async_read_messages(self) -> list[Message]:
        if self._reader is None:
            raise ChristieConnectionError("Not connected")
        try:
            data = await self._reader.read(_READ_SIZE)
        except OSError as err:
            raise ChristieConnectionError(f"Read from {self._host} failed: {err!r}") from err
        if not data:
            raise ChristieConnectionError(f"{self._host} closed the connection")
        text = self._decoder.decode(data)
        _LOGGER.debug("<- %s", text)
        return list(self._parser.feed(text))

    async def _async_ensure_connected(self) -> asyncio.StreamWriter:
        if self._writer is not None and not self._writer.is_closing():
            return self._writer
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        except (TimeoutError, OSError) as err:
            self._reader = self._writer = None
            raise ChristieConnectionError(
                f"Could not connect to {self._host}:{self._port}: {err!r}"
            ) from err
        self._parser = StreamParser()
        self._decoder.reset()
        _LOGGER.debug("Connected to %s:%s", self._host, self._port)
        return self._writer

    async def _async_close_locked(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()


def _format_value(value: int | str) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return value
