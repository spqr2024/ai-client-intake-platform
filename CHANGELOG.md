# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

## [2.1.0] — 2026-07-18

Production-readiness audit. No features were removed; all existing API
contracts are unchanged.

### Fixed
- **Structured logs were invalid JSON.** The format string interpolated the message inside quotes, so any message containing `"` (every httpx access log) produced unparseable output. Replaced with a real `JsonFormatter`; log aggregation now works.
- **Delayed queue retries could be dropped.** `asyncio.create_task` was called without keeping a reference, so the GC could collect a pending retry. Retries are now strongly referenced until completion.
- **Uploaded attachments were unreachable.** Files were stored and listed but had no download route; added an authenticated, workspace-scoped endpoint with a content-type allow-list and `nosniff`.
- **New CRM adapters could not store their options.** The settings whitelist was static while the provider registry is dynamic; added prefix-based dynamic keys so a new adapter's `option_keys` persist without touching the settings module.

### Added
- **Visual workflow builder**: step cards (question per language, answer type, quick replies, branching, reorder), live structural validation (unreachable steps, loops, dead ends, missing prompts), 5 industry templates, a reusable step library, and a dry-run simulator. JSON editing is now optional.
- **Document knowledge base**: PDF/DOCX/Markdown/TXT ingestion with graceful degradation when optional extractors are absent, paragraph-aware chunking with overlap, chunk-level embeddings, per-document indexing status, version history with restore, metadata, and retrieval analytics (hit rate, top documents, unanswered questions).
- **CRM integration layer**: `CRMProvider` registry with HubSpot, Pipedrive, Notion, Salesforce and generic-webhook adapters; queue-backed export with retry and a per-lead sync log; manual export endpoint.
- **Demo mode** (`DEMO_MODE`): auto-provisions a populated workspace — 12 leads across the pipeline, transcripts with replay metadata, drop-off conversations, KB articles (indexed at boot), branding and notifications.
- **Operations**: separate `/health/live` and `/health/ready` probes, Prometheus `/metrics` (no vendor dependency), `/metrics/json`, request-id correlation across logs and responses, request latency/status metrics, and a pluggable error-reporting seam.
- **Responsive & accessible UI**: mobile navigation drawer, card layouts for tables under `md`, skip link, ARIA roles/labels, visible focus rings, keyboard-accessible kanban moves, shared loading/empty/error primitives, and `error.tsx` / `loading.tsx` / `not-found.tsx`.
- Docs: `docs/DEPLOYMENT.md` (pre-flight checklist, Compose/PaaS/Kubernetes, backups, Prometheus/Sentry wiring, smoke test, rollback) and `docs/TROUBLESHOOTING.md` (symptom-first runbook).

### Changed
- Lead list is paginated (25/page) and returns `X-Total-Count`; the response body remains a plain array, so existing clients are unaffected.
- `ai_summary` analytics now aggregate in SQL instead of loading every conversation and lead into memory.
- Lead detail and replay use eager loading, removing N+1 queries.
- Added composite indexes on `leads(workspace_id, status)` and `leads(workspace_id, created_at)`.
- Removed the unused `ProviderConfig` model (provider config lives in workspace settings); the migrator drops the table.
- Test suite grew from 66 to 112 tests at 84% coverage.

## [2.0.0] — 2026-07-18

### Added
- **Multi-tenant workspaces**: isolated leads/KB/workflows/prompts/settings/audit per company; workspace slug on public endpoints; additive auto-migrator upgrades v1 databases without data loss.
- **White label**: per-workspace company/bot name, logo, primary color, landing texts; public branding endpoint consumed by widget and landing page.
- **Semantic knowledge base**: `EmbeddingProvider` abstraction (OpenAI/Gemini/OpenRouter + offline hashing fallback), pluggable `VectorStore` (DB-backed cosine), hybrid semantic+lexical retrieval, reindex endpoint.
- **Redis integration** (optional, graceful fallback): cluster-wide rate limiting, login lockouts, analytics cache, durable background task queue.
- **Notification center**: unified dispatch to in-app/email/Telegram with per-message delivery logs, queue-backed retries with exponential backoff, Slack/Discord extension slots; in-app bell UI.
- **Telegram v2**: retry mechanism, deep links into the CRM, lead status-change updates.
- **Email v2**: provider abstraction, branded HTML templates with plain-text alternative, delivery status tracking.
- **Prompt management**: versioned prompts with activate/deactivate/rollback, offline test bench, workflow assignment.
- **CRM v2**: kanban board with drag & drop, custom pipeline stages per workspace, tags, priorities, follow-up reminders, internal comments, summary search.
- **Conversation replay**: timestamped timeline with workflow-node metadata, KB-match scores, attachments, CRM events; play/step UI.
- **AI analytics**: conversion funnel, drop-off by node, conversation length/duration, lead quality bands, capture confidence, common questions.
- **AI memory**: short-term window + compressed rolling summary with token budget and persistence.
- **Audit log**: login/logout/failed logins, role changes, lead/prompt/workflow/KB/settings mutations with actor + IP; admin UI.
- **Security**: rotating refresh tokens with replay protection, logout, login lockout, security headers, JWT workspace claim, tabbed Settings module with billing placeholder.
- Repo quality: ARCHITECTURE.md, CONTRIBUTING.md, SECURITY.md, ROADMAP.md, issue/PR templates; 66-test suite.

### Changed
- Access-token TTL reduced to 30 minutes (refresh flow added); lead status validation is now workspace-pipeline-driven instead of a fixed enum.

## [1.0.0] — 2026-07-18

### Added
- Conversational AI intake chat widget (SSE streaming, typing indicator, quick replies, file uploads, EN/UK).
- JSON-driven workflow engine: per-language prompts, answer validation (text/choice/number/email/phone), keyword branching, clarification of vague answers, pre-fill skipping.
- Multi-provider LLM layer (OpenAI, Anthropic, Gemini, OpenRouter) with offline deterministic `mock` mode and graceful fallbacks.
- AI lead summaries with rule-based fallback; deterministic 0–100 lead scoring with configurable Qualified threshold.
- Mini-CRM: leads list (filters, search), lead detail (transcript, summary, attachments, activity log, notes, assignment), role-based access (admin/manager).
- Telegram bot integration: new-lead notifications with Accept/Reject/Call inline buttons, `/note` command, secret-token-protected webhook.
- Transactional email (client confirmation + staff alert) with editable templates and console fallback.
- Knowledge base with lexical retrieval; the bot answers off-script questions mid-flow.
- Analytics dashboard: KPIs, leads-per-day chart, status and service breakdowns.
- Runtime settings UI (prompts, provider/model, thresholds, templates) — no redeploy needed.
- Auth: JWT + PBKDF2, user management, rate limiting, input sanitization.
- Docker Compose stack (Postgres + backend + frontend), GitHub Actions CI, seed script, 35 pytest tests.
