# Roadmap

## Shipped

**v1.0 — conversational intake**
Chat widget with SSE streaming, JSON workflow engine, multi-LLM provider layer,
mini-CRM, Telegram and email notifications, analytics, EN/UK i18n, Docker, CI.

**v2.0 — multi-tenant SaaS**
Workspaces with full data isolation and white-label branding, semantic knowledge
base (embedding-provider + vector-store abstractions), Redis-backed cache and
task queue with graceful fallbacks, notification center with delivery logs and
retries, prompt management with versioning and rollback, CRM v2 (kanban, tags,
priorities, follow-ups, custom pipelines, comments), AI analytics, AI memory,
conversation replay, rotating refresh tokens, audit log, security headers.

**v2.1 — production hardening**
Structured JSON logging with request-id correlation, split liveness/readiness
probes, Prometheus `/metrics` (no vendor coupling), pluggable error-reporting
seam, document knowledge base (PDF/DOCX/MD/TXT with chunking, versions, indexing
status, retrieval analytics), CRM export adapters (HubSpot, Pipedrive, Notion,
Salesforce, webhook), visual workflow builder with live validation and a
simulator, demo mode, responsive and accessible UI.

**v2.1.1 — independent audit**
Non-root containers, `.dockerignore`, Content-Security-Policy, foreign-key
integrity with SQLite pragma enforcement, dependency auditing in CI, coverage
gate, frontend test suite, `Makefile`/pre-commit developer tooling, SEO
metadata, disaster-recovery runbook.

## Next

Ordered by value to a paying customer, not by novelty.

### Near term
- [ ] **Alembic migration chain** — the additive migrator is idempotent and safe
      for demos and early production; regulated data deserves reviewable,
      reversible migrations. Graduation path documented in [DEPLOYMENT.md](docs/DEPLOYMENT.md#5-database-migrations).
- [ ] **Screenshots and GIF walkthroughs in the README** — capture guide ready at
      [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md).
- [ ] **Playwright end-to-end suite** — browser coverage of the chat → lead →
      kanban path. Unit and integration layers are done; this closes the pyramid.
- [ ] **Embeddable widget snippet** — a one-line `<script>` tag so customers can
      drop the chat onto an existing marketing site.

### Medium term
- [ ] **Managed secret storage** for provider API keys (currently per-workspace
      settings rows; correct for self-hosting, not for shared multi-tenant SaaS).
- [ ] **Workspace self-signup and onboarding** — today a workspace is created by
      an operator; self-serve needs email verification and abuse controls.
- [ ] **Slack and Discord notification senders** — registry slots already exist;
      each needs its own OAuth app.
- [ ] **pgvector `VectorStore`** with ANN search, for knowledge bases beyond a
      few thousand chunks. The interface is already the seam.
- [ ] **CSV / scheduled CRM export** alongside the existing push adapters.

### Longer term
- [ ] **Stripe billing** — plans, usage-based AI metering, invoices. The Settings
      tab is a placeholder today.
- [ ] **SSO (Google / Microsoft OAuth)** for the admin dashboard.
- [ ] **Per-workspace custom domains** with automatic TLS.
- [ ] **OpenTelemetry tracing** — the metrics registry and error seam are already
      vendor-neutral; tracing is the remaining pillar.
- [ ] **Load testing (Locust)** to replace reasoned performance claims with
      measured ones under concurrency.

## Known limitations

Honest constraints of the current build, and what each would take to lift.

| Limitation | Impact | Lift |
|---|---|---|
| Offline embedder matches morphology, not synonyms | "money back" won't retrieve a "refund" article until a real provider is configured | Set `EMBEDDING_PROVIDER` + key, then **Re-index all** |
| Brute-force vector search | Fine to ~thousands of chunks; linear beyond | Implement `VectorStore` against pgvector |
| Tag filtering happens in Python | JSON column is portable but not indexable | Postgres GIN index on a `jsonb` column |
| No browser E2E or load tests | Concurrency behaviour is reasoned, not measured | Playwright + Locust (above) |
| Provider keys in the database | Acceptable self-hosted; not ideal shared | Secret manager integration |
| Scanned PDFs are rejected | No OCR; the uploader says so explicitly | Tesseract or a vision API |
| Attachments on a local volume | Needs a backed-up volume | Swap two functions for S3-compatible storage |
