from __future__ import annotations

import orjson
import pytest

from open_mammotion.auth.credentials import ClientCredentials, TokenSet, fingerprint
from open_mammotion.exceptions import ContractError
from tests._helpers import CREDENTIALS
from tests.unit._helpers import make_token_set


class TestClientCredentialsRepr:
    def test_repr_omits_the_secret(self) -> None:
        text = repr(CREDENTIALS)

        assert CREDENTIALS.client_secret not in text
        assert "<redacted>" in text

    def test_repr_keeps_the_client_id(self) -> None:
        assert CREDENTIALS.client_id in repr(CREDENTIALS)

    def test_str_omits_the_secret(self) -> None:
        creds = ClientCredentials(client_id="cid-test", client_secret="another-fake-secret")

        assert "another-fake-secret" not in str(creds)


class TestTokenSetRepr:
    def test_repr_omits_the_access_token_and_refresh_token(self) -> None:
        token = make_token_set(access_token="access-token-xyz", refresh_token="refresh-token-xyz")

        text = repr(token)

        assert "access-token-xyz" not in text
        assert "refresh-token-xyz" not in text

    def test_repr_shows_the_access_token_fingerprint(self) -> None:
        token = make_token_set(access_token="access-token-xyz")

        assert fingerprint("access-token-xyz") in repr(token)

    def test_repr_marks_a_present_refresh_token(self) -> None:
        assert "refresh_token=<present>" in repr(make_token_set(refresh_token="refresh-token-xyz"))

    def test_repr_reports_an_absent_refresh_token_as_none(self) -> None:
        assert "refresh_token=None" in repr(make_token_set(refresh_token=None))


class TestIsFresh:
    def test_is_fresh_before_expiry_without_lead(self) -> None:
        assert make_token_set(expires_at_s=1_000.0).is_fresh(999.0)

    def test_is_not_fresh_at_exact_expiry(self) -> None:
        assert not make_token_set(expires_at_s=1_000.0).is_fresh(1_000.0)

    def test_is_not_fresh_after_expiry(self) -> None:
        assert not make_token_set(expires_at_s=1_000.0).is_fresh(1_001.0)

    def test_is_fresh_just_outside_the_lead_window(self) -> None:
        assert make_token_set(expires_at_s=1_000.0).is_fresh(699.0, lead_s=300.0)

    def test_is_not_fresh_at_the_start_of_the_lead_window(self) -> None:
        assert not make_token_set(expires_at_s=1_000.0).is_fresh(700.0, lead_s=300.0)

    def test_is_not_fresh_inside_the_lead_window(self) -> None:
        assert not make_token_set(expires_at_s=1_000.0).is_fresh(800.0, lead_s=300.0)


class TestRoundTrip:
    def test_to_dict_is_the_persisted_json_shape(self) -> None:
        token = TokenSet(access_token="a", expires_at_s=1_234.5, refresh_token="r", token_type="Bearer")

        data = token.to_dict()

        assert data == {"access_token": "a", "expires_at_s": 1_234.5, "refresh_token": "r", "token_type": "Bearer"}
        assert orjson.loads(orjson.dumps(data)) == data

    def test_from_dict_of_to_dict_is_equal(self) -> None:
        token = TokenSet(access_token="a", expires_at_s=1_234.5, refresh_token="r", token_type="Bearer")

        assert TokenSet.from_dict(token.to_dict()) == token

    def test_round_trip_keeps_an_absent_refresh_token(self) -> None:
        token = make_token_set(refresh_token=None)

        assert TokenSet.from_dict(token.to_dict()).refresh_token is None

    def test_from_dict_defaults_token_type_to_bearer(self) -> None:
        assert TokenSet.from_dict({"access_token": "a", "expires_at_s": 1.0}).token_type == "Bearer"

    def test_from_dict_accepts_an_integer_expiry(self) -> None:
        assert TokenSet.from_dict({"access_token": "a", "expires_at_s": 5}).expires_at_s == 5.0


class TestFromDictContract:
    @pytest.mark.parametrize(
        "data",
        [
            pytest.param({"expires_at_s": 1.0}, id="access_token missing"),
            pytest.param({"access_token": "", "expires_at_s": 1.0}, id="access_token empty"),
            pytest.param({"access_token": 7, "expires_at_s": 1.0}, id="access_token not a string"),
            pytest.param({"access_token": "a"}, id="expires_at_s missing"),
            pytest.param({"access_token": "a", "expires_at_s": "1.0"}, id="expires_at_s a string"),
            pytest.param({"access_token": "a", "expires_at_s": True}, id="expires_at_s a bool"),
            pytest.param({"access_token": "a", "expires_at_s": 1.0, "refresh_token": 3}, id="refresh_token not str"),
            pytest.param({"access_token": "a", "expires_at_s": 1.0, "token_type": None}, id="token_type not str"),
        ],
    )
    def test_raises_contract_error_naming_token_set(self, data: dict[str, object]) -> None:
        with pytest.raises(ContractError) as exc_info:
            TokenSet.from_dict(data)

        assert exc_info.value.model == "TokenSet"


class TestFingerprint:
    def test_is_stable_for_the_same_token(self) -> None:
        assert fingerprint("access-token-1") == fingerprint("access-token-1")

    def test_differs_between_tokens(self) -> None:
        assert fingerprint("access-token-1") != fingerprint("access-token-2")

    def test_is_twelve_hex_characters(self) -> None:
        value = fingerprint("access-token-1")

        assert len(value) == 12
        assert all(c in "0123456789abcdef" for c in value)

    def test_does_not_contain_the_token(self) -> None:
        assert "access-token-1" not in fingerprint("access-token-1")
