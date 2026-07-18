# Roadmap

## Shipped

- **v1.0** — conversational intake, JSON workflow engine, multi-LLM layer, mini-CRM,
  Telegram/email notifications, analytics, i18n (EN/UK), Docker, CI.
- **v2.0** — multi-tenant workspaces + white label, semantic KB (embedding provider +
  vector store abstractions), Redis-backed cache & task queue with graceful fallbacks,
  notification center with delivery logs & retries, prompt management with versioning
  and rollback, CRM v2 (kanban, tags, priorities, follow-ups, custom pipelines,
  comments), AI analytics (funnel, drop-off, confidence), AI memory, conversation
  replay, refresh-token auth, audit log, security headers.

## Next (v2.x)

- [ ] Alembic migration chain for long-lived production databases
- [ ] Workspace signup & onboarding flow (self-serve tenant creation)
- [ ] Stripe billing module (plans, usage-based AI metering) — placeholder tab exists
- [ ] Slack & Discord notification senders (registry slots already in place)
- [ ] pgvector `VectorStore` implementation + ANN search for large KBs
- [ ] Embeddable JS snippet (`<script>` one-liner) for the chat widget
- [ ] CRM export webhooks (HubSpot, Salesforce) + CSV export
- [ ] Playwright E2E suite; Locust load tests
- [ ] Prometheus metrics endpoint + OpenTelemetry tracing
- [ ] SSO (Google/Microsoft OAuth) for the admin dashboard
- [ ] Per-workspace custom domains with automatic TLS
