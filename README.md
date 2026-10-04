# LeadForge 🚀
### Autonomous Open-Source Lead Scraping, Apollo-Grade Waterfall Enrichment, AI Icebreakers & Cold Outreach Platform

[![GitHub Stars](https://img.shields.io/github/stars/Aryanban/leadforge?style=social)](https://github.com/Aryanban/leadforge)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js 15](https://img.shields.io/badge/Frontend-Next.js%2015-black.svg)](https://nextjs.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Native%20Server-8A2BE2.svg)](https://modelcontextprotocol.io/)
[![Twenty CRM](https://img.shields.io/badge/CRM-Twenty%20Compatible-indigo.svg)](https://twenty.com/)
[![Tests Passing](https://img.shields.io/badge/Tests-14%2F14%20Passing-brightgreen.svg)](https://github.com/Aryanban/leadforge)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Aryanban/leadforge/pulls)

**LeadForge** is an open-source, full-stack B2B lead generation, waterfall contact enrichment, deliverability validation, and cold email outreach platform. It combines **turbo-route Google Maps scraping**, **Cloudflare XOR deobfuscation**, **Apollo-grade email permutations**, **catch-all server probing**, **0–100 AI lead quality scoring**, **80+ spam trigger word linting**, **algorithmic 1-on-1 icebreakers**, and **Twenty CRM synchronization** into a blazing fast Next.js 15 dashboard, REST API, CLI, and native MCP server.

**Zero subscriptions. Zero per-lead API costs. 100% self-hosted.**

---

## 💡 Why LeadForge? (Cost & Feature Comparison)

| Feature | **LeadForge** | **Apollo.io** | **Hunter.io** | **Outscraper** | **Lemlist** |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Monthly Cost** | **$0 / Free Forever** | $99 / mo | $49 / mo | ~$50 / 10k leads | $149 / mo |
| **Lead Limits** | **Unlimited** | 1,000 credits/mo | 500 searches/mo | Pay-per-record | 2,500 leads |
| **Self-Hosted / Local Private Data** | **Yes (100% Local)** | No (SaaS Cloud) | No (SaaS Cloud) | No (SaaS Cloud) | No (SaaS Cloud) |
| **Google Maps Turbo Scraping** | **Built-in (Route Interceptor)** | Add-on | Not included | API only | Not included |
| **Cloudflare `data-cfemail` Decoding** | **Yes (Native XOR cipher)** | No | No | No | No |
| **Apollo-Style Email Permutations** | **Yes (`first.last@`, `first@`)** | Proprietary | Paid Add-on | No | No |
| **Catch-All & Safe SMTP Verification** | **Yes (Direct DNS MX & Handshake)**| Paid | Yes | No | Add-on |
| **Cold Email Spam & Deliverability Linter**| **Yes (80+ words, 0-100 score)** | No | No | No | Included |
| **Algorithmic 1-to-1 AI Icebreakers** | **Yes (Sentiment & pain points)** | Paid Add-on | No | No | Included |
| **Multi-Step Sequences & Bounce Guard** | **Yes (Delay days, 550 auto-suppress)**| Included | Add-on | No | Included |
| **AI Agent Native (MCP Server)** | **Yes (Claude, Cursor, AGY)** | No | No | No | No |
| **Open-Source CRM Integration** | **Twenty CRM & Webhooks** | HubSpot / SF only | Zapier only | Webhooks only | Zapier only |

---

## ✨ Core Superpowers

### 1. 🗺️ Turbo Google Maps Scraper
- **Network Asset Route Interception**: Automatically blocks heavy image, font, and media assets during Playwright browsing, providing **3x–5x scraping speedups**.
- **Anti-Detection Crawling**: Humanized mouse scrolls, randomized viewport headers, and resilient multi-step extraction.
- **Unclaimed Google Business Profile Detection**: Flags businesses where *"Claim this business"* is present — the easiest agency prospecting angle for web design, marketing, and SEO.
- **Rich Business Metadata**: Operational status ("Open", "Temporarily Closed"), price tier (`$`, `$$`), review counts, ratings, and direct hyperlinked Google Maps URLs.

### 2. ⚡ Apollo-Grade Waterfall Email Enrichment & Obfuscation Decoding
- **Cloudflare XOR Cipher Decoder**: Automatically reverses Cloudflare's `data-cfemail` hex-encoded tokens to unmask protected executive emails.
- **Text Deobfuscation**: Resolves anti-scraping email patterns (e.g. `john [at] company [dot] com` $\to$ `john@company.com`).
- **Corporate Email Permutation Engine**: Generates high-yield executive permutations (`{first}.{last}@{domain}`, `{first}@{domain}`, `{first_initial}{last}@{domain}`) plus standard corporate role aliases (`contact@`, `info@`, `sales@`, `office@`).
- **Catch-All Mail Server Detection**: Probes remote mail exchangers with randomized non-existent addresses. If the server accepts all emails (`250 OK`), it flags catch-all behavior to protect your sender domain reputation.
- **Zero-Cost SMTP Verification**: Performs direct DNS MX lookups and low-latency RCPT TO handshakes without paying 3rd-party verification APIs.

### 3. 🛡️ Cold Email Deliverability & 80+ Spam Trigger Linter
- **Comprehensive Spam Trigger Dictionary**: Scans email copy against **80+ commercial spam triggers** (urgency, financial guarantees, spam flags).
- **Deliverability Scoring (0–100)**: Evaluates subject line length, excessive capitalization, exclamation marks, and link density.
- **Interactive Spam Checker Modal**: Test your subject lines and pitch copy in the UI before launching campaigns.

### 4. 🧠 Algorithmic 1-on-1 AI Outreach Icebreakers
- **Tailored Hooks**: Generates custom opening hooks, authentic compliments, and industry pain points tailored to each lead's Google rating, review count, city, and business niche.
- **Interactive UI Modal**: Click the wand button on any lead to generate and copy hooks with 1 click.

### 5. 🔥 Automated Lead Scoring (0–100)
- **🔥 HOT (Score 75–100)**: Verified deliverable email, WhatsApp-ready phone, active website, top ratings ($\ge 4.5$), high reviews.
- **⚡ WARM (Score 45–74)**: Phone number and website available; email unverified or missing.
- **❄️ COLD (Score <45)**: Limited contact data available.
- **Lead Badges**: Tagged with `Verified Email`, `WhatsApp Ready`, `Top Rated`, `Active Website`, and `Unclaimed GBP`.

### 6. 📬 Multi-Step Cold Email Sequencer & Bounce Protection
- **Multi-Step Scheduling**: Automatically spaces follow-ups across `delay_days` intervals.
- **Hard Bounce Suppression**: Automatically detects `550` and `554` SMTP bounce responses and suppresses contacts to protect your domain reputation.
- **Multi-Mailbox Rotation**: Connect Gmail, Zoho, Outlook, Amazon SES, or custom SMTP servers.
- **RFC 8058 1-Click Unsubscribe**: Automatic unsubscribe link injection with tracking suppression.

### 7. 📥 CSV Import & Open-Source CRM Sync
- **Interactive CSV Import Modal**: Drag-and-drop file upload and raw CSV text paste with fuzzy column mapping.
- **1-Click Twenty CRM Export**: Download standard `companies` and `people` schema JSON ready for [Twenty CRM](https://twenty.com/) import.
- **Webhook Push**: Instant sync to Zapier, Make, n8n, or custom CRM endpoints.

---

## ⚡ Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Aryanban/leadforge.git
cd leadforge

# 2. Run the 1-click launcher
./start.sh
```

**What `./start.sh` does automatically**:
1. Creates Python virtual environment (`.venv`) and installs all dependencies.
2. Installs headless Chromium for Playwright scraping.
3. Initializes the database with initial leads and email templates.
4. Launches the **FastAPI Backend** on [`http://localhost:8000`](http://localhost:8000) ([Swagger API Docs](http://localhost:8000/docs)).
5. Launches the **Next.js 15 Dashboard** on [`http://localhost:3000`](http://localhost:3000).

---

## 🧪 Automated Test Suite

LeadForge includes a comprehensive Pytest test suite covering permutations, SMTP verification, lead scoring, spam checking, and icebreaker generation:

```bash
# Run backend test suite:
.venv/bin/pytest backend/tests
```

All **14/14 tests pass synchronously** in under 0.5s.

---

## 🤖 MCP Server & CLI Usage

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

## 📄 License

Distributed under the **MIT License**. Maintained with ❤️ by [Aryan Bansal](https://github.com/Aryanban).
