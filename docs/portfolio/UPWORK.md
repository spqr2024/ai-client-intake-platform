# Upwork Portfolio Entry

Copy-paste ready. Adjust names and links, then delete this line.

> **Honesty guardrail:** this is a self-directed product build. Everything below
> describes what the software does and how it is built — no invented client
> outcomes, no fabricated metrics. Clients verify claims by reading the repo, and
> a single unverifiable number costs more trust than it buys.

---

## Project title

*(Upwork truncates around 70–80 characters — front-load the value.)*

**AI Client Intake Platform — Conversational Lead Qualification SaaS**

Alternatives, depending on the niche you are targeting:

- `AI Chatbot That Qualifies & Scores Leads — Full-Stack SaaS (FastAPI + Next.js)`
- `Multi-Tenant AI Intake SaaS with CRM, Telegram Bot & Analytics`

---

## Project description

**Paste this into the Portfolio "Description" field.**

---

### The problem

Most businesses lose inbound revenue at the contact form. Multi-step forms are
reported to see over 67% abandonment, and the submissions that do arrive are
three fields and a vague sentence — so someone spends a week emailing back and
forth just to learn the budget, the timeline and the scope.

### What I built

A production-grade SaaS platform that replaces the form with an AI agent which
interviews every visitor, adapts its questions to their answers, scores the lead,
and delivers a structured brief to the sales team — with instant Telegram alerts
carrying one-tap Accept / Reject / Call actions.

**For the business owner it delivers:**

- **24/7 qualification** — no lead waits until Monday
- **Structured data instead of free text** — budget, timeline, scope, contact,
  captured consistently every time
- **Prioritised pipeline** — every lead is scored 0–100 automatically, so the
  best enquiries surface first
- **Mobile-first response** — accept or reject a lead from Telegram without
  opening a laptop
- **Answers, not just questions** — the bot answers prospect questions from an
  uploaded knowledge base (PDF, Word, Markdown), then returns to qualifying

### The engineering decision that matters

Handing lead qualification to an LLM creates three business problems:
unpredictable results, prompt-injection risk, and total dependence on a
third-party API.

So I built the intake flow as a **deterministic state machine** and used AI only
at the edges — rephrasing questions, writing summaries, compressing long
conversations — each with a working fallback. The result:

- The same answers always produce the same lead — qualification is auditable
- No prompt can trick the bot into skipping a qualification step
- **If the AI provider goes down, lead capture keeps working**
- The entire 136-test suite runs with no API keys, so CI is deterministic

That is the difference between an AI demo and software a business can run.

### What is included

- **Conversational widget** — streaming replies, quick-reply buttons, file
  uploads, English + Ukrainian
- **Visual workflow builder** — non-engineers edit the bot's questions,
  branching and validation in a UI, with live checks for unreachable steps and
  loops, plus a simulator to test a flow before publishing. No JSON required
- **Kanban CRM** — drag-and-drop pipeline, custom stages, tags, priorities,
  follow-up reminders, internal comments, full activity timeline
- **Conversation replay** — step through any past conversation to see exactly
  what the bot asked and why
- **Knowledge base** — upload PDF / DOCX / Markdown / TXT; semantic search;
  version history; and a report of *questions it could not answer* so you know
  what to document next
- **Telegram bot** — new-lead alerts with inline actions and deep links into the CRM
- **CRM export** — HubSpot, Pipedrive, Notion, Salesforce or any webhook
- **Analytics** — conversion funnel, drop-off by question, lead quality, average
  budget, AI capture confidence
- **Multi-tenant + white label** — isolated workspaces, each with its own
  branding, colours, bot name and knowledge base
- **Production operations** — Docker, health and readiness probes, Prometheus
  metrics, structured logging with request tracing, audit log, disaster-recovery
  runbook

### Technology

FastAPI · Python 3.12 · SQLAlchemy 2 · PostgreSQL · Redis · Next.js 15 · React 19
· TypeScript · Tailwind · Docker · GitHub Actions · Telegram Bot API ·
OpenAI / Anthropic / Gemini / OpenRouter

### Engineering standards

- **136 automated tests**, 84% backend coverage, enforced by a CI floor
- **CI runs** lint, formatting, type checking, both test suites, dependency
  vulnerability audits, Docker builds (verifying containers run as non-root),
  migration idempotency, and a live end-to-end smoke test
- **Security**: rotating refresh tokens with replay detection, role-based access,
  tenant isolation that returns 404 rather than confirming a record exists,
  Content-Security-Policy, audit logging, rate limiting and brute-force lockout
- **Documentation**: architecture, API reference, deployment, troubleshooting and
  disaster-recovery guides — with limitations stated openly, not hidden

### Try it yourself

Two commands from a clean clone produce a fully populated dashboard — 12 sample
leads, real transcripts, working analytics — with no API keys and no database
server to install.

---

## Skills to tag

Upwork's search weights these heavily; use all the relevant slots.

```
Python · FastAPI · Next.js · React · TypeScript · PostgreSQL · Redis · Docker
REST API · SaaS Development · Full-Stack Development · AI Chatbot
Artificial Intelligence · OpenAI API · LLM · RAG · Natural Language Processing
Telegram Bot · CRM · Lead Generation · Marketing Automation
API Integration · Software Architecture · CI/CD · Automated Testing
```

---

## Profile overview snippet

For the top of your Upwork profile — the first two lines are all most clients read.

> I build AI automation that businesses can actually run in production — not
> demos. My work pairs conversational AI with the boring parts that make it
> dependable: automated tests, health checks, audit logs and documentation.
>
> **Recent build:** a multi-tenant SaaS that replaces contact forms with an AI
> agent qualifying and scoring leads 24/7, with a kanban CRM, Telegram bot and
> analytics — FastAPI + Next.js, 136 tests, fully documented and deployable via
> Docker.
>
> I specialise in: AI/LLM integration (OpenAI, Anthropic, Gemini) · FastAPI &
> Python backends · Next.js & React frontends · Telegram bots · CRM and workflow
> automation · production deployment with Docker and CI/CD.
>
> Every project I deliver includes tests, deployment instructions and
> documentation a future developer can pick up without calling me.

---

## Proposal snippet

For proposals on AI-chatbot, lead-automation or intake jobs. Keep it short;
replace the bracketed line with something specific to their posting.

> Hi [Name] — [one specific sentence about their problem, proving you read it].
>
> I recently built exactly this kind of system: an AI intake agent that
> interviews website visitors, captures budget/timeline/scope, scores each lead
> and pushes it to the team's CRM and Telegram. It is open source, so you can
> read the code rather than take my word for it: [link]
>
> One design decision worth mentioning, because it is what makes these systems
> survive contact with real traffic: I keep the qualification logic
> deterministic and use the LLM only for phrasing and summaries. That means the
> bot cannot be talked into skipping questions, results are reproducible, and
> **lead capture keeps working even if the AI provider has an outage** — the
> failure mode that quietly costs the most money.
>
> For your project I would start with [their first concrete deliverable]. Happy
> to walk you through the demo — it runs locally in two commands.
>
> — [Your name]

---

## Portfolio media checklist

Upwork portfolio items with images get materially more views. Capture per
[SCREENSHOTS.md](../SCREENSHOTS.md):

- [ ] **Cover image** — `dashboard-kanban.png` (a populated pipeline reads as a
      real product instantly)
- [ ] `hero-chat.png` — the conversational widget in action
- [ ] `analytics-ai.png` — funnel and drop-off, proving business value
- [ ] `workflow-builder.png` — the no-code editor, which differentiates you
- [ ] `telegram-notification.png` — the mobile workflow clients recognise
- [ ] Optional: `demo-intake-to-lead.gif` — visitor to qualified lead in 15 seconds
- [ ] Repository link in the project URL field
