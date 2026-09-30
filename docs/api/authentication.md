# Authentication

Source: `docs/openapi/authentication.json`; portal pages "Create Credentials"
and "Authorization". Module: `open_mammotion/auth/`.

## Credentials

Created once in the developer portal after signing in with a Mammotion
account. The secret is shown once and can only be reset (which invalidates
the previous one). The library receives them as
`ClientCredentials(client_id, client_secret)`; the secret is redacted in
`repr`.

## `POST /oauth2/token`

Host `https://id.mammotion.com`. Body `application/x-www-form-urlencoded`.

| Field | Required | Values |
|---|---|---|
| `client_id` | yes | |
| `client_secret` | yes | |
| `grant_type` | yes | `client_credentials` or `refresh_token` |
| `refresh_token` | with `refresh_token` grant | |

Response `data` (`AccessTokenVo` → `TokenSet`):

| Wire | Python | Notes |
|---|---|---|
| `access_token` | `access_token` | JWT, sent as `Bearer` |
| `refresh_token` | `refresh_token` | may be absent; `str | None` |
| `token_type` | `token_type` | `"Bearer"` |
| `expires_in` | — | seconds; converted to `expires_at_s` (absolute, from the injected clock) |

The portal states `expires_in` is 3600; when the field is absent the library
assumes `DEFAULT_TOKEN_TTL_S` (3600) and logs it at DEBUG. The API answers
HTTP 401 when the token is invalid or expired.

## Library behaviour

- `TokenClient.grant_client_credentials(credentials)` and
  `TokenClient.grant_refresh_token(credentials, refresh_token)` perform the
  two grants and return a `TokenSet`. A non-success envelope raises
  `GrantRejectedError` (an `AuthError`; `TokenManager` translates it, so the
  facade never lets it escape); 408/429/5xx/non-JSON raise `TransportError`.
  "JSON" means the body parses, whatever the `Content-Type`, because the spec
  declares the token response as `*/*`.
- `TokenManager` (implements `TokenProvider`) holds the current `TokenSet`,
  serialises renewal behind an `asyncio.Lock`, refreshes when the token is
  within `TOKEN_REFRESH_LEAD_S` of expiry, tries the refresh grant first
  and the client-credentials grant second (D7), and becomes terminal on a
  rejected client-credentials grant (`CredentialsRejectedError`).
- `TokenManager.invalidate(stale_token)` expires the held token only if it is
  the one passed (D9).
- `TokenSet.to_dict()` / `TokenSet.from_dict()` and the `on_token_updated`
  callback are the persistence surface (D12).
- `TokenManager.ensure_token()` returns the fresh `TokenSet` itself; the
  facade's `authenticate()` is that.

Open questions: Q2, Q3.
