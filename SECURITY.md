# Security Policy

## Reporting a vulnerability

Please **do not open a public issue**. Email the maintainer instead; you will get an
acknowledgement within 72 hours. Include reproduction steps and impact assessment.

## Security measures in place

| Area | Implementation |
|---|---|
| Authentication | Short-lived JWT access tokens + rotating opaque refresh tokens (SHA-256 hashed at rest, replay-safe) |
| Brute force | Per-email+IP login lockout (cache-backed, cluster-wide with Redis) |
| Authorization | Role-based (admin/manager) + workspace tenancy checks on every query; cross-tenant access returns 404 |
| Passwords | PBKDF2-SHA256, 260k iterations, constant-time comparison |
| Injection | SQLAlchemy parameterized queries; HTML stripped from user input; React-only rendering (no `dangerouslySetInnerHTML`) |
| Prompt injection | System prompts are server-side data; user text never edits prompt templates; intake logic is deterministic, not LLM-driven |
| Transport/headers | HTTPS expected in production; `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store` on every response |
| Rate limiting | Sliding-window per IP on public endpoints |
| Webhooks | Telegram webhook validated via `X-Telegram-Bot-Api-Secret-Token` |
| Secrets | Environment variables only; never stored in the database or logged; `.env.example` documents every variable |
| Audit | Login/logout/failed logins, role changes, CRM/prompt/workflow/KB/settings mutations recorded with actor + IP |
| Uploads | Extension allow-list, size cap, randomized stored names |

## Supported versions

Only the latest `main` receives security fixes.
