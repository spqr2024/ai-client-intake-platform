# Security Policy

## Reporting a vulnerability

Please **do not open a public issue**. Email the maintainer instead; you will get
an acknowledgement within 72 hours. Include reproduction steps and an impact
assessment.

## Controls in place

### Authentication and session management
| Control | Implementation |
|---|---|
| Access tokens | JWT, 30-minute TTL, carrying `sub` / `role` / `ws` |
| Refresh tokens | Opaque 48-byte values, SHA-256 hashed at rest, **rotated on every use**; replaying a rotated token fails |
| Logout | Server-side revocation, not just client-side token disposal |
| Role changes | Revoke all of that user's sessions, forcing re-authentication |
| Brute force | Per email + IP lockout (5 attempts / 15 min, configurable), cluster-wide when Redis is configured |
| Passwords | PBKDF2-SHA256, 260k iterations, constant-time comparison |

### Authorization and tenancy
- Role-based access (`admin` / `manager`) enforced by FastAPI dependencies.
- Every authenticated query filters by the caller's workspace.
- Cross-tenant access returns **404, never 403** — record existence is never leaked.
- Dedicated isolation tests cover leads, settings, users and attachments.

### Input and output handling
| Vector | Mitigation |
|---|---|
| SQL injection | SQLAlchemy parameterized queries throughout; no string-built SQL |
| XSS | HTML stripped from visitor input on ingest; React renders text as nodes — no `dangerouslySetInnerHTML` anywhere |
| CSRF | Not applicable by construction: authentication is `Authorization`-header only, with no cookie-based session for the browser to attach automatically |
| Prompt injection (OWASP LLM01) | System prompts are server-side data; user text never edits prompt templates. Intake progression is a deterministic state machine, so no prompt can make the bot skip qualification |
| Unsafe LLM output | AI text is rendered as React nodes, never HTML |
| File uploads | Extension allow-list, size cap, randomized stored names, content-type allow-list on download with `nosniff`, `attachment` disposition for anything not explicitly inline-safe |
| Upload exposure | Attachments are staff-only and workspace-scoped — never publicly addressable |

### Transport and headers
API responses carry `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Referrer-Policy`, `Permissions-Policy` and `Cache-Control: no-store`.
The web tier adds a **Content-Security-Policy** with `connect-src` pinned to the
API origin, `object-src 'none'` and `frame-ancestors 'none'`, so a successful
injection still cannot exfiltrate to an attacker-controlled host. HTTPS is
expected to terminate in front of both services in production.

### Infrastructure
- Both container images run as an **unprivileged UID**; CI asserts it.
- `.dockerignore` keeps `.env`, virtualenvs and `node_modules` out of the build
  context and therefore out of image layers.
- Compose sets `no-new-privileges` and does not publish database or Redis ports.
- Database and Redis start behind healthchecks; the API waits for them.

### Data integrity
Foreign keys declare explicit `ON DELETE CASCADE` / `SET NULL`, and the SQLite
`foreign_keys` pragma is enabled at connect time — without it SQLite silently
ignores those constraints, so the ORM's intent would not have been enforced on
the default development database.

### Secrets
Environment variables only; never committed, never logged. `.env.example`
documents every variable. The application warns at startup if `JWT_SECRET` is
short or still the documented default.

### Auditing and rate limiting
Logins (including failures), logouts, role changes, and every CRM, prompt,
workflow, knowledge-base and settings mutation are recorded with actor, entity
and IP. Public endpoints are rate limited per IP with a sliding window.

### Supply chain
CI runs `pip-audit` on Python dependencies and `npm audit` on the frontend.

## Known trade-offs

Stated plainly rather than hidden — each is a deliberate decision with a
documented upgrade path.

1. **Tokens are stored in `localStorage`.** This follows from header-based auth,
   which removes CSRF as a class. The cost is that a successful XSS could read a
   token, so XSS defence carries more weight here: React-only rendering, input
   sanitization and a strict CSP. Cookie-based sessions with `SameSite` plus CSRF
   tokens are the alternative trade, not a strict improvement.
2. **Provider API keys live in workspace settings rows.** Convenient for
   self-hosting and runtime provider switching; a shared multi-tenant SaaS should
   move them to a secret manager (on the roadmap).
3. **`DEMO_MODE` defaults to `true` in `.env.example`** so a fresh clone looks
   alive. It only seeds a workspace with zero leads and is idempotent, but the
   deployment pre-flight checklist calls out disabling it in production.
4. **One moderate advisory is knowingly unpatched**: a transitive PostCSS issue
   inside Next.js build tooling whose published fix is a downgrade to Next 9. It
   affects build-time CSS stringification, not runtime request handling. CI gates
   at `high` so this is visible rather than silently auto-"fixed" by a downgrade.
5. **No OCR for scanned PDFs.** Images-without-text are rejected with an
   explanatory message rather than silently indexed as empty documents.

## Supported versions

Only the latest `main` receives security fixes.
