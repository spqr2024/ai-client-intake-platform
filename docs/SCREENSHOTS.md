# Screenshot & GIF Capture Guide

Visual assets are **generated locally rather than committed pre-baked**, so they
always match the code in your checkout. This guide makes capturing the full set
a ~15 minute job with reproducible framing.

> **Why this file exists:** the repository was developed in a headless
> environment with no browser automation available, so the images could not be
> produced automatically. Everything needed to produce them is specified here —
> exact routes, states, framing and filenames — and the README already contains
> the wired-up markdown, so dropping files into `docs/images/` completes it with
> no further edits.

---

## 0. Prepare a clean, populated environment

Demo mode only seeds a workspace that has **zero leads**, so start from a fresh
database to get the full dataset.

```bash
# Terminal 1 — API with a freshly provisioned demo workspace
cd backend
rm -f data/intake.sqlite3            # ensures demo provisioning runs
DEMO_MODE=true ../backend/.venv/Scripts/python -m uvicorn app.main:app --port 8000
#  (or simply:  make demo)

# Terminal 2 — web app
cd frontend && npm run dev
```

Sign in at <http://localhost:3000/admin> with **`admin@example.com` /
`admin12345`**.

### Capture settings (keep these constant across all shots)

| Setting | Value | Why |
|---|---|---|
| Viewport | **1440 × 900** | Standard laptop; avoids ultrawide letterboxing |
| Device pixel ratio | **2×** (Retina) | Text stays sharp when GitHub scales the image |
| Browser chrome | **Hidden** | Capture the viewport only, not tabs/bookmarks |
| Theme | Default light | The app ships light-first |
| Zoom | 100% | |
| Format | **PNG** for stills, **GIF** (or MP4→GIF) for motion | |
| Max width | Downscale to **1600px**, target **< 500 KB** each | Keeps `git clone` fast |

**Chrome DevTools recipe:** `F12` → device toolbar (`Ctrl+Shift+M`) →
Responsive → `1440 × 900`, DPR 2 → `Ctrl+Shift+P` → "Capture screenshot".

**Mobile shots:** same menu, choose **iPhone 14 Pro (393 × 852)**.

---

## 1. Still screenshots — the required set

Save into `docs/images/` using **exactly these filenames** (the README already
references them).

| # | File | Route | State to set up | What it must prove |
|---|---|---|---|---|
| 1 | `hero-chat.png` | `/` | Open the widget, answer 3–4 questions so the transcript shows quick replies **and** a typing indicator | The product's core idea in one image |
| 2 | `dashboard-kanban.png` | `/admin` → **Kanban** | Default demo data; drag one card mid-flight if your tool captures it | A real CRM pipeline, not a list |
| 3 | `lead-detail.png` | `/admin/leads/1` | Overview tab; scroll so AI summary + transcript are both visible | AI output feeding a usable record |
| 4 | `conversation-replay.png` | `/admin/leads/1` → **Conversation replay** | Press ▶ Replay, capture mid-playback with node metadata visible | The differentiator most products lack |
| 5 | `analytics-ai.png` | `/admin/analytics` | Scroll to **AI conversation analytics** (funnel + drop-off) | Business value, not vanity metrics |
| 6 | `workflow-builder.png` | `/admin/workflows` | Expand a step card; make the amber validation panel visible | Non-engineers can edit the flow |
| 7 | `knowledge-base.png` | `/admin/kb` | Scroll so stat tiles + a document's index status are visible | Document management with real state |
| 8 | `settings-integrations.png` | `/admin/settings` → **Integrations** | Shows registered CRM adapters + delivery log | Credible integration surface |
| 9 | `telegram-notification.png` | Telegram | Requires a real bot token — see §3 | The mobile workflow |
| 10 | `mobile-dashboard.png` | `/admin` @ 393×852 | Open the hamburger drawer | Genuine responsive design |

---

## 2. GIF walkthroughs — the required set

Keep each **under 15 seconds** and **under 4 MB**. Record at 1440×900, then
downscale to 1000px wide and cap at 12 fps.

| # | File | Story to tell | Steps to record |
|---|---|---|---|
| 1 | `demo-intake-to-lead.gif` | *A visitor becomes a qualified lead* | Open `/` → chat widget → answer name, service (**Online store**), platform, goals, budget `$5000`, timeline, email → summary appears → cut to `/admin` showing the new lead at the top |
| 2 | `demo-kanban.gif` | *Managing the pipeline* | `/admin` → Kanban → drag a card from **New** to **Qualified** → open the lead → change priority → add an internal comment |
| 3 | `demo-workflow-builder.gif` | *Editing the bot without code* | `/admin/workflows` → add a step from the library → edit its question → add a branching rule → **▶ Test flow** → run the simulator |
| 4 | `demo-kb-upload.gif` | *Teaching the bot* | `/admin/kb` → **Upload document** (pick a PDF) → status goes `pending → indexed` → open `/` and ask a question the document answers → bot replies from the KB |

**Recording tools:** [ScreenToGif](https://www.screentogif.com/) (Windows),
[Kap](https://getkap.co/) (macOS), [Peek](https://github.com/phw/peek) (Linux).
Optimise afterwards with `gifsicle -O3 --lossy=80 in.gif -o out.gif`.

---

## 3. Optional: real Telegram screenshot

Screenshot 9 needs a live bot. Roughly five minutes:

1. Create a bot with [@BotFather](https://t.me/BotFather); copy the token.
2. Put `TELEGRAM_BOT_TOKEN=…` in `.env`; message your bot once so it can reply.
3. Get your chat id: `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"`.
4. Paste it into **Settings → Notifications → Telegram chat ID**.
5. Expose the API and register the webhook (see
   [DEPLOYMENT.md §8](DEPLOYMENT.md#8-telegram-webhook-registration)):
   ```bash
   ngrok http 8000
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -d "url=https://<ngrok-host>/api/webhook/telegram" \
     -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
   ```
6. Complete a chat on `/`; screenshot the Telegram card with its ✅ / ❌ / 📞
   buttons and the **Open in CRM** deep link.

If you skip this, delete the Telegram row from the README table rather than
leaving a broken image.

---

## 4. Checklist

Copy into your PR description while working through it.

**Setup**
- [ ] Fresh database (`rm backend/data/intake.sqlite3`) so demo data seeds
- [ ] Backend running with `DEMO_MODE=true`; frontend running
- [ ] Viewport 1440×900 @ 2× DPR, browser chrome hidden
- [ ] `docs/images/` directory created

**Stills**
- [ ] `hero-chat.png`
- [ ] `dashboard-kanban.png`
- [ ] `lead-detail.png`
- [ ] `conversation-replay.png`
- [ ] `analytics-ai.png`
- [ ] `workflow-builder.png`
- [ ] `knowledge-base.png`
- [ ] `settings-integrations.png`
- [ ] `telegram-notification.png` *(optional — needs a bot token)*
- [ ] `mobile-dashboard.png` *(393×852)*

**GIFs**
- [ ] `demo-intake-to-lead.gif`
- [ ] `demo-kanban.gif`
- [ ] `demo-workflow-builder.gif`
- [ ] `demo-kb-upload.gif`

**Quality pass**
- [ ] No real personal data visible (demo data only — check the browser profile)
- [ ] No API keys, tokens or `.env` contents in any frame
- [ ] Each still < 500 KB; each GIF < 4 MB
- [ ] Images render correctly in the README preview
- [ ] Total `docs/images/` weight < 15 MB

---

## 5. Wiring them in

The README's Screenshots section already contains the markdown; it currently
shows the capture guide instead of images. Once the files exist, replace that
section with:

```markdown
## 📸 Screenshots

|  |  |
|---|---|
| ![Conversational intake](docs/images/hero-chat.png)<br>**Conversational intake** — adaptive questions, quick replies, streaming | ![Kanban CRM](docs/images/dashboard-kanban.png)<br>**Kanban CRM** — drag-and-drop across workspace-defined stages |
| ![Lead detail](docs/images/lead-detail.png)<br>**Lead detail** — AI summary, transcript, activity timeline | ![Conversation replay](docs/images/conversation-replay.png)<br>**Conversation replay** — step-by-step with workflow-node metadata |
| ![AI analytics](docs/images/analytics-ai.png)<br>**AI analytics** — funnel, drop-off by node, capture confidence | ![Workflow builder](docs/images/workflow-builder.png)<br>**Visual workflow builder** — no JSON required |

### Walkthroughs

**Visitor → qualified lead**
![Intake to lead](docs/images/demo-intake-to-lead.gif)

**Editing the bot without code**
![Workflow builder](docs/images/demo-workflow-builder.gif)
```
