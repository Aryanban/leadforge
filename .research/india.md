# India Lead-Gen Research — LeadForge

_Research date: 2026-10-09. Anti-bot / phone-wall behaviour verified live from sandbox via `curl` (desktop-Chrome UA, no proxy). Snapshots drift — re-test selectors before relying on them._

**Gap-analysis context (current LeadForge India state):**
- Sources: `GoogleMapsSource` (Playwright), `JustDialSource`, `IndiaMARTSource`, `SulekhaSource`.
- `fetch_html()` = plain `httpx.GET`, desktop Chrome UA, **15s timeout, no retry, no proxy rotation**.
- Sources awaited **sequentially** in `router.discover()` — no concurrency.
- `http_utils.extract_city()` = hardcoded 30-entry `INDIAN_CITIES` tuple, else slugifies whole area.
- Dedupe normalises `+91`/`0` → 10 digits. WhatsApp only builds `https://wa.me/<digits>`; **no on-WhatsApp check**.
- Outreach = SMTP cold email only. **No WhatsApp/SMS channel.**
- **BUG 1:** campaign sender hardcodes `city="Delhi NCR"` + default category `"Real Estate"` in template data.
- **BUG 2:** no DND / consent scrubbing anywhere (TRAI + DPDP exposure, §4).

---

## 1. India lead sources — table + tiers

Legend — **Tier 1** reliable/cheap/high-value (build first); **Tier 2** usable with work; **Tier 3** fragile/login-walled/legal-risk.

| Source | Public URL pattern | Login? | Anti-bot (verified) | Phone visibility | Data richness | Tier |
|---|---|---|---|---|---|---|
| **JustDial** | `justdial.com/<City>/<Category>-nct-<id>` e.g. `/Delhi/Dentists` | No | **Strong** — plain curl UA-Chrome → **200 but only 14 bytes** (block stub; needs Playwright + proxy). Phones glyph-encoded (`.jc<v>` spans). | Present but glyph-encoded; decode via `GLYPH_TO_DIGIT {jcv:0…jc6:9}`. | High (addr, rating, reviews, area) | **1** (Playwright+proxy) |
| **IndiaMART** | `dir.indiamart.com/search.mp?ss=<kw>` / `impcat/<cat>.html` | No | **Medium** — 200/~30 KB but listing JS-rendered; cards often absent in raw GET. Selectors: `div.ls-card`, `div.r-cl`, `.card-block`, `.product-tpl`. | Behind **"View Mobile Number"** wall: `.pns`/`.livemsg`, JS-revealed. | High (products, GST, member-since) | **2** |
| **Sulekha** | `sulekha.com/<category>/<city>` e.g. `/dentists/delhi` | No | **Weak-Med** — plain curl → **200/523 KB** real HTML (works with current httpx). | Behind `.livemsg` "show number" wall (JS). | High (local services, ratings) | **1** |
| **TradeIndia** | `tradeindia.com/…`, `/seller-…` | No | **Low-Med** — homepage 200/772 KB; listing pages server-render. | Often visible on seller profile; some gated. | High (products, GSTIN) | **2** |
| **ExportersIndia** | `exportersindia.com/members/…` | No | **Low** — `/search.htm`→404 (needs right path); member pages server-render. | Usually visible on member page. | Med-High | **2** |
| **TradeBoss** | `tradeboss.com/default.cgi/action/viewcompanies/…` | No | **Low** — homepage tiny (883 B). Company pages plain HTML. | Visible on company pages. | Medium | **2/3** |
| **IndianYellowPages** | `indianyellowpages.com/company/<slug>` | No | **Low** — 200/93 KB. | Usually visible. | Medium | **3** |
| **AskLaila** | `asklaila.com/search/…/<city>/<kw>` | No | **Low** — 200/19 KB (sparse/JS). | Often present. | Low-Med | **3** |
| **ZaubaCorp** | `zaubacorp.com/company/<NAME>/<CIN>` | No | **Strong** — plain curl → **403** (Cloudflare). Needs proxy/Playwright. | N/A (registry). | Very high (directors, CIN, ROC) — legal entity, not SMB phones | **3** (enrich) |
| **Tofler** | `tofler.in/<slug>/company/<name>/<CIN>` | No | **Low-Med** — 200/142 KB plain. | N/A. | High (financials, directors) — **paid data behind paywall** | **3** (enrich) |
| **Instafinancials** | `instafinancials.com/company/<slug>/<CIN>` | No | **Low** — server-renders. | N/A. | High (registry financials) | **3** (enrich) |
| **Google Maps** | `google.com/maps/search/<kw>+in+<city>` (embed `/maps?q=&output=embed`) | No | **High** — JS + rate-limits; Playwright needed; needs **residential proxies** fast. | Phone often in listing; rich reviews/rating. | Very high | **1** (needs proxy) |
| **Bing Places/Maps** | `bing.com/maps`, `bing.com/search?q=` local pack | No | **Low-Med** — far softer than Google; cheap backfill. | Often in local pack + business site. | High | **1** (cheap backfill) |
| **DuckDuckGo html** | `html.duckduckgo.com/html/?q=<kw>` (`/lite/` alt) | No | **Medium** — returns **HTTP 202** challenge from datacenter IPs; may pass residential proxy. | Indirect (find business sites → scrape contact). | Indirect (discovery) | **2** (proxy-gated) |
| **OSM Overpass** | `overpass-api.de/api/interpreter?data=<QL>` | No | **None (API)** — **free/legal, ODbL**. NOTE: from this datacenter IP overpass-api.de→**406**, mirrors→**500**; works from normal IPs/self-host. Slot rate-limit, not bot-wall. | Phone only if tagged `phone=`/`contact:phone=` (~20–40% coverage). | Medium (name, cat, addr, some web/phone) | **1** (free seed) |
| **LinkedIn** `/company/` | `linkedin.com/company/<slug>` | Partial — full needs login; logged-out curl 200/429 KB = auth-wall shell. | Very high (DataDome). | No phones; size/industry/about. | Medium (firmographics) | **3** (enrich) |
| **Facebook Pages** | `facebook.com/<page>` | Partial — content login-walled. | High. | Sometimes phone/hours in About (login-gated). | Low-Med | **3** |
| **Wellfound / Inc42** | `wellfound.com/company/<slug>` / `inc42.com/company/<slug>` | Mostly no | Low-Med. | Rarely phones. | Startup firmographics, funding | **3** (startup only) |

### Overpass QL — worked examples (copy/paste)
Free, no key, ODbL ("© OpenStreetMap contributors"). `area[name="…"]` scopes to city; `nwr` = nodes+ways+relations so building/polygon shops are caught, not just pins.

**All dentists in Delhi:**
```overpass
[out:json][timeout:60];
area["name"="Delhi"]["boundary"="administrative"]->.a;
nwr["amenity"="dentist"](area.a);
out center tags;
```
Broader variant (clinics/doctors too): `nwr["amenity"~"dentist|doctors|clinic"](area.a);`

**All shops in Mumbai:**
```overpass
[out:json][timeout:90];
area["name"="Mumbai"]["boundary"="administrative"]->.a;
nwr["shop"](area.a);
out center tags;
```
Notes: `out center tags;` = lat/lon centroid + all tags in one shot. Parse `tags["name"]`, `tags["phone"]`/`tags["contact:phone"]`, `tags["addr:city"]`, `tags["website"]`, `tags["email"]`. India phone tags vary (`+91…`, `091-…`, `0…`) → normalise via §3 E.164 fn. One query at a time, cache, self-host for volume. Treat Overpass as **free seed + geo layer**, not the phone source (phone coverage is the weak point). Mirrors: `overpass.kumi.systems`, `overpass.private.coffee`, `overpass.nchc.org.tw`.

---

## 2. Indian email reality + verifier strategy

**Provider landscape for Indian SMBs:**
- **Gmail / Google Workspace dominates.** Most Indian small businesses & sole traders use a personal `@gmail.com` (and `@googlemail.com`) rather than a domain mailbox. Treat `gmail.com`/`googlemail.com` as first-class SMB signals, not disqualifiers.
- **`.in` domains** on shared/reseller hosting common for slightly larger SMBs: GoDaddy / BigRock / Hostinger / ResellerClub / Bluehost / HostGator India resellers.
- **Legacy webmail:** `rediffmail.com` (older/professional cohort), `yahoo.in`/`yahoo.co.in` (shrinking), `outlook.com`/`hotmail.com`.
- **Zoho Mail** — very popular with Indian SMBs wanting cheap domain email (Indian-founded); strong adoption.
- **Role accounts** at small firms: `info@`, `contact@`, `enquiry@`/`inquiries@`, `sales@`, `admin@`, `support@` — often the *only* address on a website. Deliverability to role accounts is lower (spam-trap/honeypot risk); prefer a named human where inferable, but role accounts are the realistic SMB reality.

### MX hostname → RCPT-probe viability table
**Critical fact:** Gmail/Google Workspace (`aspmx*.google.com`) and Zoho (`mx.zoho.*`) **do NOT support port-25 RCPT-TO probing.** They accept-all at SMTP then reject post-DATA (or blocklist probing IPs) — so a `RCPT TO:` verifier returns **false "valid"** for Google/Zoho, and repeated probing gets your sending IP greylisted/blocked.

| Provider (India-common) | MX hostname pattern | RCPT probe (port 25) works? |
|---|---|---|
| **Google / Workspace / gmail.com** | `aspmx.l.google.com`, `alt1.aspmx.l.google.com`, … | **NO** — accept-all + post-DATA reject. Do not probe. |
| **Zoho Mail** (`zoho.in`/`.com`) | `mx.zoho.in`, `mx2.zoho.in`, `mx.zoho.com` | **NO** — blocks/accept-all. Do not probe. |
| **GoDaddy** | `mailstore1.*.secureserver.net`, `smtp.secureserver.net` | Sometimes (catch-all varies) — unreliable |
| **BigRock / ResellerClub / LogicBoxes** | `mx*.bigrock.in`, `mail.<domain>` shared IPs | Sometimes — often accept-all |
| **Hostinger** | `mx1.hostinger.in`, `mx2.hostinger.in` | Sometimes |
| **HostGator / Bluehost (EIG)** | `localhost`/`mail.<domain>`, shared IPs | Sometimes — accept-all common |
| **Microsoft 365 / Outlook** | `<tenant>-<region>.mail.protection.outlook.com` | Partially (edge varies) |
| **Rediff / Yahoo India** | `mx*.rediffmailpro.com`, `mta5.am0.yahoodns.net` | Mostly NO / accept-all |

**What the LeadForge verifier should fall back to (no reliable SMTP):**
1. **Never RCPT-probe gmail/googlemail/zoho/outlook** — mark "unverifiable-by-SMTP, assume deliverable if MX sane."
2. **Tiered heuristic scoring** instead: syntax regex → disposable/free-domain list → MX presence + MX-provider classification → **catch-all detection** (single random RCPT, only case where SMTP is safe) → role-account flag → domain web-reputation (has website, appears in directories).
3. Optional paid/API (ZeroBounce, NeverBounce, Kickbox, Bouncer) — but these themselves can't verify Gmail inboxes; they mostly score them. **Don't over-invest in email verification in India — the channel underperforms anyway (§5).**
4. Stance for LeadForge: **email = secondary channel.** Verify syntax + MX + free/role classification; spend engineering budget on WhatsApp + phone (§3, §5).

---

## 3. Indian phone & WhatsApp

### Formats
- **10-digit mobile:** `^[6-9]\d{9}$` (start 6/7/8/9, 10 digits, no leading 0). National `0XXXXXXXXXX`; international `+91XXXXXXXXXX`.
- **Landline (STD):** 10–11 digits incl. leading trunk `0` + STD area code (2–4 digits) + subscriber. E.g. Delhi `011-XXXXXXXX`, Mumbai `022-XXXXXXXX`. STD→city: Delhi 11, Mumbai 22, Bengaluru 80, Chennai 44, Kolkata 33, Hyderabad 40, Pune 20, Ahmedabad 79.
- **Discriminate mobile vs landline:** strip non-digits; strip leading `0` or `+91`; if 10 digits start `6-9` → **mobile**; if starts `1-5` or is 11 w/ leading `0` and area code in STD table → **landline**. Toll-free `1800-…` → neither (drop).

### +91 E.164 normalisation — spec (implement in `http_utils`/dedupe)
```
normalise_in_phone(raw) -> Optional[str]   # returns "+91XXXXXXXXXX" or None
  1. s = raw.replace(non-digits, "")                 # strip spaces,-,(),dots
  2. if s.startswith("91") and len(s)==12:  s = s[2:]    # +91 / 91 prefix
     elif s.startswith("0") and len(s)==11:  s = s[1:]   # 0 + 10-digit
     elif s.startswith("0091"):               s = s[4:]
  3. if len(s)==10 and s[0] in "6789": return "+91"+s    # mobile
     if len(s) in (10,11) and s[0] in "12345": return landline marker (keep, never WA)
  4. else return None
```
Dedupe key = 10 local digits (matches LeadForge's current `+91`/`0`→10 rule). Flag `is_mobile` so outreach only WhatsApps/SMSs real mobiles.

### WhatsApp behaviour
- **`wa.me` link:** `https://wa.me/<E164-no-plus>` (e.g. `wa.me/919812345678`) opens chat on mobile; desktop redirects to `web.whatsapp.com`/`api.whatsapp.com` send. It does **not** tell you if the number is registered before send. LeadForge already builds these — fine, but add `?text=<urlencoded>` for a pre-filled opener.
- **Can you check if a number is on WhatsApp without the Business API? → NO, not reliably.** No free endpoint. Parsing `wa.me`/`api.whatsapp.com/send` redirects is blocked/ambiguous and violates ToS. Only supported way = **WhatsApp Business Cloud API** (`POST /<phone-number-id>/contacts` returns a `wa_id` if registered), requires a WABA + approved template. **LeadForge must not claim an on-WhatsApp check.** If WhatsApp matters (it does, §5), integrate the Cloud API contact-check + template messages.

### TRAI DND / NCPR (cold marketing — SMS & calls)
- **NCPR (National Customer Preference Register):** subscribers register Fully/Partially DND via 1909/carrier. **Marketing/telemarketing to DND numbers prohibited**; only service/transactional exempt.
- **TCCCPR 2018 (+ 2023–2025 amendments):** telemarketing requires **entity registration**, registered **headers**, and **consent** (digital/recorded) templates. Unregistered/blank-header promo traffic heavily filtered.
- **DLT (Distributed Ledger Technology):** all commercial SMS/calls via a registered DLT entity with pre-approved **templates & headers**; **DND scrubbing mandatory**. Bulk promo SMS without DLT = headers blocked + penalties.
- **Cold calling:** honour DND, 9am–9pm windows, registered telemarketer IDs. Practically, **do not run cold-call/SMS blasts without a compliant Indian aggregator** (MSG91, Gupshup, Kaleyra, Exotel, Textlocal) that handles DLT + DND scrubbing.

### WhatsApp Business Cloud API pricing (2025, indicative)
Meta moved to **per-message pricing**. Rough India bands (verify at `developers.facebook.com/docs/whatsapp/pricing`):
- **Marketing:** ~₹0.78–0.88 / msg (category-specific).
- **Utility:** ~₹0.115–0.125 / msg.
- **Authentication (OTP):** ~₹0.125–0.145 / msg.
- **Service** (inside customer-initiated 24h window): **free** (incl. first ~1,000 replies/window).
BSPs (Gupshup/Interakt/AiSensy) add a small platform fee but are easier to onboard than raw Cloud API.

---

## 4. India compliance — DPDP Act 2023 + TRAI

### DPDP Act 2023 (Digital Personal Data Protection Act)
- Applies to processing **digital personal data** in India (and offshore processing of Indian data); enforced via DPDP Rules (phased 2024–2025+).
- Requires **Notice** (clear + itemised data/purposes) and **consent** (free, specific, informed, unambiguous; or "legitimate uses"), **withdrawable** as easily as given.
- **Data principal rights:** access, correction, **erasure**, grievance redressal, **nomination**.
- **Obligations:** purpose limitation, data minimisation, accuracy, security safeguards (incl. breach notification), **erase when purpose met/consent withdrawn**, **DPO/grievance officer** for significant fiduciaries, **children's (<18) restrictions**.
- **Penalties:** up to **₹250 crore** per instance for failure of security safeguards (breach); other tiers ₹50 cr (notice), ₹200 cr (children's data), etc.
- **Practical:** a lead DB of business contacts = personal data of contact persons → you are a **Data Fiduciary**: need notice, lawful basis/consent, retention/erasure, security.

### TRAI commercial communication (TCCCPR 2018 + 2024/2025 amendments)
- **Registration** of sender/telemarketer entity on DLT; **headers + content templates** pre-registered/approved.
- **Consent** (explicit, recorded/digital) before promo SMS/calls; **DND/NCPR scrubbing** mandatory.
- 2024–2025 amendments tightened UCC rules, header classification, and penalties; blank-clip/spam filtering penalties hit the sender chain.
- **Penalties:** per-violation escalating (₹10 lakh+ slabs for UCC non-compliance) + blacklisting of headers/entities.

### 8-point compliance checklist for a cold-outreach tool (LeadForge)
1. **Lawful basis + notice:** collect only publicly-listed business contacts; show a privacy notice; rely on legitimate-interest/consent and record source URL + date per record.
2. **Consent capture & withdrawal:** one-click unsubscribe in every email; honour "stop" in WhatsApp/SMS immediately; log it.
3. **DND/NCPR scrubbing** before any SMS or cold call (via compliant aggregator); never promo-message DND numbers.
4. **DLT registration** (headers + templates) if you send SMS/calls in India — via MSG91/Gupshup/Exotel/Textlocal.
5. **Data minimisation & retention:** store only needed fields; auto-purge leads older than N months; purge on opt-out.
6. **Security:** encrypt PII at rest + in transit, access controls, audit logs, breach-response runbook (₹250 cr exposure).
7. **Data principal rights workflow:** process access/correction/erasure/grievance requests; name a grievance officer (DPDP).
8. **Sender identity:** valid physical address + working unsubscribe; honest "from"/header identity (TRAI). Keep proof of legitimate source per scraped record.

---

## 5. What actually converts in India

### Channel benchmarks (WhatsApp ≫ cold email)
- Indian BSPs (AiSensy, Interakt, Gupshup) commonly cite **WhatsApp open ~90–98%, response ~15–40%** vs **cold-email open ~20–40%, reply ~1–5%** for Indian B2B. Email deliverability to Gmail-dominated SMB inboxes (Promotions tab, aggressive spam filtering) is the bottleneck. **Treat WhatsApp as primary, email as secondary/backup.**
- **Calls** convert well for high-ticket local services but are DND/consent-constrained (§4) — use as manual follow-up, not automated blast.
- Caveat: numbers are vendor-reported; run your own A/B. Directionally **WhatsApp > call > email** for Indian local-business outreach.

### Language guidance (Hinglish + regional)
Default to **Hinglish** (Roman-script Hindi + English) — friendly/native, universally readable. Keep Roman script (WhatsApp-friendly). Match lead's likely primary language by city; always keep Hinglish fallback.
- **Hindi (Hinglish):** "Namaste! Aapke {business} ke liye ek chhota sawaal — abhi {service} se naye customers aa rahe hain?" / "Sir, aapki website dekhi — ek idea jo {city} mein leads 2x kar sakta hai. 2 min?"
- **Marathi (Mumbai/Pune):** "नमस्कार! तुमच्या {व्यवसाय} साठी एक छोटा प्रश्न — सध्या नवे ग्राहक कसे येतात?" / "Sir, tumchi website pahili — ek idea jo Mumbai madhye leads double karu shakte. 2 min?"
- **Tamil (Chennai):** "வணக்கம்! உங்கள் {தொழில்}க்கு ஒரு சிறிய கேள்வி — இப்போது புதிய வாடிக்கையாளர்கள் எப்படி வருகிறார்கள்?" / "Sir, ungal website paithen — oru idea, Chennai-la leads irattai aaga vendum. 2 min?"
- **Telugu (Hyderabad):** "నమస్కారం! మీ {వ్యాపారం} కోసం ఒక చిన్న ప్రశ్న — ఇప్పుడు కొత్త కస్టమర్లు ఎలా వస్తున్నారు?" / "Sir, mee website chusanu — oka idea, Hyderabad-lo leads double avvali. 2 min?"
- **Bengali (Kolkata):** "নমস্কার! আপনার {ব্যবসা}-এর জন্য একটা ছোট প্রশ্ন — এখন নতুন কাস্টমার আসছে কীভাবে?" / "Sir, apnar website dekhlam — ekta idea, Kolkata-te leads double hote pare. 2 min?"

### Price sensitivity & positioning
Highly price-sensitive; **₹/month + free trial** lands far better than USD or per-seat enterprise pricing. ROI framing ("₹X more revenue") beats feature lists. Cash-conscious buyers want **UPI/Razorpay** and low commitment.

### Send windows (IST)
Best **Tue–Thu, ~10:30am–1:00pm and 4:00–6:30pm IST**. Avoid Monday AM (backlog) and Friday PM. For WhatsApp, late morning + early evening get fastest replies; avoid very early/late night.

### Seasonality
- **Diwali (Oct/Nov):** peak retail/restaurant spend — start campaigns 2–3 weeks *before* (noise is high).
- **Financial-year end (Jan–Mar):** B2B budgets clear; **March = strong B2B buying**.
- **GST deadlines:** GSTR-1 (~11th), GSTR-3B (~20th) monthly → CA/accounting niches spike those weeks.
- **Monsoon (Jun–Sep):** lower engagement; real estate picks up around festivals.

### Per-niche angle
- **Dentists/clinics:** no-shows, Google reviews, new-patient acquisition → "more booked appointments, fewer no-shows."
- **Real estate:** lead quality, site-visit booking, WhatsApp follow-up → "more qualified site visits." (This is LeadForge's hardcoded default — fix BUG 1 so other niches work.)
- **Coaching institutes:** admissions season (post-results ~Apr–Jun + Sep), demo-class bookings → "more admission enquiries before intake closes."
- **Manufacturers/B2B (IndiaMART/TradeIndia sellers):** inbound→order conversion, export enquiries → "convert more directory enquiries into orders."
- **Restaurants:** delivery vs dine-in mix, repeat customers, WhatsApp reordering, reviews → "bring back regulars, fill weekday tables."

---

## 6. Recommended India source priority + phased plan

### Source priority order (for the LeadForge source registry)
1. **OSM Overpass** — free, legal (ODbL), no anti-bot → **bulk seed + geo backbone**. Verify QL from a non-datacenter IP or self-host. (Tier 1)
2. **Google Maps (Playwright)** — richest phones/ratings; **add rotating residential proxies** (current no-proxy setup rate-limits fast). (Tier 1)
3. **Sulekha** — already works via plain `httpx` (verified 200/523 KB). Lowest-friction India directory. (Tier 1)
4. **Bing Maps/Places** — cheap, low-anti-bot backfill for phones Maps misses. (Tier 1 backfill)
5. **JustDial** — high value but needs Playwright + proxy + glyph-phone decode (partly built). (Tier 1-with-proxy)
6. **IndiaMART / TradeIndia / ExportersIndia** — B2B/export verticals; phone behind "View Mobile Number" walls. (Tier 2)
7. **ZaubaCorp / Tofler / Instafinancials** — **enrichment only** (CIN, directors, financials), never a phone source. (Tier 3 enrich)
8. **LinkedIn / Facebook / Wellfound / Inc42** — startup/tech firmographics only, login-walled; skip for local-SMB phone gen. (Tier 3)
9. **DuckDuckGo html** — discovery engine (datacenter-IP 202; needs proxy); find business websites, then scrape site contact page for phones. (Tier 2, proxy-gated)

### Phased implementation plan
- **Phase 1 — Stabilise & fix (weeks 1–2):**
  - Fix **BUG 1** (hardcoded `city="Delhi NCR"`/category `"Real Estate"`) → thread real campaign city/category through templates. Fix **BUG 2** (add DND/consent scrubbing hooks).
  - Harden `fetch_html()`: **retries w/ backoff**, jittered desktop+mobile UAs, **proxy rotation** (mandatory for Google/JustDial); parameterise timeout.
  - Make `router.discover()` **concurrent** (`asyncio.gather` + per-source timeouts) instead of sequential.
  - Add **E.164 phone normaliser + mobile-vs-landline discriminator** (§3) into `http_utils`/dedupe; replace 30-city hardcode with STD-code→city map + Nominatim/OSM reverse lookup.
  - Ship **Overpass source** (free seed) with the QL above.
- **Phase 2 — Coverage + primary channel (weeks 3–5):**
  - Add **Bing Maps** source (cheap backfill) + complete **JustDial glyph-decode** under proxy.
  - Integrate **WhatsApp Business Cloud API**: on-WhatsApp contact check (the *only* reliable check), template messages, per-message costing (§3), reply webhooks. This is the **primary India channel**.
  - Add **Hinglish + regional templates** (§5) and per-niche angles; IST send-window scheduling.
  - Add **email verifier fallback logic** (§2): no RCPT-probe for Google/Zoho/Outlook; tiered heuristic scoring.
- **Phase 3 — Enrichment, compliance, scale (weeks 6+):**
  - Add **B2B sources** (IndiaMART/TradeIndia/ExportersIndia) + **registry enrichment** (ZaubaCorp/Tofler) for trust/firmographics.
  - Build the **8-point compliance workflow** (§4): consent log, one-click unsubscribe/"stop", retention purge, data-principal-rights endpoints, grievance officer, security/audit.
  - Route any SMS/cold-call through a **DLT-registered aggregator** (MSG91/Gupshup/Exotel) with DND scrubbing.
  - Add caching, per-source rate limits, source-health monitoring, and a source-registry tier config so flaky sources degrade gracefully.

---

## Quick reference — key files/points to fix in LeadForge
- `backend/.../http_utils.py` → `extract_city()`: replace 30-city hardcode with STD map + OSM lookup; add `normalise_in_phone()` + `is_mobile()`.
- `backend/.../router.py` → `discover()`: run sources **concurrently**.
- `backend/.../sources/google_maps.py`, `justdial.py`, `indiamart.py`, `sulekha.py` → `fetch_html()`: add retry/backoff + proxy rotation.
- campaign sender template data → **remove hardcoded `"Delhi NCR"`/`"Real Estate"`**.
- add **DND/consent scrubbing** + **WhatsApp channel** as first-class outreach.
