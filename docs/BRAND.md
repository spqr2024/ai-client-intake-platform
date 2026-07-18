# Brand & Visual Identity

This document **records the identity already implemented in the codebase** — it
does not propose a redesign. Every value below is the value the application
actually ships, with its source file cited so the two cannot drift.

---

## Product name

**IntakeAI** — used as the default `brand_company_name` fallback in the UI
(`frontend/app/page.tsx`) and throughout the documentation.

The repository is `ai-client-intake-platform`; "IntakeAI" is the product surface
name. Keep both — the descriptive repo name is what people search for, the short
product name is what they remember.

**Positioning line** (README opening, one sentence):

> Replace static contact forms with an AI agent that interviews prospects 24/7,
> qualifies and scores every lead, and hands your team a ready-to-act brief.

**Short slogan**, for the GitHub description, banner and social preview:

> *Conversational intake that qualifies leads while you sleep.*

> Note: the demo workspace deliberately brands itself **"Northwind Studio"**
> (`backend/app/demo.py`) — a fictional agency *using* IntakeAI. That separation
> is intentional: it demonstrates white-labelling rather than confusing the
> product with its customer. Do not "fix" this to match.

---

## Logo concept

The current mark is the **compass emoji 🧭**, used in the header, sidebar, admin
login and favicon.

**Why it fits and should be kept:** a compass means *guided direction* — which is
precisely what the product does to an unstructured enquiry. It reads at 16px, it
needs no design tooling, and it renders identically everywhere.

If commissioning a vector logo later, keep the concept and constrain it:

- A compass rose or needle, geometric, single weight
- Legible as a 16×16 favicon and as a monochrome 1-bit stamp
- Ships as SVG with a light and dark variant
- Pairs with the wordmark **IntakeAI** set in the UI typeface

Do not replace the compass with a generic robot or chat bubble — every AI product
uses those, and the differentiator here is *structured guidance*, not chat.

---

## Colour

Source of truth: `brand_primary_color` in
`backend/app/services/runtime_settings.py`, editable per workspace at
**Settings → Branding**.

| Role | Value | Where it appears |
|---|---|---|
| **Primary** | `#4f46e5` (indigo 600) | Chat widget header and bubbles, primary buttons, active nav, links |
| Ink | `#0f172a` / `#334155` | Headings / body copy |
| Muted | `#94a3b8` | Secondary labels, timestamps |
| Surface | `#ffffff` on `#f8fafc` | Cards on page background |
| Border | `#e2e8f0` | Card and input outlines |

### Status palette (validated, do not substitute casually)

These were checked for colour-vision-deficiency separation and contrast against
the light surface before being adopted (`frontend/app/admin/analytics/page.tsx`):

| Status | Hex |
|---|---|
| New | `#0284c7` |
| Qualified | `#059669` |
| In Progress | `#d97706` |
| Converted | `#7c3aed` |
| Rejected | `#e11d48` |
| Closed / Incomplete | `#94a3b8` (deliberately neutral — inactive states) |

Status is **never** communicated by colour alone; every badge carries its label.
Keep that rule if the palette is ever extended.

### White-label rule

Primary colour is per-workspace and applied inline at runtime, so a customer's
brand colour flows into the widget and emails automatically. Never hard-code
`#4f46e5` in new components — read it from branding, as `ChatWidget` does.

---

## Typography

**Geist** (`next/font/google`, `frontend/app/layout.tsx`), loaded with the
`latin` **and `cyrillic`** subsets — the product ships Ukrainian, and a font that
drops Cyrillic would render the UK locale in a fallback face.

| Use | Treatment |
|---|---|
| Page title | 24px / bold / `text-slate-900` |
| Section heading | 16px / semibold |
| Body | 14px / normal / relaxed leading |
| Metadata | 12px / `text-slate-400` |
| Numeric tiles | 24px / bold, above a 12px uppercase tracked label |

Use `font-mono` only for identifiers, JSON and code — never for prose.

---

## Voice

Consistent across UI copy, docs and error messages:

- **Plain, specific, unhurried.** "No leads yet — leads appear here as soon as a
  visitor finishes a chat," not "No data available."
- **Errors state the situation and the next action.** The KB uploader explains
  that a scanned PDF has no text layer *and* suggests pasting the text.
- **Never blame the user.** The bot says "I couldn't catch a number there,"
  not "Invalid input."
- **Claims are hedged honestly.** Documentation says what the offline embedder
  cannot do. That candour is part of the brand.

---

## Screenshot style

So the visual set looks like one system rather than ten sessions. Full capture
procedure in **[SCREENSHOTS.md](SCREENSHOTS.md)**; this is the aesthetic contract:

- **Populated, never empty.** Always shoot against demo data — empty states are
  for the empty-state screenshot only.
- **Consistent frame:** 1440×900 at 2× DPR, no browser chrome, 100% zoom, light theme.
- **One idea per image.** Scroll so the feature being demonstrated is fully
  visible; don't capture half a chart.
- **Show state, not chrome.** Prefer a card mid-drag or a validation panel open
  over a pristine idle screen.
- **No real data.** Demo names and addresses only; check the browser profile for
  personal bookmarks or avatars before shooting.

---

## GitHub banner & Open Graph image

Neither is committed yet (see [SCREENSHOTS.md](SCREENSHOTS.md)). Specification
so whoever produces them stays on-identity:

### Social preview / Open Graph — `docs/images/og-banner.png`
- **1280×640** (GitHub renders 1280×640; Twitter/LinkedIn crop to ~1.91:1)
- Left third: 🧭 mark + **IntakeAI** wordmark + the slogan, on `#0f172a`
- Right two-thirds: the kanban or chat screenshot, bled off the right edge
- One accent only: `#4f46e5`. No gradients, no stock photography, no drop shadows
- Body text ≥ 24px so it survives timeline downscaling
- Upload at **Settings → General → Social preview**

### README banner (optional) — `docs/images/banner.png`
- **1600×400**, same lockup, wider and shorter
- Place directly under the `# 🧭 AI Client Intake Platform` heading, above the badges
- Skip it if the screenshot grid is already carrying the page; a banner that adds
  nothing but scroll depth is worse than none

---

## Consistency checklist

Run before publishing anything public-facing:

- [ ] Product name is **IntakeAI** everywhere (repo name may stay descriptive)
- [ ] Demo workspace remains **Northwind Studio** — the white-label demonstration
- [ ] Primary colour read from branding settings, never hard-coded in components
- [ ] Status colours match the validated palette; every badge shows its label
- [ ] Geist loaded with the Cyrillic subset
- [ ] Screenshots share one viewport, theme and zoom level
- [ ] Slogan identical in README, GitHub description and OG image
