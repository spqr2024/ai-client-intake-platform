## What & why

<!-- Summary of the change and its motivation. Link related issues. -->

## Checklist

- [ ] `ruff check app tests` and `pytest` pass (backend)
- [ ] `npm run lint` and `npm run build` pass (frontend)
- [ ] New behavior is covered by tests (suite passes with zero API keys)
- [ ] New domain tables carry `workspace_id`; queries are tenant-scoped
- [ ] Security/config mutations call `services.audit.record`
- [ ] External calls go behind an abstraction with an offline fallback
- [ ] Docs updated (README / ARCHITECTURE / CHANGELOG) if user-facing
