# Architecture

`open-mammotion` is an asynchronous Python client for the Mammotion Open API
(`https://api-open.mammotion.com`, OAuth2 client-credentials tokens from
`https://id.mammotion.com`). It is a thin, typed, well-tested wrapper: one
method per endpoint, one model per schema, and a small amount of credential
and error handling that the specification leaves to the client.

This document is the map. The rules are in `CONSTITUTION.md`; the reasons are
in `decisions.md`.

## 1. Layer map

```
┌──────────────────────────────────────────────────────────────┐
│ client.py — OpenMammotion                                    │
│   Facade. Composes one TokenManager, one ApiTransport and     │
│   one instance of each API group. Async context manager.      │
├──────────────────────────────────────────────────────────────┤
│ api/ — one module per specification tag                      │
│   devices.py        Mower information: list, get             │
│   actions.py        Mower action command: perform, work      │
│                     params, task list                         │
│   work_reports.py   Mower work report: summary, search, get   │
│   faults.py         Device error-code search                  │
│   local_network.py  HA local network: save, query, ws ticket  │
│   subscriptions.py  (phase 3) material fetch + subscriptions  │
│   _base.py          ApiGroup: typed _get/_post over Requester │
├──────────────────────────────────────────────────────────────┤
│ transport/                                                    │
│   session.py        HttpSession protocol + HttpResponse       │
│   aiohttp_session.py aiohttp adapter (host may inject its own │
│                     ClientSession; the library never closes   │
│                     one it did not create)                    │
│   requester.py      Requester protocol (method, path, json →  │
│                     Envelope)                                 │
│   api.py            ApiTransport: Bearer + Accept-Language,   │
│                     envelope decode, error mapping, the single│
│                     401 retry                                 │
├──────────────────────────────────────────────────────────────┤
│ auth/                                                         │
│   credentials.py    ClientCredentials, TokenSet (redacting;  │
│                     to_dict/from_dict = the cache round-trip) │
│   token_client.py   TokenClient: the two grants               │
│   protocols.py      TokenGranter + TokenProvider protocols   │
│   token_manager.py  TokenManager: lock, lead window, refresh  │
│                     policy, terminal flag                     │
├──────────────────────────────────────────────────────────────┤
│ models/ — one module per schema family, mashumaro dataclasses │
│   common.py  Envelope, int_bool, tolerant enum bases          │
│   device.py  action.py  work_params.py  task.py               │
│   work_report.py  fault.py  local_network.py                  │
├──────────────────────────────────────────────────────────────┤
│ exceptions.py — the whole hierarchy, nothing raised elsewhere │
│ const.py      — base URLs (env-overridable), timeouts, leads  │
└──────────────────────────────────────────────────────────────┘
```

Imports only go downward in this picture, and across a seam only through
its protocol module: `api/` imports `transport.requester` (never the
`transport` package or `ApiTransport`); `transport/api.py` imports
`auth.protocols` and `auth.credentials` (never `TokenManager`); `auth/`
imports `transport.session` only (the token client needs an `HttpSession`);
`models/` imports nothing outside `models`, `exceptions`, `const`. Nothing
below `client.py` imports the package root. `tests/meta/test_conventions.py`
asserts exactly this. That is what lets every layer be unit-tested with a
hand-written fake of the layer below (`tests/unit/_fakes.py`).

## 2. The three flows

### 2.1 A request

```
OpenMammotion.devices.get("4DMC…")
  → DevicesApi._get("/v1/mower/4DMC…", DeviceDetail)
      → Requester.request("GET", "/v1/mower/4DMC…")        (ApiTransport)
          1. token = await TokenProvider.get_access_token()
          2. HttpSession.request(..., headers={Authorization: Bearer token,
                                              Accept-Language: language})
          3. status 401 → TokenProvider.invalidate(token_sent); retry once
             (steps 1–2); a second 401 raises UnauthorizedError. The
             invalidate is per call; dedupe across a burst is
             TokenManager.invalidate's job (D9)
          4. 408 / 429 / 5xx, or a non-JSON 2xx/3xx → TransportError;
             a non-JSON 4xx → ApiError(code=status)
          5. body → Envelope (JSON that is not an envelope → ContractError);
             code ∉ SUCCESS_CODES, or a 4xx status even with a success
             code (D17) → ApiError(code, msg, request_id)
          6. return Envelope (data still raw JSON)
      → model.from_dict(envelope.data)                        (ApiGroup)
         decode failure → ContractError naming the model and field
```

The `ApiGroup` helpers are the only place raw JSON becomes a model, and
`ApiTransport` is the only place an HTTP status becomes an exception. An
endpoint method is therefore two or three lines: build the path and payload,
call the helper, return the model.

### 2.2 A token

```
TokenManager.get_access_token()
  ├─ terminal flag set            → raise CredentialsRejectedError (no I/O)
  ├─ token valid beyond lead      → return it
  └─ under asyncio.Lock:
       re-check (another caller may have refreshed while we waited)
       have refresh_token → TokenClient.grant_refresh_token()
           rejected       → fall through
       TokenClient.grant_client_credentials()
           rejected       → set terminal flag, raise CredentialsRejectedError
       TransportError at any step → propagate; state untouched
       store TokenSet, fire on_token_updated, return access token
```

`invalidate(stale_token)` marks the current token expired **only if** it is
the token the caller actually sent. If a concurrent caller already rotated it,
the call is a no-op and the retry simply uses the fresh token. This is what
makes a burst of requests that all 401 on one dead token produce one refresh.

Renewal is lazy on purpose: the client-credentials grant can mint a fresh
token at any time, so there is nothing to keep warm. `decisions.md` D6.

### 2.3 An error

| Observation | Exception | State change | Caller should |
|---|---|---|---|
| network error, timeout, 408, 429, 5xx, non-JSON 2xx/3xx | `TransportError` | none | back off and retry |
| non-JSON 4xx | `ApiError(code=status)` | none | inspect `code`, `path` |
| token endpoint: JSON body that is not an envelope | `ContractError("Envelope")` | none | file a bug (Q12) |
| 401 after the one retry | `UnauthorizedError` | none (the retry's token is kept) | the next call retries with that token and refreshes only on its own 401; a persistent one is Q2 |
| token endpoint rejects the refresh token | (internal) | falls back to client credentials | — |
| token endpoint rejects client credentials | `CredentialsRejectedError` | terminal flag set | ask the user for new credentials |
| envelope `code` not in `SUCCESS_CODES` | `ApiError` | none | inspect `code`, `msg`, `request_id` |
| `commandResult: false` on an action | `CommandRejectedError` (an `ApiError`) | none | report `result_message` |
| body does not match the model | `ContractError` | none | file a bug; the API changed |
| body is JSON but not an envelope | `ContractError("Envelope")` | none | file a bug; something else answered |

Every exception carries what a log line needs and nothing a log line must not
have: a `TokenSet` in an exception is a constitution violation.

## 3. Single homes

| Question | The one place that answers it |
|---|---|
| Is this HTTP status transient? | `transport/session.py::is_transient_status` (used by `ApiTransport` and `TokenClient`) |
| Is this HTTP status an error? | `transport/api.py::ApiTransport._raise_for_status` / `_raise_for_envelope` |
| Is this envelope a success? | `models/common.py::SUCCESS_CODES` |
| Is the token fresh enough? | `auth/token_manager.py::TokenManager._fresh_token` |
| Which grant do we try next? | `auth/token_manager.py::TokenManager._renew` |
| How is a secret printed? | `auth/credentials.py` `__repr__`; `fingerprint()` for logs |
| What does an unknown enum value become? | `models/common.py::TolerantIntEnum` / `TolerantStrEnum` |
| How does a wire timestamp become a `datetime`? | `models/common.py::utc_from_ms` / `utc_from_s` |
| How is a mower path built, and an empty or dot-segment id refused? | `api/_base.py::ApiGroup._mower_path` / `_require` |
| How does a decode failure become a message? | `models/common.py::describe_decode_error` (names the field, never the value; raised `from None` so no cause carries the body) |
| Where do base URLs come from? | `const.py` (env override for the fake server) |
| What is the public API? | `open_mammotion/__init__.py::__all__` |

## 4. Extension recipes

**A new endpoint in an existing group** — add the model to the right
`models/*.py`, add one method to the group, add the route to
`tests/fakeserver/routes/<group>.py`, add a section to `docs/api/<group>.md`,
add tests to `tests/unit/api/test_<group>.py` and `tests/unit/models/`.

**A new group (a new specification tag)** — new `api/<group>.py` subclassing
`ApiGroup`, a property on `OpenMammotion`, a new `docs/api/<group>.md`, a new
fake-server route module, new test modules. Nothing else changes.

**A new error code family** — if the API starts distinguishing error classes
by `code`, add a subclass of `ApiError` and map it in one place:
`transport/api.py::ApiTransport._raise_for_envelope`. Never match a raw code
at a call site.

**A new transport (SSE, LAN WebSocket)** — these are not `Requester`s. They get
their own package (`stream/`, `lan/`) with their own protocol, documented in
`architecture.md` before code exists. See `backlog.md`.

## 5. What the library does not do

- It does not log in with a username and password. There is no password grant
  in the Open API, and none will be added.
- It does not poll, schedule or keep tokens warm. Hosts call; the library
  refreshes when a call needs it.
- It does not know about Home Assistant. Host-specific concerns (config flow,
  entity mapping, persistence of `TokenSet`) belong to the host; the library
  offers `TokenSet.to_dict()` / `from_dict()` and an `on_token_updated`
  callback and stops there.
- It does not interpret mower state beyond what the specification defines.
  Enum names are the specification's names.
