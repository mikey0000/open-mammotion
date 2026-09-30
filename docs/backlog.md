# Backlog

Open work only; finished items are deleted. Phases 1 and 2 of the original
plan are the current tree.

## Phase 3 — push channel

- `api/subscriptions.py`: `POST /v1/devices/subscriptions` (≤ 20 devices,
  10-minute validity, Luba 3 AWD only) and `POST /v1/mower/material/fetch`.
- `stream/sse.py`: one SSE connection per credential
  (`GET /developer-sse/api/client/sse`, headers `SSE-Client: developer`,
  `Accept: text/event-stream`). Handle `:: Connect to server successful ::`,
  `:: heartbeat ::`, and the kick-off `{"pushTag":"sc","pushType":"1"}` (close,
  do not reconnect). A re-subscribe task every 9 minutes while there are
  subscribers. Raw events first; typed property models once Q6 is answered.
- Fake server: an SSE route with scripted events and the kick-off control.

## Phase 4 — LAN WebSocket transport

Blocked on Q7. `lan/` package with its own protocol; the ticket and config
endpoints already exist in `api/local_network.py`.

## Library

- `tests/live/` tier with an opt-in smoke test (list devices, get one detail).
- Retry helper for `TransportError` with jittered backoff, opt-in per call,
  once real 429 behaviour is known (Q4).
- Typed `Accept-Language` (a `Literal` of the languages the portal lists) once
  Q11 is answered.
- A published wheel; release workflow tagging `v*`.

## Documentation

- `docs/api/subscriptions.md` and `docs/api/lan.md` once those phases start.
- A worked example under `examples/` that lists devices and starts a task by
  name, reading credentials from the environment.
