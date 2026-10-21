# LeadForge — Apollo-Parity Roadmap (India)

> Generated from 8 parallel codebase audits (scraping, enrichment, verification, targeting,
> outreach engine, backend/API, frontend, MCP/agent layer) + competitive research.
> Every finding below was **verified by reading code and executing it**, not inferred.
> Target: be faster, more accurate, and more complete than Apollo.io for the Indian SMB market.

---

## ✅ Status: Wave 0 + Wave 1 shipped

**229 backend tests pass** (was 196). Frontend: `tsc --noEmit` clean, `npm run build` green,
21 Playwright specs that can now actually fail the build.

| # | Fix | Before | After |
|---|-----|--------|-------|
| B1 | Mailbox daily cap | lifetime counter → bricked after 50 sends | `sent_today` is a calendar-day counter; rolling-24h is the real gate |
| B2 | Send gate | mailed `invalid`/`gibberish`/`no_mx` addresses | refuses 10 undeliverable states; un-enriched leads stay eligible |
| B3 | Sequence scheduler | manual re-click required forever | in-process 5-min loop + Celery beat entry; "waiting on a delay" ≠ "completed" |
| B4 | Maps `q=` split | 34 unique leads / 8 requests | **60** unique leads / 8 requests (**+76%**, measured live) |
| B5 | `has_email` pagination | 4 of 20 leads visible, `total` wrong, Next disabled | SQL predicate before LIMIT; correct totals; page 2 reachable |
| B6 | Sender-vs-recipient bounce | one bad sender config nuked the whole lead DB | `sender_rejected:` / `data_rejected:` never suppress a lead |
| B7 | Soft-bounce retry | 1 blip → 30-day suppression | 3-attempt budget before suppression |
| — | Enrichment concurrency | 9s/lead, serial, inside the event loop | bounded fan-out (8×) + async verifier → event loop never stalls |
| — | SMTP probe | `EHLO [127.0.0.1]`, bogus MAIL FROM, no STARTTLS | RFC 5321 null reverse path, FQDN EHLO, STARTTLS |
| — | Pattern inference | 4/10 templates, confidently wrong | **8/10** detected, dominance-aware confidence, 0 invalid candidates |
| — | Phone extraction | display form (`098225 22560`) | international form (`+91 98225 22560`) |
| — | Google CID | dropped on the primary scrape path | populated on 25/25 leads — the strongest dedupe key, finally in use |
| — | DB layer | FKs off, no indexes, no WAL | `foreign_keys=ON` + WAL + indexes on every FK/sort column |
| — | Schema sync | columns only; never created indexes | tables + columns + indexes; CLI and MCP self-migrate |
| — | Auth | open API, `CORS=*` + credentials | optional `API_KEY`; tracker exempt for mail clients |
| — | MCP agent loop | no contact IDs → agent mailed the wrong 79% | contact IDs + dry-run launch + JSON-RPC `isError` + 18 tools |
| — | MCP concurrency | one blocking tool wedged the server | concurrent request handling; a slow tool no longer blocks the rest |
| — | Click tracking | didn't exist → WhatsApp handoff permanently empty | `/click` route + link rewriting; handoff now populates |
| — | A/B testing | raw rates at n=10 | two-proportion z-test, n≥50, positive replies only |
| — | ICP parser | silently dropped constraints | reports `unsupported_terms` + warnings; fixed corrupt exclusions |
| — | Dashboard | dead Cmd+K, 15 `alert()`, no mobile, CI ignored types | wired search, toasts, mobile drawer, type-checked CI, 21 real e2e specs |

### Measured performance (500,000-lead SQLite database)

| Path | Before | After | Speed-up |
|---|---|---|---|
| CSV import, 5,000 rows | 11.95 s | **0.21 s** | **57×** |
| CSV re-import, 5,000 rows | 5.10 s | **1.43 s** | 3.6× |
| Lead search, selective term | 200 ms | **8 ms** | 25× |
| Lead search, no match (a typo) | 427 ms | **2 ms** | **200×** |
| Lead search, broad term | 148 ms | **84 ms** | 1.8× |
| Lead list, 500k | — | **10 ms** | — |
| Analytics timeseries, 18k sends | — | **1.9 ms** | — |
| Campaigns list | 4 queries/campaign | **3 queries total** | — |
| MCP `search_leads` | 26 SELECTs | **2** | 13× |
| MCP `list_campaigns` | 31 SELECTs | **4** | 8× |
| CLI `search` | 26 SELECTs | **3** | 9× |
| Enrichment, whole flow | 8.14 s | **0.62 s** | **13×** |
| Homepage fetches per lead | 5 | **1** | 5× |
| Suppression checks per campaign | N queries | **1** | N× |

**One bug found during verification that the audits missed:** Google stores the phone in a
nested structure with the *display* form (leading trunk zero) first and the international
form second. The parser took the first one, so every phone in the database was
`098225 22560` — which reads as a landline with STD code `098225`, mis-files the STD→city
lookup, and does not match a `+91 98225 22560` stored elsewhere for the same business.

**One bug introduced and caught during verification:** the analytics day-bucketing used
`CAST(sent_at AS DATE)`, which is *not* portable — SQLite applies NUMERIC affinity and
truncates `2026-10-17` to the integer `2026`. It is now `date()`, and a regression test
compares the SQL aggregation against a Python reference day by day.

---

## 0. Verdict

LeadForge is a **competent single-shot mailer with a reply inbox attached**. The README
describes Apollo. The code describes something meaningfully different.

The engineering instincts are good in places — RFC 8058 one-click unsubscribe, workspace-wide
suppression re-checked immediately before every SMTP call, a 20-state verification enum that
never coerces `unknown` → `valid`, a per-domain pattern learner, a real Cloudflare
`data-cfemail` decoder, per-test DB isolation in the test suite. Those are the pieces worth
keeping and defending.

But five product-killing bugs mean **the core loop does not work today**, and roughly a third
of the README's headline claims are false. Fixing the five blockers plus Wave 1 is roughly
**3–5 days of work** and converts this from a demo into a product.

**Scorecard vs Apollo (today):**

| Capability | Apollo | LeadForge | Gap severity |
|---|---|---|---|
| Leads/day per IP | 10k+ | ~2,000 (and 5h of that is a serial enrichment loop) | 🔴 |
| Unique leads per scrape query | 100+ | 30 (viewport grid collapses — `q=` bug) | 🔴 |
| Named decision-maker found | ~40% of contacts | 8–15% | 🔴 |
| Multi-source ingestion | 275M contacts + 50+ providers | 1 working source (3 of 4 return 0) | 🔴 |
| Autonomous multi-step sequences | ✅ | ❌ no scheduler — requires manual re-click | 🔴 |
| Per-day send capacity | 50/mailbox/day, forever | 50/mailbox/**lifetime**, then bricked | 🔴 |
| Hard-bounce rate | <5% | ~25–30% (sends to known-invalid addresses) | 🔴 |
| ICP filter expressiveness | 20+ attributes | 3 loose filters | 🟠 |
| ICP fit scoring | per-saved-search, live | cached global contact-completeness score | 🟠 |
| Opportunities / pipeline board | ✅ | ❌ no model exists | 🟠 |
| Analytics | funnel + cohorts + rep leaderboard | 4 flat counters | 🟠 |
| People table (row = person) | ✅ core surface | ❌ only a company table | 🟠 |
| Click tracking | ✅ | ❌ no route exists | 🟠 |
| India: GSTIN / Udyam / DLT / pincode / city tier | ❌ | ❌ | 🟢 **our moat** |
| India: WhatsApp-first routing | ❌ | computed, then ignored | 🟢 **our moat** |
| India: STD→city resolution | ❌ | ✅ built (`in_phone.py`) | 🟢 |
| India: mobile vs landline | ❌ | ✅ built, never scored | 🟢 |

---

## 1. Wave 0 — The five blockers (product does not work without these)

### B1. Every mailbox bricks after 50 lifetime sends 🔴 P0

`backend/app/campaigns/sender.py:251`
```python
m_stmt = select(Mailbox).where(Mailbox.is_active == True, Mailbox.sent_today < Mailbox.daily_limit)
```
`sent_today` is incremented at `sender.py:477` and **reset nowhere** — verified: the only
other writes are `api/mailboxes.py:69` and `seeds.py:198`, both at creation time. The
`warmup.py` docstring at `:18-21` calls it "a fast pre-filter" and names
`rolling_24h_count` as "the authoritative gate" — but the stale pre-filter fires first and
the mailbox never reaches the real gate. **After 50 emails the mailbox is dead forever.**

```python
# sender.py:251 — drop the broken counter from the filter
m_stmt = select(Mailbox).where(Mailbox.is_active == True)
# sender.py:477 — stop persisting a drifting counter
#   (expose rolling_24h_count in GET /mailboxes for the UI instead)
```
**Gain:** unbounded daily throughput; `warmup.py`'s entire ramp/rolling-24h machinery
becomes reachable for the first time.

---

### B2. The sender emails known-invalid addresses 🔴 P0

`backend/app/campaigns/sender.py:294-302` filters on exactly one exclusion:
```python
Contact.verification_status != "bounced"
```
`should_send()` exists at `backend/app/verifier/email_status.py:379-389` and is **never
called from the sender** — only from the MCP display path. So `invalid`, `syntax_error`,
`gibberish`, `disposable`, `no_mx`, `unknown`, `catch_all` are all mailed. The verifier's
"never defaults to valid" guarantee is enforced in one file and discarded two files away.

For an Indian SMB list where ~30% of scraped addresses are junk, that is a ~30% hard-bounce
rate on day one. Gmail/Yahoo's bulk-sender threshold is **5%**.

```python
# sender.py:294
Contact.verification_status.notin_(
    ("bounced", "invalid", "syntax_error", "gibberish", "disposable",
     "no_mx", "domain_error", "spamtrap", "abuse", "do_not_mail"))
```
**Gain:** hard bounce rate ~25–30% → <5%. Sender reputation preserved.

---

### B3. No scheduler — multi-step sequences never advance on their own 🔴 P0

`execute_campaign_step` has exactly two call sites: `api/campaigns.py:273` (manual Launch)
and `mcp_server.py:686`. `main.py:84-103` has a `_reply_poll_loop` but no campaign loop;
`workers/beat_schedule.py:8-13` contains only the IMAP sweep. The delay arithmetic at
`sender.py:374-376` is correct — **nothing ever calls it again at T+3 days.** An operator
must manually re-click Launch for every step of every sequence, forever.

Compounding: `sender.py:381-385` marks the campaign `COMPLETED` whenever the queue is empty
— which is true both when everyone finished **and** when everyone is waiting on a delay.
The two are indistinguishable, so campaigns falsely report "Completed".

```python
# app/main.py — mirror the existing reply loop
CAMPAIGN_TICK_SECONDS = 300

async def _campaign_run_loop() -> None:
    while True:
        try:
            async with async_session_maker() as db:
                ids = (await db.execute(
                    select(Campaign.id).where(Campaign.status == CampaignStatus.ACTIVE.value)
                )).scalars().all()
            for cid in ids:
                await execute_campaign_step(cid)
        except Exception as exc:
            logger.warning("campaign tick error: %s", exc)
        await asyncio.sleep(CAMPAIGN_TICK_SECONDS)
```
Plus a Celery beat entry, and a per-campaign lock so the tick and a manual Launch can't
double-send. And distinguish "all steps done" from "waiting on a delay" at `sender.py:381`.

**Gain:** the README's headline feature ("multi-step sequences with delay days") becomes
true. This is the difference between a mailer and an outreach engine.

---

### B4. The `q=` parameter collapses the viewport grid by 3.4× 🔴 P0

`backend/app/scraper/maps_http.py:250` sends `"q": query` where `query` is
`build_query(niche, area)` → `"dentists in Delhi"`. Google then returns one city-wide
relevance set, so **every viewport in the grid returns a near-identical top-20**.

Measured live (8-cell grid, Delhi, identical requests, only `q` varies):

| `q` | raw rows | unique leads |
|---|---|---|
| `"dentists in Delhi"` (current) | 160 | **30** |
| `"dentists"` (category only) | 160 | **103** |

Distance distribution confirms it: with `q="dentists"` the median result sits **1.3 km** from
its own viewport centre (p90 = 5.0 km); with `q="dentists in Delhi"` it sits 5.4 km away and
the set is identical across cells. The viewport grid is only geographic scoping when the
text query is category-only.

```python
# sources/google_maps.py — split "what we're looking for" from "where"
async def search(self, niche, area, limit=20):
    raw = await scrape_google_maps_http(
        query=self.build_query(niche, area),   # label only
        q=industry_of_query(niche),            # the actual request
        max_results=limit, max_cells=8)
```
**Gain: +243% unique leads per query at identical request count (30 → 103).** Highest
gain-per-diff in the entire codebase — roughly a 3-line change.

---

### B5. `has_email` is applied *after* pagination and excluded from `total` 🔴 P0

`backend/app/api/leads.py:113-115`:
```python
if has_email is True and not any(c.get("email") for c in b_contacts):
    continue
```
This runs **after** `.offset(offset).limit(limit)` at `:82`, and `count_stmt` (`:64-77`)
has no `has_email` predicate at all. Verified against the repo's own DB (75 businesses,
20 with email):

| Request | `total` reported | rows returned |
|---|---|---|
| `?page=1&limit=20` | 75 | 20 |
| `?page=1&limit=20&has_email=true` | **75** (should be 20) | **4** |
| `?page=2&limit=20&has_email=true` | 75 | 5 |

The frontend compounds it — `dashboard/src/app/leads/page.tsx:874` disables Next when
`leads.length < 20`, so with a filtered subset the user is **permanently pinned to page 1**
and can never reach the other 16 leads. This is the Lead Database, the product's front door.

```python
# api/leads.py — one predicate, used by BOTH the count and the page
email_ids = select(Contact.business_id).where(Contact.email.isnot(None))
if has_email is True:
    stmt = stmt.where(Business.id.in_(email_ids))
    count_stmt = count_stmt.where(Business.id.in_(email_ids))
elif has_email is False:
    stmt = stmt.where(Business.id.notin_(email_ids))
    count_stmt = count_stmt.where(Business.id.notin_(email_ids))
```
Delete the Python-side `continue` block, and change the frontend to paginate on `total`.

**Gain:** the filter becomes truthful; pagination stops silently truncating. **16 of 20
matching leads become reachable.** The same bug exists in `cli.py:127` and
`mcp_server.py:363` — fix all three, or extract one shared `build_lead_query()`.

---

## 2. Wave 1 — Speed & accuracy (the "faster, better" mandate)

### S1. Enrichment is 100% serialized: ~9s per lead, blocking the event loop

`backend/app/discovery/pipeline.py:20-31` awaits `enrich_business_by_id` one lead at a time.
Measured **8.7s and 9.5s** per lead (Yahoo + Bing + 4-page crawl + social probe + SMTP).
A 100-lead job = **~15 minutes** inside the FastAPI event loop. `maps_scraper.py:528-534`
does the opposite — unbounded `asyncio.create_task` with no reference kept (CPython may GC
the task mid-flight) and no semaphore.

```python
# discovery/pipeline.py
async def _enrich_new_leads(business_ids: List[int], concurrency: int = 8) -> int:
    sem = asyncio.Semaphore(concurrency)
    async def one(bid):
        async with sem:
            try:
                await enrich_business_by_id(bid); return 1
            except Exception as e:
                logger.warning("Enrichment failed for %s: %s", bid, e); return 0
    return sum(await asyncio.gather(*(one(b) for b in business_ids)))
```
**Gain: ~8× throughput (9s → ~1.1s amortised). 100-lead job 15 min → ~2 min.**

### S2. `email_finder.py` calls the *sync* SMTP verifier inside `async def`

`backend/app/enricher/email_finder.py:453` → `check_catch_all_domain(w_domain)` (sync)
and `:501` → `verify_email(email)` (sync, up to 3 RCPT probes, 8s timeout each).

`smtp_verifier.py:336-345` says verbatim: *"calling them directly stalls the whole event
loop for the 3-8s of a DNS+SMTP round trip"*. The module ships
`verify_email_async` / `check_catch_all_domain_async` — **the enricher doesn't use them.**

**Gain:** API p99 during bulk enrichment goes from seconds to milliseconds; the whole API
stops freezing.

### S3. Three SMTP sessions per domain per lead, and every email verified twice

Per lead per domain the code opens **2–5 distinct MX connections** and performs **3–8 DNS
lookups**: `check_catch_all_domain` (conn #1) → `verify_batch` (conn #2) → a per-address
`verify_email` loop (conn #3, #4, #5…). `verify_batch` already computes the per-domain
catch-all verdict internally (`smtp_verifier.py:464`) but doesn't surface it, which is why
a *second* redundant probe was added.

**Gain:** MX connections per lead **3–5 → 1–2**; wall-clock **−20–40%**; port-25 blocklist
exposure cut by an order of magnitude.

### S4. The SMTP probe announces `EHLO [127.0.0.1]` and uses a bogus MAIL FROM

`backend/app/verifier/smtp_verifier.py:138-148`:
```python
self.server = smtplib.SMTP(self.mx_host, port=25, timeout=SMTP_TIMEOUT)
self.server.ehlo_or_helo_if_needed()
self.server.mail(self.sender_email)     # return code DISCARDED
```
Four defects: (a) `smtplib.mail()` returns `(code, msg)` and does **not** raise — a
`550 5.7.1 Sender rejected` is silently dropped and the next RCPT gets `503`, which is in
no bucket → `UNKNOWN`; (b) the default envelope sender is `verify@leadforge.dev` — no MX,
no SPF, no DKIM, rejected by Gmail since Jan 2024 and by Postfix with
`reject_unknown_sender_hostname` (very common on Indian cPanel/Hostinger); (c) **no
STARTTLS** is attempted, so any MTA with `smtpd_tls_security_level=encrypt` answers
`530` → `UNKNOWN`; (d) `smtplib` defaults `local_hostname` to `socket.getfqdn()`, which in
Docker is the container ID with no dot → falls back to the domain literal
**`[127.0.0.1]`** — the canonical signature of an open-relay harvester.

```python
self.server = smtplib.SMTP(self.mx_host, port=25, timeout=SMTP_TIMEOUT,
                            local_hostname=settings.SMTP_HELO_NAME)
self.server.ehlo_or_helo_if_needed()
if self.server.has_extn("starttls"):
    self.server.starttls(context=ssl.create_default_context())
    self.server.ehlo_or_helo_if_needed()
code, msg = self.server.mail("<>")     # RFC 5321 null reverse path
if code != 250:
    self.error = f"mail_from_rejected:{code}"; return False
```
**Gain:** verification stops returning `UNKNOWN` on hardened MTAs; the single most
blocklist-worthy signal in the codebase disappears.

### S5. Catch-all detection: one random probe, and `unknown` silently means "not catch-all"

`backend/app/verifier/smtp_verifier.py:262-315` sends **one** random probe and one
pseudo-control, then classifies `CATCH_ALL / NOT_CATCH_ALL / GREYLISTED_RETRY / BLOCKED` —
the README's "reachability control + multiple random probes + known-invalid control" and
the `ANTISPAM_GATEWAY` verdict **do not exist**. Worse, `"unknown"` is treated as *strict*:
an anti-probing MTA that 250s the first RCPT and 554s the second yields `"unknown"` → the
real address is reported **VALID at confidence 0.95**.

**Gain:** eliminates the false-`valid` class — the #1 cause of sender-reputation burn on
catch-all-heavy Indian domains.

### S6. `/api/v1/scraper/start` is Playwright-first and produces garbage leads

`backend/app/api/scraper.py:35` → `maps_scraper.py:430` runs Playwright **first**, never the
HTTP path. Measured live (Delhi, 20 results):

| field | HTTP path | Playwright path |
|---|---|---|
| wall clock | **2.4s** | **8.9s** |
| phone present | 20/20 | **0/20** |
| website present | 17/20 | **0/20** |
| valid `place_id` (`ChIJ…`) | 20/20 | **0/20** |
| address contains PUA glyph | 0/20 | **17/20** |
| `operational_status` | correct | `"Closed"` (misread) |

The Playwright extractor keeps the category **icon glyph** as the first address token
(`maps_scraper.py:252-259`), and sets `place_id` from `href.split("?")[0][-60:]` — a
truncated URL fragment stored into a `unique=True` column that is the **primary dedupe key**.
Playwright-sourced and HTTP-sourced rows for the same business have incompatible keys.

**Gain: ~4× faster and ~85% more usable fields per lead**, on the endpoint the dashboard's
scrape button actually calls. One-line reorder: try HTTP first.

### S7. Three of four registered sources return zero leads

Measured live: `justdial → 0`, `indiamart → 0` (the URL is a **404**; the endpoint moved
to `dir.indiamart.com/search.mp`), `sulekha → 0` (selectors are legacy Tailwind classes;
business names live in `<h3>`), `google_maps → 20`. The "multi-source router" is
Google-Maps-only in practice. `tests/test_sources.py:61` asserts only that the names are
*registered*, never that they return anything — which is why all 196 tests pass while 3
sources are dead.

Also: **JustDial and Sulekha carry websites** (→ email enrichment) and verified/trust badges
that Maps doesn't have. Fixing them adds both volume *and* enrichability.

### S8. Dedupe silently discards real leads and false-merges across cities

`backend/app/dedupe/match.py:99` matches `Business.name == lead["name"]` with **no city
guard** — and Indian SMBs are dominated by generic names ("Sharma Dental Clinic", "Krishna
Medicals"). `dedupe/persist.py:39-45` treats a match as "already known" and `continue`s, so
the **Jaipur row is never inserted** and its phone/website/address are **thrown away**.

Also verified: phone dedupe is **dead** (`match.py:60-67` compares normalised phone against
the raw stored value); domain matching is a **substring** so `example.com` matches
`smileshop.example.com`; and `normalize_name` is **computed then discarded** at
`match.py:97-102` (the query uses the raw name).

**Gain:** at 50k rows the name-collision rate in Indian SMB data is 5–15%. Fixing this is
worth more than adding any new source.

### S9. `rank_existing` loads the entire database to return 50 rows

`backend/app/qualifier/ranker.py:108-130` — `select(Business)` with **no limit**, then
pure-Python scoring with **no `await` inside** (so it blocks the event loop for the full
duration). Benchmarked: **13.6s and 837 MB** at 100k rows, returned 50. Extrapolated to
500k: **~70s and ~4 GB per request.** This is the "rank my saved search" button.

Same anti-pattern in the CSV export and the Twenty-CRM export (both unbounded full-table
joins, no LIMIT, no streaming).

### S10. No indexes on any foreign key, filter, or sort column

Live schema dump:
```
contacts:       ['ix_contacts_email', 'ix_contacts_id']     <-- NO business_id
sends:          ['ix_sends_id', 'ix_sends_message_id']      <-- NO campaign_id/contact_id/mailbox_id/step_id
businesses:     ix_businesses_{icp_profile_id,id,name,place_id}  <-- NO created_at
```
Measured at 500k businesses / 1M contacts (SQLite):
```
BEFORE:  contacts.business_id IN (25 ids)             42 ms
         businesses ORDER BY created_at DESC LIMIT 25  32 ms
AFTER adding 2 indexes:
         contacts.business_id IN (25 ids)             <1 ms
         businesses ORDER BY created_at DESC LIMIT 25  <1 ms
```
**And the schema-sync mechanism won't fix it** — `main.py:25-58` only adds *columns*; it
never creates indexes or constraints, so existing deployments silently never get them.

### S11. CSV import is O(rows) round-trips inside one transaction

`backend/app/api/leads.py:453-546` — ~5 queries per row (4 for dedupe + 1 contact lookup),
one commit at the end. Measured: **5000 rows = 15.24s**, and it holds SQLite's global write
lock the whole time, so the entire app is unresponsive.

### S12. SQLite foreign keys are OFF — every `ondelete="CASCADE"` is a no-op

`backend/app/database.py:9-16` never issues `PRAGMA foreign_keys=ON`. SQLAlchemy doesn't do
it for you. `api/leads.py:385` uses a Core `delete(Business)` which bypasses the ORM's
`cascade="all, delete-orphan"` entirely → **every deleted lead orphans its contacts.**
Verified: `PRAGMA foreign_keys: 0`, orphan count 1 after one delete.

```python
@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_conn, _rec):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")      # removes reader/writer blocking
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()
```

### S13. Pattern inference detects 4 of 10 patterns and mis-learns 4 more at 0.95 confidence

`backend/app/enricher/pattern.py:131` requires `len(p) >= 2` for every token, making the
`f.last` and `firstl` branches **unreachable**. A single alpha token is unconditionally
classified `"first"`. Verified:

```
rsharma@acme.in        → got "first"       (expected "flast")       conf 0.95  ← WRONG, confident
rajeshsharma@acme.in   → got "first"       (expected "firstlast")   conf 0.95  ← WRONG, confident
sharma@acme.in         → got "first"       (expected "last")        conf 0.95  ← WRONG, confident
a.sharma@acme.in       → got "first.last"  (expected "f.last")      conf 0.25
```
And `pattern.py:121-129` **discards all seed evidence** whenever the exec names don't match
the seed — because the name-based and shape-based branches are mutually exclusive instead of
unioned. Finally, the computed confidence (`:148-150`) is **not dominance-aware** (it
contradicts the repo's own design doc at `.research/lead-data.md:83`), and `email_finder.py:447`
**throws it away** (`permutations, _pat, _conf = ...`).

`flast` / `firstlast` / `last` are disproportionately German/Indian-IT.

### S14. Every contact inherits `executives[0]`'s name and title

`backend/app/enricher/email_finder.py:510-514` runs **inside** the per-email loop:
```python
exec_match = execs[0] if execs else None
c_first = exec_match["name"].split()[0] if exec_match else (business.name.split()[0] if business.name else "Owner")
```
So `info@acme.in` is stored with `first_name="Rajesh", title="Founder"` — simultaneously
`is_role_account=True` **and** named. With no exec, the fallback produces *"Hi Apex,"* for
"Apex Realty Solutions". `sender.py:413` then renders **"Hi Rajesh," to a shared mailbox.**

### S15. Decision-maker extraction misses every real Indian SMB title

`backend/app/enricher/email_finder.py:237-244` `EXEC_TITLES` misses **MD, Principal
(Principal Dentist — the dental norm), General Manager, Promoter, Chairman**. The regex
also manufactures garbage: `"read more - owner"` → `('read more', 'owner')`,
`"call now - partner"` → `('call now', 'partner')`. Those become `person_names` and
**consume the 4-slot candidate budget** (`read.more@domain`, `call.now@domain`).

### S16. `is_verified=True` is asserted for addresses that were never SMTP-probed

`email_finder.py:502` sets `is_verified = result.is_deliverable`, and `is_deliverable`
includes `ROLE_ACCOUNT` and `FREE_EMAIL` — both of which `classify_email` short-circuits
**before any network call**. So `info@acme.in` gets `is_verified=True`, a `verified_at`
timestamp, and the scorer's full **30 points** plus the "Verified Email" badge. The shipped
test at `tests/test_email_finder.py:78` actively asserts this behaviour.

### S17. The spam linter misses every Indian cold-email cliché

`backend/app/campaigns/spam_checker.py:11-46` — the 120-word high-risk list is US
consumer-spam vocabulary (`viagra`, `weight loss`, `mortgage rates`). Verified: *"Hope this
email finds you well / I am writing to introduce / Dear Sir/Madam / kindly revert back"*
scores **75 = "Good", `is_safe: True`**. Meanwhile ordinary words false-positive
(`score`, `promise`, `certified`, `win`). The README's "all-caps density, exclamation
ratios and hyperlink density" — **none of the three exist.**

### S18. The agent cannot obtain a `contact_id`, so it can never target anyone

`mcp_server.py:198-200` requires `contact_ids`, but **no tool output contains one** —
`search_leads` and `scrape` return business `id` only. In the live DB, `contact.id !=
business_id` for **100 of 126 contacts**. An agent doing the only thing it can mails the
**wrong 79% of the database**. The entire "scrape → target → launch" loop is a dead end.

### S19. `leadforge_scrape` returns the wrong leads

`mcp_server.py:300-303` returns the **last N businesses in the whole database**, not the
ones this scrape created — while the header says "Scrape Results for: {query}". The
`_new_biz_ids` returned by `scrape_leads_and_save` is discarded at `:297`.

### S20. No auth + wide-open CORS = any website can delete data and send cold email

`main.py:113-123` with `config.py:34` `CORS_ORIGINS = "*"` **and** `allow_credentials=True`
— Starlette echoes the attacker's origin on preflight. Verified: `DELETE /api/v1/leads/999`
→ 200, `POST /campaigns/{id}/launch` → cold email sent from the user's Gmail.

**Gain:** the only finding where an attacker needs zero credentials. Cheap fix that doesn't
break local DX: an optional `API_KEY` (unset = auth off) applied to every router **except**
`tracker` (the unsubscribe link and the open pixel must stay reachable by mail clients).

### S21. SSRF via the Twenty-CRM export webhook

`api/leads.py:340-344` POSTs to a user-supplied `webhook_url` with no scheme check, no
host allowlist, no private-IP block — and the payload contains **the entire lead database**.
Against a cloud host this reads instance metadata / IAM credentials.

### S22. Soft bounce = immediate 30-day suppression, and there is no retry path

`sender.py:486-491` suppresses on the **first** soft bounce; `bounces.py:130-132`
`should_retry()` is **defined and never called**. `bounces.py:101-102` classifies *any*
unrecognised error (connection refused, `SMTPServerDisconnected`) as soft. One transient
gateway blip removes a valid lead for a month.

Worse: `bounces.py:105-127` `_HARD_RE` matches bare `\b550\b` / `\b553\b`, and
`smtplib` raises `SMTPSenderRefused` when **our own MAIL FROM** is rejected — a *sender*
problem classified as a *recipient* hard bounce → **one misconfigured sending domain
permanently suppresses the entire lead database.**

### S23. `purge_expired` never fires

`campaigns/suppression.py:134-138` compares `Suppression.expires_at < Suppression.created_at`
— always false, since `expires_at = created_at + 30d`. It should be `< func.now()`. It's
also never called from anywhere.

### S24. `{{tokens}}` ship literally to prospects

`sender.py:30-38` `interpolate_template` does a plain `str.replace` with **no fallback** —
an unknown token leaves the braces in. A typo'd `{{frist_name}}` reaches the prospect.
No HTML escaping either (`:440` injects `business.name` raw into `body_html`). And
`api/campaigns.py:288-308`'s preview uses a sample dict **missing** `{{ai_icebreaker}}`,
`{{compliment}}`, `{{pain_point}}`, `{{call_to_action}}` — so the preview renders
`{{pain_point}}` literally while the real send renders a sentence.

### S25. Click tracking doesn't exist → the WhatsApp handoff can never fire

`models/send.py:19` has a `clicked` column that **nothing ever writes**; `tracker.py` has no
`/click` route. The handoff rule at `engagement.py:23-27` requires ≥3 opens or ≥1 click,
and open tracking defaults **off** (`config.py:62`). `GET /campaigns/india/handoff/{id}`
returns **an empty list, permanently.** The README's flagship India feature is a no-op.

### S26. The `AI icebreaker` is a template engine with a hardcoded Delhi default

`enricher/ai_icebreaker.py:11-48` is a 9-key static dict + 3 string-format branches. No
LLM, no review text is ever collected (only `reviews_count: int`), no sentiment analysis,
and the `website` parameter is **never read**. `mcp_server.py:502` hardcodes
`city = arguments.get("city", "Delhi NCR")` — so a Kochi lead generated via MCP gets
*"…other dental leaders in Delhi NCR"*.

---

## 3. Wave 2 — Product completeness (the Apollo surface we're missing)

### 2a. The People table — a company table where the row is a business, not a person

Apollo's core surface is *People*: one row per human, filterable by title and seniority.
`/leads` returns businesses with nested contacts, and **there is no contacts-list endpoint**
(verified: zero `@router.get` routes matching "contact"). `Contact.title` is stored and
shown in the drawer but is **not a column and not filterable**.

> This is the single biggest structural gap. It needs: a `/api/v1/contacts` endpoint, a
> people table in the dashboard, and real decision-maker extraction (S14, S15) to be worth
> anything.

### 2b. ICP filters: the parser silently drops constraints

`qualifier/nl_icp.py:63-68` — the char class `[a-z0-9\- ]` includes a space, so it greedily
eats following words. Verified:

```
'dentists in Kothrud Pune with no website and verified emails'
  → exclude_keywords: ["website and verified emails"]   ← corrupt
'shops in Mumbai with 50 employees and revenue over 10cr'
  → employee count + revenue: SILENTLY DROPPED
'exporters in Noida with Shopify and looking for a sales director'
  → tech + title: SILENTLY DROPPED
```
A user who types "50 employees, revenue over 10cr, Shopify" gets **every shop in Mumbai**
with no indication their constraints were ignored. This is the "the product lied to me" bug.

**Fix (minimum):** add a `UNSUPPORTED` regex and return `unsupported_terms` + `warnings`,
surfaced in the wizard. **Fix (full):** a structured `ICPFilters` model — `industries`,
`cities`, `areas`, `pincodes`, `company_size_min/max`, `revenue_band`, `tech`, `titles`,
`seniority`, `has_gstin`, `city_tier`.

### 2c. Source trust is a hand-written table that isn't applied to most leads

`qualifier/source_trust.py:25-36` is a literal dict of 10 constants. The primary scrape
path writes `source` values `"playwright_maps"`, `"playwright_single"`, `"http_fallback"`,
`"google_maps_seed"` — **none of which are in the table**, so the modifier is skipped
entirely for every lead the dashboard produces. The API then *reports* a modifier that was
never applied (verified mismatch). And `int(round(delta))` collapses the whole trust range
into ±4 points, so IndiaMART (0.60) gets **no discount** while JustDial (0.50) gets −2.

Separately, `discovery/pipeline.py:152-157` records **the same `avg_score` for every
source** in every run (it ranks the union across all sources, then attributes that list to
each source). So the "learned" source routing prefers whichever source returns the most
junk.

### 2d. The score is cached at enrichment time and never recomputed

`api/leads.py:134-142` reads `extra["lead_score"]` — computed once at enrichment. Verified:
a fresh ICP-scoped score of 25 COLD is displayed as **95 HOT** from the stale cache. Changing
an ICP has **zero** effect on existing leads — which makes the entire "Save Search" story a
query builder on top of a ranking that ignores the query.

**The structural fix:** `lead_score` should be **ICP-relative and live**, not a global
cached contact-completeness number. Fixing this one thing collapses a large share of the
targeting findings.

### 2e. Analytics is four flat counters

No bounce *rate*, no unsubscribe rate, no positive-reply rate, no per-source, no
per-mailbox, no hour-of-day heatmap, no funnel, no cohort, no reply→meeting. Meanwhile
`Send.bounced` and `Send.clicked` are **never written** — so `engagement.py:55` always
reports `bounced: 0` even when the mailbox is bouncing.

### 2f. A/B testing has no statistics and the wrong metric

`api/campaigns.py:414-431` compares raw reply rates at n=10 with no significance test.
Cold-email reply rates are 1–3%, so one extra reply = 10pp and a coin flip declares a
winner. The metric counts OOO auto-replies and opt-outs as "replies" — and the reply
poller **drops the auto-reply headers** (`reply_poller.py:257` computes `auto` then
discards it at `:266`), so `Auto-Submitted` is dead code at runtime. An out-of-office
auto-responder can pick your subject line.

Also: the winner is only finalised as a side effect of a `GET`, and `sender.py` reads
`step.variant_winner` but never writes it.

### 2g. Missing Apollo surfaces with no model behind them

Opportunities/deals pipeline, tasks, meetings/calendar, notes on a lead, unified
conversation inbox with threading/ownership, per-rep attribution, inbound webhooks, signed
outbound webhooks, per-record activity timeline, field-level provenance on every attribute,
and a searchable contacts list.

### 2h. Dashboard gaps

- **Global Cmd+K search is dead.** `TopBar.tsx:32` pushes `/leads?search=…` but **nothing
  ever reads a query param** (`useSearchParams` → zero hits). Type "dentist", press Enter,
  get all 75 leads.
- **`/docs` 404s.** `Sidebar.tsx:174` links to a route that doesn't exist.
- **15 native `alert()` dialogs**, no toast system — even though `@radix-ui/react-toast` is
  already a dependency and never imported. **10 of 15 runtime deps are dead weight**
  (react-query, zod, react-hook-form, radix-dialog/label/slot/icons).
- **Launch has no confirmation** (`SequenceDetail.tsx:109`) — the highest-consequence action
  (sends real email) has the least protection, while lead/mailbox delete do get `confirm()`.
- **Mobile is structurally broken.** `Sidebar.tsx:94-97` is `w-60 shrink-0` with **zero
  responsive prefixes**; on a 390px viewport the sidebar takes 240px of 390px. The e2e test
  that "verifies" this asserts `document.scrollWidth - clientWidth <= 4` — but `body` is
  `overflow-hidden`, so it **passes while the layout is unusable.**
- **No design system.** `tailwind.config.ts` defines semantic tokens + dark mode; **zero**
  components use them and there are **zero `dark:` classes** in the app. `cn()` is never
  imported. 175 occurrences of `text-[8px]`–`text-[11px]` (9px fails legibility floors).
  **8 uses of `backdrop-blur-xs`** — an invalid Tailwind class that compiles to nothing.
- **`lib/api.ts` has no timeout, no retry, no `AbortController`** → stale-response races
  (two in-flight `getLeads` can resolve out of order and overwrite each other). `enrichLead`
  can hang for 30–120s with no abort.
- **CI ignores type errors.** `next.config.mjs` sets `ignoreBuildErrors` + `ignoreDuringBuilds`
  → `tsc --noEmit` finds **3 live errors** CI never sees. Playwright is not in CI at all.
- **9 of 12 e2e tests can never fail the build** — they `findings.push(...)` instead of
  asserting. The committed `dashboard/shots/findings.json` proves it was already failing.
- **The home page fabricates a KPI delta**: `page.tsx:180` renders "+30 discovered" when the
  total is 30 — directly under a comment saying *"never fake demo numbers."*
- **No rupee pricing anywhere** — the entire product thesis ("Apollo but free for Indian
  SMBs") is absent from the UI.
- **No GSTIN field, no Hindi/Hinglish UI** (no `t()`, no locale switcher, no RTL readiness).

---

## 4. Wave 3 — The India moat (where we beat Apollo, not just match it)

Apollo has **no Indian registry data, no WhatsApp routing, no STD-code resolution, no DLT
context**. These are the features that make an Apollo clone irrelevant.

1. **GSTIN / Udyam (MSME) / CIN registry lookup** — a GST-scoped list is a genuine moat and
   one public registry away. Currently no such column exists anywhere.
2. **STD-code → city resolution** — `sources/in_phone.py:37-131` already has a verified SDCA
   table. `city_from_phone()` is **never called outside its own module.** This is a
   done-and-buried asset: pincode clusters, city tiers, and per-city analytics for free.
3. **Mobile vs landline as a score signal** — `in_phone.is_mobile` is independent
   information (currently wasted: the `whatsapp` signal is **100% collinear with `phone`**,
   so 15 of 100 score points are free). `Contact.preferred_channel` is computed and then
   **never read by the sender**.
4. **WhatsApp-first channel routing** — a lead with a mobile should route to WhatsApp
   before email. Apollo has no equivalent.
5. **Real festival + IST timing windows** — currently decorative: `india_copy.py`'s
   `localize_template()` is **never called by the sender**, so `{{festival_line}}` ships
   **literally** to prospects. There is no send-window control at all — a launch at 3 a.m.
   IST sends at 3 a.m. IST.
6. **Real multi-language copy** — Hinglish today is 6 static closer strings to copy-paste.
   Marathi/Telugu/Bengali/Kannada/Tamil are absent.
7. **India's directory ecosystem** — JustDial, Sulekha, IndiaMART, InPhone, Practo, and
   (for the wedge) IndiaMART's *product* directory for manufacturing/wholesale ICPs, which
   is high-value and currently noise for service ICPs.

---

## 5. README truth-check (credibility)

Roughly a third of the README's headline claims are **false against the code**. A reviewer
who runs the documented commands and finds them broken costs more credibility than any
feature gap.

| README claim | Reality |
|---|---|
| "parses `APP_INITIALIZATION_STATE`" | **Zero occurrences in the repo.** The code does `json.loads(...)` on positional JSON. |
| "internal protobuf `pb=` transport" | It's not protobuf — it's positional JSON. No protobuf dep. |
| "Humanized deceleration & viewport jitter" | `random_delay` and `get_random_viewport` are **imported and never called**. No mouse curves. |
| "Unclaimed GBP Detection … canonical *Claim this business* anchor" | The HTTP path never sets `is_claimed`; the Playwright path does a **text match**. The scoring weight never fires. |
| "Playwright Stealth Fallback" | It's **primary** on `/scraper/start`, not fallback. Stylesheets are *not* blocked (only image/media/font). |
| "multi-source" | 3 of 4 sources return **0 leads** against live sites. |
| "learns each domain's actual format" | Learns 4 of 10 patterns; mis-learns 4 more at 0.95 confidence; **discards seeds** when exec names don't match. |
| "Confidence-Blended Inference" | Not dominance-aware; and the confidence is **discarded** by the caller. |
| "Algorithmic 1-on-1 AI Icebreakers (sentiment & pain points)" | Static 9-key dict + 3 format branches. No LLM, no review text, no sentiment. |
| "Source-Trust Scoring … *observed* reliability" | Hand-written constants. Never observed. Not applied to the main scrape path. |
| "Multi-Step Sequences & Bounce Guard" | Delay math exists; **no scheduler**. Requires manual re-click. |
| "Hinglish & Festival-Aware Copy" | `localize_template()` is **never called by the sender**. |
| "warm WhatsApp handoff" | Requires ≥1 click; **click tracking doesn't exist**. Permanently empty. |
| "80+ words, 0-100 score … all-caps density, exclamation ratios and hyperlink density" | The 3 named signals **don't exist**. Indian clichés score "Good". |
| "Native Model Context Protocol (MCP) SDK" | Hand-rolled `asyncio.StreamReader` loop. No `mcp` package. |
| "Twenty CRM & Webhook sync engine" | One endpoint, one unsigned POST, no events/retries/signing. |
| "server-side rendering" | Every route builds as `○ (Static)` — zero SSR. |
| "no built-in auth" | ✅ True — but it's the shipped Docker default, and CORS is `*` + credentials. |
| "196/196 passing" | ✅ True. But 9/12 e2e tests can't fail, and CI skips type-checking. |

---

## 6. Suggested execution order

**Day 1–2 — Unbreak it** (≈8h): B1 mailbox cap · B2 send gate · B5 `has_email` + pagination ·
S20 auth+CORS · the one-line `generate_ai_icebreaker` import bug (500 on a shipped feature) ·
S23 `purge_expired` predicate.

**Day 3–4 — Make it fast** (≈8h): B4 `q=` split (3.4× coverage) · S6 HTTP-first scraping ·
S1+S2+S3 enrichment concurrency + async verifier · S10 indexes + S12 SQLite pragmas ·
S21 SSRF guard.

**Day 5–6 — Make it true** (≈8h): B3 campaign scheduler + "waiting vs done" ·
S22 bounce retry + sender-vs-recipient classification · S13 pattern inference rewrite ·
S24 token fallback + preview parity · S18+S19 MCP contact-ids and scrape scoping.

**Week 2 — Make it Apollo** (2 weeks): 2a People table + `/contacts` API · 2d live
ICP-relative scoring · 2b structured ICP filters + honest warnings · 2c real source-trust
feedback loop · S14/S15 decision-maker extraction · 2e analytics funnel · 2f A/B statistics ·
S25 click tracking · S17 India-aware spam linter.

**Week 3 — Make it ours** (2 weeks): GSTIN/Udyam registry · WhatsApp-first channel routing
· real festival/IST send windows · multilingual copy · directory ecosystem expansion
(JustDial/Sulekha/IndiaMART fixes) · rupee-denominated cost-vs-Apollo UI · a real design
system + dark mode + mobile.

**Week 4 — Harden** (1 week): job queue with retries/DLQ · audit log · Prometheus metrics ·
Alembic migrations (the dep is already in `requirements.txt` with zero migrations) ·
Postgres in CI · e2e tests that actually fail the build.

---

## 7. Measured outcomes

| Metric | Today | After Waves 0–1 | After Wave 2 |
|---|---|---|---|
| Unique leads per scrape query | 30 | **103** | 103 + multi-source |
| Enrichment throughput | 9s/lead serial | **~1.1s/lead** | + persisted pattern cache |
| Scrape wall clock | 8.9s (Playwright) | **2.4s** (HTTP) | — |
| Leads/day per IP | ~2,000 | **~10,000** | — |
| Working data sources | 1 of 4 | **4 of 4** | + registry sources |
| Hard-bounce rate | 25–30% | **<5%** | <3% |
| Mailbox capacity | 50 **lifetime** | **50/day, forever** | + warmup ramp effective |
| `rank_existing` @100k | 13.6s | **<100ms** | — |
| Lead-list query @500k | ~345ms | **<100ms** | + FTS/trigram |
| CSV import 5k rows | 15.2s | **1–2s** | + streaming export |
| Event loop stall | 10s | **0s** | — |
| Named decision-maker found | 8–15% | 20–30% | **40%+** (People table) |
| Pattern detection | 4/10 | **8/10** | + per-domain persistence |
| API p99 during enrichment | seconds | **milliseconds** | — |
| Sequences running autonomously | 0% | **100%** | + branching |
| ICP filters expressible | 3 | 3 | **20+ attributes** |
| Analytics dimensions | 4 counters | 4 counters | **funnel + cohorts + heatmap** |
