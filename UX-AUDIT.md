# LeadForge — UX, Accessibility & Performance Audit

> Measured, not assumed. Every number below comes from running axe-core,
> Playwright and the live API against the running app. Companion to
> `ROADMAP.md` (which covers the product roadmap); this document covers the
> *experience* of using the thing.

---

## 1. How this was measured

| Tool | What it measures | Where it lives |
|---|---|---|
| **axe-core 4.13** | WCAG 2.1 A/AA + best-practice violations | `dashboard/e2e/a11y.spec.ts` (now a CI gate) |
| **Playwright** | Layout shift, LCP/FCP, API-call count, asset 404s | `dashboard/e2e/a11y.spec.ts` |
| **Live API** | Endpoint latency and query count | profiled per route |

The audit ran against a **production build** (`next build` + the standalone
server), not `next dev`, against a live API with real data.

---

## 2. Accessibility — before and after

### Baseline (before this pass)

```
[moderate] region          nodes=50   routes=10/10   "All page content should be contained by landmarks"
[serious ] color-contrast  nodes=53   routes=9/10    fg=#94a3b8 bg=#ffffff ratio=2.56 need=4.5:1
[moderate] heading-order   nodes=2    routes=2
[critical] select-name     nodes=1    routes=1      "Select element must have an accessible name"
```

**48 of the 53 contrast failures were one class**: `text-slate-400`
(`#94a3b8`) on white is **2.56:1** where WCAG AA needs **4.5:1**. Tailwind's
`slate-400` is a common "muted label" colour and it simply is not readable —
which matters more here than most products, because a lot of LeadForge
operators work on cheap laptop panels in bright Indian offices.

**The `region` failures were structural**: the sidebar's brand block and
footer sat outside any landmark, and the TopBar was not a `<header>`, so a
screen reader had no way to jump between the page banner, the navigation and
the content.

### What was fixed

| Fix | Detail |
|---|---|
| Landmarks | `<aside aria-label="Primary">` around the rail, `<header>` for the brand bar, `<nav aria-label="Main">` for the nav, `<footer>` for the promo/docs, `<header>` for the TopBar, `<main id="main-content">` for the content |
| `aria-current` | The active nav item now says `aria-current="page"` instead of only looking different |
| `aria-expanded` / `aria-controls` | The sidebar collapse toggle now states what it controls |
| Decorative icons | `aria-hidden="true"` on every icon that carries no meaning of its own |
| Contrast | `text-slate-400` → `text-slate-500`/`600`; `text-emerald-600` → `700`; `text-red-600` → `700` |
| Focus visibility | A visible focus ring on every interactive element (there was **none** — a keyboard user could not tell where they were) |
| Reduced motion | `motion-safe:` variants replace bare `transition-all`, so the UI respects `prefers-reduced-motion` |
| Focus management | The mobile drawer moves focus in on open, traps Tab, and restores focus to the trigger on close |
| `aria-live` | Loading and status changes are announced, not just drawn |
| Form labels | The unlabelled `<select>` now has a real `<label>` |
| Heading order | Headings are sequential on every route |
| `main` / `h1` | Exactly one `<main>` and one `<h1>` per page — now asserted by a test |

### The gate

`dashboard/e2e/a11y.spec.ts` runs axe-core against all ten routes and
**fails the build** on any `critical` or `serious` violation. It also
asserts one `<main>`, one `<h1>`, no failed asset loads, and CLS < 0.1.

CI gained two jobs:

```
frontend-a11y   Accessibility & Layout Stability   -> playwright test e2e/a11y.spec.ts
frontend-e2e    End-to-End Suite                   -> playwright test
```

This is the durable fix. An accessibility regression should be as loud as a
type error.

---

## 3. Performance — before and after

Measured on a **500,000-lead** database.

### Data paths

| Path | Before | After | Speed-up |
|---|---|---|---|
| CSV import, 5,000 rows | 11.95 s | **0.23 s** | **52×** |
| CSV re-import | 5.10 s | **0.32 s** | 16× |
| Lead search, selective term | 200 ms | **8 ms** | 25× |
| Lead search, no match (a typo) | 427 ms | **2 ms** | **200×** |
| Lead list | — | **10 ms** | — |
| Analytics timeseries | — | **1.9 ms** | — |
| Enrichment, whole flow | 8.14 s | **0.62 s** | 13× |
| Homepage fetches per lead | 5 | **1** | 5× |
| Suppression checks per campaign | N queries | **1** | N× |

### The dashboard

| Route | Load | FCP | LCP | CLS | API calls |
|---|---|---|---|---|---|
| `/` | 661 ms | 44 ms | 44 ms | **0.214** | 5 |
| `/leads` | 600 ms | 24 ms | 52 ms | **0.28** | 3 |
| `/find` | 581 ms | 40 ms | 40 ms | 0 | 1 |
| `/sequences` | 566 ms | 24 ms | 24 ms | **0.087** | 3 |
| `/inbox` | 564 ms | 24 ms | 24 ms | 0 | 2 |
| `/scrape` | 567 ms | 24 ms | 24 ms | 0.006 | 2 |
| `/settings` | **1196 ms** | 28 ms | 28 ms | 0.011 | 3 |
| `/companies` | 565 ms | 24 ms | 88 ms | 0.031 | 2 |
| `/email-health` | 569 ms | 24 ms | 24 ms | 0 | 2 |
| `/setup` | 574 ms | 24 ms | 68 ms | 0 | 2 |

**Two problems that only a real browser could find:**

1. **CLS 0.21–0.28 on the two most-used pages.** The pages rendered a short
   "Loading your lead database…" placeholder and then swapped in a much
   taller table, pushing everything down under the user's cursor. Google
   treats CLS > 0.1 as poor. The fix is a skeleton whose dimensions match the
   real content.

2. **`/settings` took twice as long as every other route** (1196 ms vs
   ~570 ms) — sequential awaits that could run concurrently.

### Bundle

`recharts` and its d3 dependencies were ending up in the **shared** chunk, so
every route — the inbox, the scraper, the settings page — downloaded a
charting library that only the overview ever renders. The chart now lives in
its own module and is loaded on demand.

---

## 4. Usability — what a person actually experiences

These came from reading the rendered screens, not from any tool.

### The lead table is unusable on a phone

The table is `min-w-[1560px]` inside a 356 px container on a 390 px phone.
The user sees a checkbox, a truncated name and a sliver of the score — the
phone number, the email and the actions are all off-screen behind a
horizontal scroll with no affordance. **A lead database that cannot show you
a phone number on a phone is not a lead database.** Below `md` the table
becomes a card list.

### Two search boxes doing the same thing

There is a global search in the TopBar and a page-level search on the Lead
Database, both filtering the same thing. Whichever one you use, the other
still looks like it is waiting for input.

### A half-finished control

"Save current filters as view…" with a greyed **Save** button sits between
the filter row and the table. It reads as a broken form rather than a
feature.

### The overview shows good news as a warning

Under **NEEDS ATTENTION**:

> ○ 26 contacts await verification
> ○ **0 addresses on the global suppression list**

"0 addresses on the suppression list" is *good*. Listing it as something
needing attention is a straight category error.

### Two of four headline numbers are always zero

"Emails Sent 0" and "Open Rate 0%" sit next to "Total Leads 83" and
"Verified Emails 50". The open-rate card also explains itself as "Tracked
via 1×1 pixel telemetry" — but open tracking is **off by default** because
the tracking pixel is a primary-inbox killer. So the card always reads 0%
and always gives the wrong reason.

### The demo data looks like your data

A fresh install seeds 83 sample businesses and the overview says "83
businesses in your database". Nothing said otherwise. The API now returns
`is_demo` so those rows can be labelled for what they are.

### Scores with decimals

Leads displayed as "84.35 HOT" and "14.35 COLD". A 0–100 score with two
decimals reads as broken. The trust modifier is still applied at full
precision internally — that is what makes a directory lead actually score
below a live Google Maps lead — but the number the operator sees is now a
whole number.

### A buzzword title

The overview is called **"Autonomous Outreach Hub"**. It does not tell the
operator what to do or what state they are in.

---

## 5. Bugs found by looking, not by tooling

| Bug | Consequence |
|---|---|
| `next start` does not work with `output: "standalone"` | The CI e2e suite was pointed at a server that serves the HTML shell while every JS chunk 404s — the page loads and the client JavaScript never does, so the app sits on a spinner forever. The suite would have "passed" against a dead page. |
| The standalone build does not include the static assets | Docker copies them by hand; locally nobody did, so a local production build was equally broken. `scripts/start-prod.mjs` now does it everywhere. |
| `saved_list` was not registered in `app/models/__init__.py` | `create_all` silently created **no** `saved_lists` table on a fresh database, and the FTS triggers failed with "no such table: businesses". |
| The lead-score column was a float | "84.35 HOT" |
| "Enrich everything" took the newest N rows | It re-enriched the same leads on every run and never reached the ones that had never been enriched |
| Seeded demo rows were indistinguishable from real leads | "83 businesses in your database" when those 83 are samples |

---

## 6. What is still open

- **The People table.** Apollo's core surface is one row per *person*,
  filterable by title. LeadForge only has a company table. This is the
  largest remaining product gap and it needs a `/api/v1/contacts` endpoint
  plus real decision-maker extraction.
- **Live ICP-relative scoring.** The score is currently a global
  contact-completeness number; Apollo's is relative to the saved search.
- **Field-level ICP filters.** "50 employees", "revenue over 10cr" and
  "Shopify" are reported as unsupported rather than silently ignored, but
  they are still not filterable.
- **A real analytics funnel.** sent → delivered → opened → replied →
  positive → meeting. Only four flat counters exist today.
- **The India moat.** GSTIN/Udyam, WhatsApp-first routing, festival and
  IST send windows, regional-language copy. These are what make an Apollo
  clone irrelevant in India — and every one of them is either absent or
  built-but-unwired.
