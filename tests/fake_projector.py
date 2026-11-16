"""A fake Christie TruLife+ projector on a local TCP port, for tests.

It answers queries from the recorded replies, applies set commands to its
state, acknowledges ``$`` commands and can be told to misbehave.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import re

from .recorded import REPLIES

_SET_RE = re.compile(
    r"^(?P<prefix>[$#&]*)(?P<code>[A-Za-z]{3}(?:\+[A-Za-z0-9]{4})?)\s*(?P<args>.*)$"
)

POWER_TEXT = {0: "Standby", 1: "On", 10: "Cooling Down", 11: "Warming Up"}


@dataclass
class FakeProjector:
    """Test double for the projector's serial-over-IP service."""

    replies: dict[str, str] = field(default_factory=lambda: dict(REPLIES))
    received: list[str] = field(default_factory=list)
    connections: int = 0
    silent: set[str] = field(default_factory=set)
    """Queries (e.g. ``"SIN?"``) that get no answer at all."""
    rejected: set[str] = field(default_factory=set)
    """Queries answered with ERR00105 Disabled control."""
    nak: set[str] = field(default_factory=set)
    """Set-command codes answered with ``^``."""
    drop_after: int | None = None
    """Close the connection after this many more messages."""
    unsolicited: list[str] = field(default_factory=list)
    """Raw text sent before the next reply (e.g. async FYI messages)."""
    split_writes: bool = False
    """Send replies one byte at a time."""

    _server: asyncio.Server | None = None
    _writers: list[asyncio.StreamWriter] = field(default_factory=list)

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)

    async def stop(self) -> None:
        for writer in self._writers:
            writer.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def set_power(self, state: int) -> None:
        self.replies["PWR?"] = f'(PWR!{state:03d} "{POWER_TEXT[state]}")'

    @property
    def sets(self) -> list[str]:
        """Received commands that were not queries."""
        return [message for message in self.received if "?" not in message]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        self._writers.append(writer)
        buffer = ""
        try:
            while data := await reader.read(1024):
                buffer += data.decode("ascii")
                while "(" in buffer and ")" in buffer[buffer.index("(") :]:
                    start = buffer.index("(")
                    end = buffer.index(")", start)
                    body, buffer = buffer[start + 1 : end], buffer[end + 1 :]
                    self.received.append(body)
                    if self.drop_after is not None:
                        if self.drop_after <= 0:
                            self.drop_after = None
                            writer.close()
                            return
                        self.drop_after -= 1
                    reply = self._respond(body)
                    if self.unsolicited:
                        reply = "".join(self.unsolicited) + reply
                        self.unsolicited.clear()
                    if reply:
                        await self._write(writer, reply)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()

    async def _write(self, writer: asyncio.StreamWriter, text: str) -> None:
        # Recorded text was captured as latin-1, so this restores the bytes.
        data = text.encode("latin-1")
        if self.split_writes:
            for byte in data:
                writer.write(bytes([byte]))
                await writer.drain()
        else:
            writer.write(data)
            await writer.drain()

    def _respond(self, body: str) -> str:
        key = body.replace(" ", "")
        if "?" in key:
            if key in self.silent:
                return ""
            if key in self.rejected:
                code = key.split("?")[0]
                return f'(65535 00000 ERR00105 "{code}: Disabled Control")'
            if key in self.replies:
                return self.replies[key]
            code = key.split("?")[0]
            return f'(65535 00000 ERR00101 "{code}: Control Not Found")'
        match = _SET_RE.match(body.strip())
        if not match:
            return '(65535 00000 ERR00009 "Unknown request")'
        prefix, code, args = match["prefix"], match["code"].upper(), match["args"].strip()
        ack = "$" in prefix
        if code in self.nak:
            return "^" if ack else f'(65535 00000 ERR00007 "{code}: Command Not Executed")'
        if code == "PWR" and args in ("0", "1"):
            self.set_power(11 if args == "1" else 10)
        elif args.lstrip("-").isdigit() and f"{code}?" in self.replies:
            value = int(args)
            width = 4 if abs(value) >= 1000 else 3
            self.replies[f"{code}?"] = f"({code}!{value:0{width}d})"
        return "$" if ack else ""
