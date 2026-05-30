import json
import logging
import re
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from config import MIN_BEDROOMS, MAX_BEDROOMS, PRICE_BY_BEDROOMS, MAX_PRICE
from scraper import _passes_geo_preflight, _is_furnished, _parse_availability

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.kijiji.ca/b-apartments-condos/city-of-vancouver/c37l1700287"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

MAX_LISTING_AGE_HOURS = 120  # 5 days


def _bedroom_param():
    parts = []
    if MIN_BEDROOMS <= 1 <= MAX_BEDROOMS:
        parts.append("1bedroom")
    if MIN_BEDROOMS <= 2 <= MAX_BEDROOMS:
        parts.append("2bedrooms")
    return ",".join(parts)


def _parse_posted_ts(iso_str):
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def get_listings():
    try:
        resp = requests.get(
            SEARCH_URL,
            headers=HEADERS,
            params={
                "numberbedrooms": _bedroom_param(),
                "price": f"0__{MAX_PRICE}",
                "sort": "dateDesc",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Kijiji fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        logger.error("Kijiji: __NEXT_DATA__ not found")
        return []

    apollo = json.loads(tag.string)["props"]["pageProps"]["__APOLLO_STATE__"]
    raw = {k: v for k, v in apollo.items() if k.startswith("RealEstateListing:")}
    logger.info(f"Kijiji: {len(raw)} raw listings in Apollo state")

    cutoff_ts = datetime.now(timezone.utc).timestamp() - MAX_LISTING_AGE_HOURS * 3600

    listings = []
    for ad in raw.values():
        # Bedrooms — check attributes first, fall back to description text
        bedrooms = None
        for attr in ad.get("attributes", {}).get("all", []):
            if attr.get("canonicalName") == "numberbedrooms":
                try:
                    bedrooms = int(attr["canonicalValues"][0])
                except (ValueError, IndexError, TypeError):
                    pass
        if bedrooms is None:
            m = re.search(r'(\d+)\s*(?:bed(?:room)?|br)\b', ad.get("description", ""), re.IGNORECASE)
            bedrooms = int(m.group(1)) if m else None
        if bedrooms is None or not (MIN_BEDROOMS <= bedrooms <= MAX_BEDROOMS):
            continue

        # Price (stored in cents)
        price_raw = ad.get("price", {}).get("amount")
        price = price_raw // 100 if price_raw else None
        budget = PRICE_BY_BEDROOMS.get(bedrooms, MAX_PRICE)
        if price and price > budget:
            continue

        # Date filter
        posted_ts = _parse_posted_ts(ad.get("activationDate"))
        if posted_ts and posted_ts < cutoff_ts:
            continue

        # Coordinates + geo pre-filter
        loc = ad.get("location", {})
        coords = loc.get("coordinates") or {}
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        title = ad.get("title", "")
        description = ad.get("description", "")

        if not _passes_geo_preflight(lat, lon, title):
            continue

        # Furnished filter
        if _is_furnished(f"{title} {description}"):
            continue

        # Neighbourhood name from Apollo ref
        hood_ref = (loc.get("neighbourhoodInfo") or {}).get("__ref", "")
        neighborhood = apollo.get(hood_ref, {}).get("name", "") if hood_ref else ""

        address = loc.get("address", "") or (f"{lat},{lon}" if lat and lon else "")
        available_from = _parse_availability(f"{title} {description}")

        listings.append({
            "id": f"kj_{ad['id']}",
            "title": title,
            "price": price,
            "neighborhood": neighborhood,
            "link": ad.get("url", ""),
            "bedrooms": bedrooms,
            "address": address,
            "posted_ts": posted_ts,
            "available_from": available_from,
            "furnished": False,
            "reply_email": "",
            "source": "kijiji",
        })

    logger.info(f"Kijiji: {len(listings)} listings after filters")
    return listings


def get_listing_details(url):
    return {}  # All needed data already extracted from search page Apollo state
