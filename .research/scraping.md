# Google Maps Scraping — 2025/2026 Implementation-Ready Report

> Research date: 2026-10-09. All endpoint behaviors, prices, and array indices below were **verified live** against Google (`/search?tbm=map`, `/maps/preview/place`, `/maps/rpc/listugcposts`), the Google pricing page, and the current `gosom/google-maps-scraper` `main` source. Where something could not be confirmed live, it is flagged.

---

## 0. TL;DR — What your scraper should be

Your current `scrape_google_maps_playwright()` is the **slowest, most fragile, most detectable** of the viable paths, and it caps you at ~20 leads/query because the DOM feed only renders 20 cards before you must scroll (and your scroll loop is unreliable). Three findings drive the whole report:

1. **There is a pure-HTTP endpoint that returns all data (name, phone, website, rating, review count, lat/lng, place_id, address) in ONE ~160 KB JSON blob — no browser, no DOM, no scroll.** It is `https://www.google.com/search?tbm=map&...&pb=<protobuf>`. Verified: returns 20 results/request with full contact data, ~0.4 s per call, paginates via a token. This should become your **primary** path. Playwright becomes the fallback for the ~1% of cases needing JS-rendered detail.
2. **`!3e2` appended to the pb string gives you page 2, page 3, … (verified: still 20 results).** You can get 100–200 leads per query over HTTP in ~2 s total, vs. your current brittle scroll loop.
3. **Reviews (`/maps/rpc/listugcposts`) returns HTTP 403 over plain curl** — it requires the browser session cookies/NID. Verified. So "get full reviews" is the *only* thing that genuinely needs Playwright; everything for lead-gen does not.

Architecture target: **HTTP pb= for discovery + contact data (fast, cheap, parallel) → Playwright only for deep reviews/email on shortlisted leads.**
