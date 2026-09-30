"""Unit tier for ``HttpResponse``: content-type parsing and JSON decoding."""

from __future__ import annotations

import orjson
import pytest

from open_mammotion.transport.session import HttpResponse, is_transient_status


def _response(headers: dict[str, str], body: bytes = b"") -> HttpResponse:
    return HttpResponse(status=200, headers=headers, body=body)


class TestContentType:
    def test_reads_the_header_case_insensitively(self) -> None:
        assert _response({"content-TYPE": "application/json"}).content_type == "application/json"

    def test_strips_parameters_and_whitespace(self) -> None:
        response = _response({"Content-Type": " Application/JSON ; charset=utf-8"})

        assert response.content_type == "application/json"

    def test_is_empty_when_the_header_is_absent(self) -> None:
        assert _response({}).content_type == ""


class TestJson:
    def test_decodes_a_json_object(self) -> None:
        assert _response({}, b'{"code": 0}').json() == {"code": 0}

    def test_raises_a_value_error_subclass_on_garbage(self) -> None:
        with pytest.raises(orjson.JSONDecodeError):
            _response({}, b"<html>bad gateway</html>").json()

    def test_raises_a_value_error_subclass_on_an_empty_body(self) -> None:
        with pytest.raises(orjson.JSONDecodeError):
            _response({}, b"").json()

    def test_decode_error_is_a_value_error(self) -> None:
        assert issubclass(orjson.JSONDecodeError, ValueError)


class TestIsTransientStatus:
    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 599])
    def test_timeouts_throttling_and_server_errors_are_transient(self, status: int) -> None:
        assert is_transient_status(status)

    @pytest.mark.parametrize("status", [200, 201, 301, 400, 401, 403, 404, 499])
    def test_everything_else_is_not(self, status: int) -> None:
        assert not is_transient_status(status)
