---
name: leadforge
description: >-
  Autonomous lead generation, real-time Google Maps scraping, multi-source web contact discovery
  (Yahoo/Bing/directories), email deliverability verification (DNS MX/SMTP), and cold email outreach engine.
  Activate whenever the user asks to scrape leads, find business contacts/phones/emails, research local companies,
  enrich leads, or sequence cold outreach.
---

# LeadForge: AI Autonomous Lead Engine

LeadForge allows you to search, scrape, enrich, and contact B2B and local business leads across any industry and geography directly from this conversation.

---

## When to Use LeadForge

Use LeadForge whenever the user asks:
- "Scrape leads for [industry] in [city/location]"
- "Find phone numbers, emails, or websites for businesses"
- "Search my lead database for [keyword]"
- "Enrich missing emails or phone numbers for business #[id]"
- "Start a cold email outreach sequence"

---

## How to Execute LeadForge Operations

You have two direct ways to control LeadForge:

### Method 1: Using the LeadForge CLI (Recommended for fast execution)
Run the built-in CLI via `run_command` in `/Users/aryanbansal/Downloads/leadforge/backend`:

1. **Scrape New Leads** (real-time Google Maps scraping with automatic web contact discovery):
   ```bash
   /Users/aryanbansal/Downloads/leadforge/.venv/bin/python -m app.cli scrape "<Query>" --limit 10 --format markdown
   ```
2. **Search Saved Leads**:
   ```bash
   /Users/aryanbansal/Downloads/leadforge/.venv/bin/python -m app.cli search --query "<Keyword>" --format markdown
   ```
3. **Deep Web Search / Enrich Contact Details**:
   ```bash
   /Users/aryanbansal/Downloads/leadforge/.venv/bin/python -m app.cli enrich <business_id>
   ```
4. **Platform Stats**:
   ```bash
   /Users/aryanbansal/Downloads/leadforge/.venv/bin/python -m app.cli stats
   ```

### Method 2: Using the LeadForge MCP Server
Call the MCP tool using `call_mcp_tool`:
- `ServerName`: `"leadforge"`
- `ToolName`: `"scrape_leads"`, `"search_leads"`, `"enrich_lead"`, `"create_campaign"`, or `"get_stats"`
- `Arguments`: e.g. `{"query": "Real Estate Agents in Rohini Delhi", "max_results": 10}`

---

## Response Formatting Guidelines

Whenever returning lead results to the user:
1. **Always Hyperlink Google Maps**: The business name or Maps link MUST be hyperlinked with the exact Google Maps URL extracted by LeadForge (`[View on Maps](url)`).
2. **WhatsApp Links**: Include clickable WhatsApp chat links for every phone number (`[WhatsApp](https://wa.me/<clean_phone>)`).
3. **Email Verification**: Clearly indicate if an email is deliverable (`✓ Verified Deliverable`) or pending verification.
4. **Next Actions**: Proactively offer to:
   - Run **Deep Web Search** on leads missing emails
   - Export results to CSV
   - Launch an automated cold email outreach campaign
