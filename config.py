import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

CRAIGSLIST_BASE_URL = "https://vancouver.craigslist.org"
SEARCH_URL = f"{CRAIGSLIST_BASE_URL}/search/apa"

TARGET_NEIGHBORHOODS = ["downtown", "yaletown", "coal harbour", "west end"]
MAX_PRICE = 3500
MIN_BEDROOMS = 2
MAX_BEDROOMS = 2

DESTINATION = "Bacchus Restaurant, 845 Hornby St, Vancouver, BC V6Z 2L2"
SEEN_LISTINGS_FILE = "seen_listings.json"
