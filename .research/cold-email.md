# Cold Email Outreach SaaS — 2025/2026 Implementation Reference

**Purpose:** reverse-engineering spec for a self-hosted, open-source equivalent (target: `leadforge`).
**Vendors analyzed:** Instantly.ai, Smartlead.ai, lemlist, Apollo.io, Mailshake, Woodpecker.co, Warmup Inbox, Mailreach, GlockApps.
**Research date:** 2026-10-09. Prices are as published on vendor pricing pages on that date; SaaS pricing changes frequently — re-verify before acting.
**Evidence base:** vendor help centers (Instantly Intercom docs incl. sitemap + `llms-full.txt` + OpenAPI spec `api.instantly.ai/openapi/api_v2.json`, lemlist Intercom docs), machine-readable pricing fact sheets (`smartlead.ai/pricing.md`), Gmail/Google sender guidelines, Yahoo Sender Hub, RFC 8058, BIMI Group implementation guide.

> **Tooling note / honesty flag:** no `web_search` tool was available in this environment. All research was done via `fetch_web_content` against canonical vendor URLs plus `curl` against vendor sitemaps, `llms.txt`, and OpenAPI specs. Where a vendor's pricing page is JS-gated (Apollo) or Notion/Cloudflare-gated (Smartlead help center), that is called out explicitly rather than guessed.

---

## 0. Platform map — what actually differentiates the category

| Capability | Instantly | Smartlead | lemlist | Woodpecker | Mailshake | Apollo |
|---|---|---|---|---|---|---|
| Warmup engine | ✅ pool + private/premium pools | ✅ private vetted pool | ✅ lemwarm | ✅ free warmup | ✅ unlimited | ✅ basic |
| Inbox rotation | ✅ unlimited accts/campaign | ✅ unlimited accts | ✅ round-robin, sticky sender | ✅ inbox rotation | ✅ Email Rotation ($49+) | ✅ per-seat mailbox |
| Per-mailbox daily cap | ✅ 30/mo recommended (50 AirMail) | ✅ platform-managed | ✅ 25–30/day cap, 50 ceiling | ✅ adjustable | ✅ throttling | provider-bound |
| Timezone/business hours | ✅ 3 modes | ✅ | ✅ per-prospect timezone | ✅ prospect timezone | ✅ scheduling | ✅ |
| A/B + auto-optimize | ✅ 26 variants/step, auto-deactivate | ✅ | ✅ permanent winner pick | ✅ 5 versions | ✅ | ✅ |
| Unified inbox | ✅ Unibox v2 (+ Others folder) | ✅ Master Inbox | ✅ Unified Inbox | ✅ Centralized inbox | ✅ ($49+) | ✅ |
| Auto-pause on high bounce | ✅ >5%, ≥200 sends | ✅ | ✅ | ✅ | — | — |
| Seed-based placement test | ✅ Inbox Placement | ✅ SmartDelivery | ✅ placement tests | ✅ domain audit | ✅ | — |
| Sequence conditional branching | ✅ Subsequences | ✅ | ✅ condition-based | ✅ condition-based | basic | ✅ |
| Dedicated IP infra | ✅ SISR | ✅ SmartServers $39 | ❌ | ❌ | ❌ | ❌ |

**The two things that separate the category from generic ESPs:** (1) a *warmup engine* that manufactures engagement against a pool of real third-party mailboxes, and (2) a *pacing/rotation scheduler* that treats per-mailbox and per-provider daily volume as a hard budget rather than a config field. Everything else (sequences, inbox, analytics) is a standard sales-engagement layer.

---

## 1. Email warmup — mechanism, metrics, and algorithmic spec

### 1.1 How it actually works (documented behavior)

**Instantly (`help.instantly.ai/en/articles/5975329`)** — the most explicitly documented of the set:

1. Enabling warmup joins your mailbox to a **shared pool of other Instantly users who also enabled warmup**.
2. Bidirectional traffic: your account sends warmup mail to pool members; pool members send to you.
3. **All warmup emails are automatically opened.** A configurable percentage receive replies "with positive sentiment."
4. Signals generated: open rate + reply rate → provider-side engagement/reputation.
5. **Spam-to-inbox rescue is first-class:** "Our system automatically moves warmup emails from spam to the inbox. This process is what builds your sender reputation over time." New accounts *start* with mail landing in spam; that is expected. Instantly continuously injects *never-before-contacted* pool accounts into your pool so the reputation generalization isn't circular.

**Smartlead** — warmup auto-starts on mailbox connect. "Self-adjusting warmup infrastructure" increases volume without manual setup; auto-moves spam→primary; AI-generated natural conversations; "custom identifier tags" in the mail. Pool is **private, curated, and reward-based**: "Only vetted senders make it into our private pool, no public sign-ups or bad actors." Access is earned, not purchased — explicitly positioned as anti-dilution vs. public warmup networks. Recommended: **≥2 weeks** for an existing account, **1–2 months** for a new domain.

**lemlist (lemwarm)** — warms **email addresses, not IPs**. Hard technical constraint: the connected mailbox must be a **real inbox supporting both SMTP and IMAP**. SMTP relays and send-only services are *not supported* (explicitly lists SendGrid, Mailgun, SES, Postmark, Mailjet, Sendinblue, Cloudmark as unsupported). It warms the **primary address on the provider side** — an alias only warms if it has its own mailbox. `1 account = 1 email address = 1 subscription` on lemwarm-only plans.

**Warmup Inbox** — publishes the most concrete pool and volume numbers:

| Tier | $/inbox/mo | Warmup msgs/day | Warmup reply rate | Notes |
|---|---|---|---|---|
| Basic | $15 | 75 | up to 25% | 30,000+ real inboxes; spam & category monitoring |
| Pro | $49 | 250 | up to 45% | + custom templates/topics, language warmup, per-ESP warmup |
| Max | $79 | 1,000 | up to 50% | + priority support, unlimited developer API |

**Mailreach** — $19.50/mailbox/mo, **up to 100 warmup emails/day per mailbox**. Works with any SMTP-capable ESP (Gmail/Workspace, Outlook/O365, Zoho, Brevo, Mailjet, Mailgun, SendGrid, SES, SparkPost, Ionos, OVH). Key content detail: *"Unlike our competitors, we don't include the same word or code in all subject lines of our warming emails"* — i.e. warmup mail must not carry a shared sentinel string, and *"Google and Microsoft suggest smart replies on our warming emails"* (content is realistic enough to trigger provider smart-reply UI). Initial phase: **14 days minimum with zero campaign sends**, then keep warming during and between campaigns.

**Woodpecker** — free warmup bundled; described as "AI-generated sales conversations with real email accounts." Extra warmups are an add-on at **$5/month per email account**.

### 1.2 Seed pool architecture (what to build)

A warmup network is a **directed graph of mailboxes** with three distinct roles:

```
SEED POOL (fixed fleet)          PARTICIPANT POOL (customer mailboxes)
  N_provider-bucketed                M mailboxes opted in
  inboxes across Gmail/               each with own ramp state
  Workspace, Outlook/O365,
  iCloud, Zoho, Yahoo, ...
```

Design constraints drawn from vendor docs:

- **Provider bucketing is mandatory.** Warmup mail must land at a diverse mix of Gmail/Outlook/iCloud/Yahoo/Zoho mailboxes — reputation is per-receiving-provider, so a Gmail-only pool does nothing for Outlook placement. GlockApps' seed list is the canonical example of provider diversity: AOL, Outlook, Yahoo, Gmail, Hotmail, Zoho, Exchange/O365, Amazon WorkMail, G Suite, ATT.net, GMX, ProtonMail, Mail.ru, Yandex, Web.de, T-online, Gmx.de, Laposte.net (FR), Seznam.cz, Onet.pl, Interia.pl, O2.pl, Ukr.net, Naver.
- **Pairing must avoid loops.** A↔B both warming means every "reply" is reciprocal and self-referential. Vendor mitigation: constantly introduce *never-contacted* partners (Instantly's stated behavior). Implement with a pairing table that excludes prior pairs and prefers low-degree partners.
- **Pool tiers change economics.** Instantly runs three pools with materially different results: **Standard** (green flame, largest), **Premium** (blue flame — aged Google + Microsoft accounts only, **9% more replies**, $500/mo/workspace for up to 1,000 third-party Microsoft accounts, $1,000/mo for 2,000, unlimited third-party Google), and **Private** ($1,000/mo+, billed per account not workspace, fully isolated, you supply the accounts, requires ≥50% Google/Outlook to be effective).

### 1.3 Documented ramp schedule

**Instantly defaults (recommended for new accounts):**

| Setting | Value |
|---|---|
| Increase per day (`warmup.increment`) | **1** |
| Daily warmup limit (`warmup.limit`) | **10** |
| Reply rate (`warmup.reply_rate`) | **30%** |
| Disable slow warmup | **off** (only for already-warmed accounts) |
| Open Rate (advanced) | configurable % of sent warmup mail auto-opened |
| Spam Protection (advanced, `spam_save_rate`) | % moved from spam→inbox |
| Mark Important (advanced, `important_rate`) | % starred/flagged |
| Read Emulation | scroll-through simulation |
| Weekdays only mode | send weekdays only, **still receive on weekends** |
| Warm custom tracking domain (`warm_ctd`) | include your CTD in warmup mail |

Derived day-by-day ramp (slow ramp on, increment 1, limit 10): **day 1 → 1, day 2 → 2, … day 10 → 10, then hold at 10.** The OpenAPI describes `increment` as "Daily increment added to the sending limit, **starting from 0**, until the full daily limit is reached (slow ramp)," enum `["disabled","0","1","2","3","4"]` — so increment 1 = +1/day.

**lemlist ramp (`Understand sending limits`):** lemwarm ramps **+1/day for ~40 days** to reach target, then **holds at target for 14 days**. Cold sending stays at **0** during that entire window.

**Composite ramp used by lemlist as the reference safe curve** (per mailbox):

```
Warmup Score < 90  → 0 cold sends. lemwarm only.
Score >= 90 AND 14d stabilization AND inbox rate > 90%
                   → cold sends open at 10–15/day per mailbox
                   → +5 per week
                   → hard cap 25–30/day cold
HARD CEILING       → warmup + cold <= 50/day per mailbox
DOMAIN < 1 month   → whole domain < 100 emails/day across ALL mailboxes
Post-incident      → restart ~15 cold + 15 warmup (~30/day),
                     ramp increment 3 (not 1)
Paused > 7 days    → trust decayed; short re-ramp required, increment 3
```

**Instantly readiness gate:** ≥2 weeks warmed (3 weeks for AirMail accounts) **and** warmup health score >90%. Pre-warmed accounts bought from Instantly are usable day 1.

### 1.4 Warmup metrics tracked — and exact formulas

**Warmup Health Score (Instantly, `articles/13939939`)** — the single most important warmup metric, and it is *not* what people assume:

```
HealthScore = (warmup_emails_in_inbox / total_sent_warmup_emails) * 100
```

- Computed over a **rolling 7-day window**.
- Measures **warmup placement only — explicitly NOT campaign placement.**
- Target: **> 90%**.
- Documented worked example: 80 sent in 7 days, 1 in spam → 79/80 = **98.7%**.
- Edge cases: starts at **0** (warmup mail begins sending after **12:00 AM UTC** the next day); **auto-resets to 0** if no warmup sent in the last 7 days.
- Spam detection mechanism: `inbox_emails = total_sent − spam_emails`, where `spam_emails` is surfaced as **"X saved from spam"** in warmup analytics. So placement is discovered by **IMAP-inspecting the receiving mailbox's Spam/Junk folder**, not by any provider API.

**lemlist Warmup Score** — a weighted composite, and lemlist is emphatic that it is *not* a placement percentage ("A score of 80 is not an 80% inbox rate"):

| Factor | Weight |
|---|---|
| Email setup / DNS (SPF, DKIM, DMARC, MX) | **40 pts** |
| Warmup spam rate | **30 pts** |
| Blacklists | **20 pts** |
| Domain age | **10 pts** |

Bands: **<65 red** (do not start campaigns; pause and investigate — usually DNS or blacklist), **65–90 orange** (still warming; no campaign may start), **≥90 green** (eligible, *plus* 14 days stabilization with inbox rate >90%). Note the consequence: because DNS is 40 of 100 points, a mailbox with broken SPF/DKIM/DMARC is **score-capped at 60 regardless of sending behavior**.

**Other metrics the platforms track per warmup/account:**

| Metric | Source |
|---|---|
| Inbox vs Spam placement % | IMAP folder inspection of partner mailboxes |
| Blacklist hits | DNSBL queries (Spamhaus ZEN, SORBS, Barracuda, SpamCop, SURBL…) |
| Warmup reply rate | target 30% (Instantly), 25/45/50% by tier (Warmup Inbox) |
| Open rate (of warmup mail) | self-generated |
| Spam-rescue count | "X saved from spam" |
| Warmup send volume/day | dashboard + `sent_today` |
| Account health | `warmup_status` enum below |
| Domain age | registration date |

**Instantly `warmup_status` enum (from OpenAPI):** `0 = Paused`, `1 = Active`, `-1 = Banned`, `-2 = Spam Folder Unknown`, `-3 = Permanent Suspension`. Note `-2`: the system explicitly models *"we cannot determine placement"* as distinct from *"placement is bad"* — a state any IMAP-based implementation must handle (e.g. partner mailbox credentials expired).

**Instantly `account.status` enum:** `1 = Active`, `2 = Paused`, `3 = Temporarily paused for maintenance (auto-resumes)`, `-1 = Connection Error`, `-2 = Soft Bounce Error`, `-3 = Sending Error`. CHUNK1
echo "chunk1 written: $(wc -l < /Users/aryanbansal/Downloads/leadforge/.research/cold-email.md) lines"

### 1.5 Concrete algorithmic spec — open-source warmup engine

#### 1.5.1 Schema

```sql
-- Pool membership
CREATE TABLE warmup_mailbox (
  id              BIGSERIAL PRIMARY KEY,
  email           TEXT UNIQUE NOT NULL,
  provider        TEXT NOT NULL,           -- google|microsoft|icloud|zoho|yahoo|smtp
  role            TEXT NOT NULL,           -- seed | participant
  -- credentials: AES-GCM encrypt at rest, KMS-held DEK. NEVER plaintext.
  smtp_host TEXT, smtp_port INT DEFAULT 587,
  imap_host TEXT, imap_port INT DEFAULT 993,
  secret_ref      TEXT NOT NULL,           -- pointer into secret store
  is_healthy      BOOLEAN DEFAULT TRUE,
  domain_age_days INT,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON warmup_mailbox(role, provider) WHERE is_healthy;

-- Per-mailbox ramp state machine
CREATE TABLE warmup_state (
  mailbox_id            BIGINT PRIMARY KEY REFERENCES warmup_mailbox(id),
  started_at            DATE NOT NULL,
  warmup_day            INT  NOT NULL DEFAULT 1,
  increment_per_day     INT  NOT NULL DEFAULT 1,   -- Instantly default: 1
  daily_limit           INT  NOT NULL DEFAULT 10,  -- Instantly default: 10
  reply_rate            REAL NOT NULL DEFAULT 0.30,-- Instantly default: 0.30
  open_rate             REAL NOT NULL DEFAULT 0.95,
  spam_save_rate        REAL NOT NULL DEFAULT 0.02,
  important_rate        REAL NOT NULL DEFAULT 0.80,
  slow_ramp_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
  weekday_only          BOOLEAN NOT NULL DEFAULT FALSE,
  read_emulation        BOOLEAN NOT NULL DEFAULT TRUE,
  warm_ctd              BOOLEAN NOT NULL DEFAULT FALSE,
  filter_tag            TEXT DEFAULT 'warmup',
  -- rolling counters, decremented lazily on read
  sent_7d               INT NOT NULL DEFAULT 0,
  spam_7d               INT NOT NULL DEFAULT 0,
  paused_until          TIMESTAMPTZ,
  warmup_status         SMALLINT NOT NULL DEFAULT 1
                     -- 0 paused, 1 active, -1 banned, -2 spam_unknown, -3 perm_suspend
);

-- Immutable event log (drives all analytics + health score)
CREATE TABLE warmup_event (
  id          BIGSERIAL PRIMARY KEY,
  mailbox_id  BIGINT REFERENCES warmup_mailbox(id),
  partner_id  BIGINT REFERENCES warmup_mailbox(id),
  direction   TEXT NOT NULL,        -- outbound | inbound
  message_id  TEXT NOT NULL,
  event       TEXT NOT NULL,        -- sent|delivered|opened|replied|spam_rescued|marked_important|bounced
  folder      TEXT,                 -- INBOX|Junk|Spam|Unknown  (IMAP-observed)
  observed_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON warmup_event(mailbox_id, observed_at DESC);
-- Idempotency: warmup retries must not double-count
CREATE UNIQUE INDEX ON warmup_event(message_id, event);

-- Non-repeating pairing ledger
CREATE TABLE warmup_pair (
  a BIGINT, b BIGINT, last_paired_at TIMESTAMPTZ,
  times INT DEFAULT 1,
  PRIMARY KEY (a, b),
  CHECK (a < b)   -- canonical ordering prevents duplicate edges
);

-- Suppression is global across warmup AND campaigns (see section 6)
CREATE TABLE suppression (
  id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL DEFAULT 'workspace',
  email TEXT, domain TEXT,
  reason TEXT NOT NULL,   -- unsubscribed|bounced_hard|blocklist|complaint|manual|ai_trigger
  source_campaign_id BIGINT,
  created_at TIMESTAMPTZ DEFAULT now(),
  CHECK (email IS NOT NULL OR domain IS NOT NULL)
);
CREATE UNIQUE INDEX ON suppression(lower(email)) WHERE email IS NOT NULL;
```

#### 1.5.2 Daily volume resolution

```python
def warmup_quota_today(state) -> int:
    """Target warmup emails for this mailbox today."""
    if state.warmup_status != 1:            return 0
    if state.paused_until and state.paused_until > now_utc():
        return 0                              # OOO smart-pause honoured
    if state.weekday_only and now_utc().weekday() >= 5:
        return 0                              # send-side only; still RECEIVES
    if not state.slow_ramp_enabled:
        return state.daily_limit              # Instantly 'Disable slow warmup'
    # Instantly: 1 on day 1, +increment/day, capped at daily_limit
    return min(state.daily_limit,
               state.increment_per_day * (state.warmup_day - 1) + 1)
```

This reproduces the documented Instantly curve exactly: increment 1, limit 10 → `[1,2,3,4,5,6,7,8,9,10,10,...]`.

#### 1.5.3 Partner selection (the rotation algorithm for warmup)

```python
def pick_partners(mailbox_id, provider, k) -> list[int]:
    """
    Constraints, in priority order:
     1. Never re-pair within cooldown (COOLDOWN_DAYS = 30) -> prevents
        a closed reciprocal loop that teaches the ISP nothing new.
     2. Provider diversity: cap per-provider share at MAX_PROVIDER_SHARE
        (0.5) so reputation generalizes across Gmail AND Microsoft.
     3. Degree balancing: prefer partners with fewest recent sends
        (least-send-first) so one mailbox is not a hub for the whole pool.
     4. Same-provider boost (weight 1.5): Gmail->Gmail reputation is what
        lemlist calls ESP matching; it demonstrably helps placement.
    """
    cands = db.query("""
        SELECT m.id, m.provider, COALESCE(p.times,0) AS times,
               COALESCE(r.sent_7d,0) AS sent_7d
        FROM warmup_mailbox m
        LEFT JOIN warmup_pair p
               ON (LEAST(m.id,$1),GREATEST(m.id,$1))=(p.a,p.b)
        LEFT JOIN warmup_state r ON r.mailbox_id=m.id
        WHERE m.role='seed' OR m.role='participant'
          AND m.id <> $1
          AND m.is_healthy
          AND m.id NOT IN (
                SELECT b FROM warmup_pair WHERE a=$1
                  AND last_paired_at > now()-interval '30 days')
        """, mailbox_id)

    score = lambda c: (1.0/(1+c.times)) * (1.0/(1+c.sent_7d)) \
                      * (1.5 if c.provider==provider else 1.0)
    chosen = heapq.nlargest(k, cands, key=score)
    enforce_provider_cap(chosen, max_share=0.5)
    return chosen
```

#### 1.5.4 Per-message action probabilities

Each outbound warmup message is assigned a treatment draw **once, at send time, and persisted on the event row** so analytics are reproducible:

```python
@dataclass
class WarmupTreatment:
    auto_open:      bool   # p = state.open_rate      (0.95)
    reply:          bool   # p = state.reply_rate     (0.30)
    reply_positive: bool   # p = 0.8 | reply          (positive sentiment)
    rescue_from_spam: bool # p = state.spam_save_rate (0.02)
    mark_important: bool   # p = state.important_rate (0.80)
    read_emulate:   bool   # p = 1.0 if state.read_emulation
    subject_variant: int   # index into template bank
    topic_cluster:  str    # lemlist 'Smart cluster'

def draw_treatment(state, rng) -> WarmupTreatment: ...
```

**Content generation requirements** (from Mailreach/Woodpecker docs):
- Realistic, multi-turn business conversation, **not** "lorem" — Google/Microsoft surface smart replies, which means the content must be reply-worthy.
- **No shared sentinel string** across all warmup subjects (Mailreach explicitly differentiates on this). Use per-message topic clusters instead of a magic token.
- Filter tag / category label so warmup mail does not pollute the user's primary inbox (Instantly `warmup_custom_ftag`, default `warmup`, with a "Generate random" helper; changes apply next sending cycle).
- If `warm_ctd` is on, embed the custom tracking domain so the warmup traffic also builds reputation on the tracking subdomain.

#### 1.5.5 Placement detection via IMAP

```python
FOLDER_ALIASES = {
  'inbox':   ['INBOX'],
  'spam':    ['Junk','Spam','Bulk','[Gmail]/Spam','Junk E-mail'],
  'archive': ['Archive','[Gmail]/All Mail'],
}

def observe_placement(partner_mailbox, msg_id) -> str:
    """Runs as the RECEIVER. This is the ground truth for HealthScore."""
    imap = IMAP4_SSL(partner_mailbox.imap_host, partner_mailbox.imap_port)
    imap.login(...)
    for canonical, aliases in FOLDER_ALIASES.items():
        for a in aliases:
            try:
                typ, data = imap.select(a, readonly=True)
                if typ != 'OK': continue
                typ, ids = imap.search(None, f'(HEADER Message-ID "{msg_id}")')
                if typ == 'OK' and ids[0].split():
                    imap.logout()
                    return canonical          # 'inbox' | 'spam' | 'archive'
            except imap.error:
                continue
    imap.logout()
    return 'unknown'                          # -> warmup_status = -2
```

Then the rescue action: if `folder == 'spam'` and treatment drew `rescue_from_spam`, `IMAP MOVE` it to INBOX and record `spam_rescued`. **Do not rescue unconditionally** — a 100% rescue rate is an obviously synthetic pattern; Instantly models this as a probability (`spam_save_rate`, example 0.02), not a guarantee.

#### 1.5.6 Health score computation

```python
def health_score(mailbox_id) -> float | None:
    row = db.one("""SELECT sent_7d, spam_7d FROM warmup_state
                    WHERE mailbox_id=$1"", mailbox_id)
    if row.sent_7d == 0:
        return 0.0     # documented: no sends in 7d -> score resets to 0
    return round(100.0 * (row.sent_7d - row.spam_7d) / row.sent_7d, 1)

# Rollup job, runs every 15 min:
#   sent_7d = count(warmup_event.event='sent' AND observed_at > now()-7d)
#   spam_7d = count(distinct message_id WHERE folder='spam'
#                    AND direction='outbound' AND observed_at > now()-7d)
```

#### 1.5.7 lemlist-style composite warmup score (recommended addition)

```python
def warmup_score(mailbox) -> tuple[int, list[str]]:
    """Returns (score 0..100, list_of_findings). Mirrors lemlist weights."""
    s, findings = 0, []
    # 1. DNS = 40 pts -- binary per record, so a broken record is a hard cap.
    dns = audit_dns(mailbox.domain)       # MX, SPF incl. mailbox, DKIM, DMARC
    got = sum([dns.mx, dns.spf, dns.dkim, dns.dmarc])
    s += 40 * got / 4
    if got < 4:
        findings.append(f'DNS {got}/4 -> capped near 60 regardless of sending')
    # 2. warmup spam rate = 30 pts (linear: 0% spam -> 30, 5%+ -> 0)
    sr = spam_rate_7d(mailbox.id)
    s += 30 * max(0.0, 1.0 - sr / 0.05)
    # 3. blacklists = 20 pts
    hits = query_dnsbl(mailbox.domain, DNSBL_LIST)
    s += 20 if not hits else 0
    findings += [f'listed on {b}' for b in hits]
    # 4. domain age = 10 pts
    age = mailbox.domain_age_days
    s += 10 if age >= 90 else (5 if age >= 30 else 0)
    return int(s), findings

# Gating (lemlist, verbatim thresholds):
#   score < 65  -> RED:  do not send. investigate.
#   65..89      -> ORANGE: still warming. no campaign.
#   >= 90 AND 14d stabilized AND inbox rate > 0.90 -> GREEN: may launch.
```

#### 1.5.8 Blacklist monitoring

```python
DNSBL_LIST = [
    'zen.spamhaus.org',        # SBL + XBL + PBL + CSS
    'bl.spamcop.net',
    'b.barracudacentral.org',
    'dnsbl.sorbs.net',
    'psbl.surriel.com',
    'dnsbl-1.uceprotect.net',
    'ix.dnsbl.manitu.net',
    'all.s5h.net',
    'multi.surbl.org',         # URIBL: checks domains in message body
    'dbl.spamhaus.org',        # domain (not IP) blocklist
]

def query_dnsbl(domain_or_ip, zones=DNSBL_LIST) -> list[str]:
    """Standard reversed-octet convention: 1.2.0.192.zen.spamhaus.org"""
    q = '.'.join(reversed(domain_or_ip.split('.'))) if is_ip(domain_or_ip) \
        else domain_or_ip
    listed = []
    for z in zones:
        try:
            if dns.resolver.resolve(f'{q}.{z}', 'A'): listed.append(z)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, TimeoutError):
            pass
    return listed
```

Schedule: **every 6h** during warmup (a listing during ramp is the earliest possible warning), **daily** afterwards. Alert on first-seen listing and auto-set `warmup_status` to a paused/investigate state rather than continuing to send into a listed IP.

#### 1.5.9 Inbox placement (seed) test — the offline complement

Warmup measures *your* mailboxes' reputation. A placement test measures *one message* against a controlled seed fleet. GlockApps' 6-step flow is the reference implementation:

1. Operator composes the real campaign email.
2. Tool emits a **unique ID string**.
3. ID is pasted into the message **body or headers** (this is how the report is correlated back — no link-clicking required).
4. Operator sends to the **seed list**.
5. Tool IMAP-polls every seed mailbox and records the folder.
6. Report renders per-provider placement + diagnostics.

```python
FOLDER_TAXONOMY = ['Inbox', 'Promotions', 'Updates', 'Spam', 'Missing']
# 'Missing' = never arrived (rejected/deferred). Must be reported distinctly
# from 'Spam': a reject is an infra problem, spam is a content/reputation problem.

def placement_report(test_id) -> dict:
    rows = db.all("SELECT provider, folder FROM placement_result WHERE test_id=$1", test_id)
    agg = defaultdict(Counter)
    for r in rows: agg[r.provider][r.folder] += 1
    return {
      'inbox_pct':   inbox / total * 100,
      'spam_pct':    spam  / total * 100,
      'missing_pct': missing / total * 100,
      'per_provider': dict(agg),
      # Note: GlockApps/Gmail both warn placement != delivery.
    }
```

Pair this with **SpamAssassin** scoring (lemlist's DNS check surfaces a SpamAssassin score) and authentication checks. LeadForge already has `backend/app/campaigns/spam_checker.py` (176 lines, 80+ trigger words, 0–100 score) — the placement test should reuse that scorer as the content-analysis half and add the seed-fleet half.

---

## 2. Inbox rotation & sending pacing

### 2.1 Mailbox selection — documented algorithms

**Instantly.** "Accounts To Use" — assign an unlimited number of email accounts (or a **tag** for bulk assignment); "the system will rotate them automatically." The docs do **not** publish the selection function, so this must be treated as unspecified; the observable invariants are: unlimited accounts per campaign, automatic rotation, and **failover semantics that differ by cause**:

- Account *removed* from the campaign → another active account takes over sending.
- Account *disconnected* in the dashboard → **the campaign waits for it** and does **not** reassign. You must manually remove the disconnected account from "Accounts To Use" to restore rotation.

That asymmetry is a real design decision worth copying: an intentional removal is a user action (fail over immediately), a connection error is transient (wait), because silently re-homing a conversation onto a new mailbox breaks the From: identity mid-thread.

**lemlist** — the most explicit rotation spec of any vendor:

- Mechanism is stated as **round-robin distribution plus scheduling**.
- **Sticky sender:** Step 1 distributes new leads across the selected senders; **Steps 2, 3, … keep the same sender** assigned at the start of the sequence "so the conversation stays consistent." Each lead holds a 1:1 relationship with its sender for the whole sequence.
- **Per-step override:** you may force a specific sender for an individual step (use case: a manager sends the final touch).
- Rotation does **not** rebalance existing assignments — senders added after launch cause uneven distribution for already-assigned leads.
- **Critical caveat, stated verbatim:** *"Rotation is not a way around the volume caps. The sending ceiling is per provider, not per mailbox in isolation: six Google mailboxes share one Google-side reputation, not six independent budgets."*
- Gate before joining a rotation: **Warmup Score 90+ plus 14 days stabilization.**

**Smartlead.** "Automatically rotates sending across all connected mailboxes within a campaign… distributes send volume evenly, protects individual sender reputation, and improves deliverability by avoiding high-volume spikes from a single address." All plans include **unlimited email accounts**.

**Woodpecker.** "Inbox rotation" + **"Adaptive sending"** (human-like sending randomization, adjustable daily limits, customizable intervals).

**Mailshake.** Email Rotation is the feature that gates the $49 tier.

### 2.2 Per-mailbox daily caps — the documented numbers

| Vendor | Recommended cold cap | Hard ceiling | Notes |
|---|---|---|---|
| Instantly | **30 cold + 10 warmup per account/day** | AirMail: 50 cold/day | Campaign `daily_limit` = accounts × 30 |
| lemlist | **10–15/day** out of warmup, +5/week | **25–30/day** cold | **warmup + cold ≤ 50/day** per mailbox |
| lemlist (per-provider) | — | **<70/day per provider** total | incl. manual replies; 6 Google boxes share one budget |
| lemlist (new domain) | — | **<100/day for the whole domain** | if domain age < 1 month |
| lemlist (new mailbox) | 30–40/day | — | "open at 30" |
| Woodpecker | unlimited mailboxes, adjustable | — | per-account limits |
| Smartlead | platform-managed | — | unlimited accounts |

### 2.3 Pacing, jitter, and the rolling window

**Instantly campaign settings** (all verified):

| Setting | Default |
|---|---|
| Time gap between emails (min) | **9 minutes** |
| Random additional time | **5 minutes** |
| Daily limit | accounts × 30 |
| Schedule modes | Any time 24/7 · During office hours · Custom days+times |
| Timezone | per-campaign (IANA, e.g. `America/Chihuahua` in the OpenAPI example) |
| Max New Leads | caps Step-1 volume/day |
| Prioritize New Leads | off by default — **follow-ups first, then new leads** |

**lemlist pacing:** "Reach a new lead every 20 minutes" is the worked example — with 100 leads over a 9:00–17:00 (8h) window, first-step mail is spread evenly across the window. Community-safe default quoted as **every 15–20 minutes**. Business-hours windows, weekend sending optional.

**Rolling vs calendar window — an important implementation detail.** Instantly reports analytics in **UTC** explicitly so numbers are timezone-independent. lemlist enforces sending limits on a **rolling 24-hour** basis, not calendar days: *"if you send 25 emails between 1 PM Tuesday and 1 PM Wednesday, those count toward your limit for that period."* Copy the rolling window for limit enforcement (it is strictly harder to accidentally burst) and UTC for reporting.

### 2.4 Concrete implementation

```python
# ---------- next eligible send time for a mailbox ----------
def next_slot(mailbox, base_min=9, jitter_max=5):
    """Instantly defaults: 9 min gap + uniform(0,5) random."""
    gap = timedelta(minutes=base_min, seconds=rng.uniform(0, jitter_max*60))
    return mailbox.last_sent_at + gap

# ---------- rolling 24h budget (lemlist semantics) ----------
def sent_in_rolling_24h(mailbox_id) -> int:
    return db.scalar("""
      SELECT count(*) FROM sends
      WHERE mailbox_id=$1
        AND status='sent'
        AND sent_at > now() - interval '24 hours'""", mailbox_id)

def remaining_budget(mailbox) -> int:
    # hard ceiling combines cold + warmup: lemlist <=50/day per mailbox
    ceiling = mailbox.hard_daily_ceiling          # 50
    warm    = warmup_quota_today(mailbox.warmup_state)
    return max(0, ceiling - sent_in_rolling_24h(mailbox.id) - warm)

# ---------- send window / business hours ----------
def in_send_window(campaign, at=None, lead_tz=None) -> bool:
    at = at or now_utc()
    if campaign.schedule_mode == 'always':   return True
    tz = ZoneInfo(lead_tz) if (campaign.use_lead_tz and lead_tz) \
         else ZoneInfo(campaign.timezone)     # campaign-level default
    local = at.astimezone(tz)
    if campaign.skip_weekends and local.weekday() >= 5:  return False
    if campaign.holiday_calendar and local.date() in campaign.holiday_calendar:
        return False
    return any(w['from'] <= local.strftime('%H:%M') <= w['to']
               for w in campaign.windows)

# ---------- mailbox selection (sticky + failover) ----------
def select_mailbox(campaign, lead) -> Mailbox | None:
    """lemlist semantics: sticky per lead; Instantly semantics: free rotation."""
    # 1. Already assigned? Keep it (thread/From consistency).
    if campaign.sticky_sender and lead.assigned_mailbox_id:
        mb = load(lead.assigned_mailbox_id)
        if mb and mb.is_active and mb.status == 1 and remaining_budget(mb) > 0:
            return mb
        # mailbox went away -> explicit re-home, logged (breaks thread)
    # 2. Candidate pool = campaign accounts (or tag), healthy, in-window
    cands = [m for m in campaign.mailboxes
             if m.status == 1 and remaining_budget(m) > 0 and in_send_window(campaign)]
    if not cands: return None
    # 3. ESP matching (lemlist 'Gmail talks to Gmail', Instantly Provider Matching)
    if campaign.esp_matching:
        matched = [m for m in cands if m.provider == provider_of(lead.email)]
        if matched: cands = matched            # else fall through to any
    # 4. Round-robin, weighted by remaining budget so hot mailboxes drain
    #    evenly rather than a single mailbox absorbing the whole day.
    cands.sort(key=lambda m: -remaining_budget(m))
    return cands[0] if not campaign.round_robin else rr_next(cands)
```

**Weighted round-robin is the right default** (not plain RR): plain RR gives every mailbox equal *turns* but not equal *load* when caps differ (AirMail 50 vs standard 30). Sorting by remaining budget approximates least-loaded-first and naturally self-balances.

### 2.5 Guardrails that vendors auto-trigger

| Guardrail | Vendor | Threshold / behavior |
|---|---|---|
| High-bounce auto-pause | Instantly | bounce rate **>5%** → auto-pause campaign; requires **≥200 emails sent** first; after a resume, **not re-triggered for 7 days**; configurable, on by default |
| Adaptive slowdown | lemlist | bounce rate ↑ → algorithm slows sending; low open rate → slows; new domain → slower |
| Domain <1mo cap | lemlist | whole domain <100/day |
| Company send limit | Instantly | max leads on the same company domain per day/week/campaign (HyperGrowth+) |
| Provider capacity indicator | lemlist | Outreach Queue: Green 90–100%, Yellow 70–89%, Orange 50–69%, Red <49% of daily limit |
| Pause on quota risk | lemlist | proactively pauses when it predicts exceeding quota |
| IP rotation | Instantly SISR | continuously monitors IP performance, rotates high-reputation IPs in, **immediately replaces flagged IPs**; dedicated/private IP blocks for Lightspeed + large volume |
| Fingerprint guard | Instantly | identical mail sent from many inboxes simultaneously → throttling; needs real spintax uniqueness |
| HyperSend mode | Instantly | throughput over safeguards; for 1,000+ mailbox operators only; documented as reputation-risky |

**lemlist capacity formula (worth copying verbatim):**

```
email_capacity = scheduled_daily_emails / daily_email_limit
linkedin_capacity = (scheduled_invites + scheduled_messages)
                    / (invite_limit + message_limit)
calls = unlimited
# multi-sender filter: sum(activities) / sum(limits)
# NOTE: capacity counts ALL connected accounts, including ones in error.
#       Manual tasks and paused leads do NOT count.
```

---

## 3. Deliverability

### 3.1 SPF / DKIM / DMARC / BIMI generation

**Record formats (exact strings from vendor docs):**

```dns
; --- SPF (TXT at apex) ---
yourdomain.com.            IN TXT  "v=spf1 include:_spf.google.com ~all"
; Google Workspace / Microsoft 365 equivalents substitute the provider's
; include:. EXACTLY ONE SPF record per domain -- multiple records = failure
; (Instantly lists this as a top troubleshooting cause).

; --- DKIM (TXT, or CNAME for provider-managed selectors) ---
; selector._domainkey.yourdomain.com IN TXT "v=DKIM1; k=rsa; p=<base64 public key>"
; Google Workspace commonly uses a CNAME:
;   google._domainkey.yourdomain.com. IN CNAME google._domainkey.yourdomain.com.
; The selector MUST match what the signing provider expects (Instantly:
; 'DKIM not found' is usually a selector mismatch or typo).

; --- DMARC (TXT at _dmarc subdomain) ---
_dmarc.yourdomain.com.      IN TXT  "v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com"

; --- MX (required to RECEIVE replies; without it you cannot do
;     reply detection, warmup placement checks, or bounce parsing) ---
yourdomain.com.            IN MX 10 aspmx.l.google.com.

; --- BIMI ---
default._bimi.yourdomain.com. IN TXT "v=BIMI1; l=https://cdn.yourdomain.com/logo.svg; a=https://cdn.yourdomain.com/vmc.pem"
```

**Ordering matters (Instantly, explicit):** set up **DKIM and SPF first**, confirm they authenticate for **≥48 hours**, and only then enable DMARC. Turning on DMARC before SPF/DKIM work produces false failures at receivers.

**DMARC policy ladder:**

```
p=none      -> monitor only.  REQUIRED MINIMUM for bulk senders (Gmail + Yahoo,
               both Feb 1 2024). Emits rua reports, no enforcement.
p=quarantine-> suspicious mail to spam. Required tier for BIMI.
p=reject    -> drop failures.       Required tier for BIMI.
sp=         -> subdomain policy. BIMI needs p AND sp at quarantine or reject.
rua=        -> aggregate report destination. Yahoo 'strongly recommended'.
ruf=        -> forensic/failure reports (optional).
pct=        -> % of failing mail the policy applies to. BIMI REJECTS pct < 100.
```

**BIMI requirements (BIMI Group implementation guide):**
1. SPF + DKIM + DMARC all present and **aligned**.
2. DMARC at **enforcement** on org domain **and subdomains**: `p=quarantine; sp=quarantine` or `p=reject; sp=reject`. `p=none` and `pct<100` are **not accepted**.
3. Logo as **SVG Tiny PS** (the restricted SVG profile, not full SVG).
4. **VMC (Verified Mark Certificate)** or **CMC (Common Mark Certificate)** — technically optional (the `a=` tag is "reserved for VMC/CMC") but **self-asserted records have limited support** across mailbox providers. Practical read: VMC is de-facto required for Gmail display.

### 3.2 Custom tracking domain (CNAME)

Instantly's exact published setup:

```dns
inst.yourdomain.com.   IN CNAME   prox.itrackly.com.
; TTL: Automatic or 3600
```

- Host/Name must be **exactly `inst`** (e.g. `ins.` fails verification).
- Then enable in the account UI and enter `inst.yourdomain.com`.
- Verification = CNAME lookup returns `prox.itrackly.com` in the Canonical Name field; states cycle `Retrying` → `CNAME Verified`.
- Additional TXT records may be demanded ("Your domain needs additional verification").
- Propagation guide says 24–72h.

**Why it exists (documented):** without a CTD, the injected tracking URL is a **shared domain across all customers** (e.g. `xyz.inreg1.com/[code]`). A CTD "acts as a proxy, **isolating your sender reputation from others**" — i.e. if another tenant gets blacklisted on the shared tracking host, your tracking links inherit that. This is the single cheapest deliverability win available.

**Organization strategy (two documented patterns):**
- **One CTD for all sending domains** — recommended if your primary domain is old/warmed (leads/agencies).
- **Separate CTD per sending domain** (`inst.first.com`, `inst.second.com`) — contains blast radius of a new/experimental domain.

**Implementation:**

```python
CTD_HOST_PREFIX = 'inst'

def tracking_url(campaign, account, kind, token) -> str:
    host = (account.tracking_domain_name
            if account.tracking_domain_status == 'active'
            else DEFAULT_TRACKING_HOST)         # shared fallback
    return f'https://{host}/{kind}/{token}'

def verify_ctd(host) -> tuple[bool, str]:
    """Resolve CNAME chain and compare the canonical target."""
    try:
        ans = dns.resolver.resolve(host, 'CNAME')
        target = str(ans[0].target).rstrip('.')
        return target == 'prox.itrackly.com', target
    except dns.exception.DNSException as e:
        return False, str(e)
```

### 3.3 Link tracking vs pixel tracking — the deliverability tradeoff

| Mechanism | What's injected | Cost |
|---|---|---|
**Pixel (open) tracking** | 1×1 `<img>` on the tracking domain | Image-blocking clients show nothing; Apple Mail Privacy Protection prefetches → **inflated opens**; some filters flag pixels
**Link tracking** | each `<a href>` rewritten to `https://<ctd>/…/token` (302 redirect) | Rewritten URLs look non-native; link reputation is now shared/your-CTD-scoped
**Delivery Optimization** | **removes images + disables open tracking** | Best deliverability, no open data
**Text-only mode** | plain `text/plain` only; hyperlinks render as **plain text URLs** | Best deliverability, degraded UX, no open tracking

**Instantly's interaction matrix (verified, and easy to get wrong):**

- `Delivery Optimization` **disables open tracking and removes images**.
- `Send emails as text-only (no HTML)` → opens not tracked for **any** step; hyperlinks in **all** steps render as plain text URLs.
- `Send first email as text-only` → opens not tracked for **Step 1 only**.
- Global `Always send first email as text-only` (Advanced Deliverability) **overrides** campaign settings and strips HTML + pixels from Step 1 across **all campaigns**.
- Global `Disable Open Tracking` overrides everything, workspace-wide.

**Recommendation for a cold-outreach default:** Step 1 plain-text with **no links** (Instantly's own bounce doc: "Links in Step 1 can increase soft bounces, especially when combined with repetitive copy" — providers are strictest on first contact), link tracking on for later steps via CTD, open tracking optional.

**Per-link opt-out:** Instantly supports `?clicktracking=off` appended to any URL; system-generated unsubscribe links are never click-tracked.

**Link-click dedupe (exact semantics):** *"If 1 lead clicks the same link 3 times → shows as 1 click (not 3). If 5 different leads click once each → shows as 5 clicks."* So the metric is **unique leads with ≥1 click**, matching the click-rate formula in §8.

### 3.4 Unsubscribe — RFC 8058 and the 2024 bulk-sender rules

**RFC 8058 (`One-Click`)** exact wire format:

```
List-Unsubscribe: <mailto:listrequest@example.com?subject=unsubscribe>, <https://example.com/unsubscribe.html/opaque123456789>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

The receiver then POSTs:

```
POST /unsubscribe.html/opaque123456789 HTTP/1.1
Host: example.com
Content-Type: application/x-www-form-urlencoded
Content-Length: 26

List-Unsubscribe=One-Click
```

RFC also defines the `multipart/form-data` variant (`Content-Disposition: form-data; name="List-Unsubscribe"` / value `One-Click`). The whole point of `List-Unsubscribe-Post` is to prevent mail user agents from **accidentally** unsubscribing users merely by prefetching the header URL: a `mailto:` is a two-step, no-side-effect action, whereas an HTTPS URI must be provably side-effect-free-on-GET, hence the POST+token requirement.

**Handler requirements:** respond **2xx** to the POST, treat the opaque token as a one-shot capability, and make the operation **idempotent** (repeat POSTs must not error).

**Gmail sender requirements (support.google.com/a/answer/81126), effective Feb 1 2024:**

*All senders to Gmail addresses:*
- SPF **or** DKIM
- valid forward **and** reverse DNS (PTR)
- **TLS** for transmission (added Dec 2023)
- spam rate **< 0.3%** in Postmaster Tools
- RFC 5322 message format
- do not impersonate Gmail `From:` headers (Gmail applies DMARC quarantine)

*Senders of **>5,000 messages/day** to Gmail:*
- SPF **and** DKIM
- **DMARC** published (policy may be `none`)
- PTR, TLS, spam <0.30%, RFC 5322
- **From: domain aligned** with the SPF domain or the DKIM domain (required for DMARC alignment)
- **one-click unsubscribe for marketing and subscribed messages**, *plus* a clearly visible unsubscribe link in the body

**Yahoo requirements (senders.yahooinc.com), enforcement began Feb 2024, gradually rolled out through H1:**

*All senders:* SPF or DKIM; spam complaint rate **<0.3%**; valid forward+reverse DNS; RFC 5321 + 5322.

*Bulk senders (additions):*
- **both SPF and DKIM**
- valid **DMARC** policy of **at least `p=none`**, DMARC must **pass**, `rua` tag strongly recommended, **relaxed alignment acceptable**
- functioning **List-Unsubscribe header supporting one-click** for marketing/subscribed mail — *"The Post (RFC 8058) method is highly recommended; the mail-to: method is acceptable"*
- **clearly visible unsubscribe link in the body** (may point to a preference page)
- **honor unsubscribes within 2 days**
- DKIM key **≥1024-bit**
- enroll in the **Complaint Feedback Loop (CFL)** — an active CFL is required for all DKIM domains
- spam rate computed **on mail delivered to inbox** (so CFL raw counts won't match their rate)
- limit messages per SMTP connection (Yahoo silently terminates the connection at the per-connection cap and **gives no error code** — reconnect logic is mandatory)

**Implementation:**

```python
def apply_unsubscribe_headers(msg, token, https_url, mailto_url):
    """RFC 8058 one-click. Both a mailto and an https URI, plus -Post."""
    msg['List-Unsubscribe'] = f'<{mailto_url}>, <{https_url}>'
    msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
    # Gmail/Yahoo additionally require a VISIBLE body link, not just headers.

# POST /unsubscribe/<token>  (opaque, single-use, idempotent)
@router.post('/unsubscribe/{token}')
async def one_click_unsubscribe(token: str):
    sub = await decode_unsub_token(token)          # signed, expiring
    await suppress(sub.email, scope='workspace',
                   reason='unsubscribed',          # global suppression, §6
                   source_campaign_id=sub.campaign_id)
    return Response(status_code=204)               # 2xx per RFC 8058
```

**Note on Gmail cold mail:** Instantly documents that Gmail may *not surface* the unsubscribe affordance when it classifies the thread as a regular conversation (typical when there's prior history between the accounts). Verification must be done via **"Show original"** and inspecting raw headers, not via UI presence.

> **LeadForge gap:** `backend/app/campaigns/sender.py` already injects `List-Unsubscribe: <url>` (line ~73) but **not** `List-Unsubscribe-Post: List-Unsubscribe=One-Click`. That means it satisfies the *mailto-style* path only and does **not** meet the Gmail/Yahoo 2024 one-click requirement for bulk senders. One-line fix; material compliance impact.

---

## 4. A/B testing, spintax, and fallback templates

### 4.1 Variant model

**Instantly A/Z testing (`articles/6661549`):**

- **Up to 26 variants per step** (A–Z).
- Variants are ordered alphabetically and can be toggled on/off individually (also from Analytics → Step Analytics).
- Subject lines and body are varied independently; you can vary the body while holding the subject constant.
- **Threading rule:** follow-ups only stay threaded if Step 2+ subjects **match Step 1's**. Changing the subject in *any* follow-up variant **breaks the thread for that variant**.
- **Variant assignment is random at each step and is NOT correlated across steps.** *"A lead who receives Variant A in Step 1 could receive any variant (A, B, C) in Step 2. This is by design, since each step can have a different number of variants."* — i.e. no factorial design, just independent per-step randomization.
- **Distribution:** by default, balanced **over the lifetime of the campaign**. Add variants mid-flight and *only the new variants send* until their usage catches up. Optional preference **"Reset A/Z variant usage tracking daily"** switches to equal **daily** distribution.
- Per-variant analytics: Sent, Replied, Reply rate, Positive reply rate, Opportunities, Meeting booked, Won.

**Auto-Optimize A/Z (`Campaign Settings → Advanced → Sending Rules`):** select a single **winning metric** — `reply_rate` | `click_rate` | `open_rate`. The system "automatically analyzes and identifies the best-performing variant" and **deactivates lower-performing versions**. Notably Instantly does **not** publish a minimum sample size or a significance test — the documented mechanism is metric-driven deactivation, not a hypothesis test.

**lemlist:** A/B tests support up to **5 versions** (Woodpecker also documents "A/B tests (up to 5 versions)"). Winner selection is **manual, explicit, and irreversible**:

- Prerequisite: **at least 100–200 leads must have received each version**.
- *"Once you select a winner, you cannot switch back or run new A/B tests on that campaign."*
- On selection: **future** leads get the winner; **existing** leads keep their original version to completion; the losing version is **archived**; campaign structure locks.
- Metric mapping documented: subject tests → **open rate**; content tests → **reply rate**; CTA tests → **click rate**.
- Explicit significance guidance: *"Small differences (e.g. 8% vs 9% reply rate) might be random; larger differences (e.g. 8% vs 14%) indicate a real winner"*; and *"If Version A and B perform within 10% of each other, pick one and move on."*
- Re-validate on **500+ leads**.

**Woodpecker** ships a public **"Cold email A/B test calculator"** to test statistical significance — a hint that the vendor acknowledges this is the hard part.

### 4.2 Statistical significance — what to actually implement

No vendor publishes a rigorous test. Here is the correct formulation for a binary metric (replied / not):

```python
from scipy import stats

def two_proportion_test(a_sent, a_conv, b_sent, b_conv, alpha=0.05):
    """Two-sided two-proportion z-test. Use Welch's t as a fallback."""
    p_pool = (a_conv + b_conv) / (a_sent + b_sent)
    se = math.sqrt(p_pool * (1 - p_pool) * (1/a_sent + 1/b_sent))
    if se == 0: return dict(significant=False)
    z = (b_conv/b_sent - a_conv/a_sent) / se
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return {
        'z': z, 'p_value': p, 'significant': p < alpha,
        'lift': (b_conv/b_sent) / (a_conv/a_sent) - 1,
        # 95% CI on the difference (Newcombe/Wald)
        'ci95': (b_conv/b_sent - a_conv/a_sent) ± 1.96*se,
    }

def min_sample_per_variant(baseline, mde, alpha=0.05, power=0.80):
    """How many sends per arm before you can even hope to detect a lift.
    baseline=0.05 (5% reply), mde=0.02 (want to see 5% -> 7%)."""
    z_a, z_b = stats.norm.ppf(1-alpha/2), stats.norm.ppf(power)
    p1, p2 = baseline, baseline + mde
    pbar = (p1 + p2) / 2
    n = (z_a*math.sqrt(2*pbar*(1-pbar))
         + z_b*math.sqrt(p1*(1-p1) + p2*(1-p2)))**2 / (p2-p1)**2
    return math.ceil(n)
```

Worked numbers: baseline reply rate 5%, want to detect a +2pp absolute lift (5%→7%) at α=0.05, power 0.80 → **~1,900 sends per variant**. At 30 sends/mailbox/day × 10 mailboxes = 300/day, a 2-arm test needs **~13 days**. This is exactly why lemlist's "100–200 leads" is far too small for a reply-rate conclusion (adequate only for a *large* effect) and why Instantly's undeclared auto-optimize can pick noise. **Ship both:** a significance gate for auto-promotion, and a minimum-send floor.

**Recommended auto-promotion policy:**

```
1. Equal-randomize arms until every arm has >= min_sample_per_variant sends.
2. Recompute the winner test every N sends.
3. Promote ONLY if: p < 0.05 AND lift >= practical_min (e.g. +20% relative)
   AND the winning arm's bounce rate is not worse (guard against a
   'winner' that wins by being sent to a cleaner sub-cohort).
4. On promotion: keep leads already in-flight on their current arm
   (lemlist behavior -- preserves historical comparability),
   route all NEW leads to the winner (Instantly 'auto-optimize' behavior).
5. Never re-enable a losing arm after promotion (lemlist: irreversible).
```

### 4.3 Spintax

**Instantly syntax (exact):**

```
{{RANDOM | option1 | option2 | option3}}
{{variableName | fallback text}}
{% if variableName == "value" %} ... {% endif %}
```

Behaviors worth copying:
- **Nesting + nesting fallbacks:** `{{RANDOM | Pay-Per-Appointment Meetings, {{companyName}} | Quick question {{firstName}} }}`
- **Chained variable fallbacks:** `{{firstName | lastName | for you}}` — first non-empty wins.
- Variables can appear *inside* spintax.
- **LiquidJS** is used under the hood for advanced cases.
- **Gotcha (documented):** without the `RANDOM` keyword the **first option may be skipped** — the parser treats `{{ | a | b }}` differently. Always include `RANDOM`.
- **Variable names are case-sensitive** and must match the CSV header exactly.
- Conditional-logic workaround: the variable must appear *somewhere* in the body for `{% if %}` to evaluate; the documented hack is a hidden `<div style="display:none;">{{Position}}</div>` at the end of the HTML.
- **`?clicktracking=off`** per-URL escape hatch.

**Uniqueness is the point, not obfuscation.** Instantly's bounce doc is blunt: *"Spintax only works when it creates real uniqueness, not awkward synonym swaps"* and warns about **fingerprinting** — *"When thousands of emails look nearly identical, providers may throttle or defer them as pattern-based outreach"* and *"identical emails sent from many inboxes simultaneously"* triggers soft bounces.

**Implementation:**

```python
SPINTAX = re.compile(r'\{\{\s*RANDOM\s*((?:\|[^|]+)+)\}\}')

def render_spintax(text, rng=None, depth=0):
    """Iterative; bounded depth to prevent pathological nesting."""
    rng = rng or random
    for _ in range(MAX_SPINTAX_DEPTH):        # e.g. 10
        new = SPINTAX.sub(
            lambda m: rng.choice(m.group(1).split('|')[1:]).strip(), text)
        if new == text: return new
        text = new
    raise ValueError('spintax nesting too deep')

COMBINATIONS = lambda opts: math.prod(len(o) for o in opts)
# Guard: if COMBINATIONS < 2 * sends_planned, warn -- uniqueness is illusory.
# Instantly's fingerprint guidance implies you want the space of distinct
# renderings to exceed the number of leads contacted per provider per day.
```

**Fallback templates.** Two distinct mechanisms exist in the wild:

1. **Per-variable fallback** (Instantly `{{var | fallback}}`) — inline, per-substitution.
2. **Step-level fallback template** — a whole alternative body used when personalization coverage is too low.

```python
def coverage(step, lead) -> float:
    """Fraction of declared personalization vars that resolved non-empty."""
    vars_ = extract_variables(step.body)
    if not vars_: return 1.0
    return sum(1 for v in vars_ if lead.get(v)) / len(vars_)

MIN_COVERAGE = 0.6

def resolve_step_body(step, lead):
    if coverage(step, lead) >= MIN_COVERAGE or not step.fallback_body:
        return render_spintax(step.body), lead
    return render_spintax(step.fallback_body), lead   # generic-but-honest copy
```

Woodpecker ships related primitives: **"Empty custom fields detection"** and **"Duplicate sending detection"** — i.e. it detects leads that would receive an obviously under-personalized or already-sent message and blocks them. Both are cheap, high-value guards to replicate.

---

## 5. Unified inbox & reply detection

### 5.1 Architecture

Every vendor builds the same thing: **IMAP polling of every connected mailbox → normalize → thread → match to a lead → classify → mutate campaign state.** Instantly's Unibox v2 documents the shape precisely:

- **Primary folder:** replies from leads that exist in any campaign or list in the workspace.
- **Others folder:** everything else captured from connected accounts — replies from people not in the workspace, leads replying from a *different* address, replies from deleted leads. Rationale: *"You will not miss any positive replies from leads that responded to you from a different email address or forwarded your email to a coworker."*
- **Attach Lead:** manually re-homes an Others-folder thread to the original lead and stops follow-ups.
- **Sync is one-way:** Unibox read/delete actions do **not** propagate back to the provider mailbox.
- Emails persist in Unibox even after the campaign or lead is deleted.
- Auto-refresh, bulk actions, in-app notes shared across the workspace, GPT-4 sentiment analysis.
- Prerequisite: **MX records must exist** or you receive nothing, including replies.

### 5.2 IMAP threading

```python
def build_thread(account, raw_msg) -> Thread:
    """RFC 5256-ish threading. Precedence matters."""
    mid   = raw_msg['Message-ID']
    refs  = parse_header_list(raw_msg.get('References'))
    parent= parse_header_list(raw_msg.get('In-Reply-To'))

    # 1. Strongest signal: In-Reply-To points at a message we sent.
    if parent and (t := thread_by_message_id(parent[0])):
        return t
    # 2. References chain (deepest ancestor we recognise).
    for r in reversed(refs):
        if (t := thread_by_message_id(r)):
            return t
    # 3. Normalised subject fallback (Re:/Fwd:/RE[2]: stripping),
    #    scoped to (lead_email, mailbox) to avoid cross-talk.
    subj = normalize_subject(raw_msg['Subject'])
    return thread_by_subject(subj, lead_email=from_addr(raw_msg),
                                  mailbox=account.email) or new_thread()

def normalize_subject(s):
    s = re.sub(r'^\s*(re|fw|fwd|aw|sv|vs)\s*(\(\d+\))?\s*:\s*', '', s or '', flags=re.I)
    return s.strip().lower()
```

**Threading is a deliverability feature, not just UX.** Instantly's threading guidance: *"If you want follow-up emails to remain threaded, keep the subject line in Step 2 (and subsequent steps) the same as Step 1."* Threaded replies land in an existing conversation — historically better placement and it's also what makes Gmail treat it as a "regular conversation" (which, per §3.4, can *suppress* the unsubscribe affordance). Keep the same `Message-ID` chain and same `Subject` on follow-ups.

### 5.3 Auto-reply / OOO detection

Standard machine signals, then LLM classification (Instantly: "AI-powered sentiment analysis, powered by LLM/GPT-4"):

```python
def is_auto_reply(msg) -> bool:
    h = {k.lower(): v for k, v in msg.items()}
    if h.get('auto-submitted', 'no') != 'no':            return True
    if h.get('x-autoreply') or h.get('x-auto-response-suppress'): return True
    if h.get('precedence', '').lower() in ('bulk', 'auto_reply'): return True
    if h.get('x-autogenerated') or h.get('x-autoreplyfrom'):      return True
    if msg.get_content_type() == 'multipart/report':       return True
    return False

OOO_PATTERNS = [
  r'out of (the )?office', r'on (annual )?(leave|vacation|holiday)',
  r'away from (my )?(desk|email|office)', r'on maternity/paternity',
  r'limited access to (my )?email', r'back (on|in) (the office )?\w+',
  r'returning (on|to work)', r'i will be back', r'currently unavailable',
]

def parse_return_date(body) -> date | None:
    """Instantly OOO Resume: 'pause the lead until their specified return
    date, and resume sending when they're back.' Date parsing must be
    conservative -- if unparseable, default to +7 days, never 'resume now'."""
    ...
```

**Instantly's AI Smart Pause & Resume (exact prerequisites):**

1. **Turn OFF** `Stop Sending Emails on Auto-Reply` in campaign settings — otherwise the lead is terminated rather than paused. Instantly explicitly recommends disabling it *in favour of* the AI Smart Pause feature.
2. **Turn ON** `Automatically tag lead status in replies` in Preferences → AI Automations.
3. The lead gets an **Out of Office** status and a **`Pause Until`** date, visible/editable in the Unibox lead-info popover.
4. On the return date the sequence **resumes from where it was interrupted**.
5. **Conflict guard:** if you use OOO Resume, **disable subsequences triggered on Out-of-Office** or you get duplicate follow-ups.

### 5.4 Interest classification & auto-pause

```python
INTENT_LABELS = {
  # value : (label, sentiment, stops_sequence, counts_as_opportunity)
   1: ('Interested',          'positive', True,  True),
   2: ('Meeting Booked',      'positive', True,  True),
   3: ('Meeting Completed',   'positive', True,  True),
   4: ('Won',                 'positive', True,  True),
   0: ('Out of Office',       'neutral',  False, False),  # pause-until, then resume
  -1: ('Not Interested',      'negative', True,  False),
  -2: ('Wrong Person',        'negative', True,  False),
  -3: ('Lost',                'negative', True,  False),
  -4: ('No Show',             'negative', True,  False),
}

# Custom labels are user-defined and carry an IMMUTABLE interest_status
# of positive | neutral | negative, set at creation time.
# ONLY positive labels count toward Opportunities.
```

**Classification controls (Instantly):**
- `Automatically tag interest status in replies` (Prefs) — master switch.
- `Update existing lead labels with AI` — **off by default**, to protect manual/AI labels from an earlier reply. When on, AI may overwrite a current label with a better one.
- Per-label AI toggles: In-Built Labels and Custom Labels can each be enabled/disabled; AI only applies custom labels with **Use with AI** enabled.
- Thumbs up/down feedback on misclassification feeds accuracy.
- Custom label descriptions are the classifier's prompt: "The AI reads the label description and uses it to determine whether a reply matches the label criteria."

**Auto-pause rules to implement:**

| Trigger | Action |
|---|---|
| Any reply received + `stop_on_reply` | stop all follow-ups for that lead |
| Reply classified positive/negative | stop sequence (any non-default status stops it) |
| Auto-reply detected + `stop_on_auto_reply` | stop sequence |
| Auto-reply detected + OOO Resume | pause until return date, then resume |
| Any lead at a company replies + `stop_campaign_for_company_on_reply` | stop **all leads at that domain**; mark them **Completed**. Auto-replies do **not** trigger this. |
| Hard bounce | suppress globally, mark Bounced |
| Unsubscribe | suppress globally, mark Unsubscribed |

**Status-reset semantics (exact, Instantly):** *"If you change the lead status to anything other than the default 'Lead' status, any follow-up emails for this lead will stop automatically. You can put the status back to 'Lead' and this lead will be reintroduced to the sequence and continue from where it got interrupted."* — so status change is a reversible interrupt, and the step cursor is preserved rather than reset.

**Reply-rate counting caveat (important for analytics correctness):**
- Auto-replies are **included** in reply rate by default; excludable via the gear icon. The setting is **per-device**, not per-account — you must re-set it on each browser.
- **"Replies to subsequence emails are not included in the reply rate metric."**
- Denominator/date-range sensitivity is the #1 source of "wrong" reply rates: a 7-day window on a campaign started 2 months ago silently excludes older replies.

---

## 6. Lead status model & suppression

### 6.1 The two-axis status model

Production tools separate **lifecycle state** (is this lead still in a sequence?) from **interest classification** (what did they say?). Conflating them — as most naive implementations do — makes it impossible to represent "replied positively but sequence not finished" or "OOO, resume later."

**Axis 1 — lead `status` (Instantly OpenAPI enum, exact):**

| Code | Label | Meaning |
|---|---|---|
| `1` | **Active** | in sequence, eligible to send |
| `2` | **Paused** | manually or temporarily halted (cursor preserved) |
| `3` | **Completed** | finished all steps |
| `-1` | **Bounced** | hard bounce; suppress globally |
| `-2` | **Unsubscribed** | opted out; suppress globally |
| `-3` | **Skipped** | excluded (e.g. BounceShield skipped, blocked, verification failure) |

**Axis 2 — `interest_status` (Instantly `lt_interest_status`, exact):**

| Code | Label |
|---|---|
| `0` | **Out of Office** |
| `1` | **Interested** |
| `2` | **Meeting Booked** |
| `3` | **Meeting Completed** |
| `4` | **Won** |
| `-1` | **Not Interested** |
| `-2` | **Wrong Person** |
| `-3` | **Lost** |
| `-4` | **No Show** |

Documented as: *"It can be either a static value (check below), or a custom status interest value"* and `null` when unset. Custom labels extend the space, each carrying an immutable `positive | neutral | negative` sentiment.

**Additional statuses surfaced in the UI:** `Lead` (default/null), `Contacted`, `Opened`, `Link Clicked`, `Email opened, No reply`, `Reply Received`, `Automatic Reply`, `In subsequence`. These are **derived activity states**, not stored enums — compute them from the event log.

**Campaign status enum (also exact):** `0 Draft`, `1 Active`, `2 Paused`, `3 Completed`, `4 Running Subsequences`, `-99 Account Suspended`, `-1 Accounts Unhealthy`, `-2 Bounce Protect`.

**Mailbox/account status enum:** `1 Active`, `2 Paused`, `3 Temporarily paused for maintenance`, `-1 Connection Error`, `-2 Soft Bounce Error`, `-3 Sending Error`. Warmup status enum: `0 Paused`, `1 Active`, `-1 Banned`, `-2 Spam Folder Unknown`, `-3 Permanent Suspension`.

**Subsequence status enum:** `0 Draft`, `1 Active`, `2 Paused`, `3 Completed`, plus `-99/-1/-2` mirroring campaign-level failure modes.

### 6.2 Recommended schema

```python
class LeadStatus(IntEnum):
    ACTIVE       =  1
    PAUSED       =  2
    COMPLETED    =  3
    BOUNCED      = -1
    UNSUBSCRIBED = -2
    SKIPPED      = -3

class InterestStatus(IntEnum):
    OUT_OF_OFFICE      =  0
    INTERESTED         =  1
    MEETING_BOOKED     =  2
    MEETING_COMPLETED  =  3
    WON                =  4
    NOT_INTERESTED     = -1
    WRONG_PERSON       = -2
    LOST               = -3
    NO_SHOW            = -4

STOPS_SEQUENCE = {*InterestStatus} - {InterestStatus.OUT_OF_OFFICE}
OPPORTUNITY_STATUSES = {INTERESTED, MEETING_BOOKED, MEETING_COMPLETED, WON}

class Contact(Base):
    status          = Column(SmallInteger, default=LeadStatus.ACTIVE, index=True)
    interest_status = Column(SmallInteger, nullable=True)   # None == 'Lead'
    interest_sentiment = Column(Enum('positive','neutral','negative'), nullable=True)
    # step cursor -- preserved across pause so resume continues correctly
    current_step    = Column(Integer, default=0)
    assigned_mailbox_id = Column(ForeignKey('mailboxes.id'), nullable=True)  # sticky
    next_send_at    = Column(DateTime(timezone=True), index=True)
    pause_until     = Column(DateTime(timezone=True), nullable=True)  # OOO
    seq_entered_at  = Column(DateTime(timezone=True))   # anchor for delays

class ContactEvent(Base):
    """Append-only. Derived states are computed, never stored as truth."""
    __table_args__ = (UniqueConstraint('dedupe_key', name='uq_event_dedupe'),)
    contact_id, campaign_id, step_id, mailbox_id
    event    = Column(String)   # sent|opened|clicked|replied|auto_reply|
                                 # bounced|unsubscribed|spam_complaint
    sent_at  = Column(DateTime(timezone=True), index=True)
    meta     = Column(JSON)     # clicked url, bounce code, intent, model version
    dedupe_key = Column(String) # e.g. f'{send_id}:opened:{lead_id}'
```

### 6.3 Global suppression

Instantly's **Global Blocklist** is the reference implementation:

- **Workspace-wide scope.** Entries block both directions of time: leads on the blocklist **will not be imported into any campaign**, *and* **will not be contacted even if they already exist in an active campaign** in the workspace.
- Two entry types: **entire domain** (`mycompetitor.com`, no `@`) or **specific address**.
- Checked **at upload time** and **across ongoing campaigns**.
- Import formats: CSV (one email/domain per row, single column, single sheet, **5 MB limit per file** — split larger lists), manual entry, or a **Google Sheet** (Column A row 1 = `Blocked`, rows 2+ = values, delete columns B–Z, share as "Anyone with the link **as Editor**").
- **Google Sheet blocklist is evaluated only at import/upload** — for already-active campaigns you must use the Blocklist tab instead. This is a real gap to be aware of.
- Bulk-add from Unibox (also deletes the reply), domain-search view, timestamp per entry, CSV export, remove action.

**AI Blocklist Triggers** — automatic, workspace-wide:

| Trigger | Availability |
|---|---|
| Unsubscribed leads → auto-add | all plans |
| Leads in **specific statuses** → auto-add | HyperGrowth+ |
| Leads whose **replies contain specific phrases** → auto-add | HyperGrowth+ (semicolon-separated phrases) |

**Implementation:**

```sql
-- Hot-path lookup must be O(1). One table, two partial unique indexes.
CREATE TABLE suppression (
  id BIGSERIAL PRIMARY KEY,
  workspace_id UUID NOT NULL,
  email TEXT, domain TEXT,
  reason TEXT NOT NULL,             -- unsubscribed|hard_bounce|complaint|
                                     -- manual|blocklist|ai_trigger|competitor
  source_campaign_id BIGINT,
  created_by UUID, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX uq_sup_email  ON suppression(workspace_id, lower(email))
  WHERE email IS NOT NULL;
CREATE UNIQUE INDEX uq_sup_domain ON suppression(workspace_id, lower(domain))
  WHERE domain IS NOT NULL;

-- Single query covers both address and domain suppression.
CREATE VIEW effective_suppression AS
SELECT workspace_id, lower(email) AS key FROM suppression WHERE email IS NOT NULL
UNION ALL
SELECT workspace_id, lower(split_part(email,'@',2))
FROM   suppression WHERE domain IS NOT NULL;

def assert_sendable(workspace_id, email) -> None:
    if db.scalar("""SELECT 1 FROM effective_suppression
                     WHERE workspace_id=$1 AND key=$2""",
                 workspace_id, email.lower()):
        raise Suppressed(email)
```

**Enforcement points (all four are required — missing any one leaks sends):**
1. **Import validation** — reject at upload, report counts back to the user.
2. **Pre-send gate** — the last check before SMTP handoff (defends against a suppression added microseconds earlier).
3. **Event-driven auto-suppress** — on `hard_bounce`, `unsubscribed`, `spam_complaint`.
4. **Scheduled sweeper** — catches anything added out-of-band (direct DB edit, Google Sheet sync).

**Bounce semantics:** hard bounces (invalid address, nonexistent domain, deleted/deactivated, typo) → suppress permanently. Soft bounces (mailbox full, server down, poor reputation, spam filter, ESG/policy block such as Proofpoint/Mimecast/Defender, catch-all domain that rejects later) → **do not** suppress; they're retryable. Bounce types reported: **Hard, Soft, Unknown**.

---

## 7. Sequence builder

### 7.1 Schema (mirrors Instantly's OpenAPI exactly)

```jsonc
{
  "sequences": [{
    "steps": [
      {
        "type": "email",                     // only 'email' supported
        "delay": 2,                          // delay BEFORE the NEXT email
        "delay_unit": "days",               // minutes | hours | days (default days)
        "pre_delay": 1,                      // subsequences ONLY: before step 1
        "pre_delay_unit": "days",
        "variants": [
          { "type": "...", "delay": 2, "subject": "...", "body": "..." }
        ]
      }
    ]
  }]
}
```

Semantics to copy precisely:
- `delay` = wait **before sending the NEXT email**, not before this one. So step 1's `delay` is the gap to step 2. This off-by-one is the most common implementation bug.
- `delay_unit` default is **`days`** for backward compatibility.
- `pre_delay` applies **only to subsequences** (delay before subsequence step 1) and is ignored for normal campaigns. The countdown **starts when the lead is added to the subsequence**.
- `sequences` is an array for historical reasons; **only the first element is used**.
- Only one element type exists: `email`.

### 7.2 Conditional branching (subsequences)

Instantly's model is **post-hoc branching**, not in-sequence if/else: a lead finishes (or exits) the main sequence and a *separate* subsequence picks them up. Three trigger families:

**1. Status-based** — default statuses: `Interested`, `Meeting Booked`, `Meeting Completed`, `Won`, `No Show`, `Out of Office`, `Wrong Person`, `Not Interested`, `Lost` (plus custom statuses).

**2. Activity-based** — `Email opened`, `Link clicks`, `Campaign completed without reply`.

**3. Keyword/phrase** — semicolon-separated (`more information; tell me more; interested in learning`).

**Critical documented gotcha:** keyword triggers must use **exact phrase matching, not single words**. Verbatim: *"if the subsequence is triggered by the word 'interested' in a lead's reply. When a lead replies, 'I am not interested.' The system will add this lead to the subsequence as it detects the word 'interested' in the reply."* Negation-blind substring matching is a real bug in production — use phrases like `I am interested`.

**Trigger combination:** multiple statuses, activities, and keywords can all feed one subsequence.

**Only-forward semantics:** *"Subsequences only activate for newly triggered leads"* and *"only leads marked as Interested after you launch will automatically enter."* Pre-existing matching leads must be moved manually (Leads → filter → checkboxes → Row Actions → Move to subsequence). This avoids a retroactive blast when you launch a new subsequence.

**Threading trick:** leave the subsequence step's **subject line empty** to keep mail in the same thread.

**Empty-state behavior:** a subsequence with no eligible leads is marked `Complete` but **auto-resumes** when leads become available.

**Subsequence daily limits:**
- Inherit from campaign (default)
- Custom limit
- No limit
- **`Ignore Account Daily Limits`** — lets the subsequence send even when accounts hit their cap, meaning accounts may exceed their configured limit. Documented warning: *"This can affect deliverability, especially for accounts that are still warming up."* Treat as an operator escape hatch with an audit trail, not a normal setting.

### 7.3 "Stop on reply" semantics

```python
def should_send_step(contact, campaign, step) -> tuple[bool, str]:
    """Ordered evaluation. Every gate returns its reason for observability."""
    if contact.status != LeadStatus.ACTIVE:      return False, 'not_active'
    if is_suppressed(contact):                   return False, 'suppressed'
    if campaign.stop_on_reply and contact.replied_at:
        return False, 'stop_on_reply'
    # A non-default interest status stops the sequence, EXCEPT Out of Office,
    # which pauses-until a date and then resumes (Instantly OOO Resume).
    if contact.interest_status in STOPS_SEQUENCE: return False, 'interest_stop'
    if contact.pause_until and contact.pause_until > now_utc():
        return False, 'paused_ooo'
    if not in_send_window(campaign, lead_tz=contact.tz):
        return False, 'out_of_window'
    if not remaining_budget(contact.assigned_mailbox):
        return False, 'mailbox_budget'
    if contact.next_send_at and contact.next_send_at > now_utc():
        return False, 'delay_not_met'
    return True, 'ok'
```

Instantly's sending-status diagnostics expose exactly these reasons via an API that explains *why* a campaign isn't sending — issue codes include `domain_limit_reached`, `follow_up_delay_not_met`, `no_accounts_available`, `healthy`. Mirror that: **every skip decision must be attributable**, because "why is my campaign not sending" is the top support question and the top user-trust problem.

### 7.4 Ordering, prioritization, and the queue

- **Default order: follow-ups first, then new leads** (Instantly). `Prioritize New Leads` inverts this and is gated to HyperGrowth/Lightspeed.
- Even with `Max New Leads = X`, follow-ups stay prioritized unless `Prioritize New Leads` is set.
- `Max New Leads` caps **Step 1** volume per day only.
- lemlist's `Prioritize` on a pending step bumps it to the top of the sender's outreach queue for the next sending cycle.
- Campaign **progress** = % of leads that completed **all** steps. Explicitly: with 3 steps, progress increases only when leads complete step 3 — not after step 1 or 2.
- Woodpecker's step budget: a campaign has **16 steps** max, and monthly email allowance = contacted prospects × 16.

**Implementation — a due-queue with a priority column:**

```python
priority = (0 if step_number > 1 else 1) if not campaign.prioritize_new_leads \
           else (0 if step_number == 1 else 1)

# Worker loop
for row in db.stream("""
    SELECT c.* FROM contacts c
    WHERE c.status = 1
      AND c.next_send_at <= now()
      AND c.campaign_id = ANY(:active_campaigns)
    ORDER BY priority, c.next_send_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch"""):
    ok, reason = should_send_step(row, ...)
    if not ok:
        metrics.incr('skip', reason=reason)   # feeds the diagnostics endpoint
        continue
    send(row)
```

`FOR UPDATE SKIP LOCKED` + Celery (already in `requirements.txt`) gives you horizontal workers without double-sends.
---

## 8. Analytics — exact KPIs and their formulas

### 8.1 Instantly's published metric definitions

| Metric | Definition (as documented) |
|---|---|
| **Total sent** | "Total emails sent across all outreach sequences in the selected date range, **including follow-ups. Each email counts, not each contact.**" |
| **Sequence started** | "Number of unique recipients who entered an outreach sequence in the selected date range. **Counts each contact once per sequence start.**" |
| **Reply rate** | "Percentage of recipients who replied to a sequence email. Calculated as **replies / total sent**." |
| **Open rate** | "Percentage of sent emails that were opened by the recipient. **Pixel-tracking opens only — text-only clients are not counted.**" Campaign-level: "Number of leads that have opened **at least one** email" |
| **Click rate** | "Percentage of sent emails where a recipient clicked **at least one tracked link**." |
| **Positive reply rate** | "Percentage of replies that were marked as an opportunity. Calculated as **opportunities / replies**." |
| **Opportunities** | Leads with status `Interested`, `Meeting Booked`, `Meeting Completed (not closed)`, `Closed`, or other **positive custom statuses**. Secondary value = total deal value attached. |
| **Conversions** | **Won** opportunities in the date range; secondary value = cash collected. |
| **Campaign progress** | % of leads that completed **all** steps (not per-step). |
| **Include auto-replies** | Toggle; auto-replies (OOO) are **included in reply rate by default**. Setting is **per-device**. |

Note the **denominator inconsistency** that vendors do not resolve: `reply_rate = replies / total_sent` (per-email) but `open_rate = opens / sequences_started` (per-lead). These are different bases and produce non-comparable numbers. Pick one basis per metric, label it in the UI, and stay consistent.

**Open-rate formula, verbatim from Instantly's Open Tracking doc:**

```
Open Rate = (Number of opens / Number of 'Sequences started') x 100%
'Sequences started' only reflects the number of leads who received Step 1
and does not include follow-up emails.
```

### 8.2 Complete KPI set to build

```python
def campaign_kpis(campaign_id, start, end, include_auto_replies=True) -> dict:
    s     = sends(campaign_id, start, end)      # every email, incl. follow-ups
    leads = distinct_contacts(s)                # sequences_started
    ev    = events(campaign_id, start, end)

    replies = [r for r in ev.reply
               if include_auto_replies or not r.is_auto_reply]

    bounced      = count(ev.bounced)
    delivered    = s - bounced
    unsubscribed = count(ev.unsubscribed)
    complaints   = count(ev.spam_complaint)
    opps = count(l for l in leads if l.interest_status in OPPORTUNITY_STATUSES)
    won  = count(l for l in leads if l.interest_status == WON)

    return {
      # --- volume ---
      'total_sent':         s,
      'sequences_started':  leads,
      'delivered':          delivered,
      # --- rates. Denominators EXPLICIT to avoid vendor ambiguity. ---
      'delivery_rate':       pct(delivered, s),
      'bounce_rate':         pct(bounced, s),             # G/Y ceiling: 0.3%
      'spam_complaint_rate': pct(complaints, delivered),
      'unsubscribe_rate':    pct(unsubscribed, s),
      # --- engagement (per-lead, deduped) ---
      'unique_opens':  count(distinct(l for l in leads if l.has_open)),
      'open_rate':     pct(unique_opens, leads),   # pixel-only, unreliable
      'unique_clicks': count(distinct(l for l in leads if l.has_click)),
      'click_rate':    pct(unique_clicks, leads),
      # --- outcomes ---
      'reply_count':         len(replies),
      'reply_rate':          pct(len(replies), s),   # Instantly basis: per-send
      'auto_reply_count':    count(ev.auto_reply),
      'positive_replies':    opps,
      'positive_reply_rate': pct(opps, len(replies)),
      'opportunities':       opps,
      'conversions':         won,
      # --- breakdowns ---
      'by_step':    step_breakdown(campaign_id),
      'by_variant': variant_breakdown(campaign_id),
      'by_mailbox': mailbox_breakdown(campaign_id),
      'progress':   pct(count(l for l in leads if l.completed_all_steps), leads),
    }

def pct(n, d): return round(100.0 * n / d, 2) if d else 0.0
```


### 8.3 Metric caveats that must be surfaced in the UI

1. **Open rate is structurally broken.** Pixel-only; blocked by image-off clients and Apple Mail Privacy Protection (prefetches inflate it), and **disabled entirely in text-only mode**. Instantly ships two dedicated docs on this ("What to Do If My Open Rate Is Low", "Why Opens Are Not Being Tracked"). **Show reply rate as the primary metric.**
2. **Reply rate includes OOO by default.** A campaign sent in August can show a 25% reply rate that is mostly vacation autoresponders.
3. **Date-range truncation** is the most common cause of "wrong" numbers: analytics must default to a window covering the campaign's full life. Instantly's audit path is *Campaign -> Leads -> filter `Reply Received` -> count*.
4. **Subsequence replies are excluded** from the main campaign reply rate.
5. **Status-change dedupe window:** Instantly ignores subsequent lead-status updates for **10 minutes** after a change so rapid updates don't double-insert analytics events. Copy this.
6. **CRM event expansion:** interest-status totals count the **first occurrence** per contact by default; `expand_crm_events=true` counts all occurrences. Expose the toggle.
7. **Reporting timezone is UTC** (Instantly's stated rationale: keeps numbers timezone-independent across clients in different zones). Sending windows remain per-lead/local — the two are deliberately decoupled.
8. **Placement is not delivery.** Gmail's own docs warn delivery diagnostics are "not an accurate indicator of deliverability or spam classification issues." Never present a placement test as a delivery guarantee.

### 8.4 Activity log schema

Instantly's CSV export is a good spec for the event table:

```
lead_email | sending_account_used | step_number | action | date | which_link_was_clicked
```

Actions: `Email sent`, `Email opened`, `Link clicked`, `Reply received`, `Unibox Reply sent`, `Bounced`, `Auto reply`, `Interested`.

Webhook event types to expose:

```
email_sent | email_opened | reply_received | auto_reply_received | link_clicked
email_bounced | lead_unsubscribed | account_error | campaign_completed
lead_neutral | lead_interested | lead_not_interested | lead_meeting_booked
lead_meeting_completed | lead_closed | lead_out_of_office | lead_wrong_person
```

---

## 9. Pricing — 2025/2026 published tiers

All figures are USD as published on the vendors' own pricing pages on **2026-10-09**. Verify before relying on them.

### 9.1 Instantly.ai

| Plan | Price | Emails/mo | Contacts/mo | Key inclusions |
|---|---|---|---|---|
| **Starter** (Outreach) | **$94/mo** (annual $85) | 5,000 | 1,000 | AI Sales Agent, unlimited email accounts, unlimited warmup |
| — Growth Credits | **$47/mo** | — | — | 1,500 credits, 450M+ lead DB, waterfall enrichment (5+ providers), 13 filters, 5 major LLMs, bring-your-own LLM key |
| — Supersonic Credits | **$197/mo** | — | — | 5,000 credits |
| **Scale** | **$194/mo** | **100,000** | 25,000 | + AI Reply Agent, Unibox, **advanced deliverability**, premium support, 5,000 credits |
| — Hypergrowth Credits | **$358/mo** | — | — | 5,000 credits |
| — Hyper Credits | **$197/mo** | — | — | 10,000 credits |
| **Agency** | **$555/mo** | **500,000** | 100,000 | + **SISR** (IP sharding), more private infrastructure, 10,000 credits |
| — Lightspeed | **$358/mo** | 500,000 | 100,000 | + SISR |
| **Premium Warmup Pool** | from **$500/mo/workspace** | — | — | up to 1,000 Microsoft accounts; $1,000/mo = 2,000; unlimited 3rd-party Google; **+9% replies** vs standard pool |
| **Private Warmup Pool** | from **$1,000/mo** | — | — | billed **per account** not per workspace; fully isolated; you supply accounts; needs >=50% Google/Outlook |

Subsequences, custom lead labels, `Limit emails per company`, and AI Lead Filtering require **Hypergrowth / Lightspeed**. `Prioritize New Leads` requires **Hyper Growth / Lightspeed**. AirMail accounts: 50 campaign emails/day/account with dynamic non-editable warmup settings.

### 9.2 Smartlead.ai

| Plan | Monthly | Annual (per mo) | Annual (per yr) | Contacts | Emails/mo |
|---|---|---|---|---|---|
| **Base** | **$39** | $32.50 | $390 | 2,000 | 6,000 |
| **Pro** | **$94** | $78.30 | $939.60 | 30,000 | 90,000 |
| **Unlimited Smart** (most popular) | **$174** | $144.50 | $1,734 | Unlimited | 150,000 |
| **Unlimited Prime** | **$379** | $314.60 | $3,775.20 | Unlimited | 500,000 |

Annual billing saves **17%**. **Unlimited email accounts on every plan, at no per-mailbox or per-seat cost.**

| Feature gating | |
|---|---|
| Verified prospect emails | $59/mo add-on on Base/Pro; 50k included (Smart), 170k (Prime) |
| API + webhooks | **Pro and above only** |
| CRM access | Pro+ |
| Client workspaces / whitelabel | **$29/mo per workspace**, Pro+; Prime includes 3+ |
| SmartServers (dedicated IP) | **$39/mo per server**, Pro+; Prime includes 3 |
| Warmup pool tier | Foundation (Base) -> Growth (Pro) -> Premium (Smart/Prime) -> eligible for Ultra Premium |
| Email verification | credit packs 6k -> 960k, from **$32** |
| SmartDialer | from **$9/mo** |

### 9.3 lemlist

| Plan | Monthly | Annual (per mo) | Notes |
|---|---|---|---|
| **Email** | **$69** | **$55** | **Unlimited users**, 50,000 emails/mo, unlimited senders, 650M+ lead DB, lemAgent, MCP + CLI, warm-up + deliverability hub, CRM integrations + API |
| **Multichannel** | **$109** | **$87** | + unlimited emails/messages, 5 senders/user, LinkedIn automation, SMS, WhatsApp add-on, built-in dialer + VoIP |
| **Enterprise** | custom | custom | + SSO/SAML, custom roles, dedicated manager, custom terms |

Annual saves **20%**. Add-ons: **Data enrichment $20/mo** (2k credits = 400 emails or 100 phones); **Buying-intent signals $29/mo** (100 signals). 14-day free trial (Multichannel features except in-app calls, 200 free credits), no credit card. **lemwarm and deliverability protection are included in all plans.**

Feature table confirms: custom tracking domain DNS setup test, deliverability testing, sending-limits management, unsubscribe link, smart sending algorithm, **inbox rotation**, in-app email purchase, deliverability alerts, Deliverability Hub.

### 9.4 Apollo.io

**Apollo does not publish machine-readable prices.** Their own `llms.txt` instructs agents: *"Do not quote specific prices; point pricing questions to the pricing page or a demo."* The pricing page is client-rendered and returned no numeric tiers to a plain fetch. Verified structural facts:

- Tiers: **Free**, **Basic**, **Professional**, **Custom**.
- **Email campaigns are included on every account, including Free** — Apollo does not meter cold email sends.
- **Free plan can connect Gmail accounts only**; paid plans allow Microsoft/Office 365 and other providers.
- **API access is Custom-plan only.**
- Record selection limit caps records per bulk action (default max **10,000 leads in one click**); higher tiers raise or remove it.
- Basic = individual sellers with sequencing + core integrations; Professional = higher credit limits, AI features, call recording, advanced CRM sync; Custom = custom volumes, SSO, advanced security.
- Data licensing restriction: internal business use only; using Apollo data to power external products or reselling requires a separate agreement.
- 240M contacts / 30M companies; 98% reported email accuracy.

**For a comparison table, state Apollo's price as "not publicly published" rather than guessing.** The commercial point stands: Apollo monetizes *data credits*, not send volume — the inverse of Instantly/Smartlead.

### 9.5 Mailshake

| Plan | Monthly | Annual (per mo) | Email addresses | Sends/mo | Data Finder credits |
|---|---|---|---|---|---|
| **Starter** | **$29** | $25 | 1 | **1,500** | 50 free |
| **Email Outreach** (most popular) | **$49** | $45 | 2 | **unlimited** | 50 free |
| **Sales Engagement** | **$99** | $85 | 10 | unlimited | 2,500 free |
| **Agency** | talk to sales | — | unlimited | unlimited | — |

All tiers: **unlimited uploaded contacts, unlimited email warmup, unlimited campaigns, unlimited email verification**, A/B Testing, SHAKESpeare AI writing.

- Gating: **Email Rotation** + email personalization + advanced scheduling/throttling + unified inbox start at **$49**.
- Dialer + 5 phone numbers + unlimited free North American dialer minutes at **$99**.
- Add-ons: **Data Finder $19/mo** ($17 annual); **Ready to Use Mailboxes $12/mo** ($11 annual).
- **Billing is per user**, and **each paid user connects exactly 1 mail account** — so 3 mailboxes = 3 users. No free trial (payment up front).

### 9.6 Woodpecker.co

**Usage-based: $7.00 per 100 contacted prospects/month**, with volume discounts down to **$0.01 per 100** at the top tiers.

- Slider tiers: 500 / 2,000 / 4,000 / 8,000 / 10,000 / 15,000 / 20,000 / 25,000 / 30,000 / 40,000 / 60,000 / 80,000 / 100,000 / 120,000 / 150,000 / 200,000 / 250,000 / 300,000 / 400,000 / 600,000 / 800,000 / 1,000,000 / Unlimited.
- **Emails/month = contacted prospects x 16** (16 = max campaign steps). Every email sent counts, including follow-ups.
- **Counting rule:** contacting the same person N times in one campaign counts **once**; the same person in 2 campaigns counts **twice**.
- Annual billing saves **33%**.
- Free trial: **14 days OR 100 cold emails**, whichever comes first.

**Included free:** unlimited team members, unlimited email accounts, unlimited email verification (via Bouncer), catch-all verification, domain audit (SPF/DKIM checker), spam words and links checker, condition-based campaigns, workflows, spintax, snippets, adaptive sending, human-like sending randomization, ESP matching, prospect-timezone sending, AI interest-level detection, OOO inbox auto-filtering, duplicate sending detection, empty-custom-field detection, A/B tests (up to 5 versions), CASA Tier 2.

**Add-ons:**

| Add-on | Price |
|---|---|
| LinkedIn connected accounts | **$29/mo per LinkedIn account** |
### 9.7 Warmup Inbox

| Tier | $/inbox/mo | Warmup msgs/day | Warmup reply rate | Annual |
|---|---|---|---|---|
| **Basic** | **$15** | **75** | up to **25%** | $180/inbox/yr |
| **Pro** (best value) | **$49** | **250** | up to **45%** | $588/inbox/yr |
| **Max** | **$79** | **1,000** | up to **50%** | $948/inbox/yr |

Annual saves **20%**. **30,000+ real inboxes** in the pool. Every inbox added lowers the average per-inbox rate; **51+ inboxes = custom quote** with consolidated billing, multi-client workspaces, specialized reports, dedicated onboarding. 7-day free trial, no credit card.

Pro adds: own templates, choose warmup topics, language warmup, custom warmup settings, custom template stats, specific-ESP warmup, scheduled warmup, priority support. Max adds premium support, technical setup check, unlimited developer API, early access.

All tiers include: spam and category monitoring, email reputation checks, outreach sequences, dashboards, human-like AI-generated content, developer API, support chat.

Free tools worth copying: DMARC generator, SPF generator, spam checker, spam-words checker, blacklist checker, email health checker, deliverability test/audit, reputation checker, placement test (Gmail Primary / Outlook Inbox / iCloud Spam, no signup). Products: email warmup, cold email sequence, **language warmup**, ESP warmup tool, **IP warmup**.

### 9.8 Mailreach

- **$19.50 per mailbox per month.**
- **Every warmer plan includes at least 20 spam-test credits** (bundled free, since "spam testing is crucial for your deliverability").
- **Up to 100 warmup emails/day per mailbox.**
- Slider: 1-100+ mailboxes; spam-test credits 20 -> 10,000+.
- Worked example on page: **80 mailboxes + 20 credits = $1,323/mo**.
- Annual saves **20%**; Pay-As-You-Go saves **23%**.
- Included: fully automated warmup, **"Smart AI warming algorithm"**, multi-ESP warmup (Google, Outlook, Zoho, Brevo, Mailjet, Mailgun, SendGrid, SES, SparkPost, Ionos, OVH), reputation tracking dashboard, domain and inbox health checks (blacklist, SPF, DKIM, DMARC, ETS).
- **1 spam-test credit = 1 inbox placement test + deliverability report.**
- Positioning: warmup should run **before, during, and between** campaigns; initial phase **14 days minimum with no campaign sends**; reputation restoration "possible in 90% of cases."
- Also sells an **IP Warmup service** and per-ESP warmup tools (Gmail, Outlook, SendGrid, Mailgun, Amazon SES, generic SMTP).

### 9.9 GlockApps

| | **Free** | **Essential** | **Growth** | **Enterprise** |
|---|---|---|---|---|
| **Monthly** | $0 | **$59** | **$99** | **$129** |
| **Annual** | — | **$708** | **$1,188** | **$1,548** |
| Spam Test credits | 2 | 360 | 1,080 | 1,800 |
| DMARC messages/mo | 10,000 | 600,000 | 1,200,000 | 12,000,000 |
| DMARC overage | — | $7.50 /100k | $5 /100k | $2 /100k |
| Uptime monitors | 5 | 15 | 25 | 30 |
| IP reputation monitors | 1 | 10 | 20 | 25 |
| DMARKOFF domains | 0 | 3 | 6 | 9 |
| Postmaster tool users | 1 | 1 | 5 | 10 |

Annual saves **30%**. DMARC domains **unlimited** on all paid tiers. Custom plans available for high-volume senders.

**Products:** Inbox Insight (seed-list placement testing), DMARC Analyzer, DMARKOFF, Uptime Monitor, IP reputation monitoring, consulting services. Free tools: Spam Checker, Domain Checker, Email Security Checker, SPF / DMARC / DKIM / MX / TXT / **BIMI** Checkers.

**Seed-list mechanics (the reference implementation):** 20+ provider mailboxes (AOL, Outlook, Yahoo, Gmail, Hotmail, Zoho, Exchange/O365, Amazon WorkMail, G Suite, ATT.net, GMX, ProtonMail, Mail.ru, Yandex, Web.de, T-online, Gmx.de, Laposte.net FR, Seznam.cz, Onet.pl, Interia.pl, O2.pl, Ukr.net, Naver). Workflow: create test -> select filters and providers -> choose target folder + optional note -> **copy the unique ID string into the email body or headers** -> send to the seed list -> view report. Reports cover **Inbox / Spam / sub-folders (Promotions etc.)**, full IP delivery chain analytics, domain analytics, spam score, and Google Postmaster Tools integration. Advanced seed lists use **sharded distribution for load balancing**; autotest scheduling and alerts; throttling logic for high-volume tests.

### 9.10 Cost model for a self-hosted build

| Line item | SaaS equivalent | Self-hosted |
|---|---|---|
| Outreach platform (100k sends/mo) | Instantly Scale **$194** / Smartlead Pro **$94** | $0 (your infra) |
| Unlimited mailboxes | included (Smartlead, Instantly) | **$4.50-9/mo per real mailbox** (Smartlead resale rates as a market reference) |
| Warmup network | $15-79/inbox/mo | seed pool: 20-50 mailboxes x $4.50-9 = **$90-450/mo** |
| Placement testing | GlockApps Growth **$99** / Mailreach $19.50/mailbox | seed pool doubles as the test fleet -> marginal $0 |
| Email verification | Smartlead from **$32** / free with Woodpecker, Mailshake, lemlist | MX + SMTP handshake (already in `verifier/smtp_verifier.py`) -> $0 |
| Lead data | Apollo / Instantly credits **$47-197/mo** | scraping pipeline (already built) -> $0 |

---

## 10. Gap analysis against the existing LeadForge codebase

Read from the actual repo at `/Users/aryanbansal/Downloads/leadforge`.

### 10.1 What already exists

| File | Current state |
|---|---|
| `backend/app/models/mailbox.py` | `email`, `password` (plaintext), `smtp_host`, `smtp_port`, `daily_limit=50`, `sent_today`, `is_active` |
| `backend/app/models/campaign.py` | `CampaignStatus`: `draft`, `active`, `paused`, `completed` |
| `backend/app/models/campaign_step.py` | `step_number`, `subject`, `body_text`, `body_html`, `delay_days=0` |
| `backend/app/models/send.py` | `status` (pending/sent/failed), `error_message`, `opened`/`clicked`/`replied`/`bounced` booleans, `sent_at`, `mailbox_id`, `step_id` |
| `backend/app/models/contact.py` | `verification_status` (valid/invalid/catch_all/unverified), `unsubscribed` bool |
| `backend/app/campaigns/sender.py` (324 ln) | raw `smtplib`, `MIMEMultipart('alternative')`, injects `List-Unsubscribe: <url>`, 1x1 open pixel, unsubscribe footer |
| `backend/app/campaigns/spam_checker.py` (176 ln) | 80+ trigger words, 0-100 score |
| `backend/app/campaigns/tracker.py` (29 ln) | open/unsubscribe endpoints |
| `backend/app/verifier/smtp_verifier.py` | MX + SMTP handshake verification |
| `requirements.txt` | Celery, Redis, dnspython, SQLAlchemy 2, FastAPI, asyncpg/aiosqlite |

### 10.2 Concrete gaps, ranked by impact

**P0 — compliance and correctness**

1. **Missing `List-Unsubscribe-Post` header.** `sender.py` sets only `List-Unsubscribe: <url>`. Gmail and Yahoo both require one-click (RFC 8058 POST) for bulk senders. Fix: add `msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'` and implement a POST handler returning 2xx. ~5-line change, outsized compliance value.
2. **Plaintext mailbox passwords.** `Mailbox.password` stored raw with a `# In prod, this can be encrypted` comment. Move to a secret store or AES-GCM with a KMS-held DEK; persist only `secret_ref`.
3. **No global suppression table.** Suppression is a single `Contact.unsubscribed` boolean — per-contact, not workspace-wide, and cannot express domain-level or reason-coded suppression. Build the `suppression` table from §6.3 and enforce at all four points.
4. **No hard/soft bounce distinction.** `Send.bounced` is a boolean. Parse the SMTP response code from `error_message` and classify: 5xx permanent -> suppress; 4xx / gateway blocks -> retry. The README claims 550/554 detection, but the model cannot represent the distinction.

**P1 — the two features that define the category**

5. **No warmup engine at all.** Largest single gap. Implement §1.5: `warmup_mailbox` / `warmup_state` / `warmup_event` / `warmup_pair`, the `warmup_quota_today` ramp, IMAP placement observation, and the health-score rollup. Gate campaign sending on `health_score > 90` and `warmup_days >= 14`.
6. **No IMAP layer.** Everything reply-related depends on it: reply detection, threading, OOO detection, warmup placement. `Mailbox` has `smtp_host`/`smtp_port` but no IMAP equivalents, and `requirements.txt` has no IMAP client.
7. **Rotation is naive and not sticky.** `sent_today` is a plain integer with no rolling window and no timezone. Replace with the rolling-24h budget from §2.4, add `assigned_mailbox_id` to `Contact` for sticky-sender semantics (a follow-up must come from the address that started the thread), and switch selection to weighted-by-remaining-budget.
### 10.3 Suggested build order

```
Phase 1 (compliance + correctness, days)
  - List-Unsubscribe-Post + POST handler
  - suppression table + 4 enforcement points
  - hard/soft bounce classification from SMTP codes
  - encrypt mailbox credentials

Phase 2 (deliverability foundation, weeks)
  - imap_host/port on Mailbox; IMAP client wrapper
  - warmup schema + ramp + IMAP placement observation + health score
  - custom tracking domain + CNAME verify
  - DNS audit (MX/SPF/DKIM/DMARC) + DNSBL monitor
  - seed-based placement test reusing spam_checker.py

Phase 3 (pacing + sequencing, weeks)
  - rolling-24h budget, sticky sender, weighted rotation
  - campaign_schedule + timezone windows + gap/jitter
  - delay/delay_unit/pre_delay on steps
  - event log replacing boolean flags

Phase 4 (optimization, weeks)
  - variants + significance-gated auto-promote
  - subsequences with phrase-exact triggers
  - OOO smart pause/resume
  - intent classification (rules first, LLM later)
  - rebuild analytics off the event log
```

### 10.4 Thresholds worth hardcoding as defaults

```
WARMUP_MIN_DAYS              = 14     (21 for managed/premium accounts)
WARMUP_HEALTH_MIN            = 90.0   (%) gate before any campaign send
WARMUP_INCREMENT_PER_DAY     = 1
WARMUP_DAILY_LIMIT_NEW       = 10
WARMUP_REPLY_RATE            = 0.30
WARMUP_OPEN_RATE             = 0.95
WARMUP_SPAM_SAVE_RATE        = 0.02
WARMUP_IMPORTANT_RATE        = 0.80
WARMUP_PAIR_COOLDOWN_DAYS    = 30
WARMUP_MAX_PROVIDER_SHARE    = 0.50

COLD_PER_MAILBOX_START       = 15     (lemlist: 10-15 out of warmup)
COLD_PER_MAILBOX_WEEKLY_ADD  = 5
COLD_PER_MAILBOX_CAP         = 30     (lemlist caps at 25-30)
COLD_PLUS_WARMUP_CEILING     = 50     per mailbox per day
NEW_DOMAIN_DAILY_CAP         = 100    whole domain if age < 1 month
EMAIL_GAP_MINUTES            = 9      (Instantly default)
EMAIL_GAP_JITTER_MINUTES     = 5      (Instantly default)
BOUNCE_AUTOPAUSE_RATE        = 0.05   (>5% pauses the campaign)
BOUNCE_AUTOPAUSE_MIN_SENDS   = 200    (before the check runs at all)
BOUNCE_AUTOPAUSE_COOLDOWN_D  = 7      (no re-trigger for 7 days after resume)
SPAM_COMPLAINT_CEILING       = 0.003  (Gmail/Yahoo: below 0.3%)
UNSUB_HONOR_WINDOW_HOURS     = 48     (Yahoo: within 2 days)
STATUS_EVENT_DEDUPE_MINUTES  = 10     (avoid analytics inflation)
AB_MIN_SAMPLE_PER_VARIANT    = 1900   (5% baseline, +2pp lift, a=0.05, power=0.8)
AB_ALPHA                     = 0.05
AB_POWER                     = 0.80
LEAD_COVERAGE_MIN            = 0.60   (below this, use the fallback template)
```

### 10.5 Sources

```
INSTANTLY (help.instantly.ai)
  5975329  How Warm-Up Works                7988514  Warmup Settings
  13939939 Warmup Health Score              10189418 Premium & Private Warmup Pool
  11118071 Standard & Basic Warmup Pool      6222396  Campaign Settings
  10355896 Advanced Deliverability          10391901 SISR system
  6222192  DNS Records (MX/SPF/DKIM/DMARC)   6984188  Custom Tracking Domain
  8030866  Link Tracking                    12114788 Open Tracking
  8860388  List-Unsubscribe                  7187587  Campaign Email Bounces
  9823139  High Bounce Auto-Pause             6661549  A/Z Testing
  6384663  Spintax                            7251329  Subsequences
  8448897  Custom Lead Labels                6762327  Update Lead Data and Status
  6192983  Global Blocklist                  9823387  AI Blocklist Triggers
  9713093  AI Smart Pause & Resume (OOO)     8797578  Unibox V2
  6602310  Analytics & Report                13925113 Reply Rate Discrepancy
  7046484  Inbox Rotation
  api.instantly.ai/openapi/api_v2.json   exact enums + field semantics
  developer.instantly.ai/llms-full.txt   webhook event types
  instantly.ai/pricing

LEMLIST (help.lemlist.com)
  4508367  Understand sending limits         4452763  Sending algorithm
  8263428  Inbox rotation                    12108624 Sending capacity in outreach queue
  8178397  What lemwarm warms up             8178526  lemwarm Plans / Warmup Score
  8136574  Email deliverability statuses     5914746  Choose a winning A/B test sequence
  lemlist.com/pricing, lemlist.com/email-deliverability

SMARTLEAD
  smartlead.ai/pricing, smartlead.ai/pricing.md, smartlead.ai/llms.txt,
  smartlead.ai/email-warmup
  NOTE: help.smartlead.ai is Notion-hosted and Cloudflare-gated; the help
  center could not be retrieved directly. Pricing facts come from the
  vendor's own machine-readable pricing.md fact sheet.

OTHER VENDORS
  woodpecker.co/pricing    mailshake.com/pricing    warmupinbox.com/pricing
  mailreach.co/pricing     glockapps.com/pricing    glockapps.com/spam-testing
  apollo.io/pricing, apollo.io/llms.txt
  NOTE: apollo.io/pricing is client-rendered and returned no numeric tiers;
  apollo's own llms.txt instructs agents not to quote its prices.

STANDARDS / PROVIDER RULES
  support.google.com/a/answer/81126       Gmail Email sender guidelines
  senders.yahooinc.com/best-practices/    Yahoo sender requirements
  datatracker.ietf.org/doc/html/rfc8058   One-click unsubscribe (RFC 8058)
  bimigroup.org/implementation-guide/     BIMI record + VMC requirements
```


**P2 — pacing, sequencing, and analytics**

8. **`delay_days` only.** `CampaignStep` needs `delay`, `delay_unit` (minutes/hours/days), and `pre_delay`/`pre_delay_unit` for subsequences. Semantics: `delay` is the wait *before the next* step.
9. **No schedule model.** `Campaign` has no `campaign_schedule` (start/end date, per-weekday windows, timezone), no `skip_weekends`, no send-gap/jitter fields. Add `email_gap` (9 min) and `random_wait_max` (5 min).
10. **Boolean flags instead of an event log.** `Send.opened/clicked/replied/bounced` cannot dedupe, cannot record *when*, cannot support per-step or per-variant breakdown, and cannot compute any rate correctly. Introduce the append-only `ContactEvent` table (§6.2) and derive booleans as cached projections.
11. **No A/B testing.** No variant model on `CampaignStep`. Add `variants` with per-step random assignment and significance-gated auto-promote (§4.2).
12. **No conditional branching.** Add subsequences with status/activity/keyword triggers, using **exact phrase** matching (§7.2) — otherwise "I am not interested" fires an "interested" subsequence.
13. **No custom tracking domain.** `settings.TRACKING_DOMAIN` is a single shared value. Add per-account `tracking_domain_name` + `tracking_domain_status` and a CNAME verification resolver (§3.2).
14. **No auto-pause guardrail.** Implement the >5% bounce auto-pause with a >=200-send minimum and a 7-day re-arm cooldown (§2.5).
15. **Analytics endpoints exist** (`backend/app/api/analytics.py`) but are computed off boolean flags; they will be wrong once events are deduped and per-step. Re-derive from the event log using §8.2.

**The real cost of self-hosting is the warmup seed pool.** That is the one thing you cannot fake with code: it requires N real, aged, provider-diverse mailboxes that actually send and receive. Budget for it explicitly.

| Additional warm-ups | **$5/mo per email account** |
| Email addresses (Google/Microsoft, pre-configured SPF/DKIM/DMARC) | **$6/mo per email address** |
| Additional Lead Finder credits | from **500 credits for $10** |
| Agency panel | add-on: separate prospects DB, global blacklist, bulk mailbox upload, client view-only access, automated client domain audits, centralized billing |
| Outbound workshops | **$2,000 / 4 sessions of 2h**; extra 2h session **$500** |

**SmartDelivery (inbox placement testing):**

| Tier | Price | Sequence tests | Sender accounts/test |
|---|---|---|---|
| Growth | **$49/mo** | 120 | up to 50 |
| Pro (most popular) | **$174/mo** | unlimited | up to 200 |
| Export | **$599/mo** | unlimited | up to 500 |

**Mailbox resale:** Gmail fresh (InfraInbox) **$4.50/mo**; Outlook fresh (InfraInbox) $16/yr + **$5/mo**; Outlook pre-warmed (Zapmail) $18/yr + **$9/mo**; SMTP fresh (Mailreef) $19/yr + **$3.99/mo**; SMTP standard (AeroSend) $13/yr + **$4.20/mo**. Pre-warmed costs roughly 2x fresh and arrives ready to send.

**Counter semantics:** a *lead credit* = one unique prospect email stored (counts against contacts); an *email credit* = one email sent (counts against sends). Two separate counters. Base = 2,000 stored contacts and 6,000 sends, so the same contact can be emailed multiple times within the send allowance.
