# Releasing & Repository Presentation

Everything needed to cut a release and to make the GitHub page itself look
maintained. The first section is the part most portfolio repositories skip.

---

## 1. Repository metadata (set once, in GitHub Settings)

These fields are what a client sees *before* opening the README — in search
results, in their starred list, and in the sidebar.

**Description** (350 char limit; this is 148):

```
Multi-tenant SaaS that replaces contact forms with an AI intake agent: qualifies and scores leads 24/7, with a kanban CRM, Telegram bot and analytics.
```

**Website:** your deployed demo URL (or leave empty rather than pointing at a
dead link — a broken demo link is worse than none).

**Topics** (GitHub allows 20; these are chosen for how clients actually search):

```
fastapi  nextjs  typescript  python  saas  multi-tenant  ai-agent  llm
openai  anthropic  rag  chatbot  crm  lead-generation  telegram-bot
postgresql  redis  docker  conversational-ai  full-stack
```

**Sidebar toggles:** enable Issues and Discussions; disable Wiki and Projects
unless you actually use them — empty tabs read as abandoned.

**Social preview image:** upload `docs/images/hero-chat.png` once captured
(Settings → General → Social preview). This is what renders when the link is
shared on LinkedIn, Slack or Upwork.

---

## 2. Versioning

[Semantic Versioning](https://semver.org/). The version lives in **one place**:

```python
# backend/app/__init__.py
__version__ = "2.1.1"
```

It is read by the OpenAPI schema and both health endpoints. The newest heading
in `CHANGELOG.md` must match it — CI fails the build if they drift.

| Bump | When |
|---|---|
| **Major** | A breaking API change. This project treats contracts as append-only, so this should be rare and loudly documented |
| **Minor** | New capability, backwards compatible (a CRM adapter, a workflow feature) |
| **Patch** | Fixes, security hardening, docs, internal refactors |

---

## 3. Release procedure

```bash
# 1. Version + changelog in the same commit
#    - bump backend/app/__init__.py
#    - move CHANGELOG "Unreleased" into a dated version heading
git commit -am "chore(release): v2.1.1"

# 2. Verify everything green before tagging
make check

# 3. Annotated tag (never lightweight — annotated tags carry author and date)
git tag -a v2.1.1 -m "v2.1.1 — independent production audit"
git push origin main --follow-tags
```

Then publish the GitHub Release from the tag, pasting that version's
`CHANGELOG.md` section as the body. Keep the same shape every time:

```markdown
## Highlights
One or two sentences a non-engineer understands.

## Fixed / Added / Changed
(from CHANGELOG.md)

## Upgrading
Anything an operator must do — env vars, reindexing, migration notes.
Say "No action required." explicitly when that is true.

**Full changelog:** https://github.com/<owner>/<repo>/compare/v2.1.0...v2.1.1
```

### Upgrade notes by version

| Version | Operator action |
|---|---|
| **v2.1.1** | None. Schema changes are additive and applied at startup. Rebuilding images picks up the non-root user and CSP. |
| **v2.1.0** | None required. Optional: `pip install pypdf python-docx` to enable PDF/DOCX knowledge-base uploads. Existing KB articles are re-chunked on first edit or via **Re-index all**. |
| **v2.0.0** | None. The startup migrator adds workspace columns and backfills the default workspace without data loss. Back up the database first, as with any schema change. |

---

## 4. Badge conventions

Badges in the README are **claims**, so keep them true:

| Badge | Update when |
|---|---|
| Tests | Test count changes — currently **136** (112 backend + 24 frontend) |
| Coverage | Backend coverage moves — currently **84%**, CI floor 80% |
| CI | Points at the workflow file; swap to a live `workflow status` badge once the repo is on GitHub |

Once pushed, replace the static CI badge with the live one:

```markdown
[![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<owner>/<repo>/actions/workflows/ci.yml)
```

---

## 5. Pre-publish checklist

Run through this before making the repository public.

**Secrets and data**
- [ ] `git log -p | grep -iE "api[_-]?key|secret|password|token"` finds only
      placeholders and documentation
- [ ] No `.env` in history (`git log --all --name-only | grep -x ".env"`)
- [ ] `backend/data/` and `backend/uploads/` are untracked
- [ ] Demo data contains no real personal information

**Presentation**
- [ ] Description and topics set (§1)
- [ ] README renders correctly on GitHub — mermaid diagrams included
- [ ] Screenshots captured per [SCREENSHOTS.md](SCREENSHOTS.md), or the section
      honestly explains they are generated locally
- [ ] Social preview image uploaded
- [ ] Default branch is `main`; branch protection requires CI to pass

**Substance**
- [ ] `make check` passes from a clean clone
- [ ] A brand-new clone reaches a populated dashboard with two commands
- [ ] All internal documentation links resolve
- [ ] `LICENSE` present and correct
- [ ] `CHANGELOG.md` newest entry matches `__version__`
