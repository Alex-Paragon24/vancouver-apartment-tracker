import re
import time
import random
import logging
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from config import (
    CRAIGSLIST_BASE_URL,
    TARGET_NEIGHBORHOODS, MAX_PRICE, MIN_BEDROOMS, MAX_BEDROOMS,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": "https://vancouver.craigslist.org/",
}

# Craigslist's map/JSON search endpoint — returns all listings with coords
JSONSEARCH_URL = f"{CRAIGSLIST_BASE_URL}/jsonsearch/apa/"

MAX_LISTING_AGE_DAYS = 14

# Keywords that indicate a furnished / short-term listing we want to skip.
# Check "unfurnished"/"unfurn" first so we don't false-positive on those.
_FURNISHED_KEYWORDS = frozenset({"furnished", "fully furnished", "furn", "short term", "short-term", "airbnb"})

# Generous bounding box covering Downtown, Yaletown, Coal Harbour, and West End.
# Used to pre-filter before fetching detail pages.
_GEO_LAT_MIN, _GEO_LAT_MAX = 49.270, 49.300
_GEO_LON_MIN, _GEO_LON_MAX = -123.155, -123.110


def _is_furnished(text):
    t = text.lower()
    if "unfurnished" in t or "unfurn" in t:
        return False
    return any(kw in t for kw in _FURNISHED_KEYWORDS)


def _passes_geo_preflight(lat, lon, title):
    """Return True if the listing might be in a target neighborhood.

    Uses lat/lon when available; falls back to keyword scan of the title.
    Only skips when both signals say "no" so we don't miss unlabeled listings.
    """
    title_match = is_target_neighborhood(title=title)
    if title_match:
        return True
    if lat is None or lon is None:
        return True  # no coordinates → can't rule out, fetch detail
    in_box = _GEO_LAT_MIN <= lat <= _GEO_LAT_MAX and _GEO_LON_MIN <= lon <= _GEO_LON_MAX
    return in_box


def get_listings():
    params = {
        "min_bedrooms": MIN_BEDROOMS,
        "max_bedrooms": MAX_BEDROOMS,
        "max_price": MAX_PRICE,
    }

    try:
        resp = requests.get(
            JSONSEARCH_URL,
            headers={**HEADERS, "Accept": "application/json"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch listings: {e}")
        return []

    # Response is [listings_array, cluster_data] — we only need index 0
    items = raw[0] if isinstance(raw, list) and raw else []
    logger.info(f"jsonsearch returned {len(items)} raw items (before price/bedroom/geo filter)")

    cutoff_ts = datetime.now(timezone.utc).timestamp() - MAX_LISTING_AGE_DAYS * 86400

    listings = []
    for item in items:
        price = item.get("price")
        if price and price > MAX_PRICE:
            continue
        bedrooms = item.get("bedrooms", 0)
        if bedrooms < MIN_BEDROOMS or bedrooms > MAX_BEDROOMS:
            continue

        posted = item.get("PostedDate", 0)
        if posted and posted < cutoff_ts:
            continue

        lat = item.get("Latitude")
        lon = item.get("Longitude")
        title = item.get("PostingTitle", "")

        if not _passes_geo_preflight(lat, lon, title):
            continue

        if _is_furnished(title):
            continue

        listings.append({
            "id": str(item["PostingID"]),
            "title": item.get("PostingTitle", ""),
            "price": price,
            "neighborhood": "",  # filled in get_listing_details
            "link": item.get("PostingURL", ""),
            "bedrooms": bedrooms,
            # lat,lon string used directly by Maps API
            "address": f"{lat},{lon}" if lat and lon else "",
        })

    return listings


def get_listing_details(url):
    time.sleep(random.uniform(3, 8))

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch listing {url}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")

    title_el = soup.select_one("#titletextonly")
    title = title_el.get_text(strip=True) if title_el else ""

    price_el = soup.select_one(".price")
    price = _parse_price(price_el.get_text(strip=True) if price_el else "")

    hood_el = soup.select_one("span.postingtitletext small")
    neighborhood = hood_el.get_text(strip=True).strip("() ") if hood_el else ""

    # Prefer street address over coordinates
    address = ""
    mapaddr_el = soup.select_one(".mapaddress")
    if mapaddr_el:
        address = mapaddr_el.get_text(strip=True)
    else:
        map_el = soup.select_one("#map")
        if map_el:
            lat = map_el.get("data-latitude", "")
            lon = map_el.get("data-longitude", "")
            if lat and lon:
                address = f"{lat},{lon}"

    desc_el = soup.select_one("#postingbody")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    bedrooms = MIN_BEDROOMS
    amenities = []
    for group in soup.select(".attrgroup"):
        for span in group.select("span"):
            text = span.get_text(strip=True)
            br_match = re.match(r"^(\d+)BR", text, re.IGNORECASE)
            if br_match:
                bedrooms = int(br_match.group(1))
            elif text and "/" not in text:
                amenities.append(text)

    return {
        "title": title,
        "price": price,
        "address": address,
        "neighborhood": neighborhood,
        "bedrooms": bedrooms,
        "amenities": ", ".join(amenities[:8]),
        "furnished": _is_furnished(f"{title} {description}"),
    }


def is_target_neighborhood(neighborhood="", title="", description=""):
    combined = f"{neighborhood} {title} {description}".lower()
    return any(hood in combined for hood in TARGET_NEIGHBORHOODS)


def _parse_price(text):
    if not text:
        return None
    m = re.search(r"\$?([\d,]+)", text.replace(",", ""))
    return int(m.group(1)) if m else None
