"""Global safety nets only (docs/testing.md §2). Builders live in ``_helpers.py``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from tests._helpers import CREDENTIALS, leaked_secrets

if TYPE_CHECKING:
    from collections.abc import Iterator

    from open_mammotion.auth.credentials import ClientCredentials


@pytest.fixture
def credentials() -> ClientCredentials:
    return CREDENTIALS


@pytest.fixture(autouse=True)
def _no_secret_in_logs(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    """Fail any test whose log output carries a fixture secret or token (Constitution §6)."""
    caplog.set_level(logging.DEBUG)
    yield
    # caplog.text at teardown holds only teardown-phase records; the test body is a separate phase.
    records = [*caplog.get_records("setup"), *caplog.get_records("call")]
    leaked = leaked_secrets(records)
    assert not leaked, f"secret values leaked into a log line: {leaked}"
