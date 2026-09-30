"""Unit tier for the aiohttp adapter: request-kwargs construction and session ownership.

End-to-end request behaviour (status, headers, body over a real socket) is covered by the
integration tier against the fake server; nothing here opens a connection.
"""

from __future__ import annotations

import aiohttp
import orjson
import pytest

from open_mammotion.exceptions import TransportError
from open_mammotion.transport.aiohttp_session import AiohttpSession, build_request_kwargs
from tests.unit._fakes import RaisingClientSession


class TestBuildRequestKwargs:
    def test_serialises_json_with_orjson_and_sets_the_content_type(self) -> None:
        kwargs = build_request_kwargs(headers=None, json={"deviceId": "dev-1", "n": 2}, form=None, timeout_s=None)

        assert kwargs["data"] == orjson.dumps({"deviceId": "dev-1", "n": 2})
        assert kwargs["headers"] == {"Content-Type": "application/json"}

    def test_json_content_type_replaces_a_caller_content_type_of_any_case(self) -> None:
        kwargs = build_request_kwargs(headers={"content-type": "text/plain"}, json={}, form=None, timeout_s=None)

        assert kwargs["headers"] == {"Content-Type": "application/json"}

    def test_sends_a_form_as_data_without_a_content_type(self) -> None:
        kwargs = build_request_kwargs(headers=None, json=None, form={"grant_type": "x"}, timeout_s=None)

        assert kwargs["data"] == {"grant_type": "x"}
        assert kwargs["headers"] == {}

    def test_keeps_caller_headers(self) -> None:
        kwargs = build_request_kwargs(
            headers={"Authorization": "Bearer t1", "Accept": "application/json"}, json={}, form=None, timeout_s=None
        )

        assert kwargs["headers"] == {
            "Authorization": "Bearer t1",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def test_turns_timeout_into_a_total_client_timeout(self) -> None:
        kwargs = build_request_kwargs(headers=None, json=None, form=None, timeout_s=12.5)

        assert kwargs["timeout"] == aiohttp.ClientTimeout(total=12.5)

    def test_omits_body_and_timeout_when_not_given(self) -> None:
        assert build_request_kwargs(headers=None, json=None, form=None, timeout_s=None) == {"headers": {}}

    def test_does_not_mutate_the_caller_headers(self) -> None:
        headers = {"Accept": "application/json"}

        build_request_kwargs(headers=headers, json={}, form=None, timeout_s=None)

        assert headers == {"Accept": "application/json"}

    def test_refuses_json_and_form_together(self) -> None:
        with pytest.raises(ValueError, match="json and form"):
            build_request_kwargs(headers=None, json={}, form={"a": "b"}, timeout_s=None)


class TestRequestRefusesBothBodies:
    async def test_raises_value_error_before_creating_a_session(self) -> None:
        session = AiohttpSession()

        with pytest.raises(ValueError, match="json and form"):
            await session.request("POST", "https://api.invalid/x", json={}, form={"a": "b"})

        assert session._session is None


class TestRequestErrorMapping:
    @pytest.mark.parametrize(
        "error",
        [TimeoutError(), OSError("connection reset"), aiohttp.ServerDisconnectedError()],
        ids=["timeout", "os-error", "client-error"],
    )
    async def test_maps_transport_failures_to_transport_error_naming_the_type(self, error: BaseException) -> None:
        session = AiohttpSession(RaisingClientSession(error))  # type: ignore[arg-type]

        with pytest.raises(TransportError) as info:
            await session.request("GET", "https://api.invalid/v1/mowers?token=not-a-real-token")

        assert type(error).__name__ in str(info.value)
        assert "not-a-real-token" not in str(info.value)
        assert info.value.__cause__ is None
        assert info.value.__suppress_context__

    async def test_maps_a_client_error_to_transport_error_naming_the_type_not_the_url(self) -> None:
        session = AiohttpSession()

        with pytest.raises(TransportError) as info:
            await session.request("GET", "/relative?token=not-a-real-token")
        await session.close()

        assert "InvalidUrl" in str(info.value)
        assert "not-a-real-token" not in str(info.value)
        assert info.value.status is None


class TestOwnership:
    async def test_does_not_close_a_borrowed_session(self) -> None:
        borrowed = aiohttp.ClientSession()
        session = AiohttpSession(borrowed)

        await session.close()

        assert not borrowed.closed
        await borrowed.close()

    async def test_closes_the_session_it_created(self) -> None:
        session = AiohttpSession()
        with pytest.raises(TransportError):
            await session.request("GET", "/relative")
        owned = session._session
        assert owned is not None

        await session.close()

        assert owned.closed

    async def test_close_twice_is_harmless(self) -> None:
        session = AiohttpSession()
        with pytest.raises(TransportError):
            await session.request("GET", "/relative")

        await session.close()
        await session.close()

        assert session._session is None

    async def test_close_without_a_request_is_harmless(self) -> None:
        session = AiohttpSession()

        await session.close()

        assert session._session is None

    async def test_uses_the_borrowed_session_for_requests(self) -> None:
        borrowed = RaisingClientSession(OSError())
        session = AiohttpSession(borrowed)  # type: ignore[arg-type]

        with pytest.raises(TransportError):
            await session.request("GET", "https://api.invalid/v1/mowers")
        await session.close()

        assert borrowed.calls == [("GET", "https://api.invalid/v1/mowers")]
        assert not borrowed.closed

    async def test_a_request_after_close_opens_a_new_owned_session(self) -> None:
        session = AiohttpSession()
        with pytest.raises(TransportError):
            await session.request("GET", "/relative")
        first = session._session
        await session.close()

        with pytest.raises(TransportError):
            await session.request("GET", "/relative")
        second = session._session
        await session.close()

        assert first is not None
        assert second is not None
        assert second is not first
        assert second.closed
