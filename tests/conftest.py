"""Fixtures for the Christie Griffyn tests."""

from collections.abc import AsyncGenerator, Generator
from unittest.mock import patch

import pytest

from .fake_projector import FakeProjector


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components in every test."""


@pytest.fixture(autouse=True)
def short_waits() -> Generator[None]:
    """Keep command delays and timeouts short."""
    with (
        patch("custom_components.christie_griffyn.switch.POST_POWER_REFRESH_DELAY", 0),
        patch("custom_components.christie_griffyn.client.QUERY_TIMEOUT", 0.5),
        patch("custom_components.christie_griffyn.client.NO_ACK_SETTLE", 0.05),
    ):
        yield


@pytest.fixture
async def projector(socket_enabled: None) -> AsyncGenerator[FakeProjector]:
    """A fake projector listening on localhost."""
    fake = FakeProjector()
    await fake.start()
    yield fake
    await fake.stop()
