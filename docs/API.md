# API Reference

Interactive, always-current documentation is generated from the code at
**`/docs`** (Swagger UI) and **`/openapi.json`**. This file covers what the
generated schema cannot: authentication flow, conventions, and worked examples.

**Base URL:** `http://localhost:8000` in development.
**Content type:** `application/json` unless stated otherwise.

---

## Conventions

| Aspect | Rule |
|---|---|
| **Auth** | `Authorization: Bearer <access_token>` on every 🔒 endpoint |
| **Roles** | 🔒 = any authenticated user · 👑 = `admin` only |
| **Tenancy** | Every response is scoped to the caller's workspace. A record in another workspace returns **404, not 403** — existence is never leaked |
| **Errors** | `{"detail": "Human-readable message"}` with a conventional status code |
| **Correlation** | Every response carries `X-Request-ID`; the same id appears in structured logs |
| **Pagination** | `limit` + `offset` query params; total row count in the `X-Total-Count` header. Response bodies stay plain arrays (contracts are append-only) |
| **Rate limits** | Public endpoints are limited per IP; exceeding returns **429** |

---

## Authentication

Access tokens are short-lived (30 min); refresh tokens are opaque, hashed at
rest, and **rotate on every use** — presenting a rotated token fails, which
detects replay.

```
POST /api/auth/login → access + refresh
        │
        ├─ access token expires (401)
        │       └─ POST /api/auth/refresh → NEW access + NEW refresh
        │                                    (old refresh now invalid)
        └─ POST /api/auth/logout → refresh revoked server-side
```

### `POST /api/auth/login`

```bash
curl -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"admin12345"}'
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "b7Qk9vXm2...",
  "token_type": "bearer"
}
```

Five failed attempts for the same email + IP trigger a 15-minute lockout (429).

### `POST /api/auth/refresh`

Body `{"refresh_token": "..."}` → a new pair. The presented token is revoked
immediately, so clients must store the new one.

### `POST /api/auth/logout` 🔒 · `GET /api/auth/me` 🔒

Logout revokes the supplied refresh token server-side (204). `me` returns the
current user including `workspace_id`.

---

## Public chat (no authentication)

These power the embeddable widget and are the only write endpoints open to
anonymous visitors.

### `POST /api/chat/start`

```bash
curl -X POST localhost:8000/api/chat/start \
  -H 'Content-Type: application/json' \
  -d '{"client_name":"Alice","email":"alice@example.com","workspace":"default"}'
```

```json
{
  "conversation_id": "9f608936f11f494f9251a4eec077e2b1",
  "bot_message": "Nice to meet you! What service are you interested in?",
  "quick_replies": ["Website", "Online store", "Mobile app", "Branding / Design", "Other"]
}
```

Supplying `client_name`/`email` pre-fills those answers and the flow skips
asking for them. `workspace` is a slug and selects the tenant (branding, flow,
knowledge base).

### `POST /api/chat/{conversation_id}/msg`

```bash
curl -X POST localhost:8000/api/chat/abc123/msg \
  -H 'Content-Type: application/json' -d '{"text":"Online store"}'
```

```json
{
  "bot_message": "Great choice! Do you have a platform in mind for the store?",
  "quick_replies": ["Shopify", "WooCommerce", "Custom build", "Not sure yet"],
  "done": false,
  "lead_id": null,
  "summary": null
}
```

When the flow completes, `done` is `true` and `lead_id` / `summary` are
populated. A finished conversation returns **409** on further messages.

Off-script questions are answered from the knowledge base and the flow then
re-asks its pending question. Messages matching a human-handoff phrase
("talk to a person") finalize the lead immediately and flag it.

### `GET /api/chat/{conversation_id}/stream?text=...`

Same processing, streamed as Server-Sent Events:

```
event: delta
data: {"delta": "When would you like "}

event: delta
data: {"delta": "the project completed by?"}

event: meta
data: {"quick_replies": ["ASAP", "Within 1 month"], "done": false, "lead_id": null}
```

Consume `delta` events for incremental rendering; `meta` arrives once at the end.

### `POST /api/chat/{conversation_id}/upload`

`multipart/form-data` with a `file` field. Extension allow-list, 10 MB cap.
Returns the attachment record (201).

### `GET /api/chat/attachments/{id}` 🔒

Staff-only, workspace-scoped download. Visitor uploads are never publicly
addressable. Served with `nosniff` and an `attachment` disposition unless the
type is explicitly inline-safe.

### `GET /api/public/branding?workspace=default`

Unauthenticated white-label lookup used by the widget and landing page.

```json
{
  "company_name": "Northwind Studio",
  "bot_name": "Nora — Intake Assistant",
  "logo_url": "",
  "primary_color": "#4f46e5",
  "hero_title": "Turn website visitors into qualified projects — automatically",
  "hero_subtitle": "Nora interviews every prospect 24/7…"
}
```

---

## CRM

### `GET /api/leads` 🔒

Query params: `status`, `priority`, `tag`, `search` (matches project, client,
email, service and summary), `limit` (default 50, max 500), `offset`.

```bash
curl -D - "localhost:8000/api/leads?status=Qualified&limit=25" \
  -H "Authorization: Bearer $TOKEN"
```

```
X-Total-Count: 12
```
```json
[{
  "id": 12, "project_name": "Online store — Lena Fischer",
  "client_name": "Lena Fischer", "service": "Online store",
  "budget": 9500.0, "timeline": "ASAP", "status": "New",
  "priority": "High", "tags": ["ecommerce", "demo"],
  "follow_up_at": "2026-07-19T09:00:00Z", "score": 88,
  "created_at": "2026-07-18T12:40:35Z"
}]
```

### `GET /api/leads/pipeline` 🔒

Kanban payload: workspace stage order plus leads grouped by status.

```json
{
  "statuses": ["New", "Qualified", "In Progress", "Converted", "Rejected", "Closed", "Incomplete"],
  "columns": { "New": [ /* LeadListItem[] */ ], "Qualified": [] }
}
```

### `GET /api/leads/{id}` 🔒

Full record: contact details, AI summary, full transcript, attachments and the
activity timeline.

### `PATCH /api/leads/{id}` 🔒

Any subset of:

```json
{
  "status": "Qualified",
  "priority": "Urgent",
  "assigned_to_id": 2,
  "tags": ["vip", "enterprise"],
  "follow_up_at": "2026-08-01T09:00:00Z",
  "clear_follow_up": false,
  "project_name": "Renamed project",
  "score": 90
}
```

`status` is validated against the **workspace's configured pipeline**, so custom
stages work; an unknown stage returns 422 listing the valid ones. Status changes
emit notifications and are recorded in both the activity timeline and the audit log.

### `POST /api/leads/{id}/notes` 🔒

`{"text": "Called — sending a proposal Monday", "kind": "comment"}` (`note` or
`comment`), appended to the timeline (201).

### `GET /api/leads/{id}/replay` 🔒

Messages, attachments and CRM events merged onto one chronological timeline with
replay metadata:

```json
{
  "conversation_id": "825007b2…", "started_at": "…", "ended_at": "…",
  "language": "en",
  "events": [{
    "at": "2026-07-18T12:40:33Z", "type": "message", "sender": "bot",
    "text": "What's your approximate budget?",
    "meta": {"node": "budget", "event": "question"}
  }]
}
```

`meta.node` is the workflow step, `meta.event` the kind (`greeting`, `question`,
`clarification`, `kb_answer`, `summary`, `human_handoff`); `kb_answer` events
also carry `kb_article_id` and `kb_score`.

---

## Knowledge base

| Endpoint | Method | Notes |
|---|---|---|
| `/api/kb` | GET 🔒 / POST 👑 | List or create an article |
| `/api/kb/upload` | POST 👑 | `multipart/form-data`; PDF, DOCX, MD, TXT |
| `/api/kb/search?q=` | GET 🔒 | Hybrid semantic + lexical retrieval |
| `/api/kb/stats` | GET 🔒 | Hit rate, index status counts, unanswered queries |
| `/api/kb/formats` | GET 🔒 | Which formats this deployment can extract |
| `/api/kb/{id}` | PUT 👑 / DELETE 👑 | Editing snapshots the previous version |
| `/api/kb/{id}/versions` | GET 🔒 | Version history |
| `/api/kb/{id}/versions/{v}/restore` | POST 👑 | Rollback, recorded as a new version |
| `/api/kb/{id}/reindex` · `/api/kb/reindex` | POST 👑 | Re-embed one article or all |

Uploads return the created article including indexing outcome:

```json
{
  "id": 6, "title": "Refund policy", "source_type": "pdf",
  "source_filename": "refund-policy.pdf", "version": 1,
  "index_status": "indexed", "chunk_count": 4,
  "doc_metadata": {"pages": 2, "bytes": 51244, "characters": 3180},
  "hit_count": 0
}
```

`index_status` is `pending` → `indexing` → `indexed` | `failed` (with
`index_error`) | `stale`. Failures never raise: lexical retrieval keeps working
and the dashboard surfaces exactly which documents need attention.

> Vectors are keyed by `(provider, model)`. After switching embedding providers,
> run **reindex** — old vectors are ignored by design rather than silently mixed.

---

## Workflows 👑

| Endpoint | Purpose |
|---|---|
| `GET /api/workflows` · `POST` · `PUT /{id}` · `DELETE /{id}` | CRUD; the default flow cannot be deleted |
| `GET /api/workflows/templates` | Five industry starters + the reusable step library |
| `POST /api/workflows/analyze` | Structural report: unreachable steps, loops, dead ends |
| `POST /api/workflows/simulate` | Dry-run a flow against scripted answers |

**Simulate** — test a flow before publishing, with no database or AI involved:

```bash
curl -X POST localhost:8000/api/workflows/simulate -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"definition": {...}, "answers": ["Alice","Online store","$5000"]}'
```

```json
{
  "transcript": [{"sender": "bot", "text": "May I have your name?", "node": "name"}],
  "collected": {"client_name": "Alice", "service": "Online store", "budget": 5000},
  "done": false
}
```

**Analyze** returns warnings rather than errors — an unreachable step is
work-in-progress, not a broken flow, so it never blocks saving:

```json
{
  "reachable": ["name", "service"], "unreachable": ["orphan"],
  "terminal_nodes": ["service"], "has_cycle": false,
  "warnings": ["1 step(s) can never be reached: orphan"]
}
```

### Workflow definition shape

```json
{
  "start": "name",
  "nodes": {
    "name": {
      "field": "client_name",
      "type": "text",
      "skip_if_known": true,
      "prompt": {"en": "May I have your name?", "uk": "Як вас звати?"},
      "next": "service"
    },
    "service": {
      "field": "service",
      "type": "choice",
      "prompt": {"en": "What service are you interested in?"},
      "options": {"en": ["Website", "Online store"]},
      "branches": [{"if_contains": ["store", "shop"], "goto": "platform"}],
      "next": "budget"
    }
  }
}
```

`type` is `text` | `choice` | `number` | `email` | `phone` and drives validation
and re-asking. An empty `next` ends the flow and creates the lead.

---

## Prompts 👑

`GET /api/prompts` · `POST /api/prompts` (creates a new version) ·
`POST /api/prompts/{id}/activate` · `/deactivate` · `POST /api/prompts/test`.

**Rollback is activation of an older version** — history is never rewritten.
`test` dry-runs a prompt against the configured provider and returns a
deterministic preview in mock mode, so the button works offline.

---

## Analytics 🔒

- `GET /api/analytics/summary?days=30` — conversations, leads, completion and
  conversion rates, average budget and score, per-day series, status/service breakdowns.
- `GET /api/analytics/ai` — funnel, drop-off by workflow node, average messages
  and duration, abandonment rate, lead-quality bands, AI capture confidence,
  most common client questions.

Both are cached for 60 seconds (cluster-wide when Redis is configured).

---

## CRM export

`GET /api/crm/providers` 🔒 lists registered adapters and the extra settings each
needs. `GET /api/crm/syncs` 🔒 returns the delivery log.
`POST /api/crm/leads/{id}/export` 👑 queues an export (202).

Exports run through the retrying task queue; each attempt updates a
`CRMSyncLog` row with `status`, `attempts`, `external_id`/`external_url` and any
error. Configure the provider under **Settings → CRM Export**.

---

## Notifications 🔒

`GET /api/notifications` (add `unread_only=true`) · `POST /api/notifications/{id}/read`
· `POST /api/notifications/read-all` · `GET /api/notifications/deliveries`
(outbound email/Telegram log with status and attempt counts).

---

## Administration 👑

`GET/PUT /api/settings` — workspace runtime settings (branding, pipeline stages,
AI provider, notification templates, CRM config). Keys prefixed `crm_option_`
are accepted dynamically so new adapters need no settings-layer change.

`GET /api/settings/workspace` · `GET /api/audit` (filter by `action`, `actor`) ·
users CRUD with `PATCH /api/users/{id}/role` (revokes that user's sessions).

---

## Integrations & operations

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/webhook/telegram` | Secret token header | Inline-button callbacks and `/note` |
| `GET /health` | none | Aggregate check (backwards compatible) |
| `GET /health/live` | none | Liveness — dependency-free, for restart decisions |
| `GET /health/ready` | none | Readiness — probes DB and cache; **503** when not ready |
| `GET /metrics` | none | Prometheus text exposition |
| `GET /metrics/json` | none | Same registry, JSON |

Keep liveness and readiness distinct: a database blip should drain traffic, not
trigger a restart storm.

---

## Status codes

| Code | Meaning here |
|---|---|
| 200 / 201 / 202 / 204 | Success · created · queued · no content |
| 400 / 401 / 403 | Bad request · missing/expired token · wrong role |
| 404 | Not found **or** belongs to another workspace |
| 409 | Conflict (duplicate name, or a finished conversation) |
| 413 / 415 | File too large · unsupported file type |
| 422 | Validation failed (Pydantic, or an invalid pipeline status) |
| 429 | Rate limited or login lockout |
| 500 | Unhandled error — response includes `request_id` for log correlation |
