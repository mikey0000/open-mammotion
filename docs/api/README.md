# API reference

The Mammotion Open API as this library models it. The source of truth is the
captured OpenAPI documents in `docs/openapi/` (`authentication.json`,
`mower.json`); these pages restate them in the library's terms — Python
names, module locations, enums, and the gaps recorded in `open_questions.md`.

Conventions used on every page:

- **Wire name → Python name.** `deviceId` → `device_id`. The wire name is the
  `Alias` on the model field.
- **Envelope.** Every response is `{code, msg, msgTitle?, data, requestId?}`
  (`models/common.py::Envelope`). Success is `code in SUCCESS_CODES` (D8).
  Pages document `data` only.
- **Timestamps** are 13-digit milliseconds, stored as `*_ms: int` (D14).
- **Auth.** Every `api-open` call sends `Authorization: Bearer <access_token>`
  and `Accept-Language: <language>`.

| Page | Tag in spec | Module | Endpoints |
|---|---|---|---|
| [authentication](authentication.md) | OAuth2 | `auth/` | `POST /oauth2/token` |
| [devices](devices.md) | Mower information | `api/devices.py` | `GET /v1/mowers`, `GET /v1/mower/{deviceId}` |
| [actions](actions.md) | Mower action command | `api/actions.py` | `POST /v1/mower/action`, `GET /v1/mower/{deviceId}/work-params`, `GET /v1/mower/{deviceId}/plan` |
| [work_reports](work_reports.md) | Mower work report | `api/work_reports.py` | `POST /v1/mower/work-reports/summary`, `POST /v1/mower/work-reports/search`, `GET /v1/mower/{deviceId}/work-reports/{workId}` |
| [faults](faults.md) | Mower information | `api/faults.py` | `POST /v1/mower/error-codes/search` |
| [local_network](local_network.md) | HA local network, Mower action command | `api/local_network.py` | `POST /v1/ha/local-network/save`, `POST /v1/ha/local-network/query`, `POST /v1/mower/ws/ticket` |
| subscriptions (phase 3) | Mower information | `api/subscriptions.py` | `POST /v1/devices/subscriptions`, `POST /v1/mower/material/fetch`, SSE stream |

Base URLs: `https://api-open.mammotion.com` (API), `https://id.mammotion.com`
(tokens). Both overridable through the environment (D11).

Prerequisites from the portal: devices are bound to the account in the
Mammotion app; tasks are created there; only mower models released in 2025
are served (Q9).
