# Résumé Entry

Three lengths for different formats. Every metric is verifiable from the
repository — nothing here needs qualifying in an interview.

---

## Long form — for a projects section (one-column CV)

**AI Client Intake Platform** — Multi-tenant SaaS · *Self-directed* · 2026
`FastAPI · Next.js 15 · PostgreSQL · Redis · Docker · OpenAI/Anthropic/Gemini`

- Built a conversational AI platform that replaces contact forms with an agent
  that interviews prospects, scores leads 0–100 and delivers structured briefs to
  a kanban CRM, with Telegram notifications carrying one-tap actions.
- **Architected intake as a deterministic state machine with the LLM confined to
  phrasing and summarisation**, making qualification reproducible and
  prompt-injection-resistant, and keeping lead capture functional during provider
  outages; the full test suite consequently runs with no API keys.
- Designed every external dependency behind an interface with an offline
  fallback (LLM, embeddings, vector store, email, cache, queue, CRM adapters), so
  the product runs zero-config locally and against managed infrastructure in
  production from the same code path.
- Implemented multi-tenant isolation returning 404 rather than 403 on
  cross-tenant access, rotating refresh tokens with replay detection, RBAC,
  audit logging, CSP and rate limiting with brute-force lockout.
- Delivered **136 automated tests at 84% backend coverage** behind a CI floor;
  the pipeline enforces lint, formatting, type checking, dependency
  vulnerability audits, non-root container verification, migration idempotency
  and a live end-to-end smoke test.
- Eliminated N+1 queries via eager loading (lead detail: 5 constant queries) and
  converted analytics from full-table scans to SQL aggregates; all dashboard
  endpoints return under 4 KB.
- Authored architecture, API, deployment, troubleshooting and disaster-recovery
  documentation, including an explicit known-limitations register with
  remediation paths.

---

## Medium form — for a two-column or one-page CV

**AI Client Intake Platform** — Multi-tenant SaaS (self-directed), 2026
*FastAPI · Next.js 15 · PostgreSQL · Redis · Docker · LLM APIs*

- Conversational AI platform replacing contact forms: interviews visitors,
  scores leads, syncs to a kanban CRM and Telegram.
- Kept intake deterministic (state machine) with the LLM only rephrasing and
  summarising — reproducible, injection-resistant, and functional during AI
  provider outages.
- Multi-tenant isolation, rotating refresh tokens, RBAC, audit logging, CSP.
- 136 tests at 84% coverage; CI runs lint, types, dependency audits, Docker
  builds and an end-to-end smoke test.

---

## Short form — one or two lines

> **AI Client Intake Platform** (FastAPI, Next.js, PostgreSQL, Docker) —
> multi-tenant SaaS where an AI agent qualifies and scores inbound leads into a
> kanban CRM with Telegram alerts. Deterministic intake core with LLM fallbacks;
> 136 tests, 84% coverage, full CI/CD.

---

## Interview talking points

Prepared answers for the questions this project invites. Keep them concrete.

**"Walk me through a technical decision you'd defend."**
Intake runs on a state machine, not a prompt. Handing qualification to an LLM
gives you non-reproducible results, prompt-injection exposure and a hard
dependency on a third party's uptime. I confined the LLM to rephrasing questions,
writing summaries and compressing context — each with a working fallback. The
cost is a less fluid conversation; the benefit is that the same answers always
produce the same lead, no prompt can skip a qualification step, and capture
survives an outage. It also made the test suite deterministic and free to run.

**"Tell me about a bug you're glad you found."**
My structured JSON logs were invalid JSON. The format string interpolated the
message inside quotes, so any message containing a double quote — every HTTP
access log — broke parsing. In production a log aggregator would have silently
dropped them and I'd have been debugging blind while believing I had
observability. I reproduced it in a failing test first, then replaced the
formatter. The lesson I took: verify the claims your system makes about itself.

**"How do you handle failure in distributed side effects?"**
Notifications and CRM exports never run inline. Each writes a delivery-log row,
then enqueues a task; the worker retries with exponential backoff and records
attempts and errors. A Telegram outage delays a notification instead of losing
it, and staff can see exactly what failed. Retries are strongly referenced —
I found a bug where `asyncio.create_task` results were garbage-collectible,
which silently weakened the guarantee.

**"How would this scale?"**
API instances are stateless — conversation state lives in the database — so it
scales horizontally behind a load balancer with Redis making rate limits, caches
and the queue cluster-wide. The honest ceilings are brute-force vector search
(fine to a few thousand chunks) and Python-side tag filtering; both sit behind
interfaces so pgvector and a `jsonb` GIN index drop in without touching callers.

**"What would you do differently?"**
Alembic from the start. My additive migrator is idempotent and CI-verified, and
it made the demo experience frictionless — but reviewable, reversible migrations
matter more once real customer data is involved. I documented the graduation path
rather than pretending the trade-off doesn't exist.

**"What are you least happy with?"**
No browser end-to-end tests and no load testing. The unit and integration layers
are thorough, but my performance claims are reasoned from query counts and
payload sizes rather than measured under concurrency. It's the first thing I'd
add, and it's at the top of the roadmap rather than hidden.

---

## Cover-letter paragraph

> I recently built a multi-tenant AI intake SaaS — an agent that interviews
> website visitors, qualifies and scores leads, and delivers structured briefs to
> a kanban CRM and Telegram. The decision I'd highlight is that I kept
> qualification logic deterministic and used the LLM only for phrasing and
> summaries, so results are reproducible, the flow can't be prompt-injected, and
> lead capture keeps working when the AI provider doesn't. It ships with 136
> tests, CI that audits dependencies and verifies containers run as non-root, and
> documentation that states its limitations rather than hiding them.
