# LinkedIn Content

Copy-paste ready. Replace `[link]` with the repository URL.

> **Honesty guardrail:** no invented adoption, users or revenue. Describe what
> was built and why the decisions were made — engineers who read carefully are
> exactly the audience worth impressing.

---

## Featured project entry

**Project name**
> AI Client Intake Platform — Conversational Lead Qualification SaaS

**Description** (LinkedIn cuts around 300 characters in preview — the first two
lines carry the weight):

> Multi-tenant SaaS that replaces contact forms with an AI agent: it interviews
> visitors 24/7, captures budget and timeline, scores each lead 0–100, and pushes
> a structured brief to a kanban CRM and Telegram.
>
> Built with FastAPI + Next.js 15. The core design decision: intake runs on a
> deterministic state machine, with the LLM only rephrasing questions and writing
> summaries — so results are reproducible, the flow can't be prompt-injected, and
> lead capture keeps working during an AI provider outage.
>
> 136 automated tests · 84% coverage · Docker · CI with dependency auditing,
> non-root image verification and migration checks. Fully documented, including
> its limitations.

---

## Skills to add

```
FastAPI · Python · Next.js · React · TypeScript · PostgreSQL · Redis · Docker
Artificial Intelligence (AI) · Large Language Models (LLM) · OpenAI API
Retrieval-Augmented Generation (RAG) · Software Architecture · SaaS
REST APIs · CI/CD · Test Automation · Multi-Tenant Architecture · Telegram Bot API
```

---

## Announcement post

The engineering-decision angle outperforms feature lists — it gives readers
something to agree or argue with.

> I shipped an AI intake platform, and the most important decision was how much
> to let the AI decide.
>
> The premise is simple: contact forms lose leads. Multi-step forms are reported
> to see 67%+ abandonment, and the submissions that arrive are three fields and
> "interested in a website" — so a week disappears into emails discovering budget
> and scope.
>
> An AI agent that interviews visitors fixes that. But handing lead
> qualification to an LLM creates three problems a business can't accept:
>
> ❌ Results aren't reproducible — the same answers can produce different leads
> ❌ Prompt injection can talk the bot out of qualifying anyone
> ❌ When the provider has an outage, you stop capturing leads entirely
>
> So I inverted the usual architecture. The intake flow is a deterministic state
> machine — each step declares what it captures, how to validate it and where to
> branch. The LLM only rephrases questions, writes summaries and compresses long
> conversations, and every one of those has a working fallback.
>
> What that buys:
>
> ✅ Same answers → same lead, every time. Qualification is auditable
> ✅ No prompt can skip a qualification step — progression isn't a prompt decision
> ✅ If OpenAI is down, intake keeps running; the phrasing just gets plainer
> ✅ All 136 tests run with zero API keys, so CI is deterministic and free
>
> The trade-off is real: it's less conversationally fluid than a pure-LLM agent.
> For lead capture, I'll take predictable over eloquent every time.
>
> The rest is the unglamorous work that makes software survive production:
> multi-tenant isolation, rotating refresh tokens, a retrying delivery queue so a
> Telegram outage delays a notification instead of losing it, Prometheus metrics,
> and a disaster-recovery runbook.
>
> It's open source, limitations documented openly: [link]
>
> If you're building with LLMs, I'd genuinely like to hear where you draw the
> line between deterministic logic and model output. I suspect most of us are
> still calibrating.
>
> #AI #SoftwareArchitecture #FastAPI #NextJS #LLM #SaaS

---

## Alternative post — the audit angle

Shorter, and unusually credible because most people only publish successes.

> I audited my own codebase last week and found four real bugs. The most
> instructive one:
>
> My structured JSON logs were invalid JSON.
>
> The format string interpolated the log message inside quotes. Any message
> containing a double quote — which is *every* HTTP access log — produced
> unparseable output. In production, a log aggregator would have silently dropped
> them. I'd have been debugging blind while believing I had observability.
>
> The other three:
>
> → Delayed retry tasks could be garbage-collected before running, quietly
>   weakening the retry guarantee for every notification
> → Uploaded files were stored and listed in the UI, but had no download route —
>   a half-built feature nobody had clicked
> → SQLite silently ignores foreign keys unless you enable a pragma, so my
>   carefully declared ON DELETE rules were doing absolutely nothing
>
> Two were caught by tests I wrote *during* the audit. That's the argument for
> tests that most "we have 90% coverage" conversations miss: coverage measures
> lines executed, not assumptions challenged.
>
> Lesson I keep relearning: verify claims your system makes about itself.
> "Structured logging" was in my README before it was true.
>
> #SoftwareEngineering #Testing #CodeQuality #Observability

---

## Headline options

```
Full-Stack Engineer · AI Automation & SaaS · FastAPI + Next.js
Building production AI systems that survive real traffic | FastAPI · Next.js · LLMs
Full-Stack & AI Engineer — conversational automation, CRM integrations, SaaS platforms
```

---

## About section snippet

> I build AI automation that runs in production, not just in demos.
>
> The gap between the two is rarely the model — it's everything around it:
> deterministic fallbacks for when the provider is down, tests that don't need an
> API key, tenant isolation that doesn't leak, and documentation that admits what
> the system can't do.
>
> Most recently I built a multi-tenant AI intake SaaS: an agent that interviews
> website visitors, scores leads and delivers structured briefs to a kanban CRM
> and Telegram — FastAPI + Next.js, 136 tests, Docker, full operational
> documentation.
>
> **I work on:** AI/LLM integration · FastAPI and Python backends · Next.js and
> React frontends · Telegram bots · CRM and workflow automation · production
> deployment with Docker and CI/CD.

---

## Posting notes

- **Tuesday–Thursday, 8–10am** in your audience's timezone performs best
- Put `[link]` in the **first comment** if reach matters — LinkedIn suppresses
  posts with outbound links; put it in the post if credibility matters more
- Lead with the decision or the failure, never with the tech stack
- Reply to every comment in the first two hours; it compounds distribution
- Attach `dashboard-kanban.png` or the intake GIF — posts with media do better,
  and a populated screenshot proves the thing is real
