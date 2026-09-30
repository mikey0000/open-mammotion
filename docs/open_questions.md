# Open questions

Things the specification does not settle. Each has the conservative reading
the code takes today and what would close the question. Closed questions are
deleted and their answer lands in `decisions.md` or `docs/api/`.

## Q1. Success code: 0 or 200?

Portal prose examples return `"code": 0, "msg": "Request success"`; the
OpenAPI examples return `200, "Success"`. Today: `SUCCESS_CODES = {0, 200}`
(D8). Closes with one real response capture.

## Q2. Does a second client-credentials grant invalidate the first token?

If the token endpoint is single-session per client id (as the app login is),
a host and a developer's script would evict each other. Today: assumed not.
Closes with two concurrent grants and a call on the first token.

## Q3. Is the refresh-token grant ever necessary?

Client credentials can always mint a new token. The refresh grant may exist
for parity only. Today: refresh first, client credentials second (D7).
Closes when Q2 is answered; if grants are single-session, refresh-first is the
safer order and stays.

## Q4. Rate limits and quotas

Nothing documented for `api-open.mammotion.com`. Unknown whether action calls
share any per-device send budget on the app side. Today: none enforced;
`429` is a `TransportError`. Closes with a documented limit or an observed
429 body.

## Q5. `deviceId` is the IoT id?

Examples (`4DMCTo…e90u5oV4`) look like a 22-character IoT id and `name` looks
like the device name. Today: `device_id` is opaque; the library never derives
it. Closes by comparing against the device list of the same account in the
app.

## Q6. SSE event payload shape

`/v1/devices/subscriptions` documents the property keys and the connection
rules but not the JSON of a pushed event. Blocks phase 3. Closes with a
capture from a Luba 3 AWD.

## Q7. LAN WebSocket: host, port, TLS, handshake, framing

`/v1/mower/ws/ticket` returns an HMAC-signed ticket; nothing says where the
mower listens, whether the certificate is self-signed, how the ticket is
presented, or what the frames are. Blocks phase 5. Closes with a capture.

## Q8. `redirectUri` on the HA local-network config

Described as "HA OAuth redirect URI", which implies an authorization-code
grant for end users that `authentication.json` does not list. If it exists,
hosts would not need per-user developer credentials. Closes by asking
Mammotion.

## Q9. Which models are "released in 2025"?

The pre-operation page limits the API to 2025 models. Today: not enforced;
the device list is authoritative. Closes with a product list from Mammotion.

## Q10. `msgTitle` and `requestId` presence

Some responses in the spec omit `msgTitle`; all have `requestId` as a string
but the example is a bare integer. Today: both optional, `request_id`
coerced to `str`. Closes with captures.

## Q11. `Accept-Language` effect

Documented as defaulting to `en-US`. Unknown which fields it localises
(`msg`? fault `implication`/`solution`?). Today: sent on every request from
the facade's `language` argument. Closes with two captures in different
languages.

## Q12. How the token endpoint reports a bad grant

Unknown whether a rejected client secret or refresh token comes back as HTTP
401, or as HTTP 200 with a non-zero `code`, and whether the body is JSON in
each case; also whether a refresh grant always re-issues a `refresh_token`.
Today: a JSON non-success envelope on any status is `GrantRejectedError`; a
non-JSON 401 is `TransportError` (never terminal on uncertain evidence); a
refresh grant without a new refresh token drops the old one, so the next
renewal uses client credentials. Closes with one capture of each.

## Q13. Does the server ever pair a 4xx status with a success `code`?

Today: treated as an error (D17). Closes with captures of 404 and 400
responses.

## Q14. Is `GET /v1/mower/{deviceId}` an object or a one-element list?

The portal page shows a list, `mower.json` an object. Today: both accepted,
anything else is `ContractError`. Closes with one capture.

## Q15. Failure envelopes the fake server assumes

The specification documents only the 401 for a bad token. `tests/fakeserver`
answers everything else with HTTP 200 and an envelope code, portal style:
`400 "<field> is required"` / `"<field> is invalid"` for body validation,
`404 "device not found"` / `"work report not found"`, `40101 "invalid
client"` and `40102 "Refresh token has expired"` from the token endpoint, and
`commandResult: false` with `"device offline"`, `"taskName is required"` or
`"task not found"` for refused actions. The WS ticket signature's field order
and key are the fake's own. Each of these closes with one capture; when the
real server differs, fix the fake first.

## Q16. Can `expires_in` be shorter than the refresh lead?

If the token endpoint ever issued a token with `expires_in` at or below
`TOKEN_REFRESH_LEAD_S` (300 s), no held token would count as fresh and every
call would run a grant. Today: not guarded; the portal documents 3600.
Closes with a captured `expires_in`; if short tokens exist, clamp the lead to
a fraction of the TTL as a new decision.
