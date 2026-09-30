from __future__ import annotations

import logging
from typing import Any

import pytest

from open_mammotion.auth.credentials import TokenSet
from open_mammotion.auth.token_client import TokenClient
from open_mammotion.const import DEFAULT_TOKEN_TTL_S, TOKEN_PATH
from open_mammotion.exceptions import ContractError, GrantRejectedError, OpenMammotionError, TransportError
from open_mammotion.transport.session import HttpResponse
from tests._helpers import CREDENTIALS, envelope, json_response, text_response, token_grant_body
from tests.unit._fakes import FakeHttpSession

AUTH_URL = "https://auth.example.invalid"
NOW_S = 1_000.0


def make_client(session: FakeHttpSession, *, timeout_s: float = 5.0) -> TokenClient:
    return TokenClient(session, auth_base_url=AUTH_URL, clock=lambda: NOW_S, timeout_s=timeout_s)


def assert_no_secrets(exc: BaseException) -> None:
    text = f"{exc!s} {exc!r}"
    assert CREDENTIALS.client_secret not in text
    assert "access-token-1" not in text
    assert "refresh-token-1" not in text
    assert "refresh-token-old" not in text


class TestClientCredentialsRequest:
    async def test_posts_the_client_credentials_form_to_the_token_path(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body()))

        await make_client(session).grant_client_credentials(CREDENTIALS)

        (request,) = session.requests
        assert request.method == "POST"
        assert request.url == f"{AUTH_URL}{TOKEN_PATH}"
        assert request.form == {
            "client_id": "cid-test",
            "client_secret": "not-a-real-secret",
            "grant_type": "client_credentials",
        }
        assert request.json is None

    async def test_asks_for_json_with_the_configured_timeout(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body()))

        await make_client(session, timeout_s=7.5).grant_client_credentials(CREDENTIALS)

        (request,) = session.requests
        assert request.headers == {"Accept": "application/json"}
        assert request.timeout_s == 7.5


class TestRefreshTokenRequest:
    async def test_posts_the_refresh_token_form_to_the_token_path(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body()))

        await make_client(session).grant_refresh_token(CREDENTIALS, "refresh-token-old")

        (request,) = session.requests
        assert request.method == "POST"
        assert request.url == f"{AUTH_URL}{TOKEN_PATH}"
        assert request.headers == {"Accept": "application/json"}
        assert request.form == {
            "client_id": "cid-test",
            "client_secret": "not-a-real-secret",
            "grant_type": "refresh_token",
            "refresh_token": "refresh-token-old",
        }


class TestTokenSetDecode:
    async def test_returns_the_issued_tokens(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body(access_token="a-1", refresh_token="r-1")))

        token = await make_client(session).grant_client_credentials(CREDENTIALS)

        assert token.access_token == "a-1"
        assert token.refresh_token == "r-1"
        assert token.token_type == "Bearer"

    async def test_computes_expiry_from_the_injected_clock(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body(expires_in=3600)))

        token = await make_client(session).grant_client_credentials(CREDENTIALS)

        assert token.expires_at_s == NOW_S + 3600

    async def test_falls_back_to_the_default_ttl_when_expires_in_is_absent(self) -> None:
        body = token_grant_body()
        del body["data"]["expires_in"]
        session = FakeHttpSession(json_response(body))

        token = await make_client(session).grant_client_credentials(CREDENTIALS)

        assert token.expires_at_s == NOW_S + DEFAULT_TOKEN_TTL_S

    async def test_logs_the_ttl_fallback_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        body = token_grant_body()
        del body["data"]["expires_in"]
        session = FakeHttpSession(json_response(body))

        await make_client(session).grant_client_credentials(CREDENTIALS)

        assert any(r.levelno == logging.DEBUG and "expires_in" in r.getMessage() for r in caplog.records)

    async def test_returns_none_when_no_refresh_token_is_issued(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body(refresh_token=None)))

        token = await make_client(session).grant_client_credentials(CREDENTIALS)

        assert token.refresh_token is None

    async def test_treats_an_empty_refresh_token_as_none(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body(refresh_token="")))

        token = await make_client(session).grant_client_credentials(CREDENTIALS)

        assert token.refresh_token is None

    async def test_decodes_the_refresh_grant_response(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body(access_token="a-2", refresh_token="r-2")))

        token = await make_client(session).grant_refresh_token(CREDENTIALS, "refresh-token-old")

        assert token == TokenSet(access_token="a-2", expires_at_s=NOW_S + 3600, refresh_token="r-2")

    async def test_defaults_token_type_to_bearer_when_absent(self) -> None:
        body = token_grant_body()
        del body["data"]["token_type"]
        session = FakeHttpSession(json_response(body))

        token = await make_client(session).grant_client_credentials(CREDENTIALS)

        assert token.token_type == "Bearer"

    async def test_accepts_the_200_success_code(self) -> None:
        session = FakeHttpSession(json_response(token_grant_body(access_token="a-200", code=200)))

        token = await make_client(session).grant_client_credentials(CREDENTIALS)

        assert token.access_token == "a-200"

    async def test_never_logs_a_token(self, caplog: pytest.LogCaptureFixture) -> None:
        session = FakeHttpSession(json_response(token_grant_body()))

        await make_client(session).grant_client_credentials(CREDENTIALS)

        assert "access-token-1" not in caplog.text
        assert "refresh-token-1" not in caplog.text


class TestTransientFailures:
    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503])
    async def test_raises_transport_error_carrying_the_status(self, status: int) -> None:
        session = FakeHttpSession(json_response(envelope(code=status, msg="busy"), status=status))

        with pytest.raises(TransportError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.status == status

    async def test_raises_transport_error_for_a_non_json_content_type(self) -> None:
        session = FakeHttpSession(text_response("<html>gateway</html>", status=200))

        with pytest.raises(TransportError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.status == 200

    async def test_raises_transport_error_for_a_malformed_json_body(self) -> None:
        response = HttpResponse(status=200, headers={"Content-Type": "application/json"}, body=b"{not json")
        session = FakeHttpSession(response)

        with pytest.raises(TransportError):
            await make_client(session).grant_client_credentials(CREDENTIALS)

    async def test_raises_transport_error_for_a_non_json_401(self) -> None:
        session = FakeHttpSession(text_response("Unauthorized", status=401, content_type="text/plain"))

        with pytest.raises(TransportError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.status == 401

    async def test_lets_a_session_transport_error_propagate(self) -> None:
        session = FakeHttpSession(TransportError("connection reset"))

        with pytest.raises(TransportError, match="connection reset"):
            await make_client(session).grant_client_credentials(CREDENTIALS)


class TestRejectedGrant:
    async def test_raises_grant_rejected_with_code_and_msg(self) -> None:
        session = FakeHttpSession(json_response(envelope(code=40101, msg="invalid client")))

        with pytest.raises(GrantRejectedError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.grant_type == "client_credentials"
        assert exc_info.value.code == 40101
        assert exc_info.value.msg == "invalid client"

    async def test_names_the_refresh_grant_when_the_refresh_token_is_rejected(self) -> None:
        session = FakeHttpSession(json_response(envelope(code=40102, msg="invalid refresh token")))

        with pytest.raises(GrantRejectedError) as exc_info:
            await make_client(session).grant_refresh_token(CREDENTIALS, "refresh-token-old")

        assert exc_info.value.grant_type == "refresh_token"

    async def test_treats_a_json_401_envelope_as_a_rejection(self) -> None:
        session = FakeHttpSession(json_response(envelope(code=401, msg="unauthorized"), status=401))

        with pytest.raises(GrantRejectedError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.code == 401

    async def test_treats_a_4xx_status_with_a_success_code_as_a_rejection(self) -> None:
        session = FakeHttpSession(json_response(envelope(code=0, msg="bad request"), status=400))

        with pytest.raises(GrantRejectedError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.code == 400


class TestContractViolations:
    @pytest.mark.parametrize(
        "body",
        [
            pytest.param([1, 2], id="a JSON array"),
            pytest.param("text", id="a JSON string"),
            pytest.param({"msg": "no code"}, id="an object without code"),
            pytest.param({"code": "zero"}, id="a non-integer code"),
        ],
    )
    async def test_raises_contract_error_naming_the_envelope(self, body: Any) -> None:
        session = FakeHttpSession(json_response(body))

        with pytest.raises(ContractError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.model == "Envelope"

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(None, id="data null"),
            pytest.param(["access-token-1"], id="data an array"),
            pytest.param({"expires_in": 3600}, id="access_token missing"),
            pytest.param({"access_token": ""}, id="access_token empty"),
            pytest.param({"access_token": 5}, id="access_token not a string"),
            pytest.param({"access_token": "access-token-1", "refresh_token": 5}, id="refresh_token not a string"),
            pytest.param({"access_token": "access-token-1", "token_type": 5}, id="token_type not a string"),
            pytest.param({"access_token": "access-token-1", "expires_in": "3600"}, id="expires_in a string"),
            pytest.param({"access_token": "access-token-1", "expires_in": True}, id="expires_in a bool"),
        ],
    )
    async def test_raises_contract_error_naming_the_token_set(self, data: Any) -> None:
        session = FakeHttpSession(json_response(envelope(data, msg="Success")))

        with pytest.raises(ContractError) as exc_info:
            await make_client(session).grant_client_credentials(CREDENTIALS)

        assert exc_info.value.model == "TokenSet"


class TestNoSecretsInErrors:
    @pytest.mark.parametrize(
        "response",
        [
            pytest.param(json_response(envelope(code=500), status=500), id="5xx"),
            pytest.param(text_response("oops"), id="non-JSON"),
            pytest.param(json_response(envelope(code=40101, msg="invalid client")), id="rejected"),
            pytest.param(json_response({"msg": "no code"}), id="bad envelope"),
            pytest.param(
                json_response(envelope({"access_token": "access-token-1", "expires_in": "soon"})), id="bad token set"
            ),
        ],
    )
    async def test_error_text_holds_no_secret_or_token(self, response: HttpResponse) -> None:
        session = FakeHttpSession(response)

        with pytest.raises(OpenMammotionError) as exc_info:
            await make_client(session).grant_refresh_token(CREDENTIALS, "refresh-token-old")

        assert_no_secrets(exc_info.value)
