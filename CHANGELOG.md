# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

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
