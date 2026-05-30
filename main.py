import json
import os
import logging
import requests
from datetime import datetime

from scraper import get_listings, get_listing_details, is_target_neighborhood
from sheets import append_to_sheet, get_seen_ids_from_sheet, update_row_status
from telegram_bot import send_notification, send_error_notification
from gmail_draft import create_draft
from config import SEEN_LISTINGS_FILE, GOOGLE_MAPS_API_KEY, DESTINATION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_seen():
    if os.path.exists(SEEN_LISTINGS_FILE):
        with open(SEEN_LISTINGS_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_LISTINGS_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def get_walking_time(origin):
    if not origin or not GOOGLE_MAPS_API_KEY:
        return "N/A"
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins": origin,
                "destinations": DESTINATION,
                "mode": "walking",
                "key": GOOGLE_MAPS_API_KEY,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "OK":
            element = data["rows"][0]["elements"][0]
            if element.get("status") == "OK":
                return element["duration"]["text"]
        logger.warning(f"Maps API returned status: {data.get('status')}")
    except Exception as e:
        logger.error(f"Maps API error for origin '{origin}': {e}")
    return "N/A"


def main():
    seen = load_seen()
    seen |= get_seen_ids_from_sheet()  # sheet is persistent; survives cache eviction
    logger.info(f"Loaded {len(seen)} previously seen listing IDs (local + sheet)")

    listings = get_listings()
    logger.info(f"Fetched {len(listings)} raw listings from Craigslist")

    new_count = 0
    skipped_seen = 0
    skipped_hood = 0
    skipped_furnished = 0

    for listing in listings:
        lid = listing["id"]

        if lid in seen:
            skipped_seen += 1
            continue

        details = get_listing_details(listing["link"])
        # Merge: detail values override search-page values only when non-empty
        full = {**listing, **{k: v for k, v in details.items() if v}}

        neighborhood = full.get("neighborhood", "")
        title = full.get("title", "")

        if not is_target_neighborhood(neighborhood, title):
            logger.debug(f"Skipping listing outside target neighborhoods: {lid} ({neighborhood})")
            seen.add(lid)
            skipped_hood += 1
            continue

        if full.get("furnished"):
            logger.debug(f"Skipping furnished/short-term listing: {lid}")
            seen.add(lid)
            skipped_furnished += 1
            continue

        full["walking_time"] = get_walking_time(full.get("address", ""))
        full["date_found"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        full.setdefault("price", None)
        full.setdefault("bedrooms", 2)
        full.setdefault("amenities", "")

        row_idx = None
        try:
            row_idx = append_to_sheet(full)
        except Exception as e:
            logger.error(f"Google Sheets error for {lid}: {e}")

        try:
            send_notification(full)
        except Exception as e:
            logger.error(f"Telegram error for {lid}: {e}")

        try:
            drafted = create_draft(full)
            if drafted and row_idx:
                update_row_status(row_idx, "Drafted")
        except Exception as e:
            logger.error(f"Gmail draft error for {lid}: {e}")

        seen.add(lid)
        new_count += 1
        logger.info(
            f"New listing processed — id={lid} | "
            f"${full.get('price')} | {neighborhood} | "
            f"walk={full['walking_time']}"
        )

    save_seen(seen)
    logger.info(
        f"Run complete: {new_count} new | "
        f"{skipped_seen} already seen | "
        f"{skipped_hood} wrong neighborhood | "
        f"{skipped_furnished} furnished/short-term"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Unhandled error in scraper run")
        send_error_notification(str(e))
