import os
import re
import logging
import gspread
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from config import GOOGLE_SHEET_ID

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.compose",
]

SHEET_HEADERS = [
    "Date Found",
    "Price",
    "Address",
    "Neighborhood",
    "Walking Time to Bacchus",
    "Posted",
    "Bedrooms",
    "Amenities",
    "Link",
    "Status",
]


def _age_str(posted_ts):
    if not posted_ts:
        return ""
    delta = datetime.now(timezone.utc).timestamp() - posted_ts
    hours = int(delta // 3600)
    if hours < 1:
        return "< 1 ч."
    if hours < 24:
        return f"{hours} ч. назад"
    return f"{hours // 24} дн. назад"


def get_creds():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return creds


def _get_client():
    return gspread.authorize(get_creds())


def _ensure_headers(worksheet):
    first_row = worksheet.row_values(1)
    if not first_row:
        worksheet.append_row(SHEET_HEADERS, value_input_option="RAW")
        logger.info("Wrote sheet headers")


def get_seen_ids_from_sheet():
    """Read posting IDs already in the sheet — used as persistent dedup store."""
    try:
        gc = _get_client()
        sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        links = sheet.sheet1.col_values(9)[1:]  # col 9 = Link (after adding Posted col), skip header
        ids = set()
        for link in links:
            m = re.search(r'/(\d+)\.html', link)
            if m:
                ids.add(m.group(1))
        logger.info(f"Loaded {len(ids)} seen IDs from Google Sheet")
        return ids
    except Exception as e:
        logger.warning(f"Could not load seen IDs from sheet: {e}")
        return set()


def append_to_sheet(listing):
    gc = _get_client()
    sheet = gc.open_by_key(GOOGLE_SHEET_ID)
    worksheet = sheet.sheet1

    _ensure_headers(worksheet)

    price = listing.get("price")
    price_str = f"${price}" if price else "N/A"

    row = [
        listing.get("date_found", ""),
        price_str,
        listing.get("address", ""),
        listing.get("neighborhood", ""),
        listing.get("walking_time", "N/A"),
        _age_str(listing.get("posted_ts")),
        listing.get("bedrooms", 2),
        listing.get("amenities", ""),
        listing.get("link", ""),
        "New",
    ]

    worksheet.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Appended to sheet: {listing.get('link', '')[:60]}")
