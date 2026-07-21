# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

## [2.4.0] — 2026-07-21

Client-chosen communication channel.

### Added
- **Communication-channel picker in intake.** Before finishing, the assistant
  now asks how the client prefers to be reached — **Email**, **Telegram**, or
  **Phone** — and collects the matching detail (address, @handle, or number).
  The choice and its value are stored on the lead (`contact_method` /
  `contact_value`); `client_email` / `client_phone` stay populated for the
  email/phone cases so email delivery and CRM export are unaffected.
- The Telegram "new lead" alert, lead card, Call action and follow-up reminder
  now show the client's **chosen channel** instead of always defaulting to
  email. The admin lead page shows a "Preferred" contact row.
- Demo/seed data spreads its leads across all three channels (email, Telegram,
  phone), so the seeded pipeline, lead cards and Telegram alerts showcase the
  picker; the seeded conversation replay shows the channel step too.

### Changed
- The built-in default intake workflow gained the channel step. Existing
  databases are upgraded in place at startup **only when the stored default is
  unmodified** (deep-equals a previous built-in); customised workflows are left
  untouched. See `chat.upgrade_default_workflows` and
  `workflow.SUPERSEDED_DEFAULTS`.

## [2.3.0] — 2026-07-19

Pre-publication security pass.

### Security
- **The Telegram webhook failed open.** Validation of the
  `X-Telegram-Bot-Api-Secret-Token` header was wrapped in
  `if settings.telegram_webhook_secret:`, so an unset secret skipped the check
  entirely rather than refusing the request — and the secret ships empty by
  default. Updates accepted on that route change lead status and write internal
  notes, so any unauthenticated caller who could reach a deployed instance could
  drive the CRM. The endpoint now **fails closed**: no configured secret means
  every request is rejected with 403.
- Secret comparison now uses `secrets.compare_digest`. A plain `!=` short-circuits
  on the first differing byte, leaking the secret to an attacker who can measure
  response latency across many attempts.
- The webhook is now rate limited like the rest of the API; it was the one
  unauthenticated public route with no limiter attached.
- `.gitignore` hardened: `credentials.docx`, `*credential*.docx`, `*password*.docx`,
  `.env.*` (with `.env.example` re-included) and Word lock files.

### Added
- **dmeta pre-commit hook** (`clear-metadata`, v0.5) strips authorship and
  revision metadata from Office documents before they can be committed. Scoped
  with a `files:` filter to Office extensions — the upstream hook declares
  `pass_filenames: false` and walks the whole tree, so unscoped it runs on every
  commit and aborts with a `PermissionError` whenever OneDrive or antivirus holds
  a lock on any Office file.
- Tests covering the webhook's authentication contract: missing secret, wrong
  secret, and unconfigured-server all reject, and a rejected call leaves lead
  state untouched.

### Changed
- **Breaking:** a deployment that relied on the webhook working without
  `TELEGRAM_WEBHOOK_SECRET` must now set it and register it with
  `setWebhook(secret_token=...)`.

## [2.2.0] — 2026-07-19

First release configured against live provider credentials. Verifying them
end to end surfaced two silently-broken defaults.

### Fixed
- **Default model IDs had gone stale and every real completion 404'd.** The OpenRouter
  default (`meta-llama/llama-3.3-70b-instruct:free`) has been delisted, and the Gemini
  default (`gemini-2.0-flash`) is closed to new API keys. Defaults are now
  `openai/gpt-oss-20b:free` and `gemini-flash-latest` — the rolling alias, because dated
  Gemini snapshots get retired for new keys. Both verified against live APIs.
- **The default Gemini embedding model `text-embedding-004` no longer exists** (404);
  replaced with `gemini-embedding-001`. Only reachable when `EMBEDDING_PROVIDER=gemini`,
  since the offline hashing embedder is the default.
- `runtime_settings.get_all` now resolves a stored empty string to the default, matching
  what `get` has always done — the two disagreed for cleared values.

### Added
- **`python -m app.doctor` (`make doctor`)** — integration preflight that checks the
  configured AI provider, embeddings, Telegram, SMTP and CRM credentials against the live
  services, plus JWT/admin-password hygiene. Read-only by default; `--send-test`
  additionally delivers a real Telegram message and email. Exits non-zero on failure, so
  it works as a deploy gate. Unconfigured integrations report SKIP, not failure, keeping
  it useful for zero-key installs.
- **Telegram chat-id discovery** — when `TELEGRAM_CHAT_ID` is unset, the doctor lists the
  chats that have messaged the bot so the id can be copied straight into `.env`. It also
  fails loudly when `TELEGRAM_CHAT_ID` is set to the *bot's own* id: that value looks
  plausible (it is the prefix of the bot token) but Telegram rejects bot-to-self sends, so
  alerts would silently go nowhere.
- **`CRM_PROVIDER` / `CRM_API_KEY` env bootstrap.** CRM credentials were reachable only
  through the admin UI, which made an unattended deploy impossible. A value stored in the
  UI still wins; only the whitelisted keys read from the environment.
- **GitHub Pages project site** (`site/`, deployed by `.github/workflows/pages.yml`).
  The repository URL is injected at build time from a `__REPO_URL__` placeholder, so a
  fork's links resolve without editing the HTML.

### Security
- The test suite now explicitly blanks provider keys and CRM credentials, so a developer's
  real `.env` cannot leak into tests — without this, the CRM export tests would have
  written real contacts into a live HubSpot account.

## [2.1.1] — 2026-07-18

Independent production audit. No features removed; all API contracts unchanged.

### Fixed
- **Pagination disabled "Previous" on non-page-aligned offsets** — found by a new frontend test; the control now guards on the offset itself rather than a derived page number.
- **`ON DELETE` rules were absent and SQLite silently ignored foreign keys** — child rows could outlive their parent when deleted via raw SQL. Added explicit `CASCADE`/`SET NULL` and enabled the SQLite `foreign_keys` pragma so the declared integrity is actually enforced.

### Security
- **Docker build context excluded nothing** (~560 MB of `.venv`/`node_modules`, and a local `.env` would have been copied into image layers). Added `.dockerignore`.
- **Containers ran as root.** Both images now create and run as an unprivileged UID; CI asserts it.
- **No Content-Security-Policy.** Added CSP plus `Permissions-Policy`/`Referrer-Policy` on the web tier, with `connect-src` pinned to the API origin.
- Compose: database and Redis ports no longer published by default, `no-new-privileges`, restart policies, healthcheck-gated startup ordering.
- CI now runs `pip-audit` and `npm audit`; the one known moderate advisory (transitive PostCSS inside Next's build tooling, whose published fix is a downgrade to Next 9) is documented rather than silently accepted.

### Removed
- Dead code: `LeadPage` schema, `kb.mark_stale`, `cache.reset_cache_for_tests`.

### Added
- **Frontend test suite** (Vitest + Testing Library, 24 tests) covering the silent token-refresh/replay flow and the accessibility contract of the shared primitives — previously zero frontend tests.
- **Developer experience**: `Makefile` task runner, `ruff format`, pre-commit hooks, `.editorconfig`, `.gitattributes`.
- **CI**: format check, coverage gate (80% floor, currently 84%), type check, `--max-warnings=0` lint, Docker image builds with non-root assertion, compose validation, and an integration job that boots demo mode, drives a chat to lead creation and proves migrations are idempotent across repeated runs.
- **SEO**: metadata/OpenGraph, `robots.txt` (disallowing `/admin`) and `sitemap.xml`.
- `docs/DISASTER_RECOVERY.md` (RPO/RTO, restore procedures, verification schedule); README gains Tech Stack, Installation, Demo Mode and FAQ sections.

### Changed
- All eight admin screens now use the shared loading/empty/error primitives — five were still hand-rolling that markup with inconsistent wording and no ARIA roles.
- Next.js `output: "standalone"` shrinks the production image to only the modules actually imported.

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
