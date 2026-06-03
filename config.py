import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_SHEET_ID     = os.getenv("GOOGLE_SHEET_ID")

TARGET_CITY = os.getenv("TARGET_CITY", "vancouver")

TARGET_NEIGHBORHOODS = [
    n.strip().lower()
    for n in os.getenv("TARGET_NEIGHBORHOODS", "downtown,yaletown,coal harbour,west end").split(",")
    if n.strip()
]

MIN_BEDROOMS = int(os.getenv("MIN_BEDROOMS", "1"))
MAX_BEDROOMS = int(os.getenv("MAX_BEDROOMS", "2"))

PRICE_BY_BEDROOMS = {
    1: int(os.getenv("MAX_PRICE_1BR", "3200")),
    2: int(os.getenv("MAX_PRICE_2BR", "3500")),
}
MAX_PRICE = max(PRICE_BY_BEDROOMS.values())

CRAIGSLIST_BASE_URL = f"https://{TARGET_CITY}.craigslist.org"
SEARCH_URL          = f"{CRAIGSLIST_BASE_URL}/search/apa"

DESTINATION        = "Bacchus Restaurant, 845 Hornby St, Vancouver, BC V6Z 2L2"
SEEN_LISTINGS_FILE = "seen_listings.json"
