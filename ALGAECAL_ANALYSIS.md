# ALGAECAL_ANALYSIS.md

## WHAT I BUILT

**Problem:** Manually checking Craigslist and Kijiji for new Vancouver apartments every few hours is slow, repetitive, and causes good listings to be missed. Each new listing also requires writing and sending a similar inquiry email.

**Solution:** A fully automated rental intelligence pipeline that scrapes two listing sources every hour, filters by neighborhood, bedroom count, price ceiling, and furnished status, then fires real-time Telegram alerts, logs to a formatted Google Sheet, auto-drafts Gmail inquiry emails, and renders a live map dashboard — all without any manual intervention.

**Architecture:**
- `scraper.py` hits Craigslist's undocumented `jsonsearch/apa/` JSON endpoint to get all listings with coordinates in one request, then applies a geo-bounding-box pre-filter (lat 49.270–49.300, lon −123.155 to −123.110) to limit expensive detail-page fetches to Downtown/Yaletown/Coal Harbour/West End.
- `kijiji_scraper.py` fetches the Kijiji search page and extracts the `__NEXT_DATA__` embedded Apollo state JSON — parsing all listing fields (price in cents, coordinates, bedroom attributes, activation date) without hitting any listing detail pages.
- `main.py` orchestrates the full pipeline: dedup against `seen_listings.json` + Google Sheet column, call Google Maps Distance Matrix API for walking time to Bacchus Restaurant (845 Hornby St), append to Google Sheets, send Telegram notification, create Gmail draft, update sheet status column. On each run it also calls `sync_sent_status()` to detect which Gmail drafts were already sent (HTTP 404 = gone from drafts = sent) and updates the sheet row to "Sent".
- `sheets.py` uses gspread with OAuth2 credentials to manage a 10-column formatted spreadsheet: date found, price (currency format, color-coded ≤$2,500 green / $2,501–$3,000 yellow / >$3,000 red), address, neighborhood, walking time, bedrooms, available from, link, status (7-state dropdown), draft ID. Sheet also serves as the persistent dedup store so seen-listing memory survives cache eviction between GitHub Actions runs.
- `telegram_bot.py` sends per-listing HTML-formatted messages and a per-run summary (counts of new CL, new Kijiji, skipped seen / wrong area / furnished).
- `gmail_draft.py` constructs personalized inquiry emails using a fixed template (professional couple, non-smokers, no pets, hospitality + marketing), encoding available-from date into the body, then posts to `gmail/v1/users/me/drafts` via REST with a Bearer token from the shared OAuth2 credentials.
- GitHub Actions (`scraper.yml`) runs on `cron: "0 * * * *"` (every hour), restores `seen_listings.json` from Actions cache between runs using `run_id` key + prefix restore.
- `dashboard/` is a static GitHub Pages site: reads the Google Sheet via the public GViz CSV endpoint, renders a Leaflet.js map (OpenStreetMap tiles), geocodes addresses via Nominatim with a 1.1-second rate-limit delay and localStorage cache, shows a Lottie animation during load, and supports mobile (tab bar toggling list/map view, collapsible filter drawer).
- `dashboard/settings.html` talks directly to the GitHub Actions REST API using a browser-stored token to enable/disable the scraper workflow, trigger manual runs, view the last 5 run statuses, and update all repo variables (city, neighborhoods, price ceilings, bedroom range) — no backend required.

**Result/ROI:** Zero manual checking. Every new in-target listing is surfaced within one hour of posting, logged with walking distance to work, and has a ready-to-send draft email — turning a multi-step daily chore into a one-tap "send draft" action.

---

## TOOLS & TECH

**Runtime:** Python 3.11 (GitHub Actions), Python 3.12 (local)

**Scraping:**
- `requests 2.31.0` — HTTP client for all scraping and API calls
- `beautifulsoup4 4.12.3` + `lxml 5.1.0` — HTML parsing for Craigslist detail pages
- Craigslist `jsonsearch/apa/` JSON endpoint — bulk coordinate + price + bedroom data in one request
- Kijiji `__NEXT_DATA__` Apollo GraphQL cache — full listing data extracted from embedded JSON, no XHR needed

**Google APIs (OAuth2, shared credential file `token.json`):**
- Google Sheets API via `gspread 6.0.2` — read/write/format spreadsheet
- `gspread-formatting 1.1.2` — conditional formatting rules, frozen rows, column widths, dropdown validation
- Google Maps Distance Matrix API — walking-time lookup per listing
- Gmail API (REST, not SDK) — draft creation and draft existence check

**Auth:** `google-auth 2.27.0` + `google-auth-oauthlib 1.2.0` — OAuth2 flow + token refresh

**Notifications:** `python-telegram-bot 21.3` — async Bot API (asyncio.run wrapper around async context manager)

**Config:** `python-dotenv 1.0.1` — `.env` file loading; all search parameters overridable via environment variables

**CI/CD:** GitHub Actions — two workflows: `scraper.yml` (hourly cron + manual dispatch, `actions/cache` for state persistence) and `deploy-dashboard.yml` (push-to-Pages on `dashboard/**` changes)

**Frontend:**
- Leaflet.js 1.9.4 (CDN) — interactive map with color-coded circle markers
- OpenStreetMap / Nominatim — tile rendering and free geocoding
- `@lottiefiles/dotlottie-web` (CDN) — Canvas-based Lottie animation for loading state
- Vanilla JS + CSS custom properties — no framework, no bundler
- GitHub Pages — zero-cost static hosting

**Filters applied at scrape time:**
- Age: max 6 hours (Craigslist), max 5 days (Kijiji)
- Bedrooms: `MIN_BEDROOMS=1`, `MAX_BEDROOMS=2`
- Price: per-bedroom ceiling (`MAX_PRICE_1BR=$3,200`, `MAX_PRICE_2BR=$3,500`)
- Geo: bounding box check on lat/lon coordinates before fetching detail pages
- Furnished: keyword set (`furnished`, `furn`, `short term`, `short-term`, `airbnb`), with `unfurnished`/`unfurn` negative check applied first

---

## IDEAS & CONCEPTS

**Dual-layer dedup:** `seen_listings.json` is a local fast-path set persisted via GitHub Actions cache. The Google Sheet (column H, link → ID regex extraction) is the durable fallback used to `|=` merge on every run — so even if the cache is evicted, no listing is processed twice.

**Geo pre-filter before expensive requests:** Craigslist's JSON search returns coordinates. A bounding-box check eliminates out-of-area listings before making individual detail-page HTTP requests (each of which includes a `random.uniform(3, 8)` second sleep to avoid rate-limiting). Only listings that pass the box or lack coordinates (can't rule out) get detail fetches.

**Apollo state extraction:** Kijiji renders a Next.js app; all listing data including price (in cents), coordinates, bedroom count, neighborhood reference, and activation date is embedded in the `<script id="__NEXT_DATA__">` tag as an Apollo cache. Parsing this avoids scraping any individual listing page — `get_listing_details()` returns `{}` for Kijiji because everything is already extracted.

**Draft lifecycle tracking:** Every Gmail draft ID is stored in column J of the sheet. Each run calls `is_draft_sent()`, which does a `GET /gmail/v1/users/me/drafts/{id}` — HTTP 404 means the draft was deleted (sent or discarded). The sheet row is then updated to "Sent". This closes the feedback loop from outbox back into the tracker without any user action.

**Settings page as a bot control panel:** The `settings.html` page uses the GitHub Actions REST API directly from the browser to enable/disable the scraper workflow schedule, trigger manual runs, and update repository variables (city, neighborhoods, price ceilings, bedroom range). The GitHub PAT is stored in `localStorage`. This means the bot can be fully controlled without touching code or opening GitHub.

**7-state rental workflow:** The status column models the full lifecycle of an apartment inquiry: New → Drafted → Sent → Replied → Viewing → Declined → Closed. Each state has a distinct conditional-format color in the sheet, and the dashboard filters by status (New / Drafted / Sent visible in the UI).

**Availability extraction via regex:** A regex (`_AVAIL_RE`) scans both structured attributes and free-text listing bodies for availability phrases (`available from June 1`, `immediately`, `Jul 15th`, etc.) and normalizes them. The extracted date is inserted into the Gmail draft body: "The June 1 move-in date works perfectly for us."

**Cost: effectively $0.** All infrastructure runs on free tiers — GitHub Actions (2,000 free minutes/month; hourly runs use ~2 min each = ~1,440 min/month), GitHub Pages (static hosting), Google Sheets/Gmail (free quota), Telegram Bot API (free), Nominatim geocoding (free, rate-limited to 1 req/sec).

---

## PROOF

**Codebase (8 Python source files):**
- `main.py` — 168 lines, orchestration pipeline
- `scraper.py` — 245 lines, Craigslist JSON + HTML scraping with geo/furnished/age filters
- `kijiji_scraper.py` — 144 lines, Kijiji Apollo state extraction
- `sheets.py` — 235 lines, Google Sheets read/write/format with 10 columns, 7-status conditional formatting
- `telegram_bot.py` — 109 lines, per-listing + run-summary notifications
- `gmail_draft.py` — 88 lines, OAuth2 draft creation + sent detection
- `config.py` — 33 lines, env-driven config with per-bedroom price ceilings
- `cleanup_sheet.py` — utility script (uncommitted, in working tree)

**Dashboard (4 files, deployed to GitHub Pages):**
- `dashboard/index.html` — 101 lines, Leaflet map + sidebar + mobile tab bar + filter drawer
- `dashboard/app.js` — 301 lines, CSV fetch from GViz, custom CSV parser, Nominatim geocoding with localStorage cache, marker management, filter state, Lottie animation
- `dashboard/settings.html` — 351 lines, GitHub API integration for bot control + config editing
- `dashboard/style.css` — CSS custom properties, responsive layout

**GitHub Actions workflows:**
- `scraper.yml` — hourly cron `0 * * * *`, `actions/cache` for `seen_listings.json`, 6 environment secrets + 6 repo variables
- `deploy-dashboard.yml` — push-triggered Pages deployment from `dashboard/` directory

**Google Sheet schema (10 columns):** Date Found | Price ($, currency format) | Address | Neighborhood | Walking Time to Bacchus | Bedrooms | Available From | Link | Status (dropdown: New/Drafted/Sent/Replied/Viewing/Declined/Closed) | Draft ID

**Dependencies pinned in `requirements.txt`:** 9 packages — requests 2.31.0, beautifulsoup4 4.12.3, lxml 5.1.0, gspread 6.0.2, google-auth 2.27.0, google-auth-oauthlib 1.2.0, python-telegram-bot 21.3, python-dotenv 1.0.1, gspread-formatting 1.1.2

**Git history (recent commits):** `c03a087` Add Lottie search animation · `11bf1ff` Add settings page + make config env-driven · `969e63a` Remove unused datetime import · `b403175` Remove unused _age_str function · `67acba8` Add status dropdown with 7 options and color coding
