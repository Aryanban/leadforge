# B2B Lead Data & Email Enrichment SaaS — Implementation Research (2025/2026)

**Scope:** Apollo.io, Clay, Lusha, Hunter.io, Snov.io, RocketReach, Dropcontact, Prospeo, Findymail, FullEnrich, Clearout, MillionVerifier, ZeroBounce, NeverBounce, Reoon, Emailable.
**Purpose:** Implementation reference for LeadForge (`backend/app/enricher/email_finder.py`, `backend/app/verifier/smtp_verifier.py`). Sources are vendor API docs, OpenAPI specs, `llms.txt`, and pricing pages captured Oct 2026.
**Legend:** ✅ = directly quoted from vendor doc; 🔶 = industry-standard inference (not vendor-published).

---

## 0. Executive Summary

1. **Pattern inference is per-domain, not global.** Providers first *learn* the domain's email format from known-verified emails (Hunter returns `data.pattern` e.g. `"{first}"`, `"{first}.{last}"`), then fall back to a global prior only when the seed set is empty. LeadForge does the opposite (global list only).
2. **Every serious provider attaches `email + status + confidence + source`** as a 4-tuple. LeadForge stores only `(bool is_verified, string status)` and collapses many statuses into `True/"valid_mx"`.
3. **Verification status is a rich enum, not a bool.** Real verifiers return 5–30 distinct states across two axes (`status` + granular `sub_status`). See §3.
4. **The most dangerous bug** in `smtp_verifier.py` is `except: return True, "valid_mx"` — it converts *unreachable/blocked/timeout* servers into "valid", inflating deliverability.
5. **Catch-all requires multi-probe.** A single random local-part probe cannot distinguish "true accept-all" from "port-25 blocked / greylisted / rate-limited". See §4.
6. **Waterfall enrichment** = ordered list of 15–25+ providers, stop-on-first-valid, pay-per-hit. FullEnrich aggregates "20+ providers"; Clay/Apollo let you reorder. LeadForge has no external provider waterfall.
7. **Signals** (technographics, funding, headcount-growth, job postings, NAICS/SIC, revenue bands) are why Apollo/Clay command premium pricing. LeadForge has zero firmographic signals.
8. **Dedupe/entity resolution** needs domain normalization + fuzzy name matching (Jaro-Winkler ~0.9 / Levenshtein ≤2) + E.164 phone. LeadForge dedupes only on exact `email ==` string.
9. **Pricing converges on "pay only on hit"** (Dropcontact, FullEnrich) or per-credit with unknown=free (ZeroBounce, NeverBounce $8/1k).
10. **Synchronous SMTP inside the async request path** blocks the event loop 3–8s per email. Must move to a worker pool / Celery (already in `requirements.txt`, unused here).

---
---

## 1. Email Pattern Engines

### 1.1 The canonical global pattern probability ranking 🔶

No vendor publishes an exact global percentage table (proprietary), but the ranking below is the de-facto industry prior used by Hunter, Snov, RocketReach, Prospeo, Findymail, Skrapp, and Clearbit-style engines. Numbers are the widely-cited industry distribution across US/EU B2B corporate domains; treat as a *prior*, always overridden by learned per-domain pattern.

| Rank | Pattern (template) | Example (John Doe) | Approx. share 🔶 | Notes |
|------|--------------------|--------------------|------------------|-------|
| 1 | `{first}.{last}` | `john.doe@` | ~35–45% | Dominant in US/EU tech & enterprise |
| 2 | `{first}` | `john@` | ~18–25% | Startups, Israel, NL, Nordics; Hunter's own example returns `"{first}"` for intercom.com |
| 3 | `{first}{last}` | `johndoe@` | ~8–12% | Germany (DE), some APAC |
| 4 | `{f}{last}` | `jdoe@` | ~5–8% | Finance, legal, UK |
| 5 | `{first}_{last}` | `john_doe@` | ~2–4% | Spain (ES), parts of LATAM/IT |
| 6 | `{first}-{last}` | `john-doe@` | ~2–4% | DE, FR, some gov |
| 7 | `{f}.{last}` | `j.doe@` | ~1–2% | Older corporates |
| 8 | `{last}.{first}` | `doe.john@` | <1% | Japan (JP), some CN/KR |
| 9 | `{last}` | `doe@` | <1% | Rare for personal; LeadForge ranks this #6 (too high) |
| 10 | `{first}{l}` | `johnd@` | <1% | |
| 11 | `{first}.{l}` | `john.d@` | <1% | |
| 12 | `{last}{f}` | `doej@` | <1% | |

**Per-country / per-region deltas 🔶** (why a global fixed order underperforms):

| Region | Skew |
|--------|------|
| US / Canada / UK | `{first}.{last}` and `{first}` dominate (>70% combined) |
| Germany (DE) | `{first}.{last}`, `{first}{last}`, `{first}-{last}` |
| France (FR) | `{first}.{last}`, `{first}-{last}`, dot-heavy `{p.last}` |
| Spain / LATAM | `{first}_{last}`, `{first}.{last}`, `{f}{last}` |
| Nordics / NL | `{first}` very common |
| Japan (JP) | `{last}.{first}`, `{first}.{last}{l}` (romanized) |
| Israel / IL | `{first}`, `{f}{last}` |

**Best single guess vs N candidates:**
- **Single guess** = learned per-domain pattern if confidence high; else argmax of global prior. Returned with `confidence`/`score` (Hunter 0–100; Apollo `email_status` + `extrapolated_email_confidence`).
- **N candidates** = top-k patterns ranked by per-domain learned frequency, each independently SMTP-verified. Hunter's Domain Search returns up to 20 `sources` per email + per-email `confidence` (example: `ciaran@intercom.com`, confidence `92`). Dropcontact returns a *qualified* single local part (nominative/generic/catch_all/random/invalid). Providers verify each candidate and stop at the first that passes SMTP without bouncing.

### 1.2 How providers LEARN a company's pattern (pattern inference) — exact algorithm

**Inputs:** a seed set of known emails on the same registrable domain, e.g. `S = {ciaran@intercom.com, des@intercom.com, ...}` plus the person records (first/last) for each.

**Algorithm (what Hunter's `data.pattern`, RocketReach, and pattern engines implement):**

```python
def infer_pattern(domain, seed_emails, person_records):
    if len(seed_emails) == 0:
        return (GLOBAL_ARGMAX_PATTERN, low_confidence, learned=False)
    template_votes = Counter()
    for (local, first, last) in seed_emails:
        tmpl = reverse_engineer(local, first, last)   # concrete -> template
        if tmpl is not None:
            template_votes[tmpl] += 1
    total = sum(template_votes.values())
    if total == 0:
        return (GLOBAL_ARGMAX_PATTERN, low_confidence, learned=False)
    best_pattern, best_count = template_votes.most_common(1)[0]
    ratio = best_count / total            # dominance of the winning template
    # Confidence blend: dominance x seed size x global prior
    confidence = clamp(round(100*(0.55*ratio + 0.25*min(1,total/5) + 0.20*global_prior[best_pattern])), 1, 99)
    if ratio >= 0.6 and total >= 2:       # domain consistent enough
        return (best_pattern, confidence, learned=True)
    return (best_pattern, confidence, learned=False)  # fall back to global prior

def reverse_engineer(local, first, last):
    f, l = normalize(first), normalize(last)   # lowercase, strip accents/punct
    candidates = {
        "{first}.{last}": f"{f}.{l}", "{first}": f, "{first}{last}": f"{f}{l}",
        "{f}{last}": f"{f[0]}{l}", "{first}_{last}": f"{f}_{l}", "{first}-{last}": f"{f}-{l}",
        "{f}.{last}": f"{f[0]}.{l}", "{last}.{first}": f"{l}.{f}", "{last}": l,
        "{last}{f}": f"{l}{f[0]}", "{first}{l}": f"{f}{l[0]}", "{first}.{l}": f"{f}.{l[0]}",
    }
    for tmpl, rendered in candidates.items():
        if local == rendered:
            return tmpl
    return None   # generic (info@, sales@) or unknown form -> ignore in vote
```

**Key rules real engines apply that LeadForge omits:**
- **Ignore generic aliases** (`info@, sales@, contact@, support@, hello@, admin@, office@, noreply@, no-reply@`) when learning — no person-pattern signal.
- **Accent/Unicode folding**: `Démogé → demoge`, `Müller → mueller`.
- **Middle names / particles / suffixes**: `van der Berg`, `Smith-Jones`, `Jr`, `III`.
- **Only override the global prior when the seed is unanimous** (ratio ≥ ~0.6).
- **Verification chained to pattern**: Hunter auto-verifies, returns status ∈ {valid, accept_all, unknown}; for accept-all the `score` estimates probability valid.

### 1.3 What LeadForge does today (gap)

`generate_email_permutations(name, domain)` in `email_finder.py`:
- Uses **business name** as person name (bug): `Acme Realty Group` → first="acme", last="realty" → `acme.realty@`, `acme@`… → essentially never correct.
- Fixed order `{first}.{last}, {first}, {first}{last}, {f}{last}, {first}_{last}, {last}` — **missing** `{f}.{last}`, `{first}-{last}`, `{last}.{first}`, `{first}{l}`, `{first}.{l}`.
- **No pattern learning**, no per-domain confidence, no seed-set inference, no accent folding.
- Always appends 7 generic aliases even when the exec pattern would work.

---
---


## 2. Waterfall Enrichment Architecture

### 2.1 The model

A **waterfall** = an ordered list of enrichment providers. For a contact (identified by `first_name + last_name + company_domain` or `linkedin_url`), the orchestrator calls provider #1; if it returns a verified email, **stop**; else #2; … until exhausted or "good enough" lands. Coverage rises with each provider; cost rises per provider attempted.

**FullEnrich (aggregator):** "aggregate data from more than 20 providers to achieve the highest enrichment rate." Find-rate: mobile ~87% (18 sources), work email ~93% (13 sources), ~80% overall.
**Clay:** users compose their own provider chain (Apollo, Hunter, Dropcontact, Prospeo, FullEnrich, Lusha, Snov, Clearbit) and reorder by cost/yield.
**Apollo:** `run_waterfall_email=true` / `run_waterfall_phone=true` on People Enrichment; returns **synchronously** with demographics + waterfall status, then delivers final email/phone **asynchronously to a webhook** (or `poll_only` + `request_id`). Webhook payload includes *"data sources attempted for each record, statuses and messages returned by each data source, final enriched values, credit usage."*

### 2.2 Cost-per-provider & stop conditions (concrete numbers ✅)

| Provider | Unit cost | Stop / charge rule |
|----------|-----------|--------------------|
| **FullEnrich** | work email **1 credit**; mobile **10**; personal email **3**; reverse-email **1**; search **0.25/person** | Credits consumed **only on hit** (Deliverable / High-Probability / Catch-all). 20+ providers aggregated. Rollover 3mo monthly / 12mo annual. |
| **Apollo** | People enrich **1–9 credits/person**: 1 credit for demographics or email, **+8** if mobile returned; 0 if nothing credit-worthy. Org enrich 1 credit/org. Job posts 1 credit/page. | Waterfall credits depend on config; **"some vendors consume credits per lookup even when no data is found."** `match_confidence=none` → no demographic credit. |
| **Dropcontact** | **Pay-on-success**: 1 credit only if a *verified* email returned (verification included). Verify-only = 1 credit. | Refunded if no email found. |
| **Hunter** | Email found **1 credit**; verified **0.5**; Domain Search 1/email (bulk 1 per 10). | No credit if not found / not verified (returns `unknown`). |
| **ZeroBounce** | 1 credit/verification; Email Finder **20 credits/successful query**; AI scoring 1 credit. | **`unknown` results are free.** |
| **NeverBounce** | **$8 / 1,000 credits** PAYG; Growth $49/mo up to 10,000. | Duplicates free. |

**Stop conditions 🔶:** (1) stop on first **verified/deliverable** email; (2) stop on first **catch-all with acceptable confidence** if "accept risk" (FullEnrich `HIGH_PROBABILITY` ~9% bounce); (3) hard cap on providers (cost ceiling) + per-record timeout; (4) concurrency: providers hit in parallel across *records* but sequentially *within* a record (or race-and-cancel — Clay does "fastest valid wins" for some).

### 2.3 Merge / dedupe / confidence model

**Canonical data model** (FullEnrich `contact_info` — cleanest public example):

```jsonc
contact_info: {
  most_probable_work_email:    { email: "john.snow@example.com", status: "DELIVERABLE" },
  most_probable_personal_email:{ email: "johnsnow@gmail.com",    status: "DELIVERABLE" },
  most_probable_phone: { number: "+1 555-123-4567", region: "US", line_type: "MOBILE",
    line_status: "ACTIVE", ownership_match: "CONFIRMED", ownership_match_confidence: 90,
    connect_rate: "HIGHEST" },
  work_emails:    [ { email, status } ],   // all candidates, not just best
  personal_emails:[ { email, status } ],
  phones:         [ { number, region, line_type, line_status, ownership_match,
                      ownership_match_confidence, connect_rate } ]
}
```

**`most_probable_work_email` selection rule (FullEnrich, quoted):** *"the work email with the lowest bounce rate. If multiple valid emails are found, we prefer the one with a domain closest to the user-entered domain. INVALID emails are excluded."*

**Merge/dedupe rules:** dedupe candidates by normalized local+domain, keep highest-status; prefer corporate-domain match over alias; exclude `INVALID` from "best" but keep in array for transparency. **Re-enrichment dedupe (FullEnrich):** dedupe on exact input tuple (first+last+domain+linkedin); varying inputs defeat dedupe → re-charged; same contact within 3 months → 0 credits (history hit); simultaneous identical requests defeat dedupe. **Confidence:** each provider attaches its own score; orchestrator merges by max(status_rank), ties broken by provider-order priority; FullEnrich triple-verifies and upgrades catch-all→`HIGH_PROBABILITY` when multiple providers agree.

### 2.4 The "email + confidence + source attribution" data model (recommended)

```python
@dataclass
class EnrichedEmail:
    email: str; local_part: str; domain: str
    status: EmailStatus            # enum, §3
    confidence: int                # 0-100
    pattern: str | None            # "{first}.{last}" if learned
    source: str                    # provider that produced the hit
    sources: list[Source]          # up to N web sources (Hunter model)
    verified_at: datetime
    smtp_detail: SmtpProbe         # mx, smtp_check, accept_all, block, code
    is_role_account: bool; is_free_provider: bool; is_disposable: bool
```

LeadForge persists only `is_verified: bool` + `verification_status: str` on `Contact` — cannot represent confidence, source, or pattern.

---
---


## 3. Email Verification Taxonomy (the COMPLETE status enum)

### 3.1 Two-axis model: `status` (coarse) + `sub_status` (granular)

The most complete public taxonomy is **ZeroBounce** (7 top-level `status` + ~27 `sub_status`). Other vendors collapse to fewer buckets. Treat the union as the target enum.

**ZeroBounce top-level `status` ✅**

| status | Definition | Sender action |
|--------|-----------|---------------|
| `valid` | Verified deliverable at time of check | **Send** |
| `invalid` | Does not exist / hard bounce | **Don't send** |
| `catch-all` | Domain accepts all addresses; individual mailbox unverifiable | **Risky — send cautiously** (or Deep Verify) |
| `spamtrap` | Known spam-trap / honeypot | **Never send** |
| `abuse` | Known complainer/abuse account | **Don't send** |
| `do_not_mail` | Role/complaint-suppressed | **Don't send** |
| `unknown` | Could not be determined | **Don't send (retry later)** — ZeroBounce does **not** charge |

**ZeroBounce `sub_status` ✅ (full list):** `none, antispam_system, greylisted, mail_server_temporary_error, forcible_disconnect, possible_trap, role_based, global_suppression, mail_server_did_not_respond, timeout_exceeded, possible_typo, unroutable_ip_address, no_mx_record, exception_occurred, toxic, disposable, role_based_catch_all, alternate, does_not_accept_mail, failed_syntax_check, no_dns_entries, mailbox_quota_exceeded, failed_smtp_connection, mx_forward`.

| sub_status | Detection / meaning |
|-----------|---------------------|
| `greylisted` | Server returned 4xx "try later" (temporary deferral). Reprocess via Greylist API. |
| `antispam_system` | Anti-spam gateway (Barracuda/Mimecast/Proofpoint) blocking the probe. |
| `mail_server_temporary_error` | 4xx SMTP during RCPT. |
| `forcible_disconnect` | Server dropped connection mid-handshake (anti-probe). |
| `possible_trap` | Pattern/age matches a known trap. |
| `role_based` / `role_based_catch_all` | Local part is a role alias (§3.4). |
| `global_suppression` | On a shared suppression list. |
| `mail_server_did_not_respond` | Connected but no RCPT response. |
| `timeout_exceeded` | Probe exceeded time budget. |
| `possible_typo` | Near a popular domain (gmial→gmail); `did_you_mean`. |
| `unroutable_ip_address` | MX points to private/unroutable IP. |
| `no_mx_record` / `no_dns_entries` | No MX / no DNS. |
| `mailbox_quota_exceeded` / `has_inbox_full` | 552 — mailbox full (Reoon `has_inbox_full`). |
| `does_not_accept_mail` | Domain refuses mail (null MX / 554). |
| `failed_smtp_connection` | Port 25 connect failed (blocked). |
| `mx_forward` | MX is a forwarding service. |

---
---


### 3.2 Cross-vendor status mapping (normalize to one enum)

| Normalized | ZeroBounce | NeverBounce | Emailable `state` | Reoon | MillionVerifier | Hunter | Clearout |
|---|---|---|---|---|---|---|---|
| **valid** | `valid` | `valid` | `deliverable` | `valid`/`safe` | `ok` | `valid` | `valid` |
| **invalid** | `invalid` | `invalid` | `undeliverable` | `invalid` | `invalid` | — | `invalid` |
| **catch_all** | `catch-all` | `catchall` | `accept_all`=true | `catch_all` | `catch_all` | `accept_all` | `catch-all` |
| **disposable** | sub `disposable` | `disposable` | `disposable`=true | `disposable` | `disposable` | `disposable`=true | `disposable` |
| **role_account** | sub `role_based` | — | `role`=true | `is_role_account` | `role` | type=`generic` | `role`-based |
| **free_email** | `free_email_host` | — | `free`=true | `is_free_email` | — | `webmail`=true | `free` |
| **greylist** | sub `greylisted` | (retry) | (retry) | — | — | — | — |
| **unknown** | `unknown` | `unknown` | `unknown` | `unknown` | `unknown` | `unknown` | `unknown` |
| **spamtrap** | `spamtrap` | — | — | `spamtrap` | — | — | — |
| **disabled** | — | — | — | `disabled` | — | — | — |
| **gibberish** | — | — | `gibberish` | — | — | `gibberish` | `gibberish` |

**Vendor-specific fields worth exposing:**
- **Hunter verifier ✅**: `status` ∈ {`valid, accept_all, webmail, disposable, invalid, unknown, pending`} (legacy `result` ∈ deliverable/undeliverable/risky); booleans `regexp, gibberish, disposable, webmail, mx_records, smtp_server, smtp_check, accept_all, block`; `score` (0–100, **50 = arbitrary for webmail/disposable**); `verification.date` (can be up to 1 month old; null when disposable or blocked).
- **Emailable ✅**: `state` ∈ {`deliverable, undeliverable, risky, unknown`}; `reason` ∈ {`accepted_email, invalid_domain, invalid_email, invalid_smtp, low_deliverability, rejected_email`}; flags `accept_all, disposable, free, role, no_reply, mailbox_full`; `score`, `did_you_mean`, `smtp_provider`, `mx_record`; `retries` flag (default on to reduce unknowns).
- **Reoon ✅**: QUICK mode (syntax+disposable+MX+domain-accept+role, <0.5s, **does NOT check individual inbox**) vs POWER mode (full SMTP). Fields: `is_valid_syntax, is_disposable, is_role_account, mx_accepts_mail, is_spamtrap, is_free_email, is_catch_all, has_inbox_full, is_disabled, can_connect_smtp, is_deliverable, is_safe_to_send`.
- **Dropcontact ✅**: qualifies local part as `nominative | catch_all | generic | random | invalid`; domain as `pro | perso | invalid`.

### 3.3 Detection pipeline (order every verifier runs)

```
1. syntax          -> failed_syntax_check
2. typo/gibberish  -> did_you_mean (gmial), gibberish (e65rc109q@)
3. role_account    -> local-part role list (§3.4)
4. free/disposable -> domain blocklists (§3.5, §3.6)
5. domain DNS      -> A/MX; no_dns_entries / no_mx_record / invalid_domain
6. MX selection    -> sort by MX preference, A-record fallback; failed_smtp_connection
7. SMTP handshake  -> HELO/EHLO, MAIL FROM, RCPT TO
     250 -> deliverable (unless accept_all, §4)
     550/551/553 -> invalid / mailbox_not_found
     552 -> mailbox_quota_exceeded
     4xx / defer -> greylisted / temporary_error -> RETRY
     disconnect/block -> forcible_disconnect / antispam_system / block
     timeout -> timeout_exceeded / unknown
8. catch-all probe -> multi-probe (§4) -> accept_all / role_based_catch_all
9. score           -> blend; catch-all gets probabilistic score
```

---
---


### 3.4 Role-account detection lists 🔶 (industry-standard)

Local parts treated as **role accounts** (route to a team, not a person; higher spam-complaint risk):

```
admin, administrator, info, contact, contacts, sales, marketing, support, help,
helpdesk, service, customer, customers, customercare, care, billing, accounts,
accounting, finance, invoicing, invoices, payments, paypal, orders, order,
purchases, hr, careers, jobs, recruiting, recruitment, talent, legal, compliance,
privacy, security, abuse, postmaster, webmaster, hostmaster, noc, office,
reception, frontdesk, hello, hi, team, enquiries, inquiries, enquire, general,
main, press, media, pr, newsletter, subscribe, unsubscribe, noreply, no-reply,
donotreply, do-not-reply, notifications, notify, alerts, mailer-daemon, mail,
email, web, www, ftp, root, ops, dev, devops, it, tech
```

**Vendor behavior:** Dropcontact labels these `generic`; ZeroBounce `role_based` / `role_based_catch_all`; Hunter sets `type: "generic"` in Domain Search. **Rule:** never count a role address as a *person* lead; many senders deprioritize them (higher complaint rate). LeadForge treats `contact@/info@/sales@` as *first-class verified contacts* — a deliverability/reputation risk.

### 3.5 Free / webmail provider lists 🔶 (must detect, don't SMTP-probe)

```
Gmail (googlemail.com), Yahoo (yahoo., ymail., rocketmail.), Microsoft
(outlook., hotmail., live., msn.), Apple (icloud., me., mac.com), AOL,
Proton (proton., protonmail., pm.me), GMX (gmx., gmx.net), Zoho, Yandex,
Mail.ru, Tutanota (tutanota., tuta.io), Fastmail, Hushmail, Lycos, Naver,
Daum, QQ (qq.com), 163 (163.com), Sina, Rediffmail, mail.com, email.com
```
Reoon `is_free_email`; Hunter `webmail=true`; Emailable `free=true`; ZeroBounce `free_email_host`. **SMTP probes to Gmail/Yahoo are unreliable** (accept-all / greylist aggressively) — treat free-provider status as authoritative, not the SMTP result.

### 3.6 Disposable / temp-mail blocklist

LeadForge has **12** domains. Real lists run to **thousands** and update continuously. Use a maintained feed (GitHub `disposable-email-domains`, or a vendor API). Extend at minimum: `mailnesia.com, temp-mail.org, temp-mail.io, tempail.com, mohmal.com, emailondeck.com, getnada.com, inboxbear.com, mintemail.com, spamdecoy.com, mytrashmail.com, mt2015.com, filzmail.com, trashmail.de, grr.la, sharklasers.com, guerrillamail.* , 10minutemail.* , throwawaymail.*`.

---
---


## 4. Catch-All Detection Methodology (multi-probe)

### 4.1 Why single-probe is WRONG

LeadForge's `check_catch_all_domain` sends **one** RCPT with a single random local part and concludes `catch_all = (code == 250)`. This conflates four distinct server states:

| Server reality | Single random probe returns | Wrongly classified as |
|----------------|----------------------------|-----------------------|
| True accept-all (catch-all domain) | 250 | catch-all ✅ correct |
| **Port 25 blocked / ISP egress blocked** | timeout/exception | **not catch-all** (silently `False`) — treated as normal domain |
| **Greylisted / 4xx deferral** | 451/450 | not catch-all (returns False) — should retry |
| **Anti-spam gateway accepts probe, rejects real** | 250 | catch-all (correct-ish) |

A single probe cannot tell "configured to accept-all" apart from "temporarily greylisting us" or "we couldn't reach it at all." Worse: the verifier has the **inverse** bug — on *any* SMTP exception it returns `True/"valid_mx"`, so a blocked port makes every address look valid while the separate catch-all probe returns `False`. These two behaviors contradict each other and both corrupt the data.

### 4.2 The correct multi-probe algorithm 🔶 (Clearout "Deep Verify", ZeroBounce, FullEnrich)

```python
def detect_catch_all(domain, n_probes=3):
    mx = best_mx(domain)                 # sorted by preference
    if not mx: return NO_MX
    # A. Reachability control: can we talk to the server at all?
    if not smtp_connect(mx):             # port 25 blocked/timeout
        return UNKNOWN_BLOCKED           # NOT "valid", NOT "not-catch-all"
    # B. N probes with DIFFERENT high-entropy random local parts
    randoms = [f"qx{rand_hex}{i}z9k@{domain}" for i in range(n_probes)]
    results = [smtp_rcpt(r) for r in randoms]
    accepted = sum(r == 250 for r in results)
    rejected = sum(r in (550, 551, 553) for r in results)
    if accepted == n_probes:               return CATCH_ALL      # accepts arbitrary addresses
    if rejected >= 1 and accepted == 0:    return NOT_CATCH_ALL  # validates individual mailboxes
    if any(r is 4xx/greylist for r in results): return GREYLISTED_RETRY  # re-probe after delay
    if mixed or connect_dropped:           return ANTISPAM_GATEWAY       # try SEG-aware/Deep Verify

def probe_real_address(addr):   # only meaningful if NOT_CATCH_ALL
    code = smtp_rcpt(addr)
    250 -> deliverable ; 550 -> invalid ; 4xx -> greylist/retry ; drop -> blocked
```

**Confidence scoring for catch-all:**
- **True catch-all** (`accepted == n_probes`): the real address is *unverifiable*; assign probabilistic confidence from local-part↔learned-pattern match + external corroboration (seen on the web? multiple providers agree?). FullEnrich calls a corroborated catch-all `HIGH_PROBABILITY` (**~9% bounce**) vs raw `CATCH_ALL` (**higher bounce**). ZeroBounce advertises **<1% average catch-all rate** because Deep Verify resolves most; NeverBounce/ZeroBounce auto-reprocess greylisted/unknown.
- **Blocked/greylisted:** status = `unknown`/`greylisted`, **not** `valid`. Re-verify later; don't send until resolved. ZeroBounce explicitly does not charge for `unknown`.
- **Best practice:** probe 3+ random local parts AND a known-invalid control; require *all* 250 before declaring catch-all; require *any* 550 before declaring strict.

### 4.3 LeadForge gaps (catch-all + verification)

1. `check_catch_all_domain` = **1 probe**, single random → cannot separate catch-all from blocked/greylisted.
2. `verify_email_smtp`: `except (...): return True, "valid_mx"` and bare `except: return True, "valid_mx"` — **treats blocked/timeout/error as valid**. Must return `unknown`/`blocked`, never `valid`.
3. MX selection uses `records[0]` with **no preference sort**, no A-record fallback ordering → may connect to a backup MX.
4. Only distinguishes `250` and `550`; every other code → `True/"server_response_<code>"` (treated valid). 4xx/552 mishandled.
5. Synchronous `smtplib` inside async `enrich_business_by_id` → blocks event loop; no retry queue for greylist; no timeout differentiation.

---
---


## 5. Signals / Data Fields (Apollo & Clay)

### 5.1 Firmographics (Apollo Organization Enrichment ✅ — real field names)

| Signal | Apollo field | Example / notes |
|--------|-------------|-----------------|
| Headcount (est.) | `estimated_num_employees` | `1600` |
| Headcount growth | `organization_headcount_six_month_growth` / `_twelve_month_growth` / `_twenty_four_month_growth` | `12.3 / 24.6 / 48.9` (%) — **growth signal** |
| Revenue | `annual_revenue` + `annual_revenue_printed` | `100000000` / `"100M"` |
| Total funding | `total_funding` + `total_funding_printed` | `251200000` / `"251.2M"` |
| Latest round | `latest_funding_round_date`, `latest_funding_stage` | `2023-08-01`, `"Series D"` |
| Funding events | `funding_events[]` | full round history |
| Industry | `industry`, `industry_tag_id`, `industry_tag_hash` | `"information technology & services"` — Apollo's own taxonomy |
| Keywords | `keywords[]` | `["revenue intelligence", ...]` |
| Technographics | `technology_names[]` (e.g. `{"information_technology": 8}`) | tech-stack counts |
| Corp hierarchy | `owned_by_organization`, `owned_by_chain[]`, `ultimate_parent_organization`, `suborganizations[]`, `num_suborganizations` | parent/subsidiary resolution |
| Phone / locations | corporate phone, `locations[]`, language counts, retail-location counts | |
| Job postings | Organization Job Postings endpoint | 1 credit/page, up to 10,000/page; shows *which departments are hiring* (growth/intent) |

**Derivation 🔶:**
- **Headcount & growth:** monitored from LinkedIn company pages + press + SEC/LinkedIn deltas; growth = % change over trailing 6/12/24 months.
- **Revenue:** modeled band from headcount × industry revenue-per-employee priors, anchored to disclosed figures; Apollo exposes a printed rounded band.
- **Funding:** parsed from Crunchbase/press/SEC filings; stage enum (Seed → Series D → IPO).
- **Technographics:** web crawl + job posts + Wappalyzer-style signature detection on the company site; counts = observed signals.
- **Industry taxonomy:** Apollo uses a proprietary tag taxonomy (`industry_tag_id`, hash); other vendors map to **NAICS**/**SIC** codes (US) or LinkedIn industry. NAICS = 6-digit North American Industry Classification System; SIC = older 4-digit Standard Industrial Classification. Clay exposes standardized industry + headcount bands.

### 5.2 Company size bands (FullEnrich enums ✅)
`1-10 · 11-50 · 51-200 · 201-500 · 501-1000 · 1001-5000 · 5001-10000 · 10001+` (plus exact `headcount` int, may be 0).

### 5.3 People signals (FullEnrich ✅)
`headline`, `description`, `location.{city,region,country,country_code}`, `social_profiles.professional_network.{url,handle,id,connection_count}` (LinkedIn), `languages[].{language,proficiency}`, seniority, job function/sub-function, `company_type` (Privately Held / Public / Nonprofit), `year_founded`, HQ structured address + offices.

### 5.4 Phone signals (FullEnrich ✅)
`phones[]`: `number` (intl format), `region` (ISO 3166-1 alpha-2), `line_type` (`MOBILE|LANDLINE|VOIP|UNKNOWN`), `line_status` (`ACTIVE|INACTIVE|UNKNOWN`), `ownership_match` (`CONFIRMED|MISMATCH`, US/CA only), `ownership_match_confidence` (0–100), `connect_rate` (`HIGHEST|...`).

### 5.5 LeadForge signals (gap)
Only has `probe_business_health` (SSL, site freshness, ad spend) for ICP scoring. **No** technographics, funding, headcount growth, revenue, NAICS/SIC, job postings, or LinkedIn-derived people data. This is the entire "intent/firmographic" layer that justifies Apollo/Clay pricing and is absent.

---
---


## 6. Dedupe / Entity Resolution

### 6.1 Domain normalization (do this first — it's the join key 🔶)

```python
def normalize_domain(url_or_domain):
    d = strip scheme, path, query, port, "www.", uppercase
    d = idna_to_unicode(d).lower()
    registrable = publicsuffix.registrable_domain(d)   # a.b.co.uk -> b.co.uk (PSL)
    return registrable
```
- Use the **Public Suffix List** so `app.intercom.com`, `blog.intercom.com` → `intercom.com`.
- Strip tracking subdomains (`mail., email., e., click., link.`) when matching marketing → corporate domains.
- Keep a `linked_domains` alias set (Hunter returns `linked_domains[]`) so `intercom.io` ↔ `intercom.com` merge.

### 6.2 Fuzzy name matching (person dedupe / exec match 🔶)

| Algorithm | Accept threshold | Use |
|-----------|------------------|-----|
| **Jaro-Winkler** | ≥ 0.90 (same person), ≥ 0.85 (review) | Names — rewards common prefix |
| **Levenshtein (normalized)** | ≤ 2 edits for len ≤ 8, ≤ 3 for longer | Typos |
| **Token-set / soundex** | exact after folding | "Jon" vs "John", transliteration |

```python
def person_key(first, last, domain):
    f = fold_accents(first).lower(); l = fold_accents(last).lower()
    l = strip_suffix(l, ["jr","sr","ii","iii","iv","phd","md"])
    return (f, l, registrable_domain(domain))

def same_person(a, b):
    if a.domain != b.domain: return False
    return jaro_winkler(a.first, b.first) >= 0.90 and jaro_winkler(a.last, b.last) >= 0.90
```

### 6.3 Phone normalization (E.164 🔶)
Use `libphonenumber` (Google) semantics:
```python
parse(raw, default_region) -> E.164  "+14155550132"
validity = is_valid_number_for_region(...)
type     = MOBILE / LANDLINE / VOIP
```
- Store canonical **E.164**; keep original for display.
- Region inferred from country code or company HQ country.
- FullEnrich stores `region` (ISO alpha-2) + `line_type` + `ownership_match` — mirror this.

### 6.4 "Merge record" conflict-resolution rules 🔶

When two records for the same entity conflict, resolve by **source trust + recency + specificity**:

| Field | Winner rule |
|-------|-------------|
| email | highest `status` rank (valid > high-prob > catch-all > unknown > invalid); tie → most sources; tie → most recent `verified_at`; exclude invalid from "best" |
| phone | `line_type=MOBILE` + `line_status=ACTIVE` + `ownership_match=CONFIRMED` preferred; keep all in array |
| name | most complete (has first+last); fold accents; prefer LinkedIn-sourced |
| headcount | exact int > range; prefer freshest; growth fields merged by max-magnitude recent |
| domain | registrable domain wins over subdomain; corporate over marketing alias |
| title | most specific; normalize case |

**Deterministic merge key:** `(registrable_domain, normalized_first, normalized_last)`; fallback `(registrable_domain, email_local, email_domain)`. Log every conflict resolution to an audit trail (Apollo surfaces "data sources attempted, statuses, messages" per record — mirror that).

### 6.5 LeadForge dedupe (gap)
Dedupes contacts only on `Contact.email == email` (exact string) + `business_id`. No domain-level entity resolution, no fuzzy name match, no accent folding, no E.164 (phones stored as raw regex captures), no conflict-resolution rules, no merge audit.

---
---


## 7. Concrete Pricing 2025/2026 (USD)

### 7.1 Email finders / enrichment

| Vendor | Model | Price | Credits / unit |
|--------|-------|-------|----------------|
| **Apollo** | per person | **1–9 credits/person** | 1 credit (demo or email) + 8 if mobile returned; org enrich 1 credit; job posts 1 credit/page |
| **FullEnrich** | pay-on-hit | **$0.055/credit** (Pro $55/mo = 1,000 credits) | work email **1**, mobile **10**, personal email **3**, reverse-email **1**, search **0.25** |
| **Hunter** | monthly credits | Free 50/mo; **Starter $49/mo** (2,000); **Growth $149/mo** (10,000) | email found **1**, verified **0.5** |
| **Dropcontact** | pay-on-success | (subscription/credit) | **1 credit only if verified email returned**; verify-only 1 credit |

### 7.2 Verifiers

| Vendor | Price | Unit |
|--------|-------|------|
| **NeverBounce** | **$8 / 1,000 credits** PAYG; Growth $49/mo (up to 10,000); Enterprise custom (250k+/mo) | 1 credit/verify; duplicates free; credits expire 12mo |
| **ZeroBounce** | **$39 / 2,000** PAYG (min); **ZeroBounce ONE $99/mo** (save up to 18%) | 1 credit/verify; **Email Finder 20 credits/successful query**; `unknown` free |
| **Clearout** | prepaid; 100 free to start | **1 verification = 1 credit**; credits never expire on subscription; bulk dedupe = free |
| **MillionVerifier** | plans **from $39**; 100 free credits | per verification; 99%+ accuracy |
| **Reoon** | up to 600 credits/mo free tier; paid credit packs | QUICK vs POWER mode |
| **Emailable** | free tier + paid; retries on by default | per verify |

**Cost-per-verification ballpark:** NeverBounce ≈ **$0.008/verify** at PAYG; ZeroBounce ≈ **$0.0195/verify** at the $39/2k entry (drops on subscription); Clearout/MillionVerifier comparable sub-$0.01–$0.02 at volume. Email-finder hits are ~10–20× a verification (ZeroBounce Finder = 20 credits ≈ 20 verifications).

---
---


## 8. Gap Analysis — What LeadForge Is Missing / Doing Wrong

Ordered by severity. Each maps to a concrete fix. File refs: `email_finder.py`, `smtp_verifier.py`.

### 🔴 P0 — Correctness bugs (produce wrong data)

**G1. `verify_email_smtp` returns `True` on every SMTP failure.**
`smtp_verifier.py:84-89`: on `socket.timeout/error/ConnectError/Disconnected` and on any bare `Exception`, returns `True, "valid_mx"`. Blocked port-25 (very common on cloud/ISPs), greylisting, and anti-spam gateways all become "valid." **Fix:** return `(False, "unknown")` / `(False, "blocked")` / `(False, "greylisted")`; never default to valid. Route 4xx to a retry queue. Highest-impact change.

**G2. Single-probe catch-all detection.** `check_catch_all_domain` sends one random RCPT. Cannot separate catch-all from blocked/greylisted/anti-spam. **Fix:** implement the multi-probe algorithm (§4.2): reachability control + 3+ random probes + known-invalid control; classify `CATCH_ALL / NOT_CATCH_ALL / GREYLISTED_RETRY / BLOCKED / ANTISPAM_GATEWAY`.

**G3. Permutations built from the *company name*, not a person.** `generate_email_permutations(business.name, domain)` turns "Acme Realty Group" into `acme.realty@` etc. **Fix:** generate person patterns only when a real person name exists; learn the domain pattern from seed emails (§1.2); ignore generic aliases when learning.

**G4. No pattern learning / no per-domain confidence.** Fixed 6-pattern order + 7 generic aliases; misses `{f}.{last}`, `{first}-{last}`, `{last}.{first}`, `{first}{l}`; no seed-set inference. **Fix:** implement `infer_pattern()` with dominance+prior confidence blend; rank candidates, verify each, stop at first deliverable.

### 🟠 P1 — Missing capabilities vs. the market

**G5. No verification status enum.** Only `{valid, mailbox_not_found, valid_mx, invalid_domain, no_mx_records, unresolvable_domain, invalid_syntax, disposable_domain, empty, server_response_<code>}`. Missing: `catch_all, accept_all, greylisted, role_account, free_email, spamtrap, abuse, do_not_mail, blocked, timeout, possible_typo, gibberish, mailbox_full, antispam_system`. **Fix:** adopt the §3.2 normalized enum; store `status` + `sub_status` + `confidence` + `smtp_detail`.

**G6. No role-account detection.** `contact@/info@/sales@/support@/hello@/admin@/office@` are created as *verified contacts*. Inflates lead counts, raises complaint rates. **Fix:** role-list detection (§3.4); flag them; never treat as a person; exclude from "person found" metrics.

**G7. No free-provider detection.** Only 12 disposable domains; no webmail/free detection (Gmail/Yahoo/Outlook/iCloud/Proton…). Free providers on a B2B lead are a quality signal and SMTP-probing them is unreliable. **Fix:** free-provider + disposable lists (§3.5/§3.6), from a maintained feed.

**G8. No MX preference sorting / A-record fallback ordering.** `records[0]` may be a backup MX; A-record fallback unordered. **Fix:** sort MX by `preference`; try in order; A-record only if no MX; respect `unroutable_ip`.

**G9. No external provider waterfall.** Everything is scraped/guessed locally; no Apollo/Hunter/Dropcontact/Prospeo/FullEnrich/Lusha fallback → find-rates will trail the ~80–93% market benchmark. **Fix:** add an ordered provider waterfall with pay-on-hit, webhook/poll for async phone/waterfall, and the §2.4 data model.

**G10. No firmographic signals.** No technographics, funding, headcount growth, revenue, NAICS/SIC, job postings, LinkedIn people data. **Fix:** add Apollo Org Enrichment / Clay signals (§5); map to headcount bands; derive growth/intent.

**G11. Synchronous SMTP in the async path.** `verify_email_smtp` (blocking `smtplib`, 3–8s) is called inside `async def enrich_business_by_id` and inside a per-candidate loop. Blocks the event loop and can't scale. Celery+Redis are already in `requirements.txt` but unused here. **Fix:** run verification in a Celery task / `run_in_executor` worker pool with a connection pool + per-domain rate limiting; make enrichment webhook/async.

---
---


### 🟡 P2 — Robustness / hygiene

**G12. No dedupe/entity resolution.** Exact `email==` only. No domain normalization (Public Suffix List), no fuzzy name matching (Jaro-Winkler), no accent folding, no E.164 phone, no conflict-resolution/merge audit. **Fix:** §6.

**G13. No confidence score or source attribution.** Stores `is_verified: bool` only. Can't rank leads, explain a result, or re-verify cheaply. **Fix:** persist `confidence`, `source`/`sources`, `pattern`, `verified_at`, `smtp_detail`.

**G14. Weak disposable list (12) + no gibberish/typo detection.** **Fix:** maintained feed; add `did_you_mean` (gmial→gmail) and gibberish (`e65rc109q@`) detection.

**G15. No greylist/retry handling.** 4xx treated as generic `server_response_<code>` → `True`. **Fix:** detect 4xx → `greylisted`, enqueue for re-verification after delay (ZeroBounce Greylist API pattern).

**G16. `EXCLUDED_EMAIL_DOMAINS` includes `google.com`** — wrongly drops legitimate `@google.com` corp emails; intent was to drop `schema.org`/example/wix noise, not all Google. Scope exclusions to placeholder/example/CDN hosts, not real corporate domains.

**G17. No rate limiting / port-25 egress awareness.** Repeated SMTP from one IP → blocklisting. **Fix:** per-MX connection reuse, backoff, distributed sender IPs (what paid verifiers operate: "3 proprietary data centers," distributed IP pools).

### ✅ What LeadForge does reasonably well (keep)
Cloudflare `data-cfemail` XOR decode; `[at]/[dot]` deobfuscation; `mailto:/tel:/wa.me` parsing; social-profile discovery; contact-page crawling with priority queue; LinkedIn/FB/IG/X/YT discovery. These are solid *seed* collectors — they should become the **seed-email harvester** for pattern inference (§1.2) rather than a permutation guesser.

---
---


## 9. Recommended Target Architecture (concrete)

```
[Seed harvest]  crawl site -> decode cfemail/deobfuscate -> collect KNOWN emails per domain
      |  (these become the seed set for pattern inference)
      v
[Pattern engine]  infer_pattern(domain, seed_set) -> pattern + confidence  (§1.2)
      |  if no seed -> global prior ranking (§1.1)
      v
[External waterfall]  ordered providers (Apollo/Hunter/Dropcontact/Prospeo/FullEnrich/Lusha)
      |  stop-on-first-deliverable; async webhook/poll for phone; pay-on-hit (§2)
      v
[Verify]  status enum (§3) via async worker pool (Celery), multi-probe catch-all (§4)
      |  retry queue for greylist; NEVER default to valid
      v
[Resolve]  domain-normalize + fuzzy-name + E.164 + conflict merge (§6)
      v
[Signals]  firmographics/technographics/funding/headcount-growth/job-posts (§5)
      v
[Persist]  email + confidence + status + sub_status + pattern + source + sources
           + verified_at + smtp_detail
```

**Verifier return contract (replace current `Tuple[bool,str]`):**

```python
class EmailStatus(str, Enum):
    VALID, INVALID, CATCH_ALL, CATCH_ALL_UNKNOWN, DISPOSABLE, ROLE_ACCOUNT,
    FREE_EMAIL, GREYLISTED, UNKNOWN, BLOCKED, SYNTAX_ERROR, DOMAIN_ERROR,
    NO_MX, SMTP_ERROR, TIMEOUT, ACCEPT_ALL, SPAMTRAP, ABUSE, DO_NOT_MAIL,
    MAILBOX_FULL, GIBBERISH, POSSIBLE_TYPO

def verify(email) -> VerificationResult:   # never returns bare True on failure
    ...
```

**Sender treatment matrix:** send = `VALID` (and `ACCEPT_ALL` only if corroborated); don't send = `INVALID, DISPOSABLE, SPAMTRAP, ABUSE, DO_NOT_MAIL, SYNTAX_ERROR, DOMAIN_ERROR, NO_MX`; risky/segment = `CATCH_ALL, CATCH_ALL_UNKNOWN, ROLE_ACCOUNT`; retry = `GREYLISTED, TIMEOUT, BLOCKED, SMTP_ERROR, UNKNOWN` (do **not** count as valid).

---
---


## Appendix A — Source map (captured directly)
- **Hunter API v2 docs:** Domain Search response (`pattern:"{first}"`, per-email `confidence:92`, `sources[]`, `accept_all`, `type:personal/generic`); Email Verifier `status` enum + `regexp/gibberish/disposable/webmail/mx_records/smtp_server/smtp_check/accept_all/block` booleans; `score` (50 for webmail/disposable); pricing (Free/Starter $49/Growth $149).
- **FullEnrich docs (`llms.txt` + raw `.md`):** email-status (DELIVERABLE 2% bounce, HIGH_PROBABILITY 9% bounce, CATCH_ALL, INVALID); credits (1/10/3/1/0.25); data dictionary (contact_info schema, phone fields, firmographics, headcount bands); OpenAPI v2 enrich response; "20+ providers"; 3-month data retention; dedupe rules.
- **Apollo docs (`llms.txt` + `.md`):** People Enrichment (1–9 credits, `match_confidence high/medium/low/none`, `run_waterfall_email/phone`, webhook async with per-source statuses); Org Enrichment (`estimated_num_employees`, `*_headcount_*_growth`, `annual_revenue`, `total_funding`, `latest_funding_*`, `technology_names`, `industry_tag_*`, `owned_by_*`, `suborganizations`); Job Postings (1 credit/page, 10k/page); `email_status` (`verified`/`likely_to_engage`), `email_true_status`, `extrapolated_email_confidence`.
- **ZeroBounce docs:** full `status` (valid/invalid/catch-all/abuse/spamtrap/do_not_mail/unknown) + 27 `sub_status`; pricing ($39/2k, ONE $99/mo, Finder 20 credits, unknown free, <1% catch-all, 99.6% accuracy).
- **NeverBounce docs (`llms.txt` + `.md`):** result codes (valid/invalid/disposable/catchall/unknown), flags (`has_dns`…), timeout→unknown; pricing $8/1k, $49/mo.
- **Emailable docs:** `state` (deliverable/undeliverable/risky/unknown) + `reason` enum + flags + retries.
- **Reoon docs:** QUICK vs POWER mode; full boolean field set; status enum.
- **Dropcontact docs:** local-part qualification (nominative/catch_all/generic/random/invalid) + domain (pro/perso/invalid); pay-on-success credits.
- **Clearout:** 99.73% accuracy, "Safe-to-Send", Deep Verify catch-all, 1 credit/verify, 20+ checks.
- **MillionVerifier:** from $39, ok/catch_all/unknown/disposable/role, Good/Risky/Bad buckets.
- **LeadForge code:** `email_finder.py` (`generate_email_permutations`, `check_catch_all_domain` call, permutation loop, `TITLE_PATTERN`, `verify_email_smtp` calls), `smtp_verifier.py` (full verifier), `requirements.txt`, `.env.example`.

*Percentages in §1.1 and thresholds in §6 are industry-standard engineering values (🔶), not vendor-published figures; all vendor-specific numbers above are ✅ from docs.*

