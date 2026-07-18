# Troubleshooting

Symptoms first, in the order people actually hit them.

---

## Setup

### `python` opens the Microsoft Store (Windows)
`python` resolves to a stub. Use the launcher:
```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

### `ModuleNotFoundError: No module named 'app'`
Run from the `backend/` directory — the package root is `backend/app`:
```bash
cd backend && uvicorn app.main:app --reload
```

### Port already in use
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F
# macOS / Linux
lsof -ti:8000 | xargs kill -9
```

---

## Frontend ↔ backend

### The chat widget says "Could not reach the server"
1. Is the backend up? `curl http://localhost:8000/health`
2. Does `NEXT_PUBLIC_API_URL` point at it? It is inlined at **build** time —
   change it and rebuild, restarting is not enough.
3. Check the browser console for a CORS error (below).

### CORS errors in the browser
`CORS_ORIGINS` must contain the exact frontend origin, including scheme and
port, comma-separated for several:
```
CORS_ORIGINS=http://localhost:3000,https://app.example.com
```

### Logged out immediately after signing in
Access tokens last 30 minutes and refresh silently. Constant logouts usually
mean `JWT_SECRET` changes between restarts (e.g. generated at boot) — set a
fixed secret. Clearing `localStorage` resolves a corrupted token pair.

---

## AI and knowledge base

### The bot asks templated questions and never rephrases
Expected in `mock` mode. Intake logic is deliberately deterministic; the LLM
only rephrases, summarizes and compresses memory. Set a provider key and
select it in **Settings → AI Providers** to enable phrasing.

### Provider configured but still behaving like mock
The provider silently falls back when its key is missing. Check the logs for
`Provider ... selected but no API key set`. Keys live in `.env`
(`OPENAI_API_KEY`, …), not in the database.

### KB search does not find an obviously relevant document
1. Check the document's **index status** on the KB page. `failed` shows the
   error; `pending`/`stale` means it needs indexing — press **Re-index**.
2. If you switched embedding providers, run **Re-index all**: vectors are
   stored per `(provider, model)` and old ones are ignored by design.
3. With the default offline embedder, matching is morphological, not
   semantic — "money back" will not match "refund". Configure a real
   `EMBEDDING_PROVIDER` for synonym recall.
4. Consult **Questions the KB could not answer** at the bottom of the KB page;
   each entry is a document you are missing.

### PDF or DOCX upload returns 415
Either the optional extractor is not installed (`pip install pypdf python-docx`)
or the PDF is a scanned image with no text layer. OCR is intentionally out of
scope — paste the text manually.

---

## Notifications and integrations

### No Telegram messages
1. `TELEGRAM_BOT_TOKEN` set and the bot started by the recipient?
2. Chat ID configured (Settings → Notifications) — for groups it is negative.
3. Webhook registered with the same `secret_token` as
   `TELEGRAM_WEBHOOK_SECRET`; check `getWebhookInfo` for `last_error_message`.
4. Look at **Settings → Integrations → Recent outbound deliveries**: a
   `failed` row shows the exact API error.

### Emails are not delivered
Without `SMTP_HOST` the platform logs emails instead of sending — that is the
development default. With SMTP configured, check the delivery log for the
provider error (authentication and port 587 vs 465 are the usual causes).

### Inline Telegram buttons do nothing
Callbacks arrive on the webhook. If the app is not publicly reachable, use a
tunnel (`ngrok http 8000`) and re-register the webhook with that URL.

### CRM export never runs
- **Settings → CRM Export**: provider selected, API key set, and
  `crm_export_on` is `qualified` or `all` (`qualified` only exports leads at
  or above the score threshold).
- Provider-specific options are required: Notion needs `database_id`,
  Salesforce `instance_url`, Pipedrive `company_domain`, webhook `url`.
- Check **Recent CRM exports** for the error and attempt count. Failures retry
  three times with backoff before being marked `failed`.

---

## Data and performance

### Leads from before an upgrade look wrong
The startup migrator adds columns with defaults; historical rows get
`priority=Medium`, empty tags and no follow-up. That is expected — it never
invents data.

### `no such column` / `column does not exist` after upgrading
The migrator runs on startup. If the process crashed mid-migration, restart it;
steps are idempotent. Restore from backup only if the schema is genuinely
inconsistent.

### The dashboard feels slow with many leads
- Lead lists are paginated (25/page) with `X-Total-Count`.
- Analytics are cached for 60 seconds; set `REDIS_URL` to share that cache
  across replicas.
- KB search is brute-force cosine over chunks — fine into the thousands. For
  much larger corpora implement `VectorStore` against pgvector; the retrieval
  callers do not change.

### Rate limited (429) during load testing
Raise `RATE_LIMIT_PER_MINUTE` or set it to `0` to disable. Without
`REDIS_URL`, limits are per process, so N replicas allow N× the traffic.

---

## Diagnostics

```bash
curl -s localhost:8000/health/ready | jq      # dependency status
curl -s localhost:8000/metrics/json | jq      # counters, latencies
curl -s localhost:8000/docs                   # interactive API docs
```

Every response carries `X-Request-ID`; the same id appears on every log line
for that request, so grep it to reconstruct a single call end to end:

```bash
docker compose logs backend | grep '"request_id":"<id>"'
```

Still stuck? Open an issue with the request id, the relevant log lines, and
your `/health/ready` output (never paste secrets).
