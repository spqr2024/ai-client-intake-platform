# Contributing

Thanks for your interest. Standard fork-and-PR workflow; everything below is
enforced by CI, so running it locally saves a round trip.

## Setup (one command)

```bash
make setup      # creates the venv, installs backend + frontend dependencies
```

<details>
<summary>Without <code>make</code> (Windows, or no GNU make)</summary>

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
cd ../frontend && npm ci
```
</details>

## Running it

```bash
make demo       # API on :8000 with a populated demo workspace
make frontend   # web app on :3000
```

Then open <http://localhost:3000> (chat widget bottom-right) and
<http://localhost:3000/admin> (`admin@example.com` / `admin12345`).

No API keys, database server or Redis are required — the defaults are a
deterministic mock AI provider, SQLite and in-process cache/queue.

Prefer a scripted, non-random dataset? `make seed`.

## Quality gates

```bash
make check      # everything CI runs: lint + format + types + all tests
```

Individually:

| Command | What it checks |
|---|---|
| `make lint` | Ruff (backend) and ESLint with `--max-warnings=0` (frontend) |
| `make format` | Ruff format + Prettier — run this before pushing |
| `make test-backend` | pytest with an 80% coverage floor |
| `make test-frontend` | Vitest + Testing Library |
| `cd frontend && npx tsc --noEmit` | TypeScript strict mode |

Optional but recommended — catches formatting before it reaches review:

```bash
pip install pre-commit && pre-commit install
```

## Conventions

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/) —
  `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- **Branches**: feature branches off `main`; PRs must pass CI before merge.
- **Line endings**: LF, enforced by `.gitattributes` and `.editorconfig`.

## Architectural rules

These are what reviewers actually check. They are not style preferences — each
one exists because breaking it has bitten this codebase before.

1. **Every external dependency sits behind an abstraction with an offline
   fallback.** The test suite must pass with zero API keys and no network.
   See `EmbeddingProvider`, `VectorStore`, `EmailProvider`, `CacheBackend`,
   the task queue and the notification/CRM registries.
2. **Every domain table carries `workspace_id`**, every authenticated query
   filters by the caller's workspace, and cross-tenant access returns **404**
   (not 403) so record existence is never leaked.
3. **Intake logic stays deterministic.** The workflow engine is a state machine;
   LLMs may rephrase, summarize and compress, but must never decide whether a
   step is satisfied. Every LLM call needs a working fallback.
4. **Security- and configuration-relevant mutations call
   `services.audit.record`** with actor, entity and request.
5. **API contracts are append-only.** Add fields and headers; don't change the
   shape of an existing response. (Pagination added `X-Total-Count` rather than
   wrapping the array in an envelope, for exactly this reason.)
6. **New async-state UI uses the shared primitives** in `components/ui.tsx`
   (`LoadingState`, `EmptyState`, `ErrorState`, `Toast`, `Pagination`) so
   loading, empty and error behaviour — and their ARIA semantics — stay
   consistent across all screens.

## Adding an integration

Each extension point is a registry; adding one is a class plus a registration,
with no edits to existing files:

| Add a… | Do this |
|---|---|
| CRM target | Subclass `CRMProvider` in `services/crm.py`, call `register_provider(...)`. Declare `option_keys`; settings persists them automatically via the `crm_option_` prefix |
| AI provider | Extend `services/llm.py` and add one entry to `resolve_config` |
| Embedding provider | Subclass `EmbeddingProvider`, add one branch to `get_provider()` |
| Notification channel | `register_channel("slack", sender)` in `services/notifications.py` |
| Workflow template | Add a dict to `TEMPLATES` in `services/workflow_templates.py` — no code change |

## Reporting issues

Use the issue templates. For security vulnerabilities see [SECURITY.md](SECURITY.md);
please do not open public issues for those.
