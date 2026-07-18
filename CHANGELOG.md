# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

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
