"""Tests for the TCP client against the fake projector."""

import pytest

from custom_components.christie_griffyn.client import (
    ChristieClient,
    ChristieCommandError,
    ChristieConnectionError,
    ChristieTimeoutError,
)
from custom_components.christie_griffyn.protocol import SystemMessage

from .fake_projector import FakeProjector


@pytest.fixture
async def client(projector: FakeProjector):
    client = ChristieClient("127.0.0.1", projector.port)
    yield client
    await client.async_close()


async def test_query(client: ChristieClient, projector: FakeProjector) -> None:
    reply = await client.async_query("LAS+POWR")
    assert reply.number == 300
    assert projector.received == ["LAS+POWR?"]


async def test_one_connection_is_reused(client: ChristieClient, projector: FakeProjector) -> None:
    await client.async_query("PWR")
    await client.async_query("SHU")
    assert projector.connections == 1


async def test_list_and_range(client: ChristieClient) -> None:
    entries = await client.async_query_list("SIN")
    assert entries[0].text == "None"
    assert entries[-1].text == "Christie Link [B]"
    zoom = await client.async_query_range("ZOM")
    assert zoom.numbers == (-1093, 1102)


async def test_group_uses_ping_as_end_marker(
    client: ChristieClient, projector: FakeProjector
) -> None:
    replies = await client.async_query_group("SST+LGHT")
    assert len(replies) > 100
    assert projector.received == ["SST+LGHT?", "PNG?"]


async def test_error_reply(client: ChristieClient) -> None:
    with pytest.raises(ChristieCommandError) as err:
        await client.async_query("PRO")
    assert err.value.number == 5


async def test_timeout_then_late_reply_ignored(
    client: ChristieClient, projector: FakeProjector
) -> None:
    projector.silent.add("SIN?")
    with pytest.raises(ChristieTimeoutError):
        await client.async_query("SIN", timeout=0.2)
    # Now make the old reply arrive just before the next answer.
    projector.unsolicited.append('(SIN!001 "One-Port HDMI0")')
    reply = await client.async_query("SHU")
    assert reply.code == "SHU"


async def test_reconnects_after_drop(client: ChristieClient, projector: FakeProjector) -> None:
    await client.async_query("PWR")
    projector.drop_after = 0
    reply = await client.async_query("PWR")
    assert reply.number == 1
    assert projector.connections == 2


async def test_cannot_connect(socket_enabled: None) -> None:
    client = ChristieClient("127.0.0.1", 1)
    with pytest.raises(ChristieConnectionError):
        await client.async_query("PWR")


async def test_set_with_ack(client: ChristieClient, projector: FakeProjector) -> None:
    await client.async_set("LAS+POWR", 500)
    assert projector.sets == ["$LAS+POWR 500"]
    assert (await client.async_query("LAS+POWR")).number == 500


async def test_set_nak(client: ChristieClient, projector: FakeProjector) -> None:
    projector.nak.add("SHU")
    with pytest.raises(ChristieCommandError):
        await client.async_set("SHU", 1)


async def test_set_without_ack_reports_errors(
    client: ChristieClient, projector: FakeProjector
) -> None:
    await client.async_set("PWR", 0, wait_for_ack=False)
    assert projector.sets == ["PWR 0"]
    projector.nak.add("PWR")
    with pytest.raises(ChristieCommandError):
        await client.async_set("PWR", 1, wait_for_ack=False)


async def test_async_messages_go_to_callback(projector: FakeProjector) -> None:
    seen: list[SystemMessage] = []
    client = ChristieClient("127.0.0.1", projector.port, on_system_message=seen.append)
    projector.unsolicited.append('(65535 00000 FYI00916 "Setting Time to 15:00:00")')
    reply = await client.async_query("PWR")
    await client.async_close()
    assert reply.number == 1
    assert [m.text for m in seen] == ["Setting Time to 15:00:00"]


async def test_byte_by_byte_and_utf8(client: ChristieClient, projector: FakeProjector) -> None:
    projector.split_writes = True
    replies = await client.async_query_group("SST+TEMP")
    assert replies[0].strings[0] == "77 °F"


async def test_raw_query_and_set(client: ChristieClient, projector: FakeProjector) -> None:
    exchange = await client.async_send_raw("SST+CONF?")
    assert exchange.command == "(SST+CONF?)"
    assert exchange.messages[0].startswith("(SST+CONF!000 000")
    assert len(exchange.messages) == 4
    exchange = await client.async_send_raw("(ITP 1)")
    assert exchange.messages == ("$",)
    assert projector.sets == ["$ITP 1"]
    exchange = await client.async_send_raw("XYZ?")
    assert exchange.messages[0].startswith("(ERR00101")
