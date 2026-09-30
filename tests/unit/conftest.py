"""Unit tier: no sockets, no DNS. Any attempt fails the test even if the code under test swallows it."""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import pytest

from tests.unit._fakes import FakeMisuseError

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts: list[str] = []

    def refuse(*args: Any, **kwargs: Any) -> None:
        attempts.append(repr(args[1:] or kwargs))
        raise FakeMisuseError("unit tests must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    yield
    assert not attempts, f"network attempted in a unit test: {attempts}"
