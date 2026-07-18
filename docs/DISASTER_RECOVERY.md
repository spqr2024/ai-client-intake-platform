# Disaster Recovery

What to back up, how to restore it, and what "recovered" means for each
failure mode. Written to be followed under pressure by someone who did not
write the code.

---

## Recovery objectives

| Metric | Target | Basis |
|---|---|---|
| **RPO** (max data loss) | ≤ 24 h, ≤ 5 min with PITR | Daily snapshots; managed Postgres point-in-time recovery |
| **RTO** (max downtime) | ≤ 1 h | Stateless app images redeploy in minutes; restore time dominates |

Tighten both by increasing snapshot frequency — nothing in the application
prevents a shorter RPO.

## What holds state

| Asset | Criticality | Backup method |
|---|---|---|
| **PostgreSQL** | Critical — leads, transcripts, users, audit, settings | Managed automated snapshots + PITR (or `pg_dump` cron below) |
| **Uploads volume** | Important — visitor attachments; irreplaceable | Volume snapshot, or migrate to S3-compatible object storage |
| **`.env` / secrets** | Critical — nothing decrypts without `JWT_SECRET` | Secret manager with its own versioning. **Never** in the repo |
| Redis | Disposable | Cache and queue; a cold start replays nothing but loses in-flight retries |
| Vector index | Rebuildable | `POST /api/kb/reindex` regenerates from article text |

> The vector index and Redis are deliberately reconstructible. Only Postgres,
> uploads and secrets require real backups.

## Backups without a managed provider

```bash
# Nightly logical backup, 14-day retention
0 2 * * * docker compose exec -T db pg_dump -U intake -Fc intake \
  > /backups/intake-$(date +\%F).dump && \
  find /backups -name 'intake-*.dump' -mtime +14 -delete

# Weekly uploads archive
0 3 * * 0 tar czf /backups/uploads-$(date +\%F).tar.gz \
  -C /var/lib/docker/volumes/aiclientintakeplatform_uploads/_data .
```

Store backups **off the application host** (object storage or another region).
A backup on the machine that just died is not a backup.

## Restore procedures

### 1. Database corruption or accidental deletion

```bash
docker compose stop backend            # stop writes first
docker compose exec -T db dropdb -U intake intake
docker compose exec -T db createdb -U intake intake
cat /backups/intake-2026-07-18.dump | \
  docker compose exec -T db pg_restore -U intake -d intake --no-owner
docker compose start backend           # migrator runs, idempotently
curl -sf localhost:8000/health/ready
```

The startup migrator is additive and idempotent, so restoring an older dump
into newer code is safe: missing columns are added, existing data is untouched.

### 2. Total host loss

1. Provision a new host with Docker.
2. `git clone` the repository at the last released tag.
3. Restore `.env` from the secret manager — **`JWT_SECRET` must match the
   original**, or every issued session and refresh token becomes invalid.
4. Restore the database dump and uploads archive (above).
5. `docker compose up -d --build`, then verify with the smoke test in
   [DEPLOYMENT.md](DEPLOYMENT.md#9-post-deploy-smoke-test).

### 3. Bad release

Application images are immutable per commit and the migrator never drops a
column older code reads, so **roll the image back** without touching the
database:

```bash
git checkout <previous-tag> && docker compose up -d --build
```

Restore the database only if the release wrote corrupt data.

### 4. Secret compromise

```bash
# 1. Rotate the signing key — invalidates every access token immediately.
JWT_SECRET=$(openssl rand -hex 32)
# 2. Restart; all sessions are forced to re-authenticate.
docker compose up -d backend
# 3. Rotate provider keys (AI, Telegram, SMTP, CRM) at each provider.
# 4. Review who did what:
curl -s "localhost:8000/api/audit?limit=500" -H "Authorization: Bearer <admin>"
```

Refresh tokens are stored hashed, so a database leak does not yield usable
tokens — but rotate anyway and force re-login.

### 5. Redis unavailable

No action required. The cache, rate limiter and task queue fall back to
in-process implementations automatically; `/health/ready` still reports ready
because Redis is not a hard dependency. In-flight queued retries are lost —
re-trigger any missed CRM export from the lead page.

## Verification schedule

A backup you have never restored is a hypothesis.

| Cadence | Exercise |
|---|---|
| Monthly | Restore the latest dump into a scratch database; confirm lead counts |
| Quarterly | Full host-loss rehearsal on a temporary VM, timed against the RTO |
| Per release | CI already verifies migration idempotency and a demo-mode boot |

## Escalation checklist

1. Capture evidence first: `docker compose logs backend > incident.log`, plus
   `/health/ready` output and the `X-Request-ID` of a failing request.
2. Stop writes before restoring anything.
3. Announce the maintenance window.
4. Restore, verify with the smoke test, then re-enable traffic.
5. Write the post-mortem — and add a regression test for whatever broke.
