"""Unit tier for ``ApiTransport``: headers, the single 401 retry, and status/envelope mapping."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import pytest

from open_mammotion.const import DEFAULT_LANGUAGE, REQUEST_TIMEOUT_S
from open_mammotion.exceptions import (
    ApiError,
    ContractError,
    CredentialsRejectedError,
    TransportError,
    UnauthorizedError,
)
from open_mammotion.models.common import Envelope
from open_mammotion.transport.api import ApiTransport
from tests._helpers import REQUEST_ID, envelope, json_response, text_response
from tests.unit._fakes import FakeHttpSession, FakeTokenProvider

if TYPE_CHECKING:
    from open_mammotion.transport.session import HttpResponse

BASE_URL = "https://api.invalid"
PATH = "/v1/mowers"


def _transport(session: FakeHttpSession, tokens: FakeTokenProvider | None = None, **kwargs: str) -> ApiTransport:
    return ApiTransport(session, tokens or FakeTokenProvider("t1"), api_base_url=BASE_URL, **kwargs)


def _ok(data: object = None, **kwargs: Any) -> HttpResponse:
    return json_response(envelope(data, **kwargs))


def _unauthorized() -> HttpResponse:
    return json_response(envelope(None, code=401, msg="Unauthorized"), status=401)


class TestRequestShape:
    async def test_sends_the_providers_token_as_a_bearer(self) -> None:
        session = FakeHttpSession(_ok())

        await _transport(session, FakeTokenProvider("t1")).request("GET", PATH)

        assert session.requests[0].authorization == "Bearer t1"

    async def test_sends_the_default_language_and_accepts_json(self) -> None:
        session = FakeHttpSession(_ok())

        await _transport(session).request("GET", PATH)

        headers = session.requests[0].headers
        assert headers["Accept-Language"] == DEFAULT_LANGUAGE
        assert headers["Accept"] == "application/json"

    async def test_sends_the_configured_language(self) -> None:
        session = FakeHttpSession(_ok())

        await _transport(session, language="de-DE").request("GET", PATH)

        assert session.requests[0].headers["Accept-Language"] == "de-DE"

    async def test_joins_the_path_to_the_base_url_with_one_slash(self) -> None:
        session = FakeHttpSession(_ok(), _ok())
        transport = ApiTransport(session, FakeTokenProvider("t1"), api_base_url=f"{BASE_URL}/")

        await transport.request("GET", "/v1/mower/dev-1")
        await transport.request("GET", "v1/mower/dev-1")

        assert [r.url for r in session.requests] == [f"{BASE_URL}/v1/mower/dev-1"] * 2

    async def test_forwards_method_json_payload_and_timeout(self) -> None:
        session = FakeHttpSession(_ok())

        await _transport(session).request("POST", "/v1/mower/action", json={"deviceId": "dev-1"})

        sent = session.requests[0]
        assert (sent.method, sent.json, sent.form, sent.timeout_s) == (
            "POST",
            {"deviceId": "dev-1"},
            None,
            REQUEST_TIMEOUT_S,
        )

    async def test_forwards_no_payload_when_none_is_given(self) -> None:
        session = FakeHttpSession(_ok())

        await _transport(session).request("GET", PATH)

        assert session.requests[0].json is None


class TestSuccess:
    @pytest.mark.parametrize("code", [0, 200])
    async def test_returns_the_envelope_for_either_success_code(self, code: int) -> None:
        session = FakeHttpSession(_ok([{"deviceId": "dev-1"}], code=code))

        result = await _transport(session).request("GET", PATH)

        assert result == Envelope(code=code, msg="Request success", data=[{"deviceId": "dev-1"}], request_id=REQUEST_ID)

    async def test_accepts_json_served_under_another_content_type(self) -> None:
        session = FakeHttpSession(text_response('{"code": 0, "data": 1}', content_type="text/plain"))

        result = await _transport(session).request("GET", PATH)

        assert result.data == 1

    async def test_logs_one_debug_line_without_the_token(self, caplog: pytest.LogCaptureFixture) -> None:
        session = FakeHttpSession(_ok())

        await _transport(session, FakeTokenProvider("secret-bearer-value")).request("GET", PATH)

        records = [r for r in caplog.records if r.name == "open_mammotion.transport.api"]
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG
        assert all(part in records[0].getMessage() for part in ("GET", PATH, "200", REQUEST_ID))
        assert "secret-bearer-value" not in caplog.text


class TestTransientStatuses:
    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
    async def test_raises_transport_error_carrying_the_status(self, status: int) -> None:
        session = FakeHttpSession(json_response(envelope(None, code=status, msg="busy"), status=status))

        with pytest.raises(TransportError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.status == status

    async def test_raises_transport_error_for_a_5xx_html_page(self) -> None:
        session = FakeHttpSession(text_response("<h1>Bad Gateway</h1>", status=502))

        with pytest.raises(TransportError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.status == 502

    async def test_does_not_invalidate_the_token(self) -> None:
        tokens = FakeTokenProvider("t1")

        with pytest.raises(TransportError):
            await _transport(FakeHttpSession(text_response("", status=503)), tokens).request("GET", PATH)

        assert tokens.invalidated == []


class TestEnvelopeErrors:
    async def test_raises_api_error_for_a_non_success_code_on_http_200(self) -> None:
        session = FakeHttpSession(_ok(None, code=1001, msg="device not bound", request_id="req-9"))

        with pytest.raises(ApiError) as info:
            await _transport(session).request("GET", PATH)

        assert (info.value.code, info.value.msg, info.value.request_id, info.value.path) == (
            1001,
            "device not bound",
            "req-9",
            PATH,
        )

    async def test_raises_api_error_from_the_envelope_of_a_4xx(self) -> None:
        session = FakeHttpSession(json_response(envelope(None, code=403, msg="forbidden"), status=403))

        with pytest.raises(ApiError) as info:
            await _transport(session).request("GET", PATH)

        assert (info.value.code, info.value.msg, info.value.request_id) == (403, "forbidden", REQUEST_ID)

    async def test_raises_api_error_even_when_a_4xx_envelope_claims_success(self) -> None:
        session = FakeHttpSession(json_response(envelope(None, code=0), status=404))

        with pytest.raises(ApiError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.code == 404

    async def test_api_error_does_not_invalidate_the_token(self) -> None:
        tokens = FakeTokenProvider("t1")

        with pytest.raises(ApiError):
            await _transport(FakeHttpSession(_ok(code=1001)), tokens).request("GET", PATH)

        assert tokens.invalidated == []


class TestNonEnvelopeBodies:
    async def test_raises_transport_error_for_a_non_json_2xx(self) -> None:
        session = FakeHttpSession(text_response("<html>captive portal</html>", status=200))

        with pytest.raises(TransportError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.status == 200
        assert "non-JSON" in str(info.value)

    async def test_raises_api_error_for_a_non_json_4xx(self) -> None:
        session = FakeHttpSession(text_response("Not Found", status=404, content_type="text/plain"))

        with pytest.raises(ApiError) as info:
            await _transport(session).request("GET", PATH)

        assert (info.value.code, info.value.msg, info.value.request_id, info.value.path) == (
            404,
            "HTTP 404 without an envelope",
            None,
            PATH,
        )

    @pytest.mark.parametrize("body", [[1, 2], "text", 3, None])
    async def test_raises_contract_error_for_json_that_is_not_an_object(self, body: object) -> None:
        session = FakeHttpSession(json_response(body))

        with pytest.raises(ContractError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.model == "Envelope"

    async def test_raises_contract_error_for_a_code_of_the_wrong_type(self) -> None:
        session = FakeHttpSession(json_response({"code": "not-a-number", "msg": "x"}))

        with pytest.raises(ContractError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.model == "Envelope"

    async def test_raises_transport_error_for_a_non_json_3xx(self) -> None:
        session = FakeHttpSession(text_response("moved", status=302))

        with pytest.raises(TransportError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.status == 302

    async def test_raises_contract_error_for_an_object_without_a_code(self) -> None:
        session = FakeHttpSession(json_response({"msg": "hello"}))

        with pytest.raises(ContractError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value.model == "Envelope"


class TestUnauthorizedRetry:
    async def test_invalidates_the_sent_token_and_retries_with_the_next(self) -> None:
        tokens = FakeTokenProvider("t1", "t2")
        session = FakeHttpSession(_unauthorized(), _ok({"n": 1}))

        result = await _transport(session, tokens).request("GET", PATH)

        assert result.data == {"n": 1}
        assert tokens.invalidated == ["t1"]
        assert [r.bearer for r in session.requests] == ["t1", "t2"]

    async def test_raises_unauthorized_after_a_second_401_with_one_invalidate(self) -> None:
        tokens = FakeTokenProvider("t1", "t2")
        session = FakeHttpSession(_unauthorized(), _unauthorized())

        with pytest.raises(UnauthorizedError) as info:
            await _transport(session, tokens).request("GET", PATH)

        assert info.value.path == PATH
        assert len(session.requests) == 2
        assert tokens.invalidated == ["t1"]

    async def test_a_401_without_an_envelope_still_triggers_the_retry(self) -> None:
        tokens = FakeTokenProvider("t1", "t2")
        session = FakeHttpSession(text_response("", status=401), _ok())

        await _transport(session, tokens).request("GET", PATH)

        assert tokens.invalidated == ["t1"]

    async def test_a_401_carries_no_token_in_the_exception(self) -> None:
        session = FakeHttpSession(_unauthorized(), _unauthorized())

        with pytest.raises(UnauthorizedError) as info:
            await _transport(session, FakeTokenProvider("tok-a", "tok-b")).request("GET", PATH)

        assert "tok-a" not in str(info.value)
        assert "tok-b" not in str(info.value)

    async def test_burst_on_one_stale_token_retries_each_call_once_with_the_fresh_token(self) -> None:
        tokens = FakeTokenProvider("t1", "t2")
        session = FakeHttpSession()
        session.router = lambda request: _unauthorized() if request.bearer == "t1" else _ok({"ok": True})
        session.gate = asyncio.Event()
        transport = ApiTransport(session, tokens, api_base_url=BASE_URL)

        calls = [asyncio.create_task(transport.request("GET", PATH)) for _ in range(5)]
        await asyncio.wait_for(session.wait_for_calls(5), timeout=1)
        session.gate.set()
        results = await asyncio.wait_for(asyncio.gather(*calls), timeout=1)

        assert all(r.data == {"ok": True} for r in results)
        assert tokens.invalidated == ["t1"] * 5
        assert sorted(r.bearer or "" for r in session.requests) == ["t1"] * 5 + ["t2"] * 5

    async def test_a_transient_status_on_the_retry_raises_transport_error(self) -> None:
        session = FakeHttpSession(_unauthorized(), text_response("", status=503))

        with pytest.raises(TransportError) as info:
            await _transport(session, FakeTokenProvider("t1", "t2")).request("GET", PATH)

        assert info.value.status == 503

    async def test_an_envelope_error_on_the_retry_raises_api_error(self) -> None:
        session = FakeHttpSession(_unauthorized(), json_response(envelope(None, code=403, msg="forbidden"), status=403))

        with pytest.raises(ApiError) as info:
            await _transport(session, FakeTokenProvider("t1", "t2")).request("GET", PATH)

        assert (info.value.code, info.value.msg) == (403, "forbidden")


class TestPropagation:
    async def test_credentials_rejected_propagates_without_any_request(self) -> None:
        session = FakeHttpSession()

        with pytest.raises(CredentialsRejectedError):
            await _transport(session, FakeTokenProvider(rejected="invalid_client")).request("GET", PATH)

        assert session.requests == []

    async def test_transport_error_from_the_session_propagates(self) -> None:
        failure = TransportError("GET request failed: ClientConnectorError")
        session = FakeHttpSession(failure)

        with pytest.raises(TransportError) as info:
            await _transport(session).request("GET", PATH)

        assert info.value is failure
