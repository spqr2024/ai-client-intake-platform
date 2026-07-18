# Contributing

Thanks for your interest! This project follows a standard fork-and-PR workflow.

## Development setup

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m app.seed        # optional demo data
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Quality gates (CI enforces all of these)

```bash
cd backend
ruff check app tests      # lint
pytest --cov=app          # tests — keep them green, add tests for new behavior

cd frontend
npm run lint
npm run build
```

## Conventions

- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/) —
  `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- **Branches**: feature branches off `main`; PRs must pass CI before merge.
- **Architecture**: new integrations go behind the existing abstractions
  (`EmbeddingProvider`, `VectorStore`, `EmailProvider`, notification channel
  registry, `CacheBackend`). Every external dependency needs a graceful
  offline fallback — the test suite must pass with zero API keys.
- **Tenancy**: every new domain table gets `workspace_id`; every authenticated
  query filters by the caller's workspace; cross-tenant access returns 404.
- **Audit**: security- or configuration-relevant mutations call
  `services.audit.record`.

## Reporting issues

Use the issue templates. For security vulnerabilities see [SECURITY.md](SECURITY.md) —
please do not open public issues for those.
