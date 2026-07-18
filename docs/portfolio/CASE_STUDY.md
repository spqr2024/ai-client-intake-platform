# Case Study — AI Client Intake Platform

**A multi-tenant SaaS that replaces contact forms with an AI agent that
qualifies leads 24/7.**

`FastAPI` · `Next.js 15` · `PostgreSQL` · `Redis` · `Docker` · `Telegram Bot API`
· `OpenAI / Anthropic / Gemini / OpenRouter`

> **Scope note:** this is a self-directed product build, not client work. Every
> number below is measured from the repository (test counts, coverage, response
> sizes, query counts) — none are customer outcomes, because it has not yet run
> a customer's traffic. Industry figures are cited as external research.

---

## The problem

Static contact forms are where inbound revenue quietly dies. Multi-step forms are
reported to see **abandonment above 67%**, and the ones that *are* completed
arrive as three fields and a vague sentence. Someone then spends a week emailing
back and forth to discover budget, timeline and scope — the qualification that
should have happened at first contact.

The interesting constraint: a conversation captures far more than a form, but
handing lead qualification to an LLM introduces problems a business cannot
accept — non-reproducible results, prompt injection, and total dependence on a
third-party API's uptime and pricing.

**The design question was therefore not "how do I add AI?" but "how much of this
is the AI allowed to decide?"**

---

## The core decision: a deterministic core with AI at the edges

Intake is driven by a **JSON-defined state machine**, not by a prompt. Each step
declares the field it captures, its answer type (`text`, `choice`, `number`,
`email`, `phone`), its branching rules, and what comes next. The LLM does three
things, each with a working fallback:

| Job | Fallback when no provider is configured |
|---|---|
| Rephrase the next question naturally | The template prompt, verbatim |
| Write the lead summary | A deterministic structured template |
| Compress long conversations | Extractive summary of captured answers |

This produces four properties that matter commercially:

1. **Reproducible.** The same answers always yield the same lead and score — a
   requirement once qualification drives who gets called back.
2. **Injection-resistant.** No prompt can make the bot skip a qualification step,
   because progression is not a prompt decision (OWASP LLM01).
3. **Outage-tolerant.** If OpenAI is down, intake continues; only phrasing gets
   plainer.
4. **Testable.** 136 tests run with **zero API keys and no network**, so CI is
   deterministic and free.

The trade-off is honest: the bot is less conversationally fluid than a pure-LLM
agent. For lead capture, predictability is worth more than eloquence.

---

## Architecture

```
Visitor ─ chat widget ─┐
                       ├─► Next.js 15 ──REST + SSE──► FastAPI ──► PostgreSQL
Manager ─ dashboard ───┘                                │
                                                        ├──► Redis (optional)
                                                        │     cache · queue · rate limits
                                                        ├──► Telegram / Email (retrying queue)
                                                        └──► LLM + Embedding providers
```

A **modular monolith**, deliberately. At this size, service boundaries would buy
deployment independence nobody needs and cost transactional integrity that
matters a lot. The seams are enforced in code instead: `core` never imports
`services`, `services` never imports `api` — verified, not aspirational.

**Every external dependency sits behind an interface with an offline fallback:**
`LLMProvider`, `EmbeddingProvider`, `VectorStore`, `EmailProvider`, `CacheBackend`,
the task queue, and the notification/CRM registries. That single rule is what
makes the product runnable with zero configuration *and* deployable against
managed infrastructure — the same code path, different config.

### Multi-tenancy

Every domain table carries `workspace_id`; every authenticated query filters by
the caller's workspace. Cross-tenant access returns **404, not 403** — a 403
confirms the record exists, which is itself a leak. Isolation has dedicated tests
covering leads, settings, users and attachments.

### Reliability of side effects

Notifications and CRM exports never run inline. Each writes a delivery-log row,
then enqueues a task; the worker retries with exponential backoff and records
attempts and errors. A Telegram outage delays a notification instead of losing it
— and staff can see exactly what failed and why.

---

## Engineering decisions worth defending

**Contracts are append-only.** When pagination was added, the first attempt
changed `GET /api/leads` from an array to an envelope. That broke an existing
test, so it was reverted in favour of an `X-Total-Count` header — the standard,
non-breaking answer. Convenient refactors are not worth breaking consumers.

**The extension points are registries.** Adding a CRM is one class plus one
`register_provider(...)` call. When a test proved a *new* adapter's options
couldn't be saved — the settings whitelist was static while the registry was
dynamic — the fix was prefix-based dynamic keys, so the coupling is gone rather
than papered over.

**Retrieval is hybrid on purpose.** Semantic similarity over chunk embeddings
(70%) blended with lexical coverage (30%). Embeddings smear exact tokens like
prices and product names; lexical scoring is the safety net. If embeddings are
unavailable, lexical alone still answers.

**Observability is vendor-neutral.** A ~120-line metrics registry renders
Prometheus text exposition with no dependency, and `report_error` is a one-line
seam for Sentry. The application never imports a monitoring vendor.

---

## Problems found and fixed during self-audit

The audits that mattered found real defects, not style issues:

| Defect | Why it was serious | Fix |
|---|---|---|
| **Structured logs were invalid JSON** — the format string interpolated messages inside quotes, so any message containing `"` (every HTTP access log) broke parsing | Log aggregation would have silently dropped production logs. The "structured logging" claim was false | Real `JsonFormatter`, reproduced the failure in a regression test first |
| **Delayed retries could be garbage-collected** — `asyncio.create_task` without a saved reference | Retry is the reliability guarantee for every notification | Strong references held until completion |
| **Uploaded files were unreachable** — stored and listed, but no download route | A manager saw `mockup.pdf` and couldn't open it | Authenticated, workspace-scoped endpoint with content-type allow-listing |
| **SQLite silently ignored foreign keys** | The ORM's `ON DELETE` rules were inert on the default dev database — declared integrity that wasn't enforced | Explicit `CASCADE`/`SET NULL` plus the `foreign_keys` pragma at connect time |
| **Pagination disabled "Previous" on unaligned offsets** | Found by a test written during the audit, not by reading the code | Guard on the offset itself |

Two of these were caught **by tests written during the audit**. That is the
argument for the test suite existing at all.

---

## Results

Measured from the repository, not projected:

| Dimension | Result |
|---|---|
| **Tests** | 136 (112 backend, 24 frontend), **84% backend coverage**, 80% CI floor |
| **Determinism** | Entire suite runs with no API keys, no network, no database server |
| **API payloads** | Every dashboard endpoint under 4 KB on demo data |
| **Query efficiency** | Lead detail: 5 constant queries (N+1 eliminated via eager loading) |
| **Frontend** | 128 KB shared JS; strict TypeScript; zero lint warnings |
| **Time to a populated demo** | Two commands from a clean clone |
| **CI** | Lint, format, types, both test suites, dependency audit, Docker build with non-root assertion, migration idempotency, live smoke test |

---

## What I would do differently at 10× scale

Stated because knowing a design's limits is part of owning it:

- **Vector search** is brute-force cosine — comfortable to a few thousand chunks,
  linear beyond. The `VectorStore` interface exists precisely so pgvector drops
  in without touching retrieval callers.
- **Tag filtering** happens in Python because tags live in a portable JSON
  column. On Postgres, `jsonb` + a GIN index moves it into the query planner.
- **Migrations** use an in-house additive migrator: idempotent, CI-verified, and
  frictionless for demos. Regulated data deserves Alembic's reviewable,
  reversible history — the graduation path is documented, not hand-waved.
- **Secrets** live in workspace settings rows. Correct for self-hosting; a shared
  multi-tenant SaaS needs a secret manager.

None of these are surprises discovered late. Each is a documented trade-off with
an upgrade path, which is the difference between a limitation and a defect.

---

## Try it

```bash
git clone <repo-url> && cd ai-client-intake-platform
make setup && make demo      # API + a fully populated demo workspace
make frontend                # http://localhost:3000
```

The dashboard opens with 12 leads across the pipeline, full chat transcripts with
replay metadata, analytics, a knowledge base and notifications — no API keys, no
database server, no configuration.

**Further reading:** [Architecture](../ARCHITECTURE.md) ·
[API reference](../API.md) · [Security](../../SECURITY.md) ·
[Deployment](../DEPLOYMENT.md) · [Roadmap & limitations](../../ROADMAP.md)
