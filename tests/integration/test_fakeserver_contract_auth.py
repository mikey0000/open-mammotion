"""Token grants and Bearer auth on the fake cloud.

These pin the fake itself (docs/testing.md §6) with a raw client, so the facade's integration tests can trust it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import orjson
import pytest

from tests.fakeserver.state import FAKE_CLIENT_SECRET

if TYPE_CHECKING:
    from tests.fakeserver.clock import ManualClock
    from tests.integration._fakeserver_client import RawClient


class TestClientCredentialsGrant:
    async def test_issues_a_bearer_token_in_the_spec_shape(self, anon_client: RawClient) -> None:
        body = await anon_client.grant()

        assert body["code"] == 200
        assert body["msg"] == "Success"
        assert set(body["data"]) == {"access_token", "refresh_token", "token_type", "expires_in"}
        assert body["data"]["token_type"] == "Bearer"
        assert body["data"]["expires_in"] == 3600
        assert body["data"]["access_token"].count(".") == 2

    @pytest.mark.parametrize(
        ("form", "code", "msg"),
        [
            ({"client_secret": "wrong"}, 40101, "invalid client"),
            ({"client_id": ""}, 400, "client_id is required"),
            ({"grant_type": "password"}, 400, "grant_type is invalid"),
            ({"grant_type": "refresh_token"}, 400, "refresh_token is required"),
        ],
        ids=["wrong-secret", "missing-field", "unsupported-grant", "refresh-without-token"],
    )
    async def test_rejects_a_bad_grant_with_http_200_and_an_error_envelope(
        self, anon_client: RawClient, form: dict[str, str], code: int, msg: str
    ) -> None:
        body = await anon_client.grant(**form)

        assert (body["code"], body["msg"], body["data"]) == (code, msg, None)

    async def test_reject_client_credentials_knob_is_sticky(self, anon_client: RawClient) -> None:
        await anon_client.control(reject_client_credentials=True)

        codes = [(await anon_client.grant())["code"], (await anon_client.grant())["code"]]

        assert codes == [40101, 40101]

    async def test_token_ttl_knob_sets_expires_in(self, anon_client: RawClient) -> None:
        await anon_client.control(token_ttl_s=120)

        body = await anon_client.grant()

        assert body["data"]["expires_in"] == 120


class TestRefreshGrant:
    async def test_rotates_the_pair_and_invalidates_the_old_refresh_token(self, raw_client: RawClient) -> None:
        first = await raw_client.grant()
        old_refresh = first["data"]["refresh_token"]

        rotated = await raw_client.grant(grant_type="refresh_token", refresh_token=old_refresh)
        reused = await raw_client.grant(grant_type="refresh_token", refresh_token=old_refresh)

        assert rotated["code"] == 200
        assert rotated["data"]["refresh_token"] != old_refresh
        assert rotated["data"]["access_token"] != first["data"]["access_token"]
        assert (reused["code"], reused["msg"]) == (40102, "Refresh token has expired")

    async def test_old_access_token_stays_valid_after_rotation(self, raw_client: RawClient) -> None:
        refresh = (await raw_client.grant())["data"]["refresh_token"]

        await raw_client.grant(grant_type="refresh_token", refresh_token=refresh)
        status, _, _ = await raw_client.raw("GET", "/v1/mowers")

        assert status == 200

    async def test_rejects_an_unknown_refresh_token(self, raw_client: RawClient) -> None:
        body = await raw_client.grant(grant_type="refresh_token", refresh_token="rt-never-issued")

        assert body["code"] == 40102

    async def test_reject_next_refresh_knob_rejects_exactly_once(self, raw_client: RawClient) -> None:
        pairs = [(await raw_client.grant())["data"]["refresh_token"] for _ in range(2)]
        await raw_client.control(reject_next_refresh=True)

        first = await raw_client.grant(grant_type="refresh_token", refresh_token=pairs[0])
        second = await raw_client.grant(grant_type="refresh_token", refresh_token=pairs[1])

        assert (first["code"], second["code"]) == (40102, 200)

    async def test_counts_successful_grants_by_kind(self, anon_client: RawClient) -> None:
        refresh = (await anon_client.grant())["data"]["refresh_token"]
        await anon_client.grant()
        await anon_client.grant(grant_type="refresh_token", refresh_token=refresh)
        await anon_client.grant(client_secret="wrong")

        snapshot = await anon_client.control()

        assert snapshot["token_grants"] == {"client_credentials": 2, "refresh_token": 1}


class TestBearerAuth:
    @pytest.mark.parametrize("token", ["", "not-a-token"], ids=["missing", "unknown"])
    async def test_answers_401_without_a_valid_token(self, raw_client: RawClient, token: str) -> None:
        status, content_type, text = await raw_client.raw("GET", "/v1/mowers", token=token)

        body = orjson.loads(text)
        assert (status, content_type) == (401, "application/json")
        assert (body["code"], body["msg"]) == (401, "Unauthorized")

    async def test_answers_401_from_the_expiry_instant_and_not_before(
        self, raw_client: RawClient, fake_clock: ManualClock
    ) -> None:
        fake_clock.advance(3599)
        before, _, _ = await raw_client.raw("GET", "/v1/mowers")
        fake_clock.advance(1)
        at_expiry, _, _ = await raw_client.raw("GET", "/v1/mowers")

        assert (before, at_expiry) == (200, 401)

    async def test_expire_tokens_knob_kills_access_but_not_refresh(self, raw_client: RawClient) -> None:
        refresh = (await raw_client.grant())["data"]["refresh_token"]
        await raw_client.control(expire_tokens=True)

        status, _, _ = await raw_client.raw("GET", "/v1/mowers")
        renewed = await raw_client.grant(grant_type="refresh_token", refresh_token=refresh)

        assert status == 401
        assert renewed["code"] == 200

    async def test_records_accept_language(self, raw_client: RawClient) -> None:
        await raw_client.raw("GET", "/v1/mowers", headers={"Accept-Language": "de-DE"})

        assert raw_client.state.requests[-1].accept_language == "de-DE"

    async def test_recorded_requests_carry_no_secret_or_token(self, raw_client: RawClient) -> None:
        refresh = (await raw_client.grant())["data"]["refresh_token"]
        await raw_client.grant(grant_type="refresh_token", refresh_token=refresh)
        await raw_client.raw("GET", "/v1/mowers")

        recorded = repr(raw_client.state.requests)

        assert FAKE_CLIENT_SECRET not in recorded
        assert refresh not in recorded
        assert raw_client.access_token not in recorded
