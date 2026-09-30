# Decisions

Numbered, append-only. A decision is superseded by a later entry, never
edited away. Each entry states the choice and the reason; alternatives get one
line at most.

## D1. Clean room, specification-driven

The library is written from `docs/openapi/*.json` and the developer portal
pages only. Nothing is ported from `pymammotion` or the app. Reason: the Open
API is a supported, documented contract; a client built on it should not
inherit assumptions from reverse-engineered protocols. Gaps go to
`open_questions.md`.

## D2. A separate package, not a module in pymammotion

Developer credentials are a different identity from the app login, the API is
a different host with a different envelope, and the supported device set is
different. A separate package keeps the dependency direction clean: a host
can use either or both. Reason over the alternative (an `openapi/` package in
`pymammotion`): it would import that library's transport and auth machinery
for nothing, and its release cadence is tied to protocol reverse-engineering.

## D3. mashumaro + orjson for models

Dataclasses with `DataClassORJSONMixin`. Reason: zero-boilerplate camelCase
aliases, fast, already a Home Assistant core dependency so the likely host
adds nothing. Pydantic was rejected for weight and for its validation-error
shape; plain dataclasses were rejected for the alias plumbing they would need.

## D4. The package mirrors the specification tags

`api/devices.py`, `api/actions.py`, `api/work_reports.py`, `api/faults.py`,
`api/local_network.py` correspond to the specification's tags (with the
"Mower information" tag split into devices and faults because the error-code
search is a different concern). Reason: a reader with the spec open finds the
method in one hop; adding an endpoint is a local change.

## D5. Protocols at every seam a test replaces

`HttpSession`, `Requester`, `TokenProvider` are `typing.Protocol`s. Reason:
each layer is tested with a hand-written fake of the layer below and no
mocking library; a host can supply its own HTTP session. Abstract base classes
were rejected because none of these seams share implementation.

## D6. Token renewal is lazy; there is no scheduler

`TokenManager.get_access_token()` refreshes when the token is inside its lead
window (`TOKEN_REFRESH_LEAD_S`, 300 s) and not otherwise. Reason: the
client-credentials grant mints a fresh token on demand, so nothing rots while
the host is idle, and a background task in a library is a lifecycle hazard for
the host. If the API ever revokes idle credentials, add a scheduler as a new
decision.

## D7. A rejected refresh token falls back to client credentials, once

Order in `TokenManager._renew`: refresh-token grant if a refresh token is
held, then client-credentials grant. A rejected client-credentials grant is
terminal (`CredentialsRejectedError`; every later call fails fast with no
I/O). Reason: the developer portal documents both paths and the secret is a
machine credential, so re-granting is not the password-hammering hazard it
would be with a user password. The bound is one grant of each kind per
renewal, no timers.

## D8. Success is `code in {0, 200}` until the API says otherwise

The portal's prose examples show `"code": 0`; the OpenAPI examples show
`200`. `SUCCESS_CODES` accepts both. Reason: refusing one of them would break
against the real server in one of the two cases and the cost of accepting
both is nil. Recorded in `open_questions.md` Q1; narrow it when a capture
settles it.

## D9. One reactive refresh per stale token

`ApiTransport` retries a 401 exactly once, after
`TokenProvider.invalidate(token_it_sent)`. `TokenManager.invalidate` is a
no-op if the token passed is not the current one. Reason: a burst of calls
that all 401 on the same dead token must produce one refresh, not N serialised
ones that rotate the refresh token against each other.

## D10. Wire models are tolerant

Unknown keys ignored, unknown enum values become `UNKNOWN` (logged once per
enum and value), optional fields default. Required fields raise
`ContractError`. Reason: the API is young and adds fields; a client that
crashes on a new `status` string takes down the host's whole integration for
a cosmetic change.

## D11. Base URLs come from `const.py` with environment overrides

`OPEN_MAMMOTION_API_URL`, `OPEN_MAMMOTION_AUTH_URL`. Reason: the fake server
in `tests/fakeserver/` and a host's dev install need to point the library at
loopback without patching.

## D12. No host knowledge

The library exposes `TokenSet.to_dict()/from_dict()` and an
`on_token_updated` callback for persistence and stops there. Reason: config
flows, entity mapping and storage are host concerns; putting them here couples
the release cycles.

## D13. Tests mirror the package; fakes live in one file

`tests/unit/<pkg>/test_<module>.py`; `tests/unit/_fakes.py` holds every
hand-written fake (the fake server under `tests/fakeserver/` is a separate
thing: a server, not a double). Reason: a renamed module has one test module to rename; a
changed protocol has one fake to update.

## D14. Timestamps are integers in milliseconds

Models store `*_ms: int` exactly as the wire sends them and expose
`datetime` through properties. Reason: lossless round-trip, no timezone
guessing in the model, and `to_dict()` sends back what the server gave.

## D15. Licence follows the ecosystem (GPL-3.0-or-later)

Same licence as `pymammotion`, which the same hosts already accept. Change
requires the author's decision, not a pull request.

## D16. A failing `on_token_updated` does not fail the renewal

`TokenManager` awaits the host's `on_token_updated` after storing a renewed
token. An exception from it is caught, logged at WARNING with the exception
type name only, and the token is still returned. Reason: the grant succeeded
and the token is in memory; a host storage failure must not fail the request
that needed the token, nor force another grant. This is the only permitted
swallow outside a `close()` path.

## D17. A 4xx status is an error even when its envelope says success

`ApiTransport` raises `ApiError(code=status)` for any 4xx whose body carries a
success `code`, and keeps the envelope's own code when it is a failure.
Reason: Constitution §5 says a non-success response is an exception; an HTTP
status the server chose is a stronger signal than an envelope field that
might be a default. Whether the real server ever does this is Q13.

## D18. Per-action wrappers are allowed over `perform`

`ActionsApi` has one method per `WorkAction` value (`start`, `pause`, …), each
a one-line call to `perform`. Constitution §2's "one public method per
endpoint" is about where an endpoint's logic lives, and it lives in `perform`
alone; the wrappers exist so a host reads `api.actions.pause(id)` instead of
an enum import. No other endpoint gets wrappers.

## D19. A required `str` field refuses `null`

mashumaro coerces with `str()`, so `{"id": null}` would decode to the string
`"None"` and then build `/v1/mower/None`. `WireModel.__pre_deserialize__`
rejects a non-string in any required `str` field. Reason: Constitution §7
says a missing required field is a `ContractError`, and a null is missing.
Optional fields keep accepting `null`.
