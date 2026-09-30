"""The facade's wiring: real layers end to end over a scripted ``FakeHttpSession``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
import pytest

from open_mammotion.client import OpenMammotion
from open_mammotion.const import DEFAULT_LANGUAGE, REQUEST_TIMEOUT_S
from open_mammotion.exceptions import CredentialsRejectedError
from open_mammotion.transport.aiohttp_session import AiohttpSession
from tests._helpers import ACCESS_TOKEN, envelope, json_response, token_grant_body
from tests.unit._fakes import FakeHttpSession
from tests.unit._helpers import make_token_set
from tests.unit.models._helpers import device_info_json, ws_ticket_json

if TYPE_CHECKING:
    from open_mammotion.auth.credentials import ClientCredentials, TokenSet

NOW_S = 1_700_000_000.0


class TestComposition:
    async def test_first_api_call_grants_a_token_then_calls_the_api(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(token_grant_body()), json_response(envelope([device_info_json()])))

        async with OpenMammotion(
            credentials, session=http, clock=lambda: NOW_S, api_url="http://api.test", auth_url="http://auth.test"
        ) as api:
            devices = await api.devices.list()

        assert [d.device_id for d in devices] == [device_info_json()["id"]]
        grant, call = http.requests
        assert grant.url == "http://auth.test/oauth2/token"
        assert grant.form is not None
        assert grant.form["grant_type"] == "client_credentials"
        assert call.url == "http://api.test/v1/mowers"
        assert call.bearer == ACCESS_TOKEN
        assert call.headers.get("Accept-Language") == DEFAULT_LANGUAGE

    async def test_resumes_with_a_persisted_token_and_no_grant(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(envelope([])))
        held = make_token_set(expires_at_s=NOW_S + 3600)

        api = OpenMammotion(credentials, session=http, tokens=held, clock=lambda: NOW_S, api_url="http://api.test")
        devices = await api.devices.list()

        assert devices == []
        assert [r.url for r in http.requests] == ["http://api.test/v1/mowers"]
        assert api.token == held

    async def test_on_token_updated_receives_each_new_token(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(token_grant_body(access_token="fresh")))
        seen: list[TokenSet] = []

        async def remember(token: TokenSet) -> None:
            seen.append(token)

        api = OpenMammotion(credentials, session=http, on_token_updated=remember, clock=lambda: NOW_S)
        token = await api.authenticate()

        assert seen == [token]
        assert token.access_token == "fresh"
        assert token.expires_at_s == NOW_S + 3600

    async def test_language_is_forwarded(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(envelope([])))

        api = OpenMammotion(
            credentials,
            session=http,
            tokens=make_token_set(expires_at_s=NOW_S + 3600),
            clock=lambda: NOW_S,
            language="de-DE",
        )
        await api.devices.list()

        assert http.requests[0].headers["Accept-Language"] == "de-DE"

    async def test_forwards_the_timeout_to_both_the_grant_and_the_api_call(
        self, credentials: ClientCredentials
    ) -> None:
        http = FakeHttpSession(json_response(token_grant_body()), json_response(envelope([])))

        api = OpenMammotion(credentials, session=http, clock=lambda: NOW_S, timeout_s=7.5)
        await api.devices.list()

        assert [r.timeout_s for r in http.requests] == [7.5, 7.5]

    async def test_defaults_the_timeout(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(token_grant_body()))

        await OpenMammotion(credentials, session=http, clock=lambda: NOW_S).authenticate()

        assert http.requests[0].timeout_s == REQUEST_TIMEOUT_S

    async def test_ws_ticket_defaults_its_timestamp_from_the_facade_clock(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(envelope(ws_ticket_json())))

        api = OpenMammotion(
            credentials, session=http, tokens=make_token_set(expires_at_s=NOW_S + 3600), clock=lambda: NOW_S
        )
        await api.local_network.ws_ticket("Yuka-1")

        assert http.requests[0].json == {"deviceName": "Yuka-1", "timestamp": int(NOW_S)}


class TestAuthenticate:
    async def test_rejected_credentials_raise_without_the_secret(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(token_grant_body(code=40101)))
        api = OpenMammotion(credentials, session=http, clock=lambda: NOW_S)

        with pytest.raises(CredentialsRejectedError) as info:
            await api.authenticate()

        assert api.credentials_rejected is not None
        assert credentials.client_secret not in str(info.value)
        assert credentials.client_secret not in api.credentials_rejected

    async def test_rejected_credentials_are_terminal_for_every_group(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession(json_response(token_grant_body(code=40101)))
        api = OpenMammotion(credentials, session=http, clock=lambda: NOW_S)
        with pytest.raises(CredentialsRejectedError):
            await api.authenticate()

        with pytest.raises(CredentialsRejectedError):
            await api.devices.list()

        assert len(http.requests) == 1


class TestSessionOwnership:
    async def test_borrowed_aiohttp_session_is_not_closed(self, credentials: ClientCredentials) -> None:
        borrowed = aiohttp.ClientSession()
        try:
            async with OpenMammotion(credentials, session=borrowed):
                pass
            assert not borrowed.closed
        finally:
            await borrowed.close()

    async def test_injected_http_session_is_closed_on_exit(self, credentials: ClientCredentials) -> None:
        http = FakeHttpSession()

        async with OpenMammotion(credentials, session=http):
            pass

        assert http.closed

    async def test_creates_and_owns_an_aiohttp_session_when_none_is_given(self, credentials: ClientCredentials) -> None:
        api = OpenMammotion(credentials)

        assert isinstance(api._http, AiohttpSession)
        await api.close()
