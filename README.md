# LeadForge 🚀
### Autonomous Lead Scraping, Apollo-Grade Waterfall Enrichment, AI Icebreakers & Cold Outreach Platform

<div align="center">

[![GitHub Stars](https://img.shields.io/github/stars/Aryanban/leadforge?style=for-the-badge&logo=github)](https://github.com/Aryanban/leadforge)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js 15](https://img.shields.io/badge/Frontend-Next.js%2015-black.svg?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Native%20Server-8A2BE2.svg?style=for-the-badge)](https://modelcontextprotocol.io/)
[![Twenty CRM](https://img.shields.io/badge/CRM-Twenty%20Compatible-indigo.svg?style=for-the-badge)](https://twenty.com/)
[![Tests Passing](https://img.shields.io/badge/Tests-191%2F191%20Passing_(100%25)-10b981.svg?style=for-the-badge&logo=pytest&logoColor=white)](https://github.com/Aryanban/leadforge)
[![Docker](https://img.shields.io/badge/Deployment-Docker%20Compose-2496ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

<br />

**A 100% self-hosted, full-stack B2B lead generation, waterfall contact enrichment, deliverability validation, and cold email outreach platform. Zero subscriptions. Zero per-lead API costs.**

[System Architecture](#-system-architecture) • [Feature Matrix & Cost Comparison](#-why-leadforge-cost--feature-comparison) • [Core Engineering Innovations](#-core-engineering-innovations) • [Technical Specifications](#-technical-specifications--engineering-decisions) • [Quickstart Guide](#-quick-start) • [Portfolio & Evaluation Showcase](#-engineering-portfolio--technical-evaluation-showcase)

</div>

---

## 📌 Executive Overview & Enterprise Problem Statement

Modern B2B revenue and agency teams spend thousands of dollars annually on SaaS data vendors (Apollo.io, Hunter.io, Lemlist, Outscraper) that gate public business data behind restrictive monthly credits. In addition to high per-lead fees, naive crawlers and sales automation tools suffer from critical engineering bottlenecks:
1. **Aggressive Anti-Bot Mitigation**: Traditional scraping scripts trigger IP bans, captchas, and bot challenges when traversing dense map nodes.
2. **Domain Reputation Destruction**: Outbound campaigns sent to unverified addresses or catch-all mail servers suffer severe bounce penalties (`550 User Not Found`), permanently burning sender domains.
3. **Obfuscated Contact Footprints**: Modern corporate websites utilize Cloudflare Email Obfuscation (`data-cfemail` XOR tokens) and anti-scraping text mutations (`[at]`, `[dot]`), defeating simple regex parsers.
4. **Generic AI Hallucinations**: Standard LLM outreach generators produce bland, templated pitches that trigger commercial spam filters.

**LeadForge** resolves these challenges through a unified, self-hosted autonomous architecture:
* **Concurrent HTTP Maps Scraper**: Speaks Google's internal protobuf `pb=` transport directly, so listings are parsed straight out of `APP_INITIALIZATION_STATE` with no browser in the loop — and a viewport-grid sweep fans queries out concurrently to blow past the ~20-results-per-query ceiling.
* **Seed-First Email Discovery & Non-Blocking Verification**: Reverses Cloudflare `data-cfemail` tokens, harvests real addresses as *seed evidence*, then **learns each domain's actual format** instead of guessing. Verification runs in a thread pool, groups candidates per domain to reuse one MX connection, and classifies into a 20-status enum via a multi-probe catch-all sentinel — never defaulting to valid.
* **Catch-All Sentinel & 80+ Spam Trigger Linter**: Identifies permissive mail servers and lints subject/body copy against 80+ commercial spam triggers before delivery.
* **Algorithmic 1-on-1 AI Icebreakers**: Analyzes business reviews, sentiment ratings, and municipal pain points to craft tailored hooks.
* **Native Model Context Protocol (MCP)**: Empowers autonomous AI agents (Google Antigravity, Claude, Cursor) to manage prospecting, enrichment, and cold campaigns end-to-end.

---

## 💡 Why LeadForge? (Cost & Feature Comparison)

| Feature | **LeadForge** | **Apollo.io** | **Hunter.io** | **Outscraper** | **Lemlist** |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Monthly Cost** | **$0 / Free Forever** | $99 / mo | $49 / mo | ~$50 / 10k leads | $149 / mo |
| **Lead Limits** | **Unlimited** | 1,000 credits/mo | 500 searches/mo | Pay-per-record | 2,500 leads |
| **Self-Hosted / Local Private Data** | **Yes (100% Local)** | No (SaaS Cloud) | No (SaaS Cloud) | No (SaaS Cloud) | No (SaaS Cloud) |
| **Google Maps Scraping** | **Built-in (HTTP `pb=` + Stealth fallback)** | Add-on | Not included | API only | Not included |
| **Cloudflare `data-cfemail` Decoding** | **Yes (Native XOR cipher)** | No | No | No | No |
| **Email Pattern Learning** | **Yes (per-domain inference from harvested seeds)** | Proprietary | Paid Add-on | No | No |
| **Catch-All & Safe SMTP Verification** | **Yes (multi-probe catch-all, 20-status enum, never defaults to valid)** | Paid | Yes | No | Add-on |
| **Cold Email Spam & Deliverability Linter**| **Yes (80+ words, 0-100 score)** | No | No | No | Included |
| **Algorithmic 1-to-1 AI Icebreakers** | **Yes (Sentiment & pain points)** | Paid Add-on | No | No | Included |
| **Multi-Step Sequences & Bounce Guard** | **Yes (Delay days, hard/soft bounce auto-suppress)**| Included | Add-on | No | Included |
| **AI Agent Native (MCP Server)** | **Yes (Claude, Cursor, AGY)** | No | No | No | No |
| **Open-Source CRM Integration** | **Twenty CRM & Webhooks** | HubSpot / SF only | Zapier only | Webhooks only | Zapier only |

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Frontend ["Presentation Layer (Next.js 15 UI / Tailwind CSS)"]
        UI["Web App (localhost:3000)"]
        ScrapeUI["/scrape (Google Maps Jobs)"]
        LeadsUI["/leads (Database Hub & Scoring)"]
        CampaignUI["/campaigns (Cold Sequencer)"]
        SpamUI["Spam Linter & AI Icebreaker Modals"]
        SettingsUI["/settings (Mailboxes & MCP)"]
    end

    subgraph Backend ["Application Layer (FastAPI & Native MCP Server)"]
        API["FastAPI REST API (/api/v1)"]
        MCP["Native MCP Server (stdio JSON-RPC 2.0)"]
        MapsScraper["Concurrent HTTP + Stealth Fallback"]
        WaterfallEnricher["Waterfall Permutation Engine"]
        CloudflareDecoder["Cloudflare XOR Deobfuscator"]
        SMTPVerifier["DNS MX & Catch-All Probe"]
        SpamLinter["80+ Keyword Deliverability Linter"]
        IcebreakerEngine["Sentiment & Review Hook Engine"]
        Scorer["0-100 Lead Quality Scorer"]
        TwentySync["Twenty CRM & Webhook Sync Engine"]
    end

    subgraph Storage ["Persistence & Queue Layer"]
        DB[("Async SQLite / PostgreSQL")]
        Redis[("Redis 7 / Task Broker")]
    end

    UI --> API
    API --> MapsScraper
    API --> WaterfallEnricher
    WaterfallEnricher --> CloudflareDecoder
    API --> SMTPVerifier
    API --> SpamLinter
    API --> IcebreakerEngine
    API --> Scorer
    API --> TwentySync
    MapsScraper --> DB
    WaterfallEnricher --> DB
    TwentySync -->|"REST / JSON"| TwentyCRM["Twenty CRM / Webhook"]
    MCP --> API
    API --> Redis
```

---

## ⚡ Core Engineering Innovations

### 1. Concurrent HTTP Maps Scraping & Anti-Detection Fallback
* **Concurrent HTTP Maps Scraper (Primary Path)**: Reverse-engineers Google's internal `search?tbm=map&pb=...` protobuf endpoint — the same transport the Maps frontend itself uses. Parses the `APP_INITIALIZATION_STATE` payload directly, so it extracts **name, phone, address, rating, review count and coordinates with no browser at all**. A viewport-grid sweep fans queries out concurrently across a locality, which is how production tools scale past the ~20-results-per-query ceiling.
* **Playwright Stealth Fallback**: If the HTTP path is blocked or returns an empty payload, a headless-Chromium scraper takes over. Route interception aborts stylesheets, web fonts, tracking beacons and media (`**/*.{png,jpg,jpeg,svg,woff,woff2,ttf}`) for a **3x–5x reduction in bandwidth**, plus humanized deceleration and viewport jitter to avoid bot fingerprinting.
* **Humanized Deceleration & Viewport Jitter**: Simulates randomized mouse curves and natural scrolling velocities, avoiding bot fingerprinting.
* **Unclaimed GBP Detection**: Evaluates DOM nodes for the canonical *"Claim this business"* anchor, immediately classifying listings with highest agency acquisition value.

### 2. Seed-Driven Pattern Inference & Cloudflare XOR Deobfuscation
* **Cloudflare Email Deobfuscation**: Corporate websites protected by Cloudflare mask emails using a single-byte XOR key in hex format (`<a data-cfemail="a1...">`). LeadForge reverses this cipher dynamically:
  $$\text{char}_i = \text{hex\_byte}_i \oplus \text{xor\_key}$$
* **Seed Harvest First, Guess Second**: Instead of fabricating permutations from a *company* name (“Acme Realty Group” → `acme.realty@`), LeadForge first harvests **real** addresses already exposed on the site, then **learns that domain's actual format** from the seed set. A `john.doe@` on the team page tells us the domain is `{first}.{last}` — so we stop guessing and generate only what the evidence supports.
* **Confidence-Blended Inference**: `infer_pattern()` scores each candidate format by observed dominance blended against a global prior, so one ambiguous seed never overrides what most domains actually do. Candidates are ranked, verified, and the walk stops at the first deliverable address.
* **Direct Socket SMTP Handshake**: Resolves authoritative DNS MX records and conducts low-latency socket handshakes (`HELO` $\rightarrow$ `MAIL FROM` $\rightarrow$ `RCPT TO`) without sending actual messages, eliminating third-party API verification costs.

### 3. Honest Deliverability Intelligence (Never Reports Unknown as Valid)
* **20-State Normalized Enum**: Every verification returns a typed `VerificationResult` — `valid`, `invalid`, `catch_all`, `catch_all_unknown`, `disposable`, `role_account`, `free_email`, `greylisted`, `unknown`, `blocked`, `syntax_error`, `domain_error`, `no_mx`, `smtp_error`, `timeout`, `spamtrap`, `abuse`, `do_not_mail`, `mailbox_full`, `gibberish`, `possible_typo` — carrying a `confidence` score and the raw `smtp_detail` for auditing.
* **The Critical Correctness Fix**: earlier versions returned `valid` on *every* SMTP failure. A blocked port 25, a greylisting server, or an anti-spam gateway all silently became “valid” — which is precisely how a sending domain gets burned. Those now resolve to `blocked` / `greylisted` / `unknown` and are routed to a retry queue, and are **never counted as valid**.
* **Multi-Probe Catch-All Detection**: a single random probe cannot separate a catch-all from a block or a greylist. LeadForge sends a reachability control, multiple random probes, and a known-invalid control, then classifies `CATCH_ALL / NOT_CATCH_ALL / GREYLISTED_RETRY / BLOCKED / ANTISPAM_GATEWAY`.
* **No-Probe MX Awareness**: Gmail, Zoho, Outlook and Yahoo accept-all on `RCPT TO` then reject after `DATA`. Probing them yields false “valid” results *and* gets your egress IP penalised, so they are never probed. This matters disproportionately in India, where a Gmail address is a legitimate and often the *only* business address.
* **Role, Free, Disposable & Typo Detection**: `info@`/`sales@`/`support@` are flagged as group mailboxes and never counted as a “person found” (the usual cause of inflated lead counts and complaint spikes); webmail is treated as a quality signal rather than a rejection reason; typo'd domains receive a `did_you_mean` suggestion instead of being silently dropped.
* **80+ Spam Keyword Linter**: Scores copy 0–100 against commercial spam triggers, subject-line extremes, all-caps density, exclamation ratios and hyperlink density.

### 6. India-Specific Outreach Readiness
* **TRAI-Accurate Phone Normalisation**: Trunk-zero STD codes resolve against a verified SDCA table (so `0481` → Kottayam and `0487` → Thrissur, not duplicates), landline vs. mobile is distinguished by subscriber-length rules, and everything is normalised to **E.164** `+91`. Foreign numbers are no longer mangled into `+91...`.
* **Channel Routing**: Landlines route to voice/email; mobiles route to WhatsApp first — which is how Indian SMBs actually answer.
* **Regulatory Advisor**: The app surfaces consent, DLT and TRAI guidance as **advisory information** and leaves every decision to the operator — LeadForge is self-hosted and does not gate or veto your sending.
* **Hinglish & Festival-Aware Copy**: Generates regionally natural phrasing and suggests culturally appropriate timing windows.
* **Source-Trust Scoring**: Weights leads by the observed reliability of each source (Google Maps vs. aggregator directories), so a scraped-aggregator lead never outranks a primary-source one.
* **Warm WhatsApp Handoff**: Emits a pre-filled `wa.me` deep link so the operator can continue in the channel the lead will actually reply on.

### 4. Algorithmic 1-on-1 AI Outreach Icebreakers
* **Review Sentiment Analysis**: Evaluates customer reviews, Google star ratings, municipal locations, and business categories.
* **Personalized Hooks**: Automatically synthesizes authentic opening hooks, hyper-specific compliments, and category-relevant pain points tailored to each individual business prospect.

### 5. Deterministic Lead Scoring & Bounce Suppression
* **0–100 Weighted Quality Score**: Evaluates each lead across email deliverability ($w_e$), phone presence ($w_p$), website activity ($w_w$), Google rating ($w_r$), and unclaimed status ($w_u$):
  * **🔥 HOT (75–100)**: Verified email, active website, top ratings ($\ge 4.5$), high reviews.
  * **⚡ WARM (45–74)**: Contact details present; email unverified or catch-all.
  * **❄️ COLD (<45)**: Limited contact footprint.
* **Classified Bounce Suppression**: SMTP responses are classified into **hard** (dead mailbox, domain gone, no-such-user → permanent suppression), **soft** (mailbox full, over-quota, greylisted → retry), and **policy** (blocked, content-filtered → *not* treated as a dead address). Suppression is enforced again at queue time, so a bounce that lands mid-batch stops the remaining sends.

---

## 🛠️ Technical Specifications & Engineering Decisions

| Dimension | Engineering Decision | Rationale |
| :--- | :--- | :--- |
| **Backend Framework** | FastAPI (Python 3.10+) | High-performance asynchronous execution, auto-generated OpenAPI documentation, and low-latency websocket streams. |
| **Maps Extraction** | HTTP protobuf `pb=` endpoint, Playwright Stealth fallback | Primary path parses `APP_INITIALIZATION_STATE` with no browser; fallback uses headless Chromium with asset-blocking. |
| **Frontend Dashboard** | Next.js 15 (App Router) + Tailwind CSS | Modern, responsive interface with server-side rendering, real-time job status streaming, and instant search filtering. |
| **Persistence Layer** | SQLAlchemy 2.0 Async + SQLite/PostgreSQL | Zero-configuration local development via SQLite with seamless production migration to PostgreSQL. |
| **Agent Interface** | Model Context Protocol (MCP) SDK | First-class integration with modern AI coding assistants and autonomous agents. |
| **CRM Integration** | Twenty CRM & Standard REST Webhooks | Direct synchronization with modern open-source CRMs without vendor lock-in. |

---

## ⚡ Quick Start

### Prerequisites
* **Python**: `3.10+`
* **Node.js**: `18+`
* **npm** or **yarn**

### Option A: One-Click Launcher (SQLite — zero config)

```bash
# 1. Clone repository
git clone https://github.com/Aryanban/leadforge.git
cd leadforge

# 2. Run the 1-click launcher
./start.sh
```

**What `./start.sh` does automatically**:
1. Creates Python virtual environment (`.venv`) and installs all backend dependencies.
2. Installs headless Chromium for Playwright scraping (`playwright install chromium`).
3. Creates the SQLite database (`leadforge.db`) and its schema automatically on first backend start — zero configuration, no seed step needed.
4. Launches the **FastAPI Backend** on [`http://localhost:8000`](http://localhost:8000) ([Swagger Docs](http://localhost:8000/docs)).
5. Launches the **Next.js 15 Dashboard** on [`http://localhost:3000`](http://localhost:3000).

> All service ports are bound openly (backend `:8000`, dashboard `:3000`) so a
> clone-and-run works on your machine and across a LAN with zero extra config.
> Keep it off the public internet unless you put it behind a reverse proxy with
> authentication — the API has no built-in auth (it is a single-user,
> self-hosted tool).

### Option B: Docker Compose (Postgres + Redis + Celery)

```bash
docker compose up --build
```

Brings up Postgres, Redis, the FastAPI backend (`:8000`), a Celery worker, and
the dashboard (`:3000`). Postgres/Redis only bind to `127.0.0.1` on the host;
the app ports are open on every interface. Before exposing the stack beyond
localhost, generate a real secret and lock CORS down:

```bash
SECRET_KEY=$(openssl rand -hex 32) ENV=production CORS_ORIGINS=https://your-domain.example docker compose up -d
```

### Configuration

Configuration is **optional** — with no `.env` at all, LeadForge runs on a
local SQLite file (`leadforge.db`), created automatically on first start. To
override anything (Postgres URL, secrets, CORS, proxy list), copy
`.env.example` to `backend/.env` and edit; every value is taken literally
(no variable interpolation inside the file). See `.env.example` for details.

--- 

## 🚀 How to Use LeadForge (End-to-End Workflow)

Once the stack is up, open the dashboard at
[`http://localhost:3000`](http://localhost:3000) and walk the pipeline:

| # | Page | What you do |
| :--- | :--- | :--- |
| 1 | **`/scrape`** | Enter a query like *"Dentists in Austin TX"* → concurrent Google Maps scrape saves listings, then auto-discovers public emails from the businesses' websites and directories. |
| 2 | **`/find`** | Alternative entry point: save an **Ideal Customer Profile** and run multi-source discovery against it (JustDial, directories, web). |
| 3 | **`/leads`** | Browse & search your database. Click any row to open the **detail drawer**: contacts, verification badges, full send history, one-click company suppression. Save current filters as **saved views** (Apollo dynamic lists) and bulk-select → Add to Sequence. |
| 4 | **`/companies`** | The Accounts view: one row per company with contact coverage (total vs verified), rating, and location. |
| 5 | **`/settings`** | **Add an SMTP mailbox** (e.g. Gmail + App Password) — required before any campaign can send. Daily limit is capped at 50/day for warmup safety. |
| 6 | **`/sequences`** | Apollo-style execution: stat-tabbed list (Active/Paused/Draft/Completed) → build sequences with `{{first_name}}`-style variables, **A/B subject variants** (winner auto-declared on reply rate once both variants clear 10 sends), select leads → **Add to Sequence** → **Launch** → monitor per-step performance → **Pause** anytime. Suppression, warmup ramps, daily limits and randomized send jitter are enforced automatically. |
| 7 | **`/inbox`** | Inbound replies detected by the IMAP reply poller (every 5 min, or "Poll now" on Email Health). Thread-attributed via stored Message-IDs; categorized Interested / Not interested / Opt-out / Away / Needs triage. **A "stop" reply auto-suppresses the address workspace-wide** — compliance gate 4 of 4. Humans can re-categorize. |
| 8 | **`/email-health`** | Mailbox reputation, warmup progress (ramp stage), daily budget bars, health-paused banners, and per-mailbox reply polling. |

**First-send checklist** — guardrails refuse to run until all three exist (by design):
the launcher blocks campaigns without steps or recipients, and the sender
blocks dispatch without a usable mailbox:

1. ✅ At least one SMTP mailbox in `/settings`
2. ✅ At least one sequence step in `/sequences`
3. ✅ At least one recipient added in `/sequences` (or via the Lead Database)

Then hit **Launch**. Watch progress on `/sequences`, replies land in `/inbox`,
and mailbox health lives on `/email-health`.

**Everything is also an API**: every dashboard action maps to a REST endpoint —
interactive Swagger docs at [`http://localhost:8000/docs`](http://localhost:8000/docs),
health check at [`http://localhost:8000/health`](http://localhost:8000/health).
Prefer the terminal? The **CLI** and **MCP agent** usage are documented below.

---

## 🧪 Automated Test Suite (191/191 Passing)

LeadForge includes a comprehensive Pytest suite covering email status/role/free/typo/gibberish classification, multi-probe catch-all sentinel, SMTP verification status mapping, per-domain pattern learning, seed harvesting, lead scoring and source-trust ranking, spam checking, AI icebreakers, Indian phone/STD normalisation and DND scrubbing, deliverability (bounce classification, suppression, warm-up ramps, India send-timing advice), deduplication/entity resolution, discovery pipeline, and the sources + leads/campaign/ICP APIs:

```bash
# Install test dependencies (once):
.venv/bin/pip install -r backend/requirements-dev.txt

# Run backend test suite:
(cd backend && ../.venv/bin/python -m pytest -q tests/)
```

All **191/191 tests pass synchronously** in under 1s — no network, no browser, no external services required.

---

## 🤖 MCP Server & CLI Usage

The MCP server exposes **17 tools** covering the full agent automation loop:
scrape → search → enrich → create campaign → add targets → launch → monitor →
pause, plus mailboxes, email verification, spam scoring, AI icebreakers, and
the global suppression list.

LeadForge is a native **Model Context Protocol (MCP)** server, enabling AI coding assistants (Google Antigravity, Claude Code, Cursor) to drive lead generation autonomously.

### Antigravity / Claude Desktop Configuration (`mcp_config.json`):
```json
{
  "mcpServers": {
    "leadforge": {
      "command": "/absolute/path/to/leadforge/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/leadforge/backend"
    }
  }
}
```

### Full-Featured CLI Commands:
```bash
# Set Python path
export PYTHONPATH=backend

# 1. Scrape Google Maps leads & output as markdown table:
.venv/bin/python -m app.cli scrape "Dentists in Austin TX" --limit 10 --format markdown

# 2. Search database by query:
.venv/bin/python -m app.cli search --query "Dental" --format markdown

# 3. Waterfall enrich a specific lead:
.venv/bin/python -m app.cli enrich 1

# 4. Check email deliverability & spam triggers:
.venv/bin/python -m app.cli spam "URGENT: Guaranteed 100% free profit for your business"

# 5. Generate personalized AI outreach icebreaker:
.venv/bin/python -m app.cli icebreaker 1

# 6. View database statistics:
.venv/bin/python -m app.cli stats
```

---

## 👨‍💻 Engineering Portfolio & Technical Evaluation Showcase

**LeadForge** was architected and built by **Aryan Bansal** as an enterprise-grade autonomous data scraping and lead intelligence system. It serves as an end-to-end technical demonstration for:
* **High-Bar Engineering Roles & Technical Job Evaluations**: Demonstrates deep competency in asynchronous Python concurrency (`asyncio`), resilient web scraping, network protocol verification (DNS MX & SMTP sockets), and clean microservices architecture (e.g. **Trilogy**, backend systems engineering, and data platform roles).
* **Competitive Hackathons & Innovation Showcases**: Highlights modern AI agent integration via Model Context Protocol (MCP), open-source CRM interoperability, and automated lead intelligence pipelines.

### 🌟 Core Engineering Competencies Demonstrated

| Competency Area | Architecture & Implementation | Engineering Impact |
| :--- | :--- | :--- |
| **Asynchronous Web Automation** | Playwright Stealth with network asset route interception | 3x–5x faster crawling; resilient extraction across dense Google Maps nodes without IP bans. |
| **Reverse Cipher Deobfuscation** | Cloudflare `data-cfemail` single-byte XOR reverse cipher | Unmasks protected executive emails directly from obfuscated DOM trees. |
| **Network & Socket Engineering** | Direct DNS MX query resolution and low-level SMTP socket handshakes | Eliminates third-party API verification costs; prevents catch-all bounce penalties. |
| **Deliverability Linter** | 80+ spam trigger word scanner + deliverability health scoring | Protects outbound sender reputation by catching spam flags before transmission. |
| **Agentic AI Protocol (MCP)** | JSON-RPC 2.0 Model Context Protocol server exposing tool contracts | Enables autonomous agents to execute complex prospecting sequences end-to-end. |
| **Full-Stack SaaS Architecture** | FastAPI + Next.js 15 App Router + Twenty CRM webhook engine | Sub-second lead querying, batch CSV/JSON export, and one-click CRM ingestion. |

---

## 📄 License & Contact

* **Author**: Aryan Bansal ([GitHub: @Aryanban](https://github.com/Aryanban))
* **Email**: `contact@dholeramap.com` / `aryan24120@iiitd.ac.in`
* **Portfolio**: [webforge.me](https://www.webforge.me)
* **LinkedIn**: [linkedin.com/in/aryan-bansal-b29b69370](https://www.linkedin.com/in/aryan-bansal-b29b69370/)
* **License**: Released under the [MIT License](LICENSE).
