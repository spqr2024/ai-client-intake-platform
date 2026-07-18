# 🧭 AI Client Intake Platform

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](backend/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=nextdotjs)](frontend/)
[![Tests](https://img.shields.io/badge/tests-136_passing-brightgreen)](backend/tests/)
[![Coverage](https://img.shields.io/badge/coverage-84%25-brightgreen)](backend/tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A **multi-tenant SaaS platform** that replaces static contact forms with an intelligent
conversational interface. An AI agent interviews prospects 24/7, adapts its questions,
qualifies and scores every lead, and hands your team a structured summary — with a
built-in **kanban CRM**, **Telegram/email/in-app notifications**, **prompt management
with versioning**, **semantic knowledge-base retrieval**, **AI analytics** and full
**white-label branding** per workspace.

> Runs fully offline out of the box (deterministic mock AI, SQLite, in-memory cache) —
> and scales up to Postgres + Redis + your choice of OpenAI / Anthropic / Gemini /
> OpenRouter purely through configuration.

**`DEMO_MODE=true` (the default in `.env.example`) provisions a populated demo
workspace on first start** — 12 leads across the pipeline, full chat transcripts,
analytics, a knowledge base and notifications — so the dashboard looks alive the
moment you clone it.

## ✨ Features

| Module | Highlights |
|---|---|
| 💬 **AI Chat Widget** | SSE streaming, typing indicator, quick replies, file uploads, EN/UK auto-detection, white-label colors & bot name |
| 🔀 **Visual Workflow Builder** | Compose intake flows from step cards — question text per language, answer type, quick replies, branching rules, reordering — with live structural validation (unreachable steps, loops, dead ends), 5 industry templates, a step library and a dry-run simulator. JSON editing is an optional "Advanced" toggle, never a requirement |
| 🧠 **Prompt Management** | Versioned prompts, one-click activate / rollback, offline test bench, per-workflow assignment |
| 🤖 **Multi-AI Provider** | OpenAI, Anthropic, Gemini, OpenRouter or deterministic mock — switchable at runtime per workspace |
| 📚 **Document Knowledge Base** | Upload **PDF / DOCX / Markdown / TXT** (or type articles); paragraph-aware chunking; embedding-provider abstraction + pluggable vector store; hybrid semantic + lexical retrieval; per-document indexing status, version history with restore, metadata, and retrieval analytics including *questions the KB could not answer* |
| 🔗 **CRM Integrations** | Provider registry with **HubSpot, Pipedrive, Notion, Salesforce and generic-webhook** adapters; queue-backed export with retry and a per-lead sync log. Adding a CRM is one class + one `register_provider` call — no provider is referenced anywhere else |
| 📈 **Operations** | Separate liveness/readiness probes, Prometheus `/metrics` with zero vendor dependencies, request-id correlation across structured JSON logs, and a pluggable error-reporting seam (Sentry in ~3 lines) |
| 🧵 **AI Memory** | Short-term verbatim window + LLM-compressed rolling summary, token-budgeted, persisted per conversation |
| 📋 **CRM v2** | Kanban pipeline with drag & drop, custom stages per workspace, tags, priorities, follow-up reminders, internal comments, activity timeline, full-text search |
| ▶️ **Conversation Replay** | Step-by-step replay with timestamps, workflow-node metadata, KB-match scores, attachments and CRM events on one timeline |
| 🔔 **Notification Center** | In-app bell + email + Telegram behind one dispatch API; queue-backed retries with exponential backoff; per-message delivery log; Slack/Discord registry slots |
| 📱 **Telegram Bot** | New-lead alerts with ✅/❌/📞 inline actions, deep links into the CRM, status-change updates, `/note` command, secret-protected webhook |
| ✉️ **Email v2** | Provider abstraction (SMTP + console; extensible), branded HTML templates with plain-text alternative, delivery status tracking |
| 📊 **Analytics + AI Analytics** | KPIs, leads/day, conversion funnel, drop-off by workflow node, conversation length, lead quality bands, AI capture confidence, common client questions |
| 🏢 **Multi-Tenant Workspaces** | Isolated data per company: leads, KB, workflows, prompts, settings, branding, audit — 404-on-cross-tenant by construction |
| 🎨 **White Label** | Per-workspace company name, bot name, logo, primary color, landing texts, email branding |
| 🛡️ **Security** | Rotating refresh tokens, login lockout, RBAC + tenancy checks, audit log with actor/IP, security headers, sanitized inputs, rate limiting |
| ⚡ **Redis (optional)** | Cluster-wide rate limits, caches and task queue when `REDIS_URL` is set; transparent in-memory fallback when it isn't |

## 🏗 Architecture

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full picture (diagrams,
tenancy model, determinism rationale, retrieval & delivery pipelines, auth design).

```mermaid
flowchart LR
    V[Visitor] -->|chat widget| FE[Next.js 15]
    M[Manager] -->|dashboard| FE
    FE -->|REST + SSE| BE[FastAPI]
    BE --> DB[(Postgres / SQLite)]
    BE <--> RQ[(Redis · optional<br/>cache + queue)]
    BE -->|retry queue| TG[Telegram] & MAIL[Email]
    BE -->|abstractions| LLM[LLM + Embedding providers<br/>openai · anthropic · gemini · openrouter · mock]
```

Key design decisions:

- **Deterministic core** — the intake flow is a JSON state machine; LLMs only rephrase,
  summarize and compress. Zero API keys ⇒ fully working product, unflaky tests.
- **Everything behind an interface** — `LLMProvider`, `EmbeddingProvider`, `VectorStore`,
  `EmailProvider`, `CacheBackend`, task queue, notification channels. Each has an
  offline fallback and a production implementation.
- **Stateless API** — conversation state, memory and queues live in DB/Redis, so
  replicas scale horizontally.

## 🧱 Tech stack

| Layer | Choice | Why |
|---|---|---|
| **API** | FastAPI · Python 3.12 · SQLAlchemy 2 (typed ORM) · Pydantic v2 | Async-native, generates OpenAPI for free, typed models end to end |
| **Web** | Next.js 15 (App Router) · React 19 · TypeScript strict · Tailwind v4 | Server-rendered public page for SEO, client-side dashboard, one toolchain |
| **Data** | PostgreSQL (prod) · SQLite (dev, zero-config) | Same SQLAlchemy code path both ways; nothing to install to start |
| **Cache / queue** | Redis, optional | Cluster-wide rate limits and durable retries; degrades to in-process |
| **AI** | OpenAI · Anthropic · Gemini · OpenRouter · offline mock | Provider-agnostic behind one interface; the mock keeps tests deterministic |
| **Tests** | pytest + coverage gate · Vitest + Testing Library | 136 tests, no API keys or network required |
| **Quality** | Ruff (lint + format) · ESLint · tsc strict · pre-commit | Enforced in CI, not by convention |
| **Ops** | Docker (non-root, multi-stage) · Compose · GitHub Actions · Prometheus `/metrics` | Reproducible builds, dependency audits, image scanning in CI |

## 🚀 Quick start

### Docker (Postgres + Redis + backend + frontend)

```bash
git clone <repo-url> && cd ai-client-intake-platform
cp .env.example .env
docker compose up --build
```

### Installation — local dev (nothing beyond Python 3.12 + Node 22)

```bash
# Backend — http://localhost:8000 (Swagger at /docs)
cd backend
python -m venv .venv && .venv/Scripts/activate    # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.seed                                 # demo data
uvicorn app.main:app --reload

# Frontend — http://localhost:3000
cd frontend && npm install && npm run dev
```

Open **http://localhost:3000** (chat widget bottom-right).
Admin: **/admin** — `admin@example.com` / `admin12345`. Seeded manager: `manager@example.com` / `manager123`.

Existing databases upgrade automatically on first start (additive migrator,
no data loss).

With `make` available, every routine task has a shortcut — run `make help`:

```bash
make setup     # install backend + frontend dependencies
make demo      # API with a freshly provisioned demo workspace
make frontend  # web app in dev mode
make check     # everything CI runs: lint + types + all tests
make format    # ruff format + prettier
make docker-up # full stack: Postgres + Redis + API + web
```

## 🎭 Demo mode

`DEMO_MODE=true` (default in `.env.example`) provisions a complete, believable
workspace the first time the API starts against an empty database:

- **12 leads** spread across every pipeline stage, with realistic budgets,
  tags, priorities and follow-up reminders
- **Full chat transcripts** with replay metadata, including a Ukrainian
  conversation and four drop-offs so funnel/abandonment analytics are non-trivial
- **5 knowledge-base articles**, indexed at boot so the bot answers FAQs immediately
- **Branding, notifications and activity history** already populated

It is **idempotent** (re-running never duplicates) and **inert once real data
exists** (it only seeds a workspace with zero leads). Turn it off in production.

```bash
make demo                       # or: DEMO_MODE=true uvicorn app.main:app
# Admin dashboard → admin@example.com / admin12345
```

For a scripted, non-random dataset instead, use `make seed`.

### Enabling production integrations

| Integration | How |
|---|---|
| Real LLM | Set the provider key in `.env`, pick provider/model in **Settings → AI** |
| Semantic embeddings | `EMBEDDING_PROVIDER=openai` (or gemini/openrouter) + key, then **KB → Reindex** |
| Redis | `REDIS_URL=redis://…` — rate limits, caches and the delivery queue go cluster-wide |
| Telegram | Bot token in `.env`, chat ID in **Settings → Notifications**, register webhook: `https://api.telegram.org/bot<token>/setWebhook?url=https://<host>/api/webhook/telegram&secret_token=<TELEGRAM_WEBHOOK_SECRET>` |
| Email | `SMTP_*` in `.env` — branded HTML + plain-text alternative |

## 📡 API overview

Interactive OpenAPI docs at `/docs`. Highlights (🔒 = JWT, 👑 = admin):

| Area | Endpoints |
|---|---|
| Public | `POST /api/chat/start` · `POST /api/chat/{id}/msg` · `GET /api/chat/{id}/stream` (SSE) · `POST /api/chat/{id}/upload` · `GET /api/public/branding` |
| Operations | `GET /health` · `GET /health/live` · `GET /health/ready` · `GET /metrics` (Prometheus) · `GET /metrics/json` |
| KB documents 👑 | `POST /api/kb/upload` (PDF/DOCX/MD/TXT) · `GET /api/kb/stats` · `GET /api/kb/{id}/versions` · `POST /api/kb/{id}/versions/{v}/restore` · `POST /api/kb/{id}/reindex` |
| Workflow builder 👑 | `GET /api/workflows/templates` · `POST /api/workflows/analyze` · `POST /api/workflows/simulate` |
| CRM export | `GET /api/crm/providers` · `GET /api/crm/syncs` 🔒 · `POST /api/crm/leads/{id}/export` 👑 |
| Auth | `POST /api/auth/login` · `POST /api/auth/refresh` (rotating) · `POST /api/auth/logout` · `GET /api/auth/me` |
| CRM 🔒 | `GET /api/leads` (status/priority/tag/search filters) · `GET /api/leads/pipeline` (kanban) · `GET/PATCH /api/leads/{id}` · `POST /api/leads/{id}/notes` · `GET /api/leads/{id}/replay` |
| Prompts 👑 | `GET/POST /api/prompts` · `POST /api/prompts/{id}/activate|deactivate` · `POST /api/prompts/test` |
| KB | `GET/POST/PUT/DELETE /api/kb` 👑 · `GET /api/kb/search` 🔒 · `POST /api/kb/reindex` 👑 |
| Notifications 🔒 | `GET /api/notifications` · `POST /api/notifications/{id}/read` · `read-all` · `GET /api/notifications/deliveries` |
| Analytics 🔒 | `GET /api/analytics/summary` · `GET /api/analytics/ai` |
| Admin 👑 | `GET/PUT /api/settings` · `GET /api/audit` · users CRUD + role changes · workflows CRUD |
| Integrations | `POST /api/webhook/telegram` (secret-token protected) · `GET /health` |

## 🧪 Testing & quality

```bash
cd backend && ruff check app tests && pytest --cov=app   # 112 tests, 84% coverage
cd frontend && npm run lint && npm run build
```

- The suite runs with **zero API keys and zero external services** — mock LLM,
  hashing embeddings, console email, in-memory cache/queue.
- Coverage spans: workflow engine, chat E2E (EN+UK), tenancy isolation, refresh-token
  rotation/replay, prompts versioning/rollback, kanban/custom statuses/tags, replay
  timeline, notification center + delivery logs, queue retry, semantic KB, memory
  compression, audit trail, Telegram webhook.

## 📁 Project structure

```
backend/app/
  api/          # routers: auth, chat, leads, prompts, notifications, audit, kb, …
  core/         # config, security (JWT+refresh), cache, queue, rate limiting
  services/     # chat, workflow engine, llm, embeddings, vectorstore, kb, memory,
                # notifications, telegram, email, prompts, audit, analytics, scoring
  db_migrate.py # additive auto-migrator (v1 → v2 data-preserving)
frontend/app/   # landing + /admin (kanban CRM, analytics, prompts, audit, settings…)
docs/           # ARCHITECTURE.md
```

## 📸 Screenshots

> **Status:** this repository was built in a headless environment with no
> browser automation, so the images are captured locally rather than committed
> pre-baked — which also guarantees they always match your checkout.
> **[docs/SCREENSHOTS.md](docs/SCREENSHOTS.md)** specifies every route, state,
> viewport and filename, plus a copy-paste checklist. Two commands and about
> fifteen minutes produce the full set.

```bash
make demo        # API on :8000 with a fully populated demo workspace
make frontend    # web app on :3000  →  admin@example.com / admin12345
```

**The views worth capturing** — each one proves a different claim:

| View | Route | What it demonstrates |
|---|---|---|
| Conversational intake | `/` | Adaptive questions, quick replies, SSE streaming |
| Kanban pipeline | `/admin` → Kanban | A real CRM board, not a lead list |
| Lead detail | `/admin/leads/1` | AI summary feeding a workable record |
| Conversation replay | `/admin/leads/1` → Replay | Step-by-step playback with workflow-node metadata |
| AI analytics | `/admin/analytics` | Funnel, drop-off by node, capture confidence |
| Visual workflow builder | `/admin/workflows` | Non-engineers editing the bot, with live validation |
| Knowledge base | `/admin/kb` | Document ingestion with real indexing status |
| Integrations | `/admin/settings` → Integrations | CRM adapters and the delivery log |
| Mobile dashboard | `/admin` @ 393×852 | Genuine responsive layout, not a squeezed table |

Four short GIF walkthroughs are scripted in the same guide: visitor → qualified
lead, kanban management, editing the bot without code, and teaching the bot from
an uploaded PDF.

## ❓ FAQ

<details>
<summary><b>Do I need an OpenAI key to run this?</b></summary>

No. The default `mock` provider is a deterministic offline implementation, and
the whole test suite runs without a single API key. Intake logic is a state
machine, so the product is fully functional offline — an LLM only rephrases
questions, writes summaries and compresses memory. Add a key when you want
those touches.
</details>

<details>
<summary><b>Why is the conversation a state machine instead of "just an LLM"?</b></summary>

Three reasons that matter commercially: lead capture stays **reproducible**
(the same answers always produce the same lead), it cannot be **prompt-injected**
into skipping qualification steps, and the product **still works** when a
provider has an outage. LLMs improve the phrasing; they are not load-bearing.
</details>

<details>
<summary><b>Is it really multi-tenant?</b></summary>

Yes. `workspace_id` is on every domain table, every authenticated query filters
by the caller's workspace, and cross-tenant access returns **404 rather than
403** so record existence is never leaked. There are dedicated isolation tests.
</details>

<details>
<summary><b>Do I need Redis?</b></summary>

Only for multi-replica deployments. Without `REDIS_URL` the cache, rate limiter
and task queue run in-process with identical semantics; set it and they become
cluster-wide. Nothing in the application imports Redis directly.
</details>

<details>
<summary><b>How do I add a CRM, an AI provider or a notification channel?</b></summary>

Each is a registry: write one class and register it. A new CRM is a
`CRMProvider` subclass plus `register_provider(...)` — no existing file changes,
including the settings layer, which accepts a provider's option keys
dynamically. Same pattern for embeddings, email and notification channels.
</details>

<details>
<summary><b>Why isn't the knowledge base finding an obviously related document?</b></summary>

The default offline embedder is a feature-hasher: it matches morphological
variants ("refund"/"refunds"), not synonyms ("money back"). Set a real
`EMBEDDING_PROVIDER` and run **Re-index all** for true semantic recall. The
retrieval pipeline is identical either way. The KB dashboard also lists
**questions it could not answer** — each is a document you're missing.
</details>

<details>
<summary><b>Can this be deployed for a paying customer today?</b></summary>

Yes — see [DEPLOYMENT.md](docs/DEPLOYMENT.md), which starts with a pre-flight
checklist (rotate `JWT_SECRET`, disable demo mode, managed Postgres, TLS).
Containers run as non-root, readiness and liveness are separate probes, and
migrations are additive and idempotent. The known gaps are listed honestly in
[ROADMAP.md](ROADMAP.md).
</details>

<details>
<summary><b>Why an in-house migrator instead of Alembic?</b></summary>

Deliberate trade-off for this stage: the additive migrator makes clone-and-run
frictionless and is idempotent (CI verifies it across repeated runs). It never
drops a column older code reads, so image rollbacks stay safe. DEPLOYMENT.md
documents exactly how to graduate to Alembic when schema changes get riskier.
</details>

## ⚠️ Known limitations

Stated plainly, because a repository that hides its edges is harder to trust
than one that names them. Full table with remediation paths in
**[ROADMAP.md](ROADMAP.md#known-limitations)**.

| Limitation | What it means in practice |
|---|---|
| Offline embedder matches morphology, not synonyms | Out of the box, "money back" won't retrieve a "refund" article. Set `EMBEDDING_PROVIDER` + key and **Re-index all** for true semantic recall |
| Brute-force vector search | Comfortable to a few thousand chunks; linear beyond. `VectorStore` is the seam for pgvector |
| Tag filtering runs in Python | The JSON column is portable but not indexable; a Postgres `jsonb` + GIN index is the upgrade |
| No browser E2E or load tests | Unit and integration layers are thorough; concurrency behaviour is reasoned, not measured |
| Provider API keys live in workspace settings | Fine self-hosted; a shared SaaS should move them to a secret manager |
| Scanned PDFs are rejected | No OCR — the uploader says so explicitly rather than indexing an empty document |
| In-house additive migrator, not Alembic | Idempotent and CI-verified; [DEPLOYMENT.md](docs/DEPLOYMENT.md#5-database-migrations) documents the graduation path |

## 📚 More docs

**Engineering**
[Architecture](docs/ARCHITECTURE.md) · [API reference](docs/API.md) ·
[Security](SECURITY.md) · [Deployment](docs/DEPLOYMENT.md) ·
[Troubleshooting](docs/TROUBLESHOOTING.md) · [Disaster recovery](docs/DISASTER_RECOVERY.md)

**Project**
[Contributing](CONTRIBUTING.md) · [Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md) ·
[Releasing](docs/RELEASING.md)

**Presentation**
[Case study](docs/portfolio/CASE_STUDY.md) · [Brand & visual identity](docs/BRAND.md) ·
[Screenshot capture guide](docs/SCREENSHOTS.md)

## 📄 License

[MIT](LICENSE)
