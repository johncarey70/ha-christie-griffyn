"""Tests for message parsing, using replies recorded from a real Griffyn."""

import pytest

from custom_components.christie_griffyn.protocol import (
    Ack,
    Reply,
    StreamParser,
    SystemMessage,
    command_code,
    is_list_end,
    is_query,
    list_option_from_reply,
    normalize_command,
    parse_body,
    parse_hours,
    parse_signal,
    parse_temperature_c,
    status_item_from_reply,
    unescape,
)

from .recorded import REPLIES


def parse_all(text: str) -> list:
    return list(StreamParser().feed(text))


def test_power_reply() -> None:
    [reply] = parse_all(REPLIES["PWR?"])
    assert isinstance(reply, Reply)
    assert reply.code == "PWR"
    assert reply.number == 1
    assert reply.text == "On"


def test_ping_reply_has_firmware() -> None:
    [reply] = parse_all(REPLIES["PNG?"])
    assert reply.numbers == (70, 1, 3, 7)


def test_negative_and_range_values() -> None:
    [lvo] = parse_all(REPLIES["LVO?"])
    assert lvo.number == -511
    [zoom] = parse_all(REPLIES["ZOM?m"])
    assert zoom.prefix == "M"
    assert zoom.numbers == (-1093, 1102)


def test_subcode_reply_and_quoted_value() -> None:
    [mac] = parse_all(REPLIES["NET+MAC0?"])
    assert mac.code == "NET+MAC0"
    assert mac.number is None
    assert mac.text == "00:11:22:33:44:66"
    [uid] = parse_all(REPLIES["UID?"])
    assert uid.text == "Default User"
    assert uid.numbers == (4,)


def test_channel_list() -> None:
    replies = parse_all(REPLIES["CHA?L"])
    assert is_list_end(replies[-1])
    options = [o for r in replies[:-1] if (o := list_option_from_reply(r))]
    assert options[0].value == 600
    assert options[0].label == "One-Port HDMI0"
    # The blank first entry is skipped.
    assert all(o.label for o in options)
    assert "One-Port [HDBaseT]" in [o.label for o in options]


def test_test_pattern_list_marks_unavailable_entries() -> None:
    replies = parse_all(REPLIES["ITP?L"])
    options = {o.label: o for r in replies if (o := list_option_from_reply(r))}
    assert options["Grid"].available
    assert not options["FLIR"].available


def test_profile_list_unescapes_names() -> None:
    replies = parse_all(REPLIES["PRO?L"])
    assert is_list_end(replies[-1])
    options = [o for r in replies if (o := list_option_from_reply(r))]
    assert options[0].value == 0
    assert options[0].label == "Defaults"
    assert options[2].label == "Griffyn 4K35-RGB_2025-11-16 (1)"
    assert options[6].label == "(Empty)"


def test_command_error() -> None:
    [error] = parse_all(REPLIES["PRO?"])
    assert isinstance(error, SystemMessage)
    assert error.is_command_error
    assert error.number == 5
    assert error.subject == "PRO"
    [error] = parse_all(REPLIES["HFR+ENBL?"])
    assert error.subject == "HFR+ENBL"
    assert error.number == 101


def test_async_messages_are_not_command_errors() -> None:
    [fyi, warn] = parse_all(
        '(65535 00000 FYI00916 "Setting Time to 15:00:00")'
        '(65535 00000 ERR00000 "System Warning: \\(SST+LAMP?001\\) Lamp Hours = N/A")'
    )
    assert fyi.kind == "FYI" and not fyi.is_command_error
    assert warn.kind == "ERR" and not warn.is_command_error
    assert warn.text == "System Warning: (SST+LAMP?001) Lamp Hours = N/A"


def test_stream_parser_handles_split_input_acks_and_flow_control() -> None:
    parser = StreamParser()
    text = '\x13$(PWR!001 "On")^\x11(SIN!001 "One-Port HDMI0")'
    messages = [m for char in text for m in parser.feed(char)]
    assert messages[0] == Ack(ok=True)
    assert isinstance(messages[1], Reply) and messages[1].code == "PWR"
    assert messages[2] == Ack(ok=False)
    assert messages[3].code == "SIN"


def test_parentheses_inside_quotes_and_restart() -> None:
    [reply] = parse_all('(EDO!060 "60Hz \\(Default\\)")')
    assert reply.text == "60Hz (Default)"
    # A new "(" before ")" discards the partial message.
    [reply] = parse_all('(PWR!0(SHU!000 "Open")')
    assert reply.code == "SHU"


def test_status_items() -> None:
    items = [status_item_from_reply(r) for r in parse_all(REPLIES["SST+TEMP?"])]
    first = items[0]
    assert first is not None
    assert first.key == "TEMP_002"
    assert first.description == "Air Intake Temperature (Temp 2)"
    assert parse_temperature_c(first.value) == 25.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [("77 °F", 25.0), ("31.4", 31.4), ("40 °C - High Temperature", 40.0), ("Unknown", None)],
)
def test_temperature(value: str, expected: float | None) -> None:
    assert parse_temperature_c(value) == expected


def test_hours() -> None:
    assert parse_hours("1728:54 (h:m)") == 1728.9
    assert parse_hours("1714.2") == 1714.2
    assert parse_hours("N/A") is None


def test_signal() -> None:
    signal = parse_signal("HDMI, 4096x2160 @ 23.98Hz  RGB-limited 4:4:4 bpp:8 SDR (Primary)")
    assert signal.port_type == "HDMI"
    assert signal.resolution == "4096x2160"
    assert signal.frame_rate == 23.98
    assert signal.color_format == "RGB-limited 4:4:4"
    assert signal.bit_depth == 8
    assert signal.dynamic_range == "SDR"
    assert signal.note == "Primary"
    hdr = parse_signal("HDMI, 3840x2160 @ 59.94Hz  YCbCr 4:2:2 bpp:12 HDR10 (Primary)")
    assert hdr.dynamic_range == "HDR10"
    nothing = parse_signal("HDMI (No signal)")
    assert nothing.resolution is None
    assert nothing.note == "No signal"


def test_commands() -> None:
    assert normalize_command("PWR?") == "(PWR?)"
    assert normalize_command(" (LAS+POWR 500) ") == "(LAS+POWR 500)"
    assert normalize_command("$SHU 1") == "($SHU 1)"
    with pytest.raises(ValueError):
        normalize_command("hello world")
    with pytest.raises(ValueError):
        normalize_command("")
    assert command_code("($LAS+POWR 500)") == "LAS+POWR"
    assert is_query("(SST+TEMP?)")
    assert is_query("ZOM?m")
    assert not is_query("(PWR 1)")


def test_unescape() -> None:
    assert unescape(r"a\(b\)\"c\\d\h41") == 'a(b)"c\\dA'


def test_unknown_body() -> None:
    assert parse_body("garbage").__class__.__name__ == "Unknown"
