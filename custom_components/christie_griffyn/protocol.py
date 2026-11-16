"""Christie TruLife+ serial protocol: framing, parsing and value helpers.

This module has no Home Assistant imports so it can be tested on its own.
Message format follows Christie's "TruLife+ Serial Commands" technical
reference (P/N 020-103316) and "TruLife+ Status System" reference
(P/N 020-103327).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
import re

# Function code (3 letters) with an optional +subcode (4 letters/digits).
_CODE = r"[A-Za-z]{3}(?:\+[A-Za-z0-9]{4})?"
_REPLY_RE = re.compile(rf"^(?:\d+\s+\d+\s*)?(?P<code>{_CODE})!(?P<data>.*)$", re.DOTALL)
_SYSTEM_RE = re.compile(
    r'^(?P<dest>\d+)\s+(?P<src>\d+)\s+(?P<kind>ERR|FYI)(?P<num>\d+)\s*"(?P<text>(?:\\.|[^"\\])*)"\s*$',
    re.DOTALL,
)
_TOKEN_RE = re.compile(r'"((?:\\.|[^"\\])*)"|(-?\d+)|(\S+)')
# A command we send must look like (CODE[+SUB][ data]) with no stray brackets.
_COMMAND_RE = re.compile(rf"^[$#&]{{0,2}}{_CODE}(?:\s*\?[A-Za-z]?\d*|\s.*|)$", re.DOTALL)

XON = "\x11"
XOFF = "\x13"
ACK = "$"
NAK = "^"
LIST_END = "--END--"
LIST_END_FLAG = 111

# Error numbers from the "Descriptive error" table.
ERROR_TEXT: dict[int, str] = {
    3: "Invalid parameter",
    4: "Too many parameters",
    5: "Too few parameters",
    6: "Channel not found",
    7: "Command not executed",
    8: "Checksum error",
    9: "Unknown request",
    10: "Error receiving serial data",
    101: "Control not found",
    102: "Subcontrol not found",
    103: "Wrong control type",
    104: "Invalid value",
    105: "Disabled control",
    106: "Invalid language",
    107: "Exceeded list size",
    110: "Communication timeout",
    111: "Communications failure",
    112: "Failed to set hardware",
    113: "Bad file",
    114: "Memory failure",
    115: "Not implemented",
    116: "Invalid security",
    117: "Invalid access group",
    118: "System busy - Try again later",
}


def unescape(text: str) -> str:
    r"""Undo the protocol's two-character escapes (\( \) \" \\ \n \h##)."""
    out: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "n":
                out.append("\n")
                i += 2
                continue
            if (
                nxt == "h"
                and i + 3 < len(text)
                and re.fullmatch(r"[0-9A-Fa-f]{2}", text[i + 2 : i + 4])
            ):
                out.append(chr(int(text[i + 2 : i + 4], 16)))
                i += 4
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


def escape(text: str) -> str:
    """Escape a string so it can be sent inside double quotes."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\n", "\\n")
    )


@dataclass(frozen=True, slots=True)
class Reply:
    """A reply such as ``(PWR!001 "On")`` or ``(SIN!L001 001 00001 "HDMI0")``."""

    code: str
    """Upper-case function code with subcode, e.g. ``LAS+POWR``."""
    raw: str
    """Data after the ``!``, still escaped."""
    prefix: str | None
    """``L`` for list entries, ``M`` for min/max replies, otherwise None."""
    numbers: tuple[int, ...]
    strings: tuple[str, ...]

    @property
    def number(self) -> int | None:
        """First numeric field, or None."""
        return self.numbers[0] if self.numbers else None

    @property
    def text(self) -> str | None:
        """First quoted string, unescaped, or None."""
        return self.strings[0] if self.strings else None


@dataclass(frozen=True, slots=True)
class SystemMessage:
    """``(65535 00000 ERR00005 "ITP: Too Few Parameters")`` or an FYI message."""

    kind: str
    """``ERR`` or ``FYI``."""
    number: int
    text: str

    @property
    def is_command_error(self) -> bool:
        """True for an error caused by a command (non-zero error number)."""
        return self.kind == "ERR" and self.number != 0

    @property
    def subject(self) -> str | None:
        """The command an error refers to, from a ``CODE+SUB:`` text prefix."""
        match = re.match(rf"^({_CODE})\s*:", self.text)
        return match.group(1).upper() if match else None


@dataclass(frozen=True, slots=True)
class Ack:
    """A bare ``$`` (success) or ``^`` (failure) acknowledgement."""

    ok: bool


@dataclass(frozen=True, slots=True)
class Unknown:
    """A bracketed message we could not classify."""

    body: str


type Message = Reply | SystemMessage | Ack | Unknown


def parse_body(body: str) -> Reply | SystemMessage | Unknown:
    """Parse the text between the brackets of one message."""
    body = body.strip()
    if match := _SYSTEM_RE.match(body):
        return SystemMessage(
            kind=match["kind"], number=int(match["num"]), text=unescape(match["text"])
        )
    if match := _REPLY_RE.match(body):
        return parse_reply(match["code"].upper(), match["data"])
    return Unknown(body)


def parse_reply(code: str, data: str) -> Reply:
    """Split reply data into numbers and quoted strings."""
    prefix: str | None = None
    rest = data
    if len(data) > 1 and data[0] in "LM" and (data[1].isdigit() or data[1] in '-" '):
        prefix, rest = data[0], data[1:]
    numbers: list[int] = []
    strings: list[str] = []
    for quoted, number, other in _TOKEN_RE.findall(rest):
        if number:
            numbers.append(int(number))
        elif other:
            continue
        else:
            strings.append(unescape(quoted))
    return Reply(code, data, prefix, tuple(numbers), tuple(strings))


@dataclass(slots=True)
class StreamParser:
    """Turns a byte stream from the projector into messages.

    Handles concatenated replies, escapes inside strings, bare ``$``/``^``
    acknowledgements and XON/XOFF flow-control characters.
    """

    _buffer: list[str] = field(default_factory=list)
    _in_message: bool = False
    _escape: bool = False
    _in_quotes: bool = False

    def feed(self, text: str) -> Iterator[Message]:
        """Consume text and yield every complete message found."""
        for char in text:
            if char in (XON, XOFF):
                continue
            if not self._in_message:
                if char == "(":
                    self._start()
                elif char == ACK:
                    yield Ack(ok=True)
                elif char == NAK:
                    yield Ack(ok=False)
                continue
            if self._escape:
                self._buffer.append(char)
                self._escape = False
                continue
            if char == "\\":
                self._buffer.append(char)
                self._escape = True
                continue
            if char == '"':
                self._in_quotes = not self._in_quotes
                self._buffer.append(char)
                continue
            if char == ")" and not self._in_quotes:
                body = "".join(self._buffer)
                self._in_message = False
                self._buffer = []
                yield parse_body(body)
                continue
            if char == "(" and not self._in_quotes:
                # A new start before the end discards the partial message.
                self._start()
                continue
            self._buffer.append(char)

    def _start(self) -> None:
        self._buffer = []
        self._in_message = True
        self._escape = False
        self._in_quotes = False


def normalize_command(command: str) -> str:
    """Return ``(CMD)`` for user input with or without the outer brackets."""
    text = command.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    if not text or not _COMMAND_RE.match(text):
        raise ValueError(f"Not a Christie serial command: {command!r}")
    return f"({text})"


def command_code(command: str) -> str:
    """Upper-case ``CODE+SUB`` of a command such as ``(LAS+POWR 500)``."""
    text = command.strip().lstrip("(").lstrip("$#&")
    match = re.match(_CODE, text)
    if not match:
        raise ValueError(f"No function code in {command!r}")
    return match.group(0).upper()


def is_query(command: str) -> bool:
    """True if the command only asks for information (contains ``?``)."""
    text = command.strip().strip("()").lstrip("$#&")
    return bool(re.match(rf"^{_CODE}\s*\?", text))


# --- Status system -------------------------------------------------------


class StatusState:
    """Condition field of a status item."""

    OK = 0
    WARNING = 1
    ERROR = 2


@dataclass(frozen=True, slots=True)
class StatusItem:
    """One ``(SST+<group>!<index> <state> "<value>" "<description>")`` item."""

    group: str
    index: int
    state: int
    value: str
    description: str

    @property
    def key(self) -> str:
        """Stable key such as ``TEMP_002``."""
        return f"{self.group}_{self.index:03d}"


def status_item_from_reply(reply: Reply) -> StatusItem | None:
    """Convert an ``SST+XXXX!`` reply into a status item."""
    if not reply.code.startswith("SST+") or len(reply.numbers) < 2:
        return None
    value = reply.strings[0] if reply.strings else ""
    description = reply.strings[1] if len(reply.strings) > 1 else ""
    return StatusItem(
        group=reply.code[4:],
        index=reply.numbers[0],
        state=reply.numbers[1],
        value=value.strip(),
        description=description.strip(),
    )


# --- Lists ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ListOption:
    """One selectable entry from a ``?L`` list or the profile list."""

    value: int
    label: str
    available: bool = True


def list_option_from_reply(reply: Reply) -> ListOption | None:
    """Parse one list entry; returns None for the end marker or blanks.

    Two shapes exist on the Griffyn:
    ``(CHA!L001 001 00600 "One-Port HDMI0")`` (available, ?, value, label) and
    ``(PRO!003 "Name")`` (value, label) for the profile list.
    """
    label = reply.text
    if label is None or label == LIST_END:
        return None
    if reply.prefix == "L":
        if len(reply.numbers) < 3 or reply.numbers[0] == LIST_END_FLAG:
            return None
        if label == "":
            return None
        return ListOption(reply.numbers[2], label, available=reply.numbers[0] == 1)
    if reply.numbers:
        return ListOption(reply.numbers[0], label)
    return None


def is_list_end(reply: Reply) -> bool:
    """True for ``(XXX!L111 "--END--")`` or ``(PRO!"--END--")``."""
    if reply.text == LIST_END:
        return True
    return reply.prefix == "L" and bool(reply.numbers) and reply.numbers[0] == LIST_END_FLAG


# --- Value helpers ---------------------------------------------------------

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_TEMP_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:°|Â°|º)?\s*([CF])?\b")
_HM_RE = re.compile(r"^\s*(\d+):(\d{1,2})")
_SIGNAL_NOTE_RE = re.compile(r"\(([^()]*)\)\s*$")
_SIGNAL_MODE_RE = re.compile(r"(\d+)\s*x\s*(\d+)\s*@\s*(\d+(?:\.\d+)?)\s*Hz", re.IGNORECASE)
_DYNAMIC_RANGE = re.compile(r"^(SDR|HDR\w*|HLG|PQ|DV)$", re.IGNORECASE)


def parse_float(value: str | None) -> float | None:
    """First number in a status value such as ``" 12.40A"`` or ``"6980 RPM"``."""
    if value is None:
        return None
    match = _NUMBER_RE.search(value)
    return float(match.group(0)) if match else None


def parse_temperature_c(value: str | None) -> float | None:
    """Temperature in °C from ``"77 °F"``, ``"31.4"`` or ``"25 °C - High Temperature"``."""
    if value is None:
        return None
    match = _TEMP_RE.match(value)
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2) == "F":
        return round((number - 32) * 5 / 9, 1)
    return number


def parse_hours(value: str | None) -> float | None:
    """Hours from ``"1728:54 (h:m)"`` or ``"1714.2"``."""
    if value is None:
        return None
    if match := _HM_RE.match(value):
        return round(int(match.group(1)) + int(match.group(2)) / 60, 2)
    return parse_float(value)


@dataclass(frozen=True, slots=True)
class SignalInfo:
    """Details parsed from a signal status value."""

    description: str
    port_type: str
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    color_format: str | None = None
    bit_depth: int | None = None
    dynamic_range: str | None = None
    note: str | None = None

    @property
    def resolution(self) -> str | None:
        """``WIDTHxHEIGHT`` or None."""
        if self.width is None or self.height is None:
            return None
        return f"{self.width}x{self.height}"


def parse_signal(value: str) -> SignalInfo:
    """Parse e.g. ``HDMI, 4096x2160 @ 23.98Hz  RGB-limited 4:4:4 bpp:8 SDR (Primary)``."""
    text = " ".join(value.split())
    note: str | None = None
    body = text
    if match := _SIGNAL_NOTE_RE.search(body):
        note = match.group(1).strip()
        body = body[: match.start()].strip()
    port_type, _, rest = body.partition(",")
    width = height = None
    frame_rate: float | None = None
    if match := _SIGNAL_MODE_RE.search(rest):
        width, height = int(match.group(1)), int(match.group(2))
        frame_rate = float(match.group(3))
        rest = rest[: match.start()] + rest[match.end() :]
    bit_depth: int | None = None
    dynamic_range: str | None = None
    color_tokens: list[str] = []
    for token in rest.split():
        if token.lower().startswith("bpp:"):
            depth = token[4:]
            bit_depth = int(depth) if depth.isdigit() else None
        elif _DYNAMIC_RANGE.match(token):
            dynamic_range = token.upper()
        else:
            color_tokens.append(token)
    return SignalInfo(
        description=text,
        port_type=port_type.strip(),
        width=width,
        height=height,
        frame_rate=frame_rate,
        color_format=" ".join(color_tokens) or None,
        bit_depth=bit_depth,
        dynamic_range=dynamic_range,
        note=note,
    )
